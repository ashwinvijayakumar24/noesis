"""Contentless-claim detection for the retrieval query set.

WHY THIS EXISTS
    ``docs/history/WAVE_LOG.md`` carries a standing caveat about the retrieval
    baseline:

        "The query set also contains a large population of contentless claims
        that no retriever can serve; filtering them would raise every arm and
        improve nothing."

    That sentence asserts a quantity ("large") and an effect ("would raise every
    arm") without measuring either. This module exists to replace both halves
    with numbers that carry their ``n``. It does **not** exist to make the
    baseline look better. Filtering a benchmark down to the queries it happens to
    do well on is fabrication; measuring how much of a benchmark is unservable by
    construction, and reporting both populations side by side with both ceilings,
    is a result. ``CONTENTLESS.md`` reports both.

WHAT "CONTENTLESS" MEANS HERE
    The queries are claims extracted from manuscripts, and the labels are the
    manuscript's own resolved reference list. So a query is *servable* when a
    literature search over that reference list could plausibly return one of
    those references, and *contentless* when it could not -- not because the
    retriever is weak, but because the sentence names nothing outside the
    manuscript to key on.

    Operationally: strip from the sentence

      (i)   first-person and contribution framing  ("we show", "our method"),
      (ii)  evaluative and comparative rhetoric    ("significantly outperforms"),
      (iii) the manuscript's own protagonist names ("TabR", "BATTLE", "SaNN"),
      (iv)  intra-document deixis                  ("Fig. 3", "these results"),
      (v)   generic academic prose                 ("performance", "extensive"),

    and ask what is left. If what is left contains no named external entity and
    no specific domain phenomenon -- only the manuscript's own topic label and
    ordinary academic English -- the query is contentless.

    The fifth strip is the one that matters and the one that makes this hard:
    "TabR substantially outperforms the existing retrieval-based DL models while
    being significantly more efficient" reads technical, but every technical
    token in it is either the paper's own system or the paper's own topic label,
    which every one of its 40+ candidate references shares. It discriminates
    nothing. Contrast "SaNN implicitly, is strictly more powerful than GAMLPs,
    SPIN, or SIGN", where three externally-named models survive the strip and a
    retriever has something to find.

    The "discriminates within its own topic" test is why per-topic document
    frequency appears below rather than a fixed keyword list: what counts as a
    contentful term is a property of the manuscript, not of English. "LLM" is a
    referent in a paper about tabular data and is noise in a paper about LLMs.

EDGE CASES, AND WHERE THE LINE WAS DRAWN
    * **Priority claims** ("our work is the first to ..."). Contentless *only*
      when the thing claimed first is described in the paper's own vocabulary.
      "our method is the first to conduct a behavior-oriented adversarial attack
      against DRL agents through PbRL" names PbRL and DRL and is servable; "Our
      work is the first to highlight the importance of error analysis in
      enhancing the prompt" is not.
    * **Pure rhetoric that still names a field** ("the future of retrieval-based
      tabular DL looks positive"). Servable. The predicate is empty but the
      subject is a searchable subfield, and a retriever *can* return the cited
      retrieval-for-tabular papers from it. Calling this contentless would be
      scoring the sentence's intellectual content, which is a different and much
      more subjective question than the one being asked.
    * **Result reports naming an external baseline** ("MASS-enabled architectures
      consistently outperforms all other methods, including baseline and APS").
      Servable: APS is somebody else's method and is in the reference list.
    * **Inline citation markers** ("(Grinsztajn et al., 2022)"). Always servable,
      short-circuited before any lexical analysis. The author has pointed at the
      literature inside the sentence; whatever else is true, there is a referent.
    * **Anaphora with no antecedent** ("These observations demonstrate that ...",
      "the tradeoffs identified in section 4.1"). Contentless unless something
      survives the strip, because the antecedent lives in a part of the
      manuscript the query does not carry.

    A different labeller would draw some of these lines elsewhere. That is why
    ``contentless_hand_labels.json`` exists, why the agreement between this code
    and those labels is measured and published rather than assumed, and why the
    headline agreement figure is the **held-out** one.

NO LLM CALLS, EVER
    Everything here is lexical and structural over the stdlib. That is not a
    performance choice, it is a validity one: a classifier that asks GPT-5.2
    whether a claim is contentless would be asking the family of model that
    *wrote the claim extraction* to adjudicate its own output, would cost money
    per benchmark rerun, and -- because ``temperature`` is stripped for every
    ``gpt-5.2*`` model with no seed anywhere (see WAVE_LOG variance section) --
    would not reproduce. ``test_contentless.py`` asserts the spend counters read
    exactly zero after classifying the whole query set.

DETERMINISM
    Same query set in, same partition out, on any machine. The only stateful
    input is the query set itself, whose fingerprint is reported alongside every
    number this module produces.
"""

from __future__ import annotations

import collections
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

RETRIEVAL_DIR = Path(__file__).resolve().parent
HAND_LABELS_PATH = RETRIEVAL_DIR / "contentless_hand_labels.json"

# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------
#
# These two constants were tuned against the DEVELOPMENT half of the hand
# labels and then frozen before the held-out half was labelled. The held-out
# agreement in CONTENTLESS.md is therefore an out-of-sample number and the
# development agreement is not; both are published, and the gap between them
# (0.850 -> 0.733) is the honest measure of how much of the fit was the tuning.
#
# Changing either value invalidates the published agreement figures. Re-label
# before re-tuning, or the classifier becomes unfalsifiable.

#: A token appearing in at least this fraction of a topic's queries is that
#: manuscript's OWN vocabulary -- its protagonist system, its topic label -- and
#: cannot discriminate between its candidate references. Per-topic document
#: frequency, computed from the query set, never hardcoded per paper.
TOPIC_VOCAB_FRACTION = 0.20

#: Distinct surviving referent tokens below which a query is contentless. Four,
#: not one: a single surviving token is almost always a stray adjective the
#: generic list missed, and requiring a small cluster of them is what separates
#: "names something" from "the lexicon has holes".
MIN_REFERENTS = 4

CONFIG = {
    "topic_vocab_fraction": TOPIC_VOCAB_FRACTION,
    "min_referents": MIN_REFERENTS,
    "classifier_version": "1.0.0",
}


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------
#
# Hand-curated, and that is a limitation worth stating plainly rather than
# hiding behind a corpus statistic: with 15 topics and 338 queries there is not
# enough data to learn "generic academic English" by inverse document frequency
# (a sweep over cross-topic spread thresholds 4..8 yields between 10 and 101
# tokens, none of which is a usable stoplist). The lists below are therefore the
# classifier's largest source of error and its most inspectable component.

STOPWORDS = frozenset("""
a an the and or but if then than that this these those there here of in on at to for with without
from by as is are was were be been being it its their they them he she we our us i my me you your
have has had do does did can could will would shall should may might must not no nor so such very
more most much many few some any all both each other others another same different only also even
still yet however therefore thus hence moreover furthermore additionally consequently while whereas
although though because since which who whom whose what when where why how about into over under
between across through during after before above below up down out off again further once per via
etc eg ie vs onto upon within toward towards along
""".split())

#: Ordinary academic prose: the vocabulary every paper in every field uses to
#: frame a claim. A sentence built only from these names nothing.
GENERIC_ACADEMIC = frozenset("""
paper work works study studies research researcher researchers literature field area areas realm scope
approach approaches method methods methodology methodologies technique techniques strategy strategies
model models framework frameworks architecture architectures system systems design designs scheme schemes
result results finding findings outcome outcomes observation observations evidence experiment experiments
experimental experimentation empirically empirical theoretically theoretical numerically numerical
show shows shown showed showing demonstrate demonstrates demonstrated demonstrating prove proves proved
proven observe observes observed observing note notes noted noting notice noticed noteworthy
indicate indicates indicated indicating suggest suggests suggested suggesting reveal reveals revealed
find finds found verify verified verifies confirm confirms confirmed validate validated
propose proposed proposes proposing present presents presented presenting introduce introduces introduced
develop develops developed developing build builds building construct constructed create creates created
achieve achieves achieved achieving obtain obtains obtained yield yields yielded deliver delivers delivered
attain attains attained reach reaches reached gain gains gained provide provides provided providing
perform performs performed performing performance quality qualities accuracy accurate accurately
effective effectiveness effectively efficient efficiency efficiently efficacy
improve improves improved improving improvement improvements enhance enhances enhanced enhancing
better best superior superiority outperform outperforms outperformed outperforming surpass surpasses
surpassed exceed exceeds exceeded excellent excellence advantage advantages advantageous benefit
benefits beneficial worse worst inferior drawback drawbacks disadvantage disadvantages
significant significantly substantial substantially notable notably remarkable remarkably marked markedly
strong stronger strongest strongly great greater greatly good high higher highest low lower lowest
large larger largest small smaller smallest short shorter shortest long longer longest
new newer novel novelty first pioneering pioneer initiative advance advances
advancement advent progress step steps forward milestone breakthrough revolutionary
important importance crucial critical critically essential essentially key primary main major minor
potential potentially promising promise viable feasible relevant relevance applicable
comprehensive extensive extensively various variety several multiple numerous general generally overall
broad broader broadly wide wider widely universal universally common commonly typical typically
task tasks problem problems setting settings scenario scenarios case cases context contexts
domain domains instance instances example examples aspect aspects factor factors dimension dimensions
sample samples size sizes scale scales scaling number numbers amount amounts level levels degree degrees
quantity rate rates ratio proportion fraction percentage percent
time times duration cost costs expensive cheap computational compute complexity capability capabilities
ability abilities capacity resource resources memory runtime speed fast faster slow slower
compare compares compared comparing comparison comparisons comparable baseline baselines
exist exists existing prior previous previously current currently recent recently future
limit limits limited limitation limitations restrict restricted challenge challenges challenging
issue issues concern concerns difficulty difficulties gap gaps absence absent lack lacking
insight insights conclusion conclude concludes concluded conclusions analysis analyses analyze analyzed
analyzing analytical consider considers considered consideration believe believes posit posits
argue argues argued highlight highlights highlighted emphasize emphasized underscore underscores
underemphasized overlooked explore explores explored exploration examine examined investigate investigated
require requires required requirement need needs needed allow allows allowing enable enables enabled
enabling apply applies applied application applications use uses used using useful utility utilize
train trains trained training test tests tested testing evaluate evaluates evaluated evaluation
measure measures measured measurement report reports reported
value values term terms type types kind kinds form forms way ways manner
process processes procedure practice practices practical practically implement implements implemented
implementation setup pipeline stage stages phase phases iteration iterations
fig figure figures table tables section sections appendix subsection eq equation equations
theorem lemma proof corollary proposition assumption assumptions condition conditions mild
aforementioned following followed follows whether respect regard regarding respectively
addition additional particular particularly especially specific
possible possibly likely unlikely probably clearly clear obvious obviously evident evidently
seen see seeing given thereby therein nevertheless nonetheless
directions direction extend extends extended extension leave leaves left
consistent consistently consistency stable stability robust robustness reliable reliability
correlate correlated correlation relationship relation relations depend depends dependence dependent
combination combining combine combined alternating alternate simple simpler simplistic
sufficient sufficiently adequate adequately enough necessary correct correctness
difference differences differ differs differing similar similarity
increase increases increased increasing decrease decreases decreased decreasing reduce reduces reduced
reduction change changes changed vary varies varied varying variation variations
based order well make makes making made
statistically statistical average averaged mean centered slightly moderate moderately
technically summary finally firstly secondly thirdly lastly
counter-intuitive under-explored underexplored unexplored preliminary systematic
""".split())

#: Self-reference and contribution framing.
SELF_REFERENCE = frozenset("we our ours us i my me".split())

#: Deixis pointing back into the manuscript the query does not carry.
DEIXIS = frozenset("""
this that these those it its their there here such former latter thereof herein
""".split())

#: An inline citation makes the sentence servable regardless of everything else:
#: the author has named the literature inside the query. Matches "et al." and any
#: parenthetical containing a 4-digit year.
CITATION_RE = re.compile(r"et\s+al\.|\(\s*[^()]*\b(?:19|20)\d{2}[a-z]?\s*\)")

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-'µ]*")

#: Orthographic evidence of a named technical entity: an embedded run of capitals
#: (GBDT, PINN, MMLU), interior camel case (GraphSAGE, TabR), or an embedded digit
#: (OPT-1.3B, L2). Deliberately does NOT match a plain sentence-initial-style
#: capitalised word: "Wikipedia" and "Meta-world" are missed, and that is a
#: measured, published limitation rather than a silent one -- CONTENTLESS.md
#: §2 "Known false positives and negatives" names both. Not patched after the
#: fact, because fixing it against the held-out errors would destroy the only
#: out-of-sample agreement figure in that document.
ANCHOR_RE = re.compile(
    r"\b(?:[A-Za-z]*[A-Z]{2,}[A-Za-z0-9\-]*|[a-z]+[A-Z][A-Za-z]*|[A-Za-z]+[0-9]+[A-Za-z0-9\-]*)\b"
)


def _normalise(token: str) -> str:
    return token.lower().strip("-'")


def content_tokens(text: str) -> list[str]:
    """Tokens surviving the stopword / generic / self / deixis strips.

    Order-preserving and duplicate-preserving; callers that want distinct
    referents take a set. Not a tokenizer anyone should reuse -- it exists to
    answer one question about one query set.
    """
    out: list[str] = []
    for match in TOKEN_RE.finditer(text):
        token = _normalise(match.group(0))
        if len(token) < 2:
            continue
        if token in STOPWORDS or token in GENERIC_ACADEMIC:
            continue
        if token in SELF_REFERENCE or token in DEIXIS:
            continue
        out.append(token)
    return out


def topic_vocabulary(
    queries: list,
    fraction: float = TOPIC_VOCAB_FRACTION,
) -> dict[str, frozenset[str]]:
    """``{topic: terms this manuscript uses so often they discriminate nothing}``.

    Per-topic document frequency over the query set. A term in this set is the
    paper's protagonist system, its topic label, or its own coined metric -- all
    three are shared by the paper's entire candidate reference list, so none of
    them tells a retriever which reference to return.

    Computed from the query set rather than declared per paper on purpose: a
    hardcoded list of system names would have to be maintained by hand for every
    new manuscript and would silently rot the first time one was added.
    """
    by_topic: dict[str, list] = collections.defaultdict(list)
    for query in queries:
        by_topic[query.topic].append(query)

    vocab: dict[str, frozenset[str]] = {}
    for topic, topic_queries in by_topic.items():
        document_frequency: collections.Counter = collections.Counter()
        for query in topic_queries:
            for token in set(content_tokens(query.text)):
                document_frequency[token] += 1
        n = len(topic_queries)
        vocab[topic] = frozenset(
            token for token, count in document_frequency.items() if count / n >= fraction
        )
    return vocab


@dataclass(frozen=True)
class Verdict:
    """One classification, with the evidence that produced it.

    The evidence fields are not decoration. A boolean that cannot be argued with
    is a boolean nobody can check; ``referents`` and ``anchors`` are what make a
    disagreement with the hand labels diagnosable instead of merely countable.
    """

    query_id: str
    contentless: bool
    reason: str
    referents: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def classify_text(
    text: str,
    topic: str,
    topic_vocab: dict[str, frozenset[str]],
    min_referents: int = MIN_REFERENTS,
    query_id: str = "",
) -> Verdict:
    """Classify one claim. Three tests, in order, first match wins.

    1. An inline citation marker -- servable, no lexical analysis needed.
    2. A named-entity anchor that is not the paper's own vocabulary -- servable.
    3. Otherwise count distinct surviving referents against ``min_referents``.
    """
    own = topic_vocab.get(topic, frozenset())

    if CITATION_RE.search(text):
        return Verdict(query_id, False, "inline_citation")

    anchors = sorted(
        {
            _normalise(m.group(0))
            for m in ANCHOR_RE.finditer(text)
            if _normalise(m.group(0)) not in own
            and _normalise(m.group(0)) not in GENERIC_ACADEMIC
            and _normalise(m.group(0)) not in STOPWORDS
        }
    )
    if anchors:
        return Verdict(query_id, False, "named_entity", anchors=tuple(anchors))

    referents = tuple(sorted({t for t in content_tokens(text) if t not in own}))
    contentless = len(referents) < min_referents
    return Verdict(
        query_id,
        contentless,
        "too_few_referents" if contentless else "sufficient_referents",
        referents=referents,
    )


def classify_queries(
    queries: list,
    fraction: float = TOPIC_VOCAB_FRACTION,
    min_referents: int = MIN_REFERENTS,
) -> dict[str, Verdict]:
    """``{query_id: Verdict}`` for a whole query set. Zero LLM calls."""
    vocab = topic_vocabulary(queries, fraction)
    return {
        q.query_id: classify_text(q.text, q.topic, vocab, min_referents, q.query_id)
        for q in queries
    }


def partition(
    queries: list,
    fraction: float = TOPIC_VOCAB_FRACTION,
    min_referents: int = MIN_REFERENTS,
) -> tuple[list, list]:
    """``(servable, contentless)``, preserving the input order in both halves.

    This is the function the eval harness wants. It returns BOTH halves rather
    than a filtered list, because a caller that can only see the survivors cannot
    report what it dropped, and a filter whose discards are invisible is how a
    benchmark quietly becomes a different benchmark.
    """
    verdicts = classify_queries(queries, fraction, min_referents)
    servable = [q for q in queries if not verdicts[q.query_id].contentless]
    contentless = [q for q in queries if verdicts[q.query_id].contentless]
    return servable, contentless


# ---------------------------------------------------------------------------
# Hand labels and agreement
# ---------------------------------------------------------------------------


@dataclass
class Agreement:
    """Classifier vs. human, with every count needed to recompute every rate."""

    split: str
    n: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    hand_contentless: int = field(default=0)

    @property
    def agreement(self) -> float:
        return (self.true_positive + self.true_negative) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def prevalence(self) -> float:
        """Hand-judged contentless rate in this split -- the number the caveat asserts."""
        return self.hand_contentless / self.n if self.n else 0.0

    def to_dict(self) -> dict:
        out = asdict(self)
        out.update(
            agreement=self.agreement,
            precision=self.precision,
            recall=self.recall,
            f1=self.f1,
            prevalence=self.prevalence,
        )
        return out


def load_hand_labels(path: Path | None = None) -> dict:
    """Read the hand-label file. Raises rather than defaulting to empty.

    An unvalidated classifier makes every downstream number unfalsifiable, so a
    missing label file is a hard error and never a silent skip.
    """
    p = Path(path) if path else HAND_LABELS_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Hand labels not found at {p}. Every number this module produces is "
            "conditioned on the measured agreement between the classifier and a "
            "human; without the labels there is nothing to condition on."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def score_against_hand_labels(
    queries: list,
    hand_labels: dict | None = None,
    fraction: float = TOPIC_VOCAB_FRACTION,
    min_referents: int = MIN_REFERENTS,
) -> dict[str, Agreement]:
    """``{split: Agreement}`` for every split in the hand-label file, plus "all".

    ``development`` was used to tune ``TOPIC_VOCAB_FRACTION`` / ``MIN_REFERENTS``
    and is in-sample. ``held_out`` was labelled after those were frozen and is
    the only figure that may be quoted as the classifier's accuracy.
    """
    labels = hand_labels if hand_labels is not None else load_hand_labels()
    verdicts = classify_queries(queries, fraction, min_referents)

    buckets: dict[str, list[tuple[bool, bool]]] = collections.defaultdict(list)
    for record in labels["labels"]:
        verdict = verdicts.get(record["query_id"])
        if verdict is None:
            raise KeyError(
                f"Hand-labelled query {record['query_id']} is not in this query set. "
                f"The labels were made against queries fingerprint "
                f"{labels['queries_fingerprint']}; a different query set is a "
                "different measurement and the agreement must not be carried over."
            )
        pair = (verdict.contentless, bool(record["contentless"]))
        buckets[record["split"]].append(pair)
        buckets["all"].append(pair)

    out: dict[str, Agreement] = {}
    for split, pairs in buckets.items():
        tp = sum(1 for p, h in pairs if p and h)
        fp = sum(1 for p, h in pairs if p and not h)
        fn = sum(1 for p, h in pairs if not p and h)
        tn = sum(1 for p, h in pairs if not p and not h)
        out[split] = Agreement(
            split=split,
            n=len(pairs),
            true_positive=tp,
            false_positive=fp,
            false_negative=fn,
            true_negative=tn,
            hand_contentless=tp + fn,
        )
    return out


def hand_label_partition(
    queries: list,
    hand_labels: dict | None = None,
) -> tuple[list, list]:
    """``(servable, contentless)`` over the HAND-LABELLED queries only.

    The classifier-free measurement. Scoring the two hand-labelled halves
    separately gives an effect size that does not inherit the classifier's error
    rate at all -- smaller ``n``, but nothing between the human judgment and the
    metric. CONTENTLESS.md reports it beside the classifier-filtered table for
    exactly that reason.
    """
    labels = hand_labels if hand_labels is not None else load_hand_labels()
    judged = {r["query_id"]: bool(r["contentless"]) for r in labels["labels"]}
    servable = [q for q in queries if judged.get(q.query_id) is False]
    contentless = [q for q in queries if judged.get(q.query_id) is True]
    return servable, contentless


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(queries: list, verdicts: dict[str, Verdict]) -> None:
    n = len(queries)
    n_contentless = sum(1 for v in verdicts.values() if v.contentless)
    reasons = collections.Counter(v.reason for v in verdicts.values())
    by_topic: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for q in queries:
        bucket = by_topic[q.topic]
        bucket[0] += 1
        bucket[1] += int(verdicts[q.query_id].contentless)

    print("=" * 68)
    print("  CONTENTLESS CLAIM CLASSIFIER")
    print("=" * 68)
    print(f"  config            : {CONFIG}")
    print(f"  queries           : {n}")
    print(f"  contentless       : {n_contentless}  ({n_contentless / n:.1%} of {n})")
    print(f"  servable          : {n - n_contentless}")
    print("  verdict reasons   :")
    for reason, count in reasons.most_common():
        print(f"      {reason:<22} {count}")
    print("  per topic (contentless / total):")
    for topic in sorted(by_topic):
        total, bad = by_topic[topic]
        print(f"      {topic:<14} {bad:>3} / {total:<3}  {bad / total:.0%}")


def _print_agreement(scores: dict[str, Agreement]) -> None:
    print("\n" + "=" * 68)
    print("  AGREEMENT WITH HAND LABELS")
    print("=" * 68)
    print(f"  {'split':<14}{'n':>5}{'agree':>8}{'prec':>8}{'rec':>8}{'F1':>8}{'prev':>8}")
    for split in ("development", "held_out", "all"):
        a = scores.get(split)
        if a is None:
            continue
        print(f"  {split:<14}{a.n:>5}{a.agreement:>8.3f}{a.precision:>8.3f}"
              f"{a.recall:>8.3f}{a.f1:>8.3f}{a.prevalence:>8.3f}")
    print("\n  'development' is IN SAMPLE -- the two thresholds were tuned on it.")
    print("  'held_out' was labelled after the thresholds were frozen and is the")
    print("  only figure quotable as the classifier's accuracy.")


#: The arms recomputed for CONTENTLESS.md. Names, retrievers and depths mirror
#: the runs already in ``results/retrieval_eval.jsonl`` for label snapshot
#: 230c6ea9d9b7e8fd, so the unfiltered column of the published table can be
#: checked line by line against the existing baseline rather than taken on trust.
ARMS = (
    {"arm": "dense_os5", "retriever": "dense", "chunk_oversample": 5},
    {"arm": "dense_os12", "retriever": "dense", "chunk_oversample": 12},
    {"arm": "keyword_v1", "retriever": "keyword", "chunk_oversample": 5, "use_v2": False},
    {"arm": "keyword_v2", "retriever": "keyword", "chunk_oversample": 5, "use_v2": True},
    {"arm": "rrf_k60", "retriever": "hybrid", "chunk_oversample": 5, "use_v2": True, "k_rrf": 60},
)

#: Metrics reported per arm. recall@10 is the headline because the labels measure
#: "would we have found what the author cited"; every precision-like metric is a
#: lower bound under that design (WAVE_LOG standing caveat).
ARM_METRICS = ["recall@10", "ndcg@10", "mrr"]


def _score_subset(run_out_raw, qrels_all, subset_query_ids, corpus_doc_ids, unresolved):
    """Score one arm on one subset of queries, recomputing the subset's ceiling.

    THE CEILING IS RECOMPUTED HERE AND IT HAS TO BE. Every query inherits its
    manuscript's whole resolved reference list, so recall@10 is capped at
    ``mean(min(10, |rel_q|) / |rel_q|)`` -- a property of *which queries are in
    the set*. Dropping queries changes it. Reusing the full set's 0.5199 for a
    filtered subset would silently rescale the arm and is precisely the error
    ``docs/BENCHMARKS.md`` forbids ("one label snapshot's ceiling is never
    applied to another's measurement").
    """
    from scripts.eval.retrieval.metrics import (
        evaluate_run,
        percent_of_attainable,
        recall_ceilings,
    )

    qrels = {q: r for q, r in qrels_all.items() if q in subset_query_ids and r}
    raw = {q: run_out_raw.get(q, []) for q in qrels}
    result = evaluate_run(
        qrels_dict=qrels,
        raw_results=raw,
        corpus_doc_ids=corpus_doc_ids,
        unit="document",
        k=10,
        metrics=ARM_METRICS,
        unresolved_count=unresolved,
    )
    ceilings = recall_ceilings(qrels, [10])
    return {
        "n_scored": result.n_queries_scored,
        "n_relevant": result.n_relevant_total,
        "metrics": result.metrics,
        "recall_ceilings": ceilings,
        "percent_of_attainable": percent_of_attainable(result.metrics, ceilings),
    }


def _run_arms(query_list, project_id: str | None = None) -> dict:
    """Retrieve once per arm over ALL queries, then score every subset from it.

    Retrieval happens once and the subsets are cut from the same raw results, so
    the filtered and unfiltered columns cannot differ because of retrieval
    nondeterminism -- only because of which queries are in the denominator. That
    is the whole comparison, and running the retriever twice would confound it.

    Zero LLM calls: all 338 query embeddings are already in
    ``cache/retrieval_query_embeddings/``. If one were missing this would raise
    under the kill switch rather than quietly buy a vector.
    """
    from scripts.eval.retrieval import labels as labels_mod
    from scripts.eval.retrieval.adapters import (
        EVAL_PROJECT_ID,
        DenseRetriever,
        HybridRetriever,
        KeywordRetriever,
        production_embed_fn,
    )
    from scripts.eval.retrieval import queries as queries_mod
    from scripts.eval.retrieval.run_retrieval_eval import _remap, db_doc_id_map

    pid = project_id or EVAL_PROJECT_ID
    label_set, _ = labels_mod.load_or_build(labels_mod.CORPORA_DIR, use_cache=True)
    qrels_all = label_set.qrels(queries_mod.queries_by_topic(query_list))
    id_map = db_doc_id_map(label_set)
    corpus_doc_ids = set(label_set.docs)
    unresolved = sum(len(t.unresolved) for t in label_set.topics.values())

    embed_fn = production_embed_fn()
    verdicts = classify_queries(query_list)
    hand_servable, hand_contentless = hand_label_partition(query_list)

    subsets = {
        "unfiltered": {q.query_id for q in query_list},
        "classifier_servable": {
            q.query_id for q in query_list if not verdicts[q.query_id].contentless
        },
        "classifier_contentless": {
            q.query_id for q in query_list if verdicts[q.query_id].contentless
        },
        "hand_servable": {q.query_id for q in hand_servable},
        "hand_contentless": {q.query_id for q in hand_contentless},
    }

    out: dict = {"subsets": {k: len(v) for k, v in subsets.items()}, "arms": {}}
    for spec in ARMS:
        if spec["retriever"] == "dense":
            retriever = DenseRetriever(project_id=pid, embed_fn=embed_fn)
        elif spec["retriever"] == "keyword":
            retriever = KeywordRetriever(project_id=pid, use_v2=spec["use_v2"])
        else:
            retriever = HybridRetriever(
                dense=DenseRetriever(project_id=pid, embed_fn=embed_fn),
                keyword=KeywordRetriever(project_id=pid, use_v2=spec["use_v2"]),
                k_rrf=spec["k_rrf"],
            )
        depth = 10 * spec["chunk_oversample"]
        raw = {q.query_id: _remap(retriever.retrieve(q.text, depth), id_map)
               for q in query_list}
        plan = getattr(retriever, "plan_summary", None)
        out["arms"][spec["arm"]] = {
            "spec": {k: v for k, v in spec.items() if k != "arm"},
            "plan": plan() if callable(plan) else "unknown",
            "subsets": {
                name: _score_subset(raw, qrels_all, ids, corpus_doc_ids, unresolved)
                for name, ids in subsets.items()
            },
        }
    return out


def _print_arms(report: dict) -> None:
    order = ("unfiltered", "classifier_servable", "classifier_contentless",
             "hand_servable", "hand_contentless")
    for name in order:
        print("\n" + "=" * 92)
        print(f"  SUBSET: {name}   (n queries in subset: {report['subsets'][name]})")
        print("=" * 92)
        print(f"  {'arm':<14}{'n':>6}{'R@10':>10}{'ceiling':>10}{'%attain':>10}"
              f"{'NDCG@10':>10}{'MRR':>9}{'judgments':>11}")
        for arm, data in report["arms"].items():
            s = data["subsets"][name]
            m, c = s["metrics"], s["recall_ceilings"]
            pct = s["percent_of_attainable"].get("recall@10")
            print(f"  {arm:<14}{s['n_scored']:>6}{m['recall@10']:>10.4f}"
                  f"{c['recall@10']:>10.4f}{(pct or 0):>9.0%}"
                  f"{m['ndcg@10']:>11.4f}{m['mrr']:>9.4f}{s['n_relevant']:>11}")


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    repo_root = str(RETRIEVAL_DIR.parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from scripts.eval.retrieval import queries as queries_mod  # noqa: E402

    ap = argparse.ArgumentParser(
        description="Measure the contentless-claim population in the retrieval query set."
    )
    ap.add_argument("--exports-dir", default=str(queries_mod.EXPORTS_DIR))
    ap.add_argument("--topic", action="append", dest="topics")
    ap.add_argument("--validate", action="store_true",
                    help="Score the classifier against the hand labels")
    ap.add_argument("--arms", action="store_true",
                    help="Recompute every retrieval arm on every subset. Needs the "
                         "local pgvector container; makes zero LLM calls (all query "
                         "embeddings are cached).")
    ap.add_argument("--project-id", help="Eval corpus project id (default: adapters.EVAL_PROJECT_ID)")
    ap.add_argument("--list", choices=["contentless", "servable"],
                    help="Print the queries on one side of the partition")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    query_list = queries_mod.build_query_set(Path(args.exports_dir), topics=args.topics)
    verdicts = classify_queries(query_list)

    if args.json:
        payload = {
            "config": CONFIG,
            "queries_fingerprint": queries_mod.fingerprint(query_list),
            "n_queries": len(query_list),
            "n_contentless": sum(1 for v in verdicts.values() if v.contentless),
            "verdicts": [v.to_dict() for v in verdicts.values()],
        }
        if args.validate:
            payload["agreement"] = {
                k: v.to_dict() for k, v in score_against_hand_labels(query_list).items()
            }
        if args.arms:
            payload["arms"] = _run_arms(query_list, args.project_id)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"[contentless] queries fingerprint: {queries_mod.fingerprint(query_list)}")
    _print_report(query_list, verdicts)
    if args.validate:
        _print_agreement(score_against_hand_labels(query_list))
    if args.arms:
        _print_arms(_run_arms(query_list, args.project_id))
    if args.list:
        want = args.list == "contentless"
        print("\n" + "=" * 68)
        print(f"  {args.list.upper()} QUERIES")
        print("=" * 68)
        for q in query_list:
            v = verdicts[q.query_id]
            if v.contentless is want:
                print(f"\n[{q.topic}] {v.reason}")
                print(f"  {q.text[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
