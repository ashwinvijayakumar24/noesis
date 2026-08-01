"""Contentless-claim classifier: determinism, zero LLM spend, published agreement.

The tests that matter here are not the unit tests on the lexical helpers. They
are the three that keep the published numbers honest:

* ``test_classifier_makes_zero_llm_calls`` -- the whole point of a lexical
  classifier is that it can be rerun for free and reproduces; a single LLM call
  would break both properties at once.
* ``test_published_agreement_reproduces`` -- the agreement figures in
  CONTENTLESS.md are pinned here, so tuning the thresholds without re-labelling
  turns the suite red instead of silently invalidating the writeup.
* ``test_published_population_reproduces`` -- likewise for the headline
  "X of 338" figure.
"""

import json

import pytest

from scripts.eval.retrieval import contentless as C
from scripts.eval.retrieval import queries as Q


# ---------------------------------------------------------------------------
# Fixtures: a miniature two-topic query set with known composition
# ---------------------------------------------------------------------------


class _Q:
    """Stand-in for queries.Query -- the classifier only reads three fields."""

    def __init__(self, query_id, topic, text):
        self.query_id = query_id
        self.topic = topic
        self.text = text


SERVABLE = [
    _Q("s1", "t1", "SaNN implicitly, is strictly more powerful than GAMLPs, SPIN, or SIGN."),
    _Q("s2", "t1", "Exact methods guarantee optimality through rigorous mathematical "
                   "reasoning but require prohibitive computational effort on large graphs."),
    _Q("s3", "t2", "Adam has previously been reported to be worse than SGD "
                   "(Grefenstette et al., 2019)."),
]
CONTENTLESS = [
    _Q("c1", "t1", "We experimentally verified that our method can achieve good results."),
    _Q("c2", "t1", "The result indicates that our framework effectively improves the "
                   "quality of the solution by alternating between these two models."),
    _Q("c3", "t2", "Extensive experimentation demonstrates that our model delivers better "
                   "performance in shorter time compared to baseline algorithms."),
]
MINI = SERVABLE + CONTENTLESS

#: The fixture set has 4-5 queries per topic, where a 0.20 document-frequency
#: threshold means "appears in one query" and strips essentially everything as
#: the manuscript's own vocabulary. The fixture tests therefore pass an explicit
#: high fraction; the degeneracy itself is asserted in
#: ``test_topic_vocabulary_degenerates_on_tiny_topics`` rather than papered over.
FIXTURE_FRACTION = 0.9


@pytest.fixture()
def real_queries():
    """The actual 338-query set. Skips rather than fails where exports are absent."""
    try:
        qs = Q.build_query_set()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"cached exports unavailable: {exc}")
    if not qs:
        pytest.skip("cached exports produced no queries")
    return qs


# ---------------------------------------------------------------------------
# Lexical machinery
# ---------------------------------------------------------------------------


def test_content_tokens_strip_generic_self_and_deixis():
    tokens = C.content_tokens("We show that our approach significantly improves performance.")
    assert tokens == []


def test_content_tokens_keep_domain_terms():
    tokens = C.content_tokens("Shift-equivariant properties are maintained across layers in CNNs.")
    assert "shift-equivariant" in tokens
    assert "cnns" in tokens


def test_topic_vocabulary_captures_the_protagonist_system():
    vocab = C.topic_vocabulary([
        _Q("a", "t", "TabR outperforms GBDT on the benchmark."),
        _Q("b", "t", "TabR is simple and efficient."),
        _Q("c", "t", "TabR confirms its status as a strong solution."),
        _Q("d", "t", "Gradient boosted trees remain competitive on wide tabular inputs."),
    ], fraction=0.5)
    assert "tabr" in vocab["t"]
    assert "gbdt" not in vocab["t"]


def test_topic_vocabulary_is_per_topic_not_global():
    """A term is only 'own vocabulary' for the manuscript that overuses it."""
    vocab = C.topic_vocabulary([
        _Q("a", "t1", "LLMs flatter users under negation."),
        _Q("b", "t1", "LLMs lose judgement consistency under misleading input."),
        _Q("c", "t2", "Tabular deep learning models trail gradient boosting on wide inputs."),
        _Q("d", "t2", "Retrieval components help LLMs only marginally on tabular tasks."),
    ], fraction=0.6)
    assert "llms" in vocab["t1"]
    assert "llms" not in vocab["t2"]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_inline_citation_short_circuits_to_servable():
    vocab = C.topic_vocabulary(MINI, FIXTURE_FRACTION)
    v = C.classify_text("We show that our method works (Smith et al., 2021).", "t1", vocab)
    assert v.contentless is False
    assert v.reason == "inline_citation"


def test_named_entity_anchor_makes_a_claim_servable():
    vocab = C.topic_vocabulary(MINI, FIXTURE_FRACTION)
    v = C.classify_text("Our model beats GBDT.", "t1", vocab)
    assert v.contentless is False
    assert v.reason == "named_entity"
    assert "gbdt" in v.anchors


def test_protagonist_name_is_not_an_anchor():
    """The paper's own system cannot discriminate among its own references."""
    queries = [_Q(str(i), "t", "TabR is efficient.") for i in range(5)]
    vocab = C.topic_vocabulary(queries)
    v = C.classify_text("TabR is efficient.", "t", vocab)
    assert v.contentless is True


def test_partition_returns_both_halves_and_preserves_order():
    servable, contentless = C.partition(MINI, FIXTURE_FRACTION)
    assert [q.query_id for q in servable] == ["s1", "s2", "s3"]
    assert [q.query_id for q in contentless] == ["c1", "c2", "c3"]
    assert len(servable) + len(contentless) == len(MINI)


def test_classification_is_deterministic_across_calls(real_queries):
    a = C.classify_queries(real_queries)
    b = C.classify_queries(real_queries)
    assert {k: v.contentless for k, v in a.items()} == {k: v.contentless for k, v in b.items()}


def test_verdict_carries_its_evidence():
    vocab = C.topic_vocabulary(MINI, FIXTURE_FRACTION)
    v = C.classify_text(
        "Exact methods guarantee optimality through rigorous mathematical reasoning "
        "but require prohibitive computational effort on large graphs.",
        "t1", vocab,
    )
    assert v.referents, "a servable verdict must name what it found servable"


# ---------------------------------------------------------------------------
# Zero LLM calls -- the load-bearing invariant
# ---------------------------------------------------------------------------


def test_classifier_makes_zero_llm_calls(real_queries):
    """Assert against the real spend counters used everywhere else in scripts/eval.

    Not 'we did not write an OpenAI import' -- the process-wide accumulator in
    app.core.llm_budget is what every other cost figure in this repo is measured
    with, so it is what this asserts against.
    """
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[4] / "services" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    try:
        from app.core import llm_budget
    except ImportError:  # pragma: no cover - backend deps absent
        pytest.skip("app.core.llm_budget not importable")

    llm_budget.reset()
    C.classify_queries(real_queries)
    C.partition(real_queries)

    assert llm_budget.events() == []
    assert llm_budget.total_spend_usd() == 0.0
    assert llm_budget.unpriced_calls() == 0


def test_classifier_path_imports_no_model_client():
    """Structural guard over the classifier's own imports.

    Scoped to import statements rather than the whole file, because the module
    docstring legitimately discusses why an LLM classifier was rejected. The
    ``--arms`` driver does import the DB-backed retrievers and the cached
    embedding function; those are the retrieval arms being measured, not the
    classifier, and the spend assertion above covers the classifier path.
    """
    import ast

    source = (C.RETRIEVAL_DIR / "contentless.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    classifier_fns = {"content_tokens", "topic_vocabulary", "classify_text",
                      "classify_queries", "partition"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in classifier_fns:
            for inner in ast.walk(node):
                assert not isinstance(inner, (ast.Import, ast.ImportFrom)), (
                    f"{node.name} must not import anything at call time"
                )

    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {a.name for n in top_level if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module or "" for n in top_level if isinstance(n, ast.ImportFrom)}
    assert names <= {"__future__", "collections", "json", "re", "dataclasses", "pathlib"}, (
        f"contentless.py must import only the stdlib at module level, got {sorted(names)}"
    )


def test_topic_vocabulary_degenerates_on_tiny_topics():
    """A known and published limitation, asserted rather than discovered later.

    With fewer than 1/TOPIC_VOCAB_FRACTION queries in a topic, a document
    frequency of one clears the threshold and every term in the topic is treated
    as the manuscript's own vocabulary. The real query set's smallest topic has
    8 queries, so this does not bite there -- but a future topic with 3 would be
    classified entirely contentless and would look like a finding.
    """
    tiny = [_Q("a", "t", "Simplicial complexes admit Hodge Laplacians on every order.")]
    vocab = C.topic_vocabulary(tiny, C.TOPIC_VOCAB_FRACTION)
    assert "simplicial" in vocab["t"], "df=1 of 1 clears a 0.20 threshold"


# ---------------------------------------------------------------------------
# Hand labels and the published numbers
# ---------------------------------------------------------------------------


def test_hand_labels_are_present_and_well_formed():
    labels = C.load_hand_labels()
    assert labels["labels_snapshot"] == "230c6ea9d9b7e8fd"
    assert len(labels["labels"]) == 120
    splits = {r["split"] for r in labels["labels"]}
    assert splits == {"development", "held_out"}
    ids = [r["query_id"] for r in labels["labels"]]
    assert len(set(ids)) == len(ids), "a query must not be labelled twice"


def test_hand_label_splits_are_disjoint():
    labels = C.load_hand_labels()
    dev = {r["query_id"] for r in labels["labels"] if r["split"] == "development"}
    held = {r["query_id"] for r in labels["labels"] if r["split"] == "held_out"}
    assert len(dev) == 60 and len(held) == 60
    assert not (dev & held), "held-out must share no query with the tuning split"


def test_missing_hand_labels_raise_rather_than_default_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        C.load_hand_labels(tmp_path / "nope.json")


def test_hand_labels_belong_to_this_query_set(real_queries):
    labels = C.load_hand_labels()
    assert labels["queries_fingerprint"] == Q.fingerprint(real_queries)


def test_agreement_rejects_labels_from_another_query_set(real_queries):
    labels = json.loads(json.dumps(C.load_hand_labels()))
    labels["labels"][0]["query_id"] = "0000000000000000"
    with pytest.raises(KeyError):
        C.score_against_hand_labels(real_queries, labels)


#: Pinned from the run that produced CONTENTLESS.md. See the module docstring
#: there for why the held-out figure is the only quotable one.
PUBLISHED_AGREEMENT = {
    "development": {"n": 60, "agreement": 0.850, "precision": 0.700, "recall": 0.538},
    "held_out": {"n": 60, "agreement": 0.733, "precision": 0.571, "recall": 0.444},
    "all": {"n": 120, "agreement": 0.792, "precision": 0.625, "recall": 0.484},
}


def test_published_agreement_reproduces(real_queries):
    scores = C.score_against_hand_labels(real_queries)
    for split, expected in PUBLISHED_AGREEMENT.items():
        got = scores[split]
        assert got.n == expected["n"]
        assert got.agreement == pytest.approx(expected["agreement"], abs=5e-4)
        assert got.precision == pytest.approx(expected["precision"], abs=5e-4)
        assert got.recall == pytest.approx(expected["recall"], abs=5e-4)


def test_published_population_reproduces(real_queries):
    """71 of 338 = 21.0%. Changing a lexicon entry without re-measuring fails here."""
    assert len(real_queries) == 338
    _, contentless = C.partition(real_queries)
    assert len(contentless) == 71


def test_hand_label_partition_matches_the_published_counts(real_queries):
    servable, contentless = C.hand_label_partition(real_queries)
    assert len(servable) == 89
    assert len(contentless) == 31
    assert len(servable) + len(contentless) == 120


def test_frozen_config_is_what_the_agreement_was_measured_at():
    assert C.TOPIC_VOCAB_FRACTION == 0.20
    assert C.MIN_REFERENTS == 4
