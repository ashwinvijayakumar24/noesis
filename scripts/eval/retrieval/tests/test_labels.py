"""Label construction, and above all the denominator property.

The correctness property that matters most in this lane:
unresolved references are EXCLUDED from the recall denominator and counted
separately -- and when the denominator is unknown it is reported as unknown, not
silently replaced by the resolved count.
"""

import json

import pytest

from scripts.eval.retrieval import labels as L


def _make_pdf(path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture()
def corpora(tmp_path):
    root = tmp_path / "corpora"
    _make_pdf(root / "draftA" / "smith_2020_neural_scaling_laws.pdf", b"%PDF-A1")
    _make_pdf(root / "draftA" / "jones_2019_attention_mechanisms_survey.pdf", b"%PDF-A2")
    _make_pdf(root / "draftB" / "lee_2021_graph_transformers_benchmark.pdf", b"%PDF-B1")
    (root / "draftC").mkdir(parents=True)  # empty corpus
    return root


# ---------------------------------------------------------------------------
# Corpus construction
# ---------------------------------------------------------------------------


def test_builds_pooled_corpus_and_per_topic_labels(corpora):
    ls = L.build_label_set(corpora)
    assert len(ls.docs) == 3
    assert len(ls.topics["draftA"].relevant_doc_ids) == 2
    assert len(ls.topics["draftB"].relevant_doc_ids) == 1
    assert ls.topics["draftC"].relevant_doc_ids == []


def test_identical_pdf_in_two_corpora_collapses_to_one_doc_id(corpora):
    """Content addressing: the same paper cited by two manuscripts is one document."""
    _make_pdf(corpora / "draftB" / "smith_2020_neural_scaling_laws.pdf", b"%PDF-A1")
    ls = L.build_label_set(corpora)
    assert len(ls.docs) == 3  # not 4
    shared = set(ls.topics["draftA"].relevant_doc_ids) & set(ls.topics["draftB"].relevant_doc_ids)
    assert len(shared) == 1


def test_doc_ids_are_content_addressed_not_name_addressed(tmp_path):
    a = _make_pdf(tmp_path / "x" / "one.pdf", b"same-bytes")
    b = _make_pdf(tmp_path / "y" / "different_name.pdf", b"same-bytes")
    c = _make_pdf(tmp_path / "z" / "one.pdf", b"other-bytes")
    assert L.doc_id_for(a) == L.doc_id_for(b)
    assert L.doc_id_for(a) != L.doc_id_for(c)


# ---------------------------------------------------------------------------
# THE denominator property
# ---------------------------------------------------------------------------


def test_unresolved_refs_excluded_from_denominator_and_counted_separately(corpora):
    """Sidecar lists 5 attempted refs; 2 resolved. Rate is 2/5, NOT 2/2."""
    sidecar = [
        {"title": "Neural scaling laws", "doi": "10.1/a"},          # resolves
        {"title": "Attention mechanisms survey", "doi": "10.1/b"},  # resolves
        {"title": "Paywalled monograph on econometrics", "doi": "10.1/c"},
        {"title": "Unindexed workshop note about kernels", "doi": None},
        {"title": "Broken download of quantum annealing review", "doi": "10.1/e"},
    ]
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(json.dumps(sidecar))

    ls = L.build_label_set(corpora, topics=["draftA"])
    t = ls.topics["draftA"]

    assert len(t.relevant_doc_ids) == 2
    assert t.references_total == 5
    assert len(t.unresolved) == 3            # counted separately
    assert t.resolution_rate == pytest.approx(2 / 5)
    assert t.denominator_recoverable is True

    # The three excluded refs are NOT in the label set -- they cannot be missed.
    unresolved_titles = {u.title for u in t.unresolved}
    assert "Paywalled monograph on econometrics" in unresolved_titles
    assert len(t.relevant_doc_ids) + len(t.unresolved) == t.references_total


def test_missing_sidecar_reports_unknown_never_100_percent(corpora):
    """Without the attempted-reference list, resolved/resolved would read 100%."""
    ls = L.build_label_set(corpora)
    t = ls.topics["draftA"]
    assert t.references_total is None
    assert t.resolution_rate is None
    assert t.denominator_recoverable is False

    rep = ls.resolution_report()
    assert rep["references_resolved"] == 3
    assert rep["references_attempted"] is None
    assert rep["resolution_rate"] is None       # explicitly NOT 1.0
    assert rep["denominator_recoverable"] is False
    assert set(rep["topics_missing_denominator"]) == {"draftA", "draftB", "draftC"}


def test_one_unrecoverable_topic_poisons_the_global_rate(corpora):
    """A partial denominator reported as if total is the exact bug we guard against."""
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(
        json.dumps([{"title": "Neural scaling laws"}, {"title": "Attention mechanisms survey"}])
    )
    rep = L.build_label_set(corpora).resolution_report()
    assert rep["denominator_recoverable"] is False
    assert rep["resolution_rate"] is None
    assert "draftB" in rep["topics_missing_denominator"]


def test_empty_topics_are_reported(corpora):
    assert L.build_label_set(corpora).resolution_report()["empty_topics"] == ["draftC"]


def test_malformed_sidecar_falls_back_to_unknown(corpora):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text("{not json")
    assert L.build_label_set(corpora).topics["draftA"].references_total is None


def test_sidecar_dict_form_accepted(corpora):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(
        json.dumps({"references": [{"title": "Neural scaling laws"}, {"title": "Ghost"}]})
    )
    t = L.build_label_set(corpora).topics["draftA"]
    assert t.references_total == 2
    assert [u.title for u in t.unresolved] == ["Ghost"]


# ---------------------------------------------------------------------------
# qrels, caching, determinism
# ---------------------------------------------------------------------------


def test_qrels_expand_topic_labels_to_every_query(corpora):
    ls = L.build_label_set(corpora)
    qrels = ls.qrels({"draftA": ["q1", "q2"], "draftB": ["q3"], "draftC": ["q4"]})
    assert set(qrels) == {"q1", "q2", "q3"}          # draftC has no labels
    assert qrels["q1"] == qrels["q2"]
    assert all(v == 1 for v in qrels["q1"].values())  # binary by decision


def test_qrels_ignore_unknown_topics(corpora):
    assert L.build_label_set(corpora).qrels({"nope": ["q1"]}) == {}


def test_build_is_deterministic(corpora):
    a = L.build_label_set(corpora)
    b = L.build_label_set(corpora)
    assert a.to_dict() == b.to_dict()
    assert a.fingerprint() == b.fingerprint()


def test_cache_round_trips_and_hits(tmp_path, corpora):
    cache = tmp_path / "cache"
    first, hit1 = L.load_or_build(corpora, cache_dir=cache)
    second, hit2 = L.load_or_build(corpora, cache_dir=cache)
    assert hit1 is False and hit2 is True
    assert first.to_dict() == second.to_dict()


def test_cache_invalidates_when_corpus_changes(tmp_path, corpora):
    cache = tmp_path / "cache"
    L.load_or_build(corpora, cache_dir=cache)
    _make_pdf(corpora / "draftB" / "new_2022_extra_paper.pdf", b"%PDF-NEW-CONTENT")
    rebuilt, hit = L.load_or_build(corpora, cache_dir=cache)
    assert hit is False
    assert len(rebuilt.docs) == 4


def test_corrupt_cache_entry_rebuilds(tmp_path, corpora):
    cache = tmp_path / "cache"
    L.load_or_build(corpora, cache_dir=cache)
    for f in cache.glob("*.json"):
        f.write_text("{{{corrupt")
    rebuilt, hit = L.load_or_build(corpora, cache_dir=cache)
    assert hit is False and len(rebuilt.docs) == 3


def test_missing_corpora_root_yields_empty_label_set(tmp_path):
    ls = L.build_label_set(tmp_path / "does_not_exist")
    assert ls.docs == {} and ls.topics == {}


# ---------------------------------------------------------------------------
# Sidecar-driven resolution -- the authoritative matcher
# ---------------------------------------------------------------------------


def _status_sidecar(entries):
    return json.dumps({
        "corpus": "draftA",
        "references_attempted": len(entries),
        "references_resolved": sum(1 for e in entries if e["status"] == "resolved"),
        "references": entries,
    })


def test_sidecar_status_is_authoritative_over_filename_guessing(corpora):
    """A no_oa_pdf reference whose TITLE matches a downloaded file is still a gap.

    This is the exact bug: the title-token matcher saw "Neural scaling laws" and
    the file smith_2020_neural_scaling_laws.pdf and called the reference
    resolved -- crediting the retriever with a document that build_corpus.py
    records as never downloaded.
    """
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
        {"title": "Attention mechanisms survey", "status": "resolved",
         "filename": "jones_2019_attention_mechanisms_survey.pdf", "doi": "10.1/b"},
        # Same words as a file on disk, but it NEVER resolved.
        {"title": "Neural scaling laws", "status": "no_oa_pdf",
         "filename": None, "doi": "10.1/a"},
    ]))

    t = L.build_label_set(corpora, topics=["draftA"]).topics["draftA"]

    assert t.matcher == L.MATCHER_SIDECAR
    assert len(t.relevant_doc_ids) == 1                 # NOT 2
    assert [u.reason for u in t.unresolved] == ["no_oa_pdf"]
    assert t.unresolved[0].title == "Neural scaling laws"


def test_non_resolved_statuses_are_excluded_from_the_denominator(corpora):
    """Every non-resolved status is a corpus gap, counted separately by reason."""
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
        {"title": "A", "status": "resolved",
         "filename": "smith_2020_neural_scaling_laws.pdf"},
        {"title": "B", "status": "no_oa_pdf", "filename": None},
        {"title": "C", "status": "no_openalex_match", "filename": None},
        {"title": "D", "status": "download_failed", "filename": None},
        {"title": "E", "status": "pending", "filename": None},
        {"title": "F", "status": "skipped_max_papers", "filename": None},
    ]))

    t = L.build_label_set(corpora, topics=["draftA"]).topics["draftA"]

    assert len(t.relevant_doc_ids) == 1
    assert t.references_total == 6
    assert len(t.unresolved) == 5
    assert t.resolution_rate == pytest.approx(1 / 6)
    assert t.unresolved_by_reason == {
        "download_failed": 1, "no_oa_pdf": 1, "no_openalex_match": 1,
        "pending": 1, "skipped_max_papers": 1,
    }
    # The five gaps are not in the label set, so they cannot be scored as misses.
    assert len(t.relevant_doc_ids) + len(t.unresolved) == t.references_total


def test_resolved_reference_with_missing_file_is_a_gap_not_a_miss(corpora):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
        {"title": "Ghost", "status": "resolved", "filename": "not_on_disk.pdf"},
    ]))
    t = L.build_label_set(corpora, topics=["draftA"]).topics["draftA"]
    assert t.relevant_doc_ids == []
    assert [u.reason for u in t.unresolved] == [L.STATUS_FILE_MISSING]


def test_sidecar_matcher_ignores_files_no_reference_claims(corpora):
    """Labels follow the sidecar, not the directory listing."""
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
        {"title": "A", "status": "resolved",
         "filename": "smith_2020_neural_scaling_laws.pdf"},
    ]))
    t = L.build_label_set(corpora, topics=["draftA"]).topics["draftA"]
    assert len(t.relevant_doc_ids) == 1  # the other PDF in draftA is unclaimed


# ---------------------------------------------------------------------------
# The lenient fallback: fires only without statuses, and announces itself
# ---------------------------------------------------------------------------


def test_title_token_fallback_only_fires_for_a_statusless_sidecar(corpora):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(
        json.dumps([{"title": "Neural scaling laws"}, {"title": "Ghost"}])
    )
    (corpora / "draftB" / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
        {"title": "Graph transformers benchmark", "status": "resolved",
         "filename": "lee_2021_graph_transformers_benchmark.pdf"},
    ]))
    ls = L.build_label_set(corpora)

    assert ls.topics["draftA"].matcher == L.MATCHER_TITLE_TOKEN
    assert ls.topics["draftA"].uses_lenient_matcher is True
    assert ls.topics["draftB"].matcher == L.MATCHER_SIDECAR
    assert ls.topics["draftB"].uses_lenient_matcher is False
    # No sidecar at all is neither -- and must not be reported as lenient.
    assert ls.topics["draftC"].matcher == L.MATCHER_NONE
    assert ls.topics["draftC"].uses_lenient_matcher is False


def test_report_names_every_topic_using_the_lenient_matcher(corpora):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(
        json.dumps([{"title": "Neural scaling laws"}])
    )
    rep = L.build_label_set(corpora).resolution_report()
    assert rep["topics_using_lenient_matcher"] == ["draftA"]
    assert rep["matchers"]["draftA"] == L.MATCHER_TITLE_TOKEN


def test_cli_shouts_when_the_lenient_matcher_is_used(corpora, capsys, monkeypatch):
    (corpora / "draftA" / L.REFERENCES_SIDECAR).write_text(
        json.dumps([{"title": "Neural scaling laws"}])
    )
    monkeypatch.setattr(
        "sys.argv", ["labels", "--corpora-root", str(corpora), "--no-cache"]
    )
    L._main()
    out = capsys.readouterr().out
    assert "LENIENT TITLE-TOKEN FALLBACK IN USE" in out
    assert "INFLATED" in out
    assert "draftA" in out


def test_no_lenient_warning_when_every_sidecar_carries_statuses(corpora, capsys, monkeypatch):
    for topic, filename in (("draftA", "smith_2020_neural_scaling_laws.pdf"),
                            ("draftB", "lee_2021_graph_transformers_benchmark.pdf")):
        (corpora / topic / L.REFERENCES_SIDECAR).write_text(_status_sidecar([
            {"title": "x", "status": "resolved", "filename": filename},
        ]))
    monkeypatch.setattr(
        "sys.argv", ["labels", "--corpora-root", str(corpora), "--no-cache"]
    )
    L._main()
    assert "LENIENT TITLE-TOKEN FALLBACK IN USE" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The database join
# ---------------------------------------------------------------------------


def test_full_content_hash_is_retained_for_the_database_join(corpora):
    """doc_id is a 16-char prefix; the DB id needs the whole digest."""
    ls = L.build_label_set(corpora)
    for doc in ls.docs.values():
        assert len(doc.content_sha256) == 64
        assert doc.content_sha256.startswith(doc.doc_id)


def test_stale_cache_from_the_old_matcher_cannot_be_served(tmp_path, corpora, monkeypatch):
    """The schema version is in the cache key, so a pre-fix cache entry misses."""
    cache = tmp_path / "cache"
    L.load_or_build(corpora, cache_dir=cache)
    monkeypatch.setattr(L, "LABELS_SCHEMA_VERSION", L.LABELS_SCHEMA_VERSION + 1)
    _, hit = L.load_or_build(corpora, cache_dir=cache)
    assert hit is False
