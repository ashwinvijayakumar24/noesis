"""Tokenising document text that literally contains special-token strings.

tiktoken's ``encode()`` defaults to ``disallowed_special="all"`` and RAISES
ValueError on any text containing "<|endoftext|>", "<|im_start|>", etc. Both
chunking call sites (rag_ingest.chunk_text, rag_chunking.chunk_section_content)
used that default, so ingestion crashed outright on a real published paper --
greshake et al. 2023, "Not what you've signed up for", which quotes those
strings because it is *about* prompt injection. Any AI-research manuscript
discussing tokenisation hits the same wall.

The fix (rag_chunking._DISALLOWED_SPECIAL / count_and_encode) makes the literal
string encode as ordinary text: it round-trips, and it is NOT promoted to a
control token id.
"""

from pathlib import Path

import pytest
import tiktoken

from app.services.rag_chunking import chunk_section_content, count_and_encode
from app.services.rag_ingest import chunk_text

# Strings that appear in real papers about tokenisation / prompt injection.
SPECIAL_STRINGS = ["<|endoftext|>", "<|im_start|>", "<|im_end|>", "<|fim_prefix|>"]

# The subset that is actually in cl100k_base's special vocabulary, i.e. the ones
# the old code raised on. <|im_start|>/<|im_end|> belong to the o200k/ChatML
# vocabularies and are ordinary text under cl100k_base -- they are still covered
# by the tolerance tests above, because the encoding in use is a config detail
# that must not decide whether ingestion succeeds.
RAISING_SPECIALS = ["<|endoftext|>", "<|fim_prefix|>", "<|endofprompt|>"]


@pytest.fixture
def enc():
    return tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Regression: this is exactly what used to blow up
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("special", RAISING_SPECIALS)
def test_bare_encode_still_raises_documenting_the_bug(enc, special):
    """The old behaviour, pinned. If this ever stops raising, tiktoken changed
    its default and the comment in rag_chunking needs revisiting -- but the
    production bug this suite covers was precisely this exception escaping."""
    with pytest.raises(ValueError):
        enc.encode(f"The token {special} terminates a sequence.")


@pytest.mark.parametrize("special", SPECIAL_STRINGS)
def test_count_and_encode_does_not_raise(enc, special):
    tokens = count_and_encode(enc, f"The token {special} terminates a sequence.")
    assert len(tokens) > 0


REPO_ROOT = Path(__file__).resolve().parents[3]
OFFENDING_PDF = (
    REPO_ROOT
    / "scripts/eval/corpora/9ceadCJY4B"
    / "greshake_2023_not_what_youve_signed_up_for_compromising_real_world_llm_integrate.pdf"
)


@pytest.mark.skipif(not OFFENDING_PDF.exists(), reason="eval corpus PDF not present")
def test_real_corpus_pdf_that_crashed_ingestion(enc):
    """The actual document that broke ingestion, end to end."""
    import fitz

    with fitz.open(OFFENDING_PDF) as doc:
        text = "".join(page.get_text() for page in doc)

    assert "<|endoftext|>" in text  # if this stops holding, the fixture changed
    with pytest.raises(ValueError):
        enc.encode(text)  # old behaviour
    assert len(count_and_encode(enc, text)) > 0  # new behaviour
    assert chunk_text(text, max_tokens=500, overlap_tokens=100)


# ---------------------------------------------------------------------------
# Both call sites
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("special", SPECIAL_STRINGS)
def test_chunk_text_handles_special_token_strings(special):
    """rag_ingest.chunk_text -- the fallback/plain-text ingestion path."""
    text = f"Prior work injects {special} into the prompt. " * 40
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
    assert chunks
    assert any(special in chunk for chunk in chunks)


@pytest.mark.parametrize("special", SPECIAL_STRINGS)
def test_chunk_section_content_handles_special_token_strings(special):
    """rag_chunking.chunk_section_content -- the section-aware ingestion path."""
    content = f"Prior work injects {special} into the prompt. " * 60
    chunks = chunk_section_content(
        content=content,
        max_chunk_size=80,
        overlap=20,
        section_title="Threat Model",
        section_type="methods",
    )
    assert chunks
    assert all(chunk["tokens"] > 0 for chunk in chunks)
    assert any(special in chunk["content"] for chunk in chunks)


def test_short_section_below_max_also_encodes(enc):
    """The early-return branch of chunk_section_content encodes too."""
    content = "We treat <|endoftext|> as literal text."
    chunks = chunk_section_content(
        content=content,
        max_chunk_size=500,
        overlap=50,
        section_title="Intro",
        section_type="intro",
    )
    assert len(chunks) == 1
    assert chunks[0]["content"] == content
    assert chunks[0]["tokens"] == len(count_and_encode(enc, content))


# ---------------------------------------------------------------------------
# Realistic academic chunk: round-trip + sane count
# ---------------------------------------------------------------------------

ACADEMIC_CHUNK = (
    "3.2 Delimiter Attacks. A common defence is to fence untrusted input between "
    "delimiters. This fails when the attacker can emit the model's own control "
    "strings: appending <|endoftext|> or a forged <|im_start|>system turn to a "
    "retrieved web page lets the injected instructions escape the fence. We "
    "evaluate both variants against GPT-4 and observe a 76% success rate, and we "
    "note that <|fim_prefix|> behaves identically under the cl100k_base "
    "vocabulary."
)


def test_academic_chunk_round_trips(enc):
    tokens = count_and_encode(enc, ACADEMIC_CHUNK)
    assert enc.decode(tokens) == ACADEMIC_CHUNK


def test_academic_chunk_token_count_is_sane(enc):
    tokens = count_and_encode(enc, ACADEMIC_CHUNK)
    words = len(ACADEMIC_CHUNK.split())
    # English prose runs roughly 1.2-2.5 tokens/word; the special strings are
    # spelled out as several tokens each rather than collapsing to one id.
    assert words < len(tokens) < words * 4


def test_special_strings_are_not_encoded_as_control_token_ids(enc):
    """The security-relevant half of the choice: disallowed_special=() rather
    than allowed_special={...}. Document text must never become a real control
    token, or a crafted PDF could inject one into anything reusing the ids."""
    tokens = count_and_encode(enc, "literal <|endoftext|> here")
    # cl100k_base's <|endoftext|> id is 100257; it must not appear.
    assert 100257 not in tokens
    assert len(count_and_encode(enc, "<|endoftext|>")) > 1


# ---------------------------------------------------------------------------
# No regression on the common path
# ---------------------------------------------------------------------------

NORMAL_TEXTS = [
    "",
    "The quick brown fox jumps over the lazy dog.",
    "Fig. 3 shows a 12.5% improvement (p < 0.01) over the baseline of Smith et al.",
    "Unicode: naïve café — “quoted” … 日本語 ✓",
    "Tabs\tand\nnewlines\r\nand   runs of   spaces.",
    "def f(x):\n    return x ** 2  # comment",
]


@pytest.mark.parametrize("text", NORMAL_TEXTS)
def test_normal_text_count_identical_to_old_behaviour(enc, text):
    """Text with no special strings must tokenise exactly as before the change."""
    assert count_and_encode(enc, text) == enc.encode(text)


def test_normal_text_chunking_unchanged(enc):
    text = "Retrieval augmented generation improves factuality. " * 200
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
    assert chunks
    # Every chunk is decoded from tokens produced by the old, unchanged path.
    assert "".join(chunks) != ""
    assert len(count_and_encode(enc, text)) == len(enc.encode(text))
