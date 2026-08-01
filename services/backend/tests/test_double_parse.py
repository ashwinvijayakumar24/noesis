"""The PDF is parsed twice per upload. These tests pin down the fix.

THE FINDING (measured -- scripts/eval/E2E_LATENCY.md, n=7 real runs)
    ``POST /drafts/upload`` calls ``validate_file_format``, which calls
    ``extract_text(file_bytes, 'pdf')`` -- the full GROBID/Docling document
    pipeline. ``ingest_draft`` then re-downloads the same file from Storage and
    calls the identical ``extract_text`` again. In all 7 measured runs the two
    calls returned identical output (same chars, sections, references). The
    first result is used for exactly one thing::

        if len(sample_text.strip()) < 50:

    and is then discarded. Parsing is 39.2% of the mean user-visible path;
    parse #1 alone is 52.38 s p50 of a 212.82 s p50 total.

THE FIX AND ITS FLAG
    ``DRAFT_VALIDATION_CHEAP_PARSE`` (default OFF -- the measured behaviour).
    When on, and only for PDFs, ``validate_file_format`` answers its one
    question with ``probe_pdf_text``: a local PyMuPDF read that stops as soon as
    it has seen 50 characters. DOCX and TXT are untouched -- their extraction is
    already local and was never the cost.

WHAT "EQUIVALENT" MEANS HERE, AND WHAT THESE TESTS CAN AND CANNOT PROVE
    ``ingest_draft`` is not modified by either arm, so the parse whose output
    reaches structure, anchors and the graph is the *same call in both arms*.
    ``test_ingest_parse_is_untouched_by_the_flag`` proves that directly: it runs
    the ingest-side parse under both flag values against the same bytes and
    asserts identical full_text (by SHA-256), identical section titles in order,
    identical reference count and identical anchor map. That is the equivalence
    definition used in scripts/eval/E2E_DOUBLEPARSE.md.

    What they cannot prove is that the cheap gate rejects everything the full
    gate rejected -- that needs real PDFs through a real GROBID, and it was run
    separately over 18 real manuscripts plus 6 adversarial synthetics. The
    result is recorded in E2E_DOUBLEPARSE.md. What is pinned here is the one
    divergence that analysis of the code predicts
    (``test_known_divergence_grobid_empty_but_pymupdf_has_text``), so that if
    someone later makes the cheap gate silently stricter or looser, a test
    breaks rather than a user.
"""

import asyncio
import hashlib
import os
from pathlib import Path

import fitz
import pytest

from app.services import draft_processing as dp
from app.services.draft_errors import FileEmptyError, PDFExtractionError

FLAG = dp.DRAFT_VALIDATION_CHEAP_PARSE_ENV
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "scripts" / "eval" / "openreview" / "ICLR.cc_2024_Conference" / "10eQ4Cfh8p.pdf"
)


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


def _pdf(text: str | None, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    out = doc.tobytes()
    doc.close()
    return out


class _RecordingExtract:
    """Stands in for ``extract_text`` and counts how often it was called."""

    def __init__(self, payload=None, raises=None):
        self.calls = []
        self.payload = payload or {
            "full_text": "x" * 4000, "title": "", "sections": [],
            "references": [], "metadata": {},
        }
        self.raises = raises

    async def __call__(self, file_bytes, file_type):
        self.calls.append(file_type)
        if self.raises:
            raise self.raises
        return self.payload


# ---------------------------------------------------------------------------
# The flag itself
# ---------------------------------------------------------------------------

def test_flag_defaults_to_the_measured_behaviour():
    """Absent the env var, nothing changes. This is the arm E2E_LATENCY measured."""
    assert dp.cheap_validation_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
def test_flag_accepts_the_repo_s_truthy_spellings(monkeypatch, value):
    monkeypatch.setenv(FLAG, value)
    assert dp.cheap_validation_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_flag_rejects_everything_else(monkeypatch, value):
    monkeypatch.setenv(FLAG, value)
    assert dp.cheap_validation_enabled() is False


# ---------------------------------------------------------------------------
# What each arm actually calls -- the whole point of the change
# ---------------------------------------------------------------------------

def test_default_arm_still_parses_the_pdf_in_validation(monkeypatch):
    rec = _RecordingExtract()
    monkeypatch.setattr(dp, "extract_text", rec)
    result = asyncio.run(dp.validate_file_format(_pdf("A" * 300), "pdf"))
    assert result["valid"] is True
    assert rec.calls == ["pdf"], "default arm must be the behaviour that was measured"


def test_cheap_arm_does_not_call_extract_text_for_a_pdf(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    rec = _RecordingExtract()
    monkeypatch.setattr(dp, "extract_text", rec)
    result = asyncio.run(dp.validate_file_format(_pdf("A" * 300), "pdf"))
    assert result["valid"] is True
    assert result["can_extract_text"] is True
    assert rec.calls == [], "the cheap arm exists precisely to skip this parse"


@pytest.mark.parametrize("file_type", ["docx", "txt"])
def test_cheap_arm_leaves_docx_and_txt_on_the_full_path(monkeypatch, file_type):
    """Only PDF parsing was expensive. Changing the others would be scope creep."""
    monkeypatch.setenv(FLAG, "1")
    rec = _RecordingExtract()
    monkeypatch.setattr(dp, "extract_text", rec)
    payload = b"hello world " * 100 if file_type == "txt" else b"PK\x03\x04" + b"\x00" * 4000
    asyncio.run(dp.validate_file_format(payload, file_type))
    assert rec.calls == [file_type]


# ---------------------------------------------------------------------------
# The cheap probe's own behaviour
# ---------------------------------------------------------------------------

def test_probe_returns_text_from_a_readable_pdf():
    assert "HELLO" in dp.probe_pdf_text(_pdf("HELLO" * 40))


def test_probe_stops_early_instead_of_reading_the_whole_document():
    """50 chars is the whole question; page 3 of 40 cannot change the answer."""
    doc = fitz.open()
    for i in range(40):
        page = doc.new_page()
        page.insert_text((72, 72), "B" * 80)
    data = doc.tobytes()
    doc.close()
    text = dp.probe_pdf_text(data)
    assert len(text.strip()) >= dp.MIN_EXTRACTABLE_CHARS
    assert len(text) < 40 * 80, "the probe read the entire document"


def test_probe_returns_empty_for_a_blank_pdf_so_the_caller_rejects_it():
    assert dp.probe_pdf_text(_pdf(None, pages=3)).strip() == ""


def test_probe_raises_the_same_error_the_full_parse_raises_for_unopenable_bytes():
    with pytest.raises(PDFExtractionError):
        dp.probe_pdf_text(b"this is not a pdf at all" * 40)


@pytest.mark.parametrize("body,valid", [("A" * 300, True), (None, False), ("Hi.", False)])
def test_cheap_gate_agrees_with_the_50_char_floor(monkeypatch, body, valid):
    monkeypatch.setenv(FLAG, "1")
    result = asyncio.run(dp.validate_file_format(_pdf(body), "pdf"))
    assert result["valid"] is valid
    if not valid:
        assert result["can_extract_text"] is False


def test_cheap_gate_rejects_bytes_that_are_not_a_pdf(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    result = asyncio.run(dp.validate_file_format(b"%PDF-1.7\n" + b"\x00" * 3000, "pdf"))
    assert result["valid"] is False


# ---------------------------------------------------------------------------
# The one divergence the code predicts, pinned deliberately
# ---------------------------------------------------------------------------

def test_known_divergence_grobid_empty_but_pymupdf_has_text(monkeypatch):
    """The cheap gate is not the same gate. This is exactly where they differ.

    ``extract_text_from_pdf`` raises FileEmptyError when GROBID *succeeds* and
    returns empty text -- it does NOT fall back to PyMuPDF in that branch. So a
    PDF whose text PyMuPDF can read but GROBID renders empty is rejected at
    upload by the full gate and accepted at upload by the cheap one. It is not
    then analysed regardless: ``ingest_draft`` calls the same ``extract_text``
    and raises the same FileEmptyError, so the draft fails there instead. The
    difference is a 400 at upload versus a failed draft, not bad analysis.
    """
    data = _pdf("A" * 300)

    monkeypatch.setattr(dp, "extract_text", _RecordingExtract(raises=FileEmptyError("pdf")))
    full = asyncio.run(dp.validate_file_format(data, "pdf"))
    assert full["valid"] is False

    monkeypatch.setenv(FLAG, "1")
    cheap = asyncio.run(dp.validate_file_format(data, "pdf"))
    assert cheap["valid"] is True


# ---------------------------------------------------------------------------
# Equivalence: the parse that ingest consumes is identical in both arms
# ---------------------------------------------------------------------------

class _StubGrobid:
    """A GROBID that returns the shape the n=7 measurement actually saw:
    13 body sections and 33 references, deterministically."""

    async def process_pdf(self, _b):
        sections = [
            {"title": t, "type": "body", "content": f"{t} content. " * 30}
            for t in ("Introduction", "Related Work", "Method", "Setup",
                      "Results", "Ablations", "Analysis", "Limitations",
                      "Broader Impact", "Conclusion", "Reproducibility",
                      "Acknowledgements", "Appendix A")
        ]
        return {
            "full_text": "\n\n".join(f"{s['title']}\n{s['content']}" for s in sections),
            "title": "A Stubbed Manuscript",
            "abstract": "An abstract long enough to matter. " * 5,
            "sections": sections,
            "references": [{"title": f"Ref {i}", "authors": []} for i in range(33)],
            "metadata": {"page_count": 12},
        }


class _DeadGrobid:
    """A GROBID outage -- the path that falls through to PyMuPDF."""

    async def process_pdf(self, _b):
        raise RuntimeError("grobid unavailable")


@pytest.mark.skipif(not FIXTURE.exists(), reason="eval fixture PDF not present")
@pytest.mark.parametrize("grobid", [_StubGrobid, _DeadGrobid],
                         ids=["grobid_ok", "grobid_down"])
def test_ingest_parse_is_untouched_by_the_flag(monkeypatch, grobid):
    """"Equivalent" = same full_text SHA-256, same section titles in order, same
    reference count, same anchor map. Run against the same real manuscript the
    n=7 latency measurement used, under both parser regimes that measurement
    observed (GROBID up, 5 of 7 runs; GROBID down, 2 of 7), with GROBID itself
    deterministic so the assertion is about the flag and not about GROBID's
    day-to-day variance.
    """
    from app.services.draft_parse_artifacts import (
        build_anchor_map, build_structure_from_extracted_data,
    )

    data = FIXTURE.read_bytes()

    def fingerprint() -> tuple:
        extracted = asyncio.run(dp.extract_text(data, "pdf"))
        structure = build_structure_from_extracted_data(extracted)
        anchors = build_anchor_map(structure)
        return (
            hashlib.sha256(extracted["full_text"].encode()).hexdigest(),
            tuple(s.get("title") for s in extracted.get("sections") or []),
            len(extracted.get("references") or []),
            tuple(a.get("anchor_id") for a in anchors),
        )

    monkeypatch.setattr(dp, "get_grobid_client", lambda: grobid())

    monkeypatch.delenv(FLAG, raising=False)
    baseline = fingerprint()

    monkeypatch.setenv(FLAG, "1")
    cheap = fingerprint()

    assert baseline == cheap
    text_sha, titles, n_refs, anchors = baseline
    assert text_sha != hashlib.sha256(b"").hexdigest()
    if grobid is _StubGrobid:
        # the comparison is only load-bearing when there is structure to compare
        assert len(titles) == 13 and n_refs == 33 and len(anchors) > 0
