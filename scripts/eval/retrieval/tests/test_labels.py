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
