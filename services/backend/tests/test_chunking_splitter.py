"""Sentence segmentation for chunking (app/services/rag_chunking.py).

The old splitter was `content.replace('. ', '.|').split('|')`, which shatters on
every academic abbreviation. These tests pin the pysbd behaviour, and pin the
legacy behaviour too -- the legacy arm is deliberately retained so the retrieval
cost of the naive split can be measured, and it must keep splitting wrongly.
"""

import threading

import pytest

from app.services import rag_chunking
from app.services.rag_chunking import chunk_section_content, split_sentences


@pytest.fixture(autouse=True)
def default_splitter(monkeypatch):
    monkeypatch.delenv("CHUNKING_SPLITTER", raising=False)
    yield


@pytest.fixture
def legacy(monkeypatch):
    monkeypatch.setenv("CHUNKING_SPLITTER", "legacy")


# (text, fragment). Every case must survive pysbd intact.
ABBREVIATION_CASES = [
    ("Smith et al. found a strong effect.", "et al."),
    ("The layout appears in Fig. 3 of the appendix.", "Fig. 3"),
    ("The derivation is on p. 12 of the supplement.", "p. 12"),
    ("The difference was significant at p < 0.05 overall.", "p < 0.05"),
    ("Some models, e.g. transformers, scale well.", "e.g."),
    ("The metric, i.e. recall at ten, was reported.", "i.e."),
    ("Dr. Smith supervised the annotation effort.", "Dr. Smith"),
    ("Participants were recruited in the U.S. during 2024.", "U.S."),
]

# Legacy only breaks on "<punct><space>", so a fragment must be followed by a
# space to trip it. `p < 0.05.` at end-of-string does not, hence the trailing
# clause -- which is exactly how these appear in real prose anyway.
LEGACY_SHATTER_CASES = [
    case for case in ABBREVIATION_CASES if case[1] != "p < 0.05"
] + [
    ("The difference was significant at p < 0.05. We report it.", "p < 0.05."),
]


class TestPysbdKeepsAbbreviationsIntact:
    @pytest.mark.parametrize("text,fragment", ABBREVIATION_CASES)
    def test_not_split_mid_abbreviation(self, text, fragment):
        segments = split_sentences(text)
        assert segments == [text], f"{fragment!r} was split: {segments}"

    def test_multiple_abbreviations_in_one_sentence(self):
        text = "Smith et al. report p < 0.05 in Fig. 3 on p. 12."
        assert split_sentences(text) == [text]

    def test_real_sentence_boundaries_are_still_found(self):
        text = "Smith et al. found p < 0.05. See Fig. 3 on p. 12. Next sentence here."
        assert split_sentences(text) == [
            "Smith et al. found p < 0.05.",
            "See Fig. 3 on p. 12.",
            "Next sentence here.",
        ]


class TestLegacyPathStillHasTheBug:
    """Documents exactly what the flag preserves. If these ever pass 'correctly'
    the legacy experiment arm has stopped being the control it exists to be."""

    @pytest.mark.parametrize("text,fragment", LEGACY_SHATTER_CASES)
    def test_legacy_splits_mid_abbreviation(self, legacy, text, fragment):
        segments = split_sentences(text)
        assert len(segments) > 1, f"expected legacy to shatter {fragment!r}"

    def test_legacy_shatters_the_showcase_paragraph(self, legacy):
        text = "Smith et al. found p < 0.05. See Fig. 3 on p. 12. Next sentence here."
        segments = split_sentences(text)
        # pysbd gives 3; the naive splitter gives many more, all fragments.
        assert len(segments) > 3
        assert "Smith et al." in segments


class TestFlagSelection:
    def test_default_is_pysbd(self):
        text = "Smith et al. found an effect."
        assert split_sentences(text) == [text]

    def test_explicit_pysbd(self, monkeypatch):
        monkeypatch.setenv("CHUNKING_SPLITTER", "pysbd")
        text = "Smith et al. found an effect."
        assert split_sentences(text) == [text]

    def test_legacy_selects_old_path(self, legacy):
        assert len(split_sentences("Smith et al. found an effect.")) > 1

    def test_flag_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("CHUNKING_SPLITTER", "LEGACY")
        assert len(split_sentences("Smith et al. found an effect.")) > 1

    def test_unknown_value_falls_back_to_pysbd(self, monkeypatch):
        monkeypatch.setenv("CHUNKING_SPLITTER", "banana")
        text = "Smith et al. found an effect."
        assert split_sentences(text) == [text]

    def test_flag_is_read_per_call_not_at_import(self, monkeypatch):
        text = "Smith et al. found an effect."
        assert split_sentences(text) == [text]
        monkeypatch.setenv("CHUNKING_SPLITTER", "legacy")
        assert len(split_sentences(text)) > 1


class TestEdgeCases:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n"])
    def test_empty_input_returns_empty_list(self, text):
        assert split_sentences(text) == []

    def test_empty_input_legacy(self, legacy):
        assert split_sentences("") == []

    def test_single_sentence_without_terminator(self):
        text = "A sentence with no terminating punctuation"
        assert split_sentences(text) == [text]

    def test_newlines_are_handled(self):
        text = "First sentence here.\nSecond sentence here.\n\nThird sentence here."
        assert split_sentences(text) == [
            "First sentence here.",
            "Second sentence here.",
            "Third sentence here.",
        ]

    def test_segments_are_stripped_and_non_empty(self):
        segments = split_sentences("  One.   Two.   ")
        assert segments == ["One.", "Two."]
        assert all(s == s.strip() and s for s in segments)


class TestAcademicParagraph:
    PARAGRAPH = (
        "Prior work by Smith et al. established the baseline for this task. "
        "We replicate their setup, i.e. the same 5-fold split, on a larger corpus. "
        "Accuracy improved by 3.2 points (p < 0.05). "
        "The full ablation is shown in Fig. 3 on p. 12 of the appendix. "
        "Dr. Chen independently verified the annotations in the U.S. cohort. "
        "We release code and data."
    )

    def test_exact_segment_count(self):
        segments = split_sentences(self.PARAGRAPH)
        assert len(segments) == 6, segments

    def test_each_segment_is_a_real_sentence(self):
        segments = split_sentences(self.PARAGRAPH)
        assert segments[0].startswith("Prior work by Smith et al.")
        assert segments[3] == "The full ablation is shown in Fig. 3 on p. 12 of the appendix."
        assert segments[-1] == "We release code and data."

    def test_legacy_produces_strictly_more_fragments(self, legacy):
        assert len(split_sentences(self.PARAGRAPH)) > 6


class TestCallerBehaviourPreserved:
    """chunk_section_content joins segments with ' ' and tracks token overlap;
    the splitter swap must not disturb that contract."""

    def test_small_section_returns_single_chunk_untouched(self):
        content = "Smith et al. found p < 0.05. See Fig. 3."
        chunks = chunk_section_content(content, 1000, 50, "Results", "results")
        assert len(chunks) == 1
        assert chunks[0]["content"] == content

    def test_large_section_splits_into_multiple_chunks(self):
        content = " ".join(
            f"Sentence number {i} describes the experimental protocol in detail."
            for i in range(120)
        )
        chunks = chunk_section_content(content, 120, 20, "Methods", "methods")
        assert len(chunks) > 1
        assert all(c["section_title"] == "Methods" for c in chunks)
        assert all(c["section_type"] == "methods" for c in chunks)
        assert [c["chunk_index_in_section"] for c in chunks] == list(range(len(chunks)))
        assert all(c["tokens"] > 0 for c in chunks)
        assert all(c["content"] == c["content"].strip() for c in chunks)

    def test_no_chunk_ends_mid_citation(self):
        content = " ".join(
            f"Result {i} was reported by Smith et al. at p < 0.05 in Fig. {i}."
            for i in range(60)
        )
        chunks = chunk_section_content(content, 120, 20, "Results", "results")
        assert len(chunks) > 1
        for chunk in chunks:
            assert not chunk["content"].endswith("et al.")
            assert not chunk["content"].endswith("p <")


class TestThreadSafety:
    """pysbd.Segmenter stores the input on `self` during segment(), so a shared
    instance would let concurrent documents splice into each other. The module
    keeps one Segmenter per thread; this proves it holds under contention."""

    def test_concurrent_segmentation_is_uncorrupted(self):
        texts = [
            f"Doc {i} by Smith et al. reports p < 0.05. Doc {i} continues in Fig. 3."
            for i in range(20)
        ]
        expected = {
            text: [f"Doc {i} by Smith et al. reports p < 0.05.", f"Doc {i} continues in Fig. 3."]
            for i, text in enumerate(texts)
        }

        results: dict[str, list] = {}
        errors: list[BaseException] = []
        barrier = threading.Barrier(len(texts))

        def worker(text: str) -> None:
            try:
                barrier.wait()
                for _ in range(25):
                    results[text] = split_sentences(text)
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in texts]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        for text, segments in results.items():
            assert segments == expected[text]

    def test_each_thread_gets_its_own_segmenter(self):
        # Hold real references: ids get recycled once a dead thread's local is
        # collected, which would make an id-based assertion pass by accident.
        seen: list = []
        lock = threading.Lock()
        barrier = threading.Barrier(4)

        def worker() -> None:
            barrier.wait()
            segmenter = rag_chunking._get_segmenter()
            with lock:
                seen.append(segmenter)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(seen) == 4
        assert len({id(s) for s in seen}) == 4

    def test_same_thread_reuses_one_segmenter(self):
        assert rag_chunking._get_segmenter() is rag_chunking._get_segmenter()
