"""NUL-byte sanitisation for text bound for PostgreSQL.

11 of the 38 PDFs in the eval corpus carry NUL characters in their extracted
text (95 in total, worst case 55 in one file). PostgreSQL cannot store U+0000
in a `text` or `jsonb` value, so those documents fail ingestion outright.
These tests pin the sanitiser's behaviour: what it removes, what it must leave
alone, and the fact that it reports what it did.
"""

import logging

import pytest

from app.services.rag_ingest import (
    sanitize_chunks_for_postgres,
    sanitize_for_postgres_text,
    sanitize_json_for_postgres,
)


# ---------------------------------------------------------------- removal ---

def test_nul_is_removed_and_counted():
    cleaned, removed = sanitize_for_postgres_text("a\x00b\x00c")
    assert "\x00" not in cleaned
    assert removed == 2


def test_nul_between_words_is_stripped_not_replaced_with_space():
    """Documented choice: strip. The surrounding spaces still separate the words."""
    cleaned, removed = sanitize_for_postgres_text("Smith et \x00 al. (2019)")
    assert cleaned == "Smith et  al. (2019)"
    assert removed == 1


def test_nul_mid_word_rejoins_the_word():
    """The case stripping exists for: NUL stands in for a glyph that failed to
    map, so removing it yields the intended word. Replacing with a space would
    split 'temperature' into two tokens and break keyword search on it."""
    cleaned, removed = sanitize_for_postgres_text("the tempera\x00ture rose")
    assert cleaned == "the temperature rose"
    assert removed == 1
    assert "tempera ture" not in cleaned


def test_worst_case_document_density():
    """55 NULs in one file was the observed worst case in the eval corpus."""
    text = "word\x00" * 55
    cleaned, removed = sanitize_for_postgres_text(text)
    assert removed == 55
    assert cleaned == "word" * 55


# ------------------------------------------------------------ preservation ---

@pytest.mark.parametrize(
    "text",
    [
        "café naïve Grüße Ångström",           # accented Latin
        "深層学習のモデル 中文摘要 한국어",      # CJK
        "results 🎉 were significant 📈",        # emoji
        "∑ x_i ≤ α·β ⇒ ∇f(θ) → 0 ∈ ℝⁿ",       # mathematical symbols
        "line one\nline two\r\nline three",      # newlines (U+000A/U+000D)
        "col1\tcol2\tcol3",                     # tabs (U+0009)
        "page one\x0cpage two",                  # form feed U+000C - PDF page break
        "vertical\x0btab",                       # U+000B
        "bell\x07 and escape\x1b[0m",            # U+0007, U+001B
        "record\x1eseparator\x1funit",           # U+001E, U+001F
        "delete\x7fchar",                        # U+007F
        "line\u2028sep\u2029para",              # Unicode line/paragraph separators
        "\ufeffbom-prefixed text",              # BOM U+FEFF
    ],
)
def test_legal_content_survives_untouched(text):
    """Only U+0000 is illegal in PostgreSQL text. Everything here round-trips
    (verified directly against the local pgvector Postgres), so the sanitiser
    must not touch it -- over-sanitising mangles real extracted content."""
    cleaned, removed = sanitize_for_postgres_text(text)
    assert cleaned == text
    assert removed == 0


def test_realistic_academic_chunk_without_nuls_is_unchanged():
    chunk = (
        "3.2 Results\n\n"
        "We evaluated the model on the held-out split (n = 1,204).\tAccuracy "
        "reached 87.3% (95% CI [85.1, 89.5]), a significant improvement over "
        "the baseline of 79.1% (p < 0.001, two-tailed t-test; Cohen's d = 0.62).\n"
        "As Müller et al. [14] observed, the effect is strongest when α ≥ 0.5.\n"
        "See Figure 3 and Table 2 for per-class breakdowns.\n"
    )
    cleaned, removed = sanitize_for_postgres_text(chunk)
    assert cleaned == chunk
    assert removed == 0


# --------------------------------------------------------------- edge cases ---

def test_empty_string():
    assert sanitize_for_postgres_text("") == ("", 0)


def test_string_that_is_entirely_nuls():
    cleaned, removed = sanitize_for_postgres_text("\x00" * 7)
    assert cleaned == ""
    assert removed == 7


def test_idempotent():
    text = "a\x00b\x00\x00c"
    once, first = sanitize_for_postgres_text(text)
    twice, second = sanitize_for_postgres_text(once)
    assert twice == once
    assert first == 3
    assert second == 0


# ------------------------------------------------------------- collections ---

def test_chunk_list_is_sanitised_with_a_document_wide_total():
    chunks = ["clean chunk", "a\x00b", "no nuls here", "x\x00y\x00z"]
    cleaned, total = sanitize_chunks_for_postgres(chunks)
    assert total == 3
    assert cleaned == ["clean chunk", "ab", "no nuls here", "xyz"]
    assert all("\x00" not in c for c in cleaned)


def test_nested_metadata_is_sanitised_and_non_strings_pass_through():
    metadata = {
        "grobid_title": "Deep\x00 Learning for X",
        "page_count": 12,
        "cost_ceiling_applied": False,
        "grobid_sections": [{"title": "Intro\x00duction", "type": None}],
        "grobid_references": [{"raw": "Smith 2019"}, {"raw": "Jones\x002020"}],
    }
    cleaned, total = sanitize_json_for_postgres(metadata)
    assert total == 3
    assert cleaned["grobid_title"] == "Deep Learning for X"
    assert cleaned["grobid_sections"][0]["title"] == "Introduction"
    assert cleaned["grobid_references"][1]["raw"] == "Jones2020"
    assert cleaned["page_count"] == 12
    assert cleaned["cost_ceiling_applied"] is False


# ------------------------------------------------------------------ logging ---

def test_removal_count_is_logged_per_document(caplog):
    """Silent sanitisation hides the next data-quality problem: the ingest path
    must say how much text it altered, and say it once per document."""
    from app.services import rag_ingest

    _, total = sanitize_chunks_for_postgres(["a\x00b", "c\x00d\x00e"])

    with caplog.at_level(logging.WARNING, logger=rag_ingest.logger.name):
        rag_ingest.report_nul_removal("doc-123", total, "chunk content")

    records = [r for r in caplog.records if "NUL character(s)" in r.getMessage()]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "Removed 3 NUL character(s)" in message
    assert "chunk content" in message
    assert "doc-123" in message
    assert records[0].levelno == logging.WARNING


def test_clean_document_logs_nothing(caplog):
    from app.services import rag_ingest

    with caplog.at_level(logging.WARNING, logger=rag_ingest.logger.name):
        rag_ingest.report_nul_removal("doc-456", 0, "chunk content")

    assert [r for r in caplog.records if "NUL character(s)" in r.getMessage()] == []


def test_ingest_paths_route_their_counts_through_the_reporter():
    """Every surface that sanitises must also report. Guards against a future
    edit dropping the log and reintroducing silent sanitisation."""
    import inspect

    from app.services import rag_ingest

    ingest_src = inspect.getsource(rag_ingest.ingest_document)
    assert "sanitize_chunks_for_postgres" in ingest_src
    assert "sanitize_json_for_postgres" in ingest_src
    assert ingest_src.count("report_nul_removal(") == 2

    import_src = inspect.getsource(rag_ingest.embed_imported_document)
    assert "sanitize_for_postgres_text" in import_src
    assert "report_nul_removal(" in import_src
