"""Ground-truth label construction for retrieval eval.

Label source: each manuscript's own reference list, as materialised on disk by
``scripts/eval/build_corpus.py``. A PDF in ``corpora/<stem>/`` exists if and only
if a reference of ``<stem>`` survived GROBID extraction, OpenAlex resolution,
open-access availability and download. Presence *is* the resolved-reference
label. See docs/EVAL_GUIDE.md §Relevance §4.

The correctness property this module exists to guarantee:

    Unresolvable references are EXCLUDED from the recall denominator and
    reported separately. A reference the retriever could never have surfaced is
    not a retriever miss.

And its corollary, which is where most harnesses quietly go wrong:

    When the denominator is unknown, it is reported as unknown -- never
    substituted with the resolved count, which would report a 100% resolution
    rate by construction.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

EVAL_DIR = Path(__file__).resolve().parent.parent
CORPORA_DIR = EVAL_DIR / "corpora"
CACHE_DIR = EVAL_DIR / "cache" / "retrieval_labels"

#: Optional sidecar written next to a corpus giving the reference list that was
#: *attempted*. Without it the resolution denominator is unrecoverable.
REFERENCES_SIDECAR = "references.json"

DOC_ID_LEN = 16

#: Bumped whenever the label schema or the resolution rule changes. It is part of
#: the cache key, so a stale cache written under the old lenient title-token
#: matcher can never be silently served for a run under the sidecar matcher.
LABELS_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusDoc:
    """A single document in the pooled evaluation corpus."""

    doc_id: str          # sha256(pdf_bytes)[:16] -- content addressed
    doc_key: str         # "<corpus>/<filename stem>" -- human readable
    corpus: str          # owning corpus directory name
    filename: str
    size_bytes: int
    #: Full sha256 of the PDF bytes. ``doc_id`` is its 16-char prefix; the full
    #: digest is retained because scripts/eval/ingest.py derives the DATABASE
    #: document id as uuid5(namespace, <this full hex digest>). Without it the
    #: retrieved ids cannot be joined back to labels at all.
    content_sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class UnresolvedRef:
    """A reference that never became a corpus document.

    ``reason`` carries the sidecar's authoritative ``status`` when one exists
    (``no_oa_pdf`` / ``no_openalex_match`` / ``download_failed`` / ``pending`` /
    ``skipped_max_papers``). Only when no per-reference status is recorded does
    it fall back to the undifferentiated ``"unresolved"``. See docs/EVAL_GUIDE.md §Relevance §4.
    """

    topic: str
    title: str
    doi: str | None = None
    reason: str = "unresolved"

    def to_dict(self) -> dict:
        return asdict(self)


#: How a topic's references were mapped onto corpus documents.
MATCHER_SIDECAR = "sidecar_status"        # authoritative: references.json status field
MATCHER_TITLE_TOKEN = "title_token_fallback"  # guessed from filenames -- LENIENT
MATCHER_NONE = "none"                     # no sidecar at all; denominator unknown


@dataclass
class TopicLabels:
    """Labels for one manuscript ("topic") against the pooled corpus."""

    topic: str
    relevant_doc_ids: list[str]
    #: Total references attempted, or None when unrecoverable.
    references_total: int | None
    unresolved: list[UnresolvedRef]
    #: Which of the three matchers produced the above. Recorded because the
    #: title-token fallback is deliberately lenient and inflates recall.
    matcher: str = MATCHER_NONE

    @property
    def uses_lenient_matcher(self) -> bool:
        return self.matcher == MATCHER_TITLE_TOKEN

    @property
    def unresolved_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for u in self.unresolved:
            counts[u.reason] = counts.get(u.reason, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def denominator_recoverable(self) -> bool:
        return self.references_total is not None

    @property
    def resolution_rate(self) -> float | None:
        if self.references_total is None or self.references_total == 0:
            return None
        return len(self.relevant_doc_ids) / self.references_total

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "relevant_doc_ids": sorted(self.relevant_doc_ids),
            "n_relevant": len(self.relevant_doc_ids),
            "references_total": self.references_total,
            "n_unresolved": len(self.unresolved),
            "denominator_recoverable": self.denominator_recoverable,
            "resolution_rate": self.resolution_rate,
            "matcher": self.matcher,
            "unresolved_by_reason": self.unresolved_by_reason,
            "unresolved": [u.to_dict() for u in self.unresolved],
        }


@dataclass
class LabelSet:
    """The complete label set: pooled corpus + per-topic relevance."""

    docs: dict[str, CorpusDoc] = field(default_factory=dict)
    topics: dict[str, TopicLabels] = field(default_factory=dict)
    graded: bool = False
    corpora_root: str = ""

    # -- qrels ------------------------------------------------------------

    def qrels(self, query_ids_by_topic: dict[str, Iterable[str]]) -> dict[str, dict[str, int]]:
        """Expand per-topic labels into per-query qrels.

        Every query belonging to a topic inherits that topic's relevant docs.
        Binary grades by decision (docs/EVAL_GUIDE.md §Relevance §5); the int is passed straight
        through to ranx so graded labels need no metric-side change.
        """
        out: dict[str, dict[str, int]] = {}
        for topic, query_ids in query_ids_by_topic.items():
            labels = self.topics.get(topic)
            if labels is None:
                continue
            grade_map = {doc_id: 1 for doc_id in labels.relevant_doc_ids}
            if not grade_map:
                continue
            for qid in query_ids:
                out[qid] = dict(grade_map)
        return out

    # -- reporting --------------------------------------------------------

    def resolution_report(self) -> dict:
        """Aggregate resolution accounting. The honest denominator lives here."""
        resolved = sum(len(t.relevant_doc_ids) for t in self.topics.values())
        unresolved = sum(len(t.unresolved) for t in self.topics.values())
        recoverable = [t for t in self.topics.values() if t.denominator_recoverable]
        unrecoverable = [t for t in self.topics.values() if not t.denominator_recoverable]

        attempted: int | None
        if unrecoverable:
            # Any unrecoverable topic poisons the global denominator. Refuse to
            # report a rate rather than report a partial one as if it were total.
            attempted = None
            rate = None
        else:
            attempted = sum(t.references_total or 0 for t in recoverable)
            rate = (resolved / attempted) if attempted else None

        by_reason: dict[str, int] = {}
        for t in self.topics.values():
            for reason, n in t.unresolved_by_reason.items():
                by_reason[reason] = by_reason.get(reason, 0) + n

        return {
            "pooled_corpus_size": len(self.docs),
            "n_topics": len(self.topics),
            "n_topics_with_labels": sum(1 for t in self.topics.values() if t.relevant_doc_ids),
            "references_resolved": resolved,
            "references_unresolved_excluded": unresolved,
            "references_unresolved_by_reason": dict(sorted(by_reason.items())),
            "references_attempted": attempted,
            "resolution_rate": rate,
            "denominator_recoverable": not unrecoverable,
            "topics_missing_denominator": sorted(t.topic for t in unrecoverable),
            "topics_using_lenient_matcher": sorted(
                t.topic for t in self.topics.values() if t.uses_lenient_matcher
            ),
            "matchers": {t.topic: t.matcher for t in sorted(
                self.topics.values(), key=lambda x: x.topic)},
            "empty_topics": sorted(
                t.topic for t in self.topics.values() if not t.relevant_doc_ids
            ),
        }

    def to_dict(self) -> dict:
        return {
            "corpora_root": self.corpora_root,
            "graded": self.graded,
            "docs": [self.docs[d].to_dict() for d in sorted(self.docs)],
            "topics": [self.topics[t].to_dict() for t in sorted(self.topics)],
            "resolution_report": self.resolution_report(),
        }

    def fingerprint(self) -> str:
        """Stable content hash of the label set, for the run config hash."""
        payload = json.dumps(
            {
                "schema": LABELS_SCHEMA_VERSION,
                "graded": self.graded,
                "docs": sorted(self.docs),
                "topics": {
                    t: {
                        "relevant": sorted(self.topics[t].relevant_doc_ids),
                        "matcher": self.topics[t].matcher,
                    }
                    for t in sorted(self.topics)
                },
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def content_sha256_for(pdf_path: Path) -> str:
    """Full sha256 hex of a PDF's bytes."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def doc_id_for(pdf_path: Path) -> str:
    """Content-addressed doc id. Identical papers in two corpora collapse to one."""
    return content_sha256_for(pdf_path)[:DOC_ID_LEN]


def _load_sidecar(corpus_dir: Path) -> list[dict] | None:
    """Load the optional attempted-references sidecar. None when absent."""
    path = corpus_dir / REFERENCES_SIDECAR
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict):
        data = data.get("references") or []
    return data if isinstance(data, list) else None


def _ref_title(ref: dict) -> str:
    return (ref.get("title") or ref.get("display_name") or "").strip()


def _title_tokens(title: str) -> set[str]:
    return {w.lower() for w in title.replace("-", " ").split() if len(w) > 3}


def _sidecar_matches_doc(ref: dict, doc: CorpusDoc) -> bool:
    """LENIENT title-token match of an attempted reference to a downloaded file.

    build_corpus.py names files ``<lastname>_<year>_<slugified title>.pdf``, so we
    match on title-token overlap against the filename stem.

    THIS IS A GUESS AND IT WAS MEASURABLY WRONG. Against the four corpora that
    now carry an authoritative sidecar it credited 21 references as resolved that
    build_corpus.py records as never having resolved (44 unresolved counted vs 65
    actually non-resolved). Crediting an unresolvable reference as retrievable
    inflates recall. It survives ONLY for corpora whose sidecar carries no
    per-reference ``status`` field, and every caller is told when it fired.
    """
    tokens = _title_tokens(_ref_title(ref))
    if not tokens:
        return False
    stem_tokens = {w for w in doc.filename.lower().replace(".pdf", "").split("_") if len(w) > 3}
    if not stem_tokens:
        return False
    return len(tokens & stem_tokens) / min(len(tokens), len(stem_tokens)) >= 0.5


#: A sidecar entry with this status resolved to a downloaded PDF. Anything else
#: is a CORPUS GAP, not a retrieval miss.
STATUS_RESOLVED = "resolved"

#: Recorded when the sidecar claims a resolution whose file is not on disk. Still
#: a corpus gap -- there is nothing for the retriever to return.
STATUS_FILE_MISSING = "resolved_but_file_missing"


def _sidecar_is_authoritative(refs: list[dict]) -> bool:
    """True when the sidecar records a per-reference outcome we can defer to."""
    return any(isinstance(r, dict) and r.get("status") for r in refs)


def _resolve_by_status(
    topic: str, refs: list[dict], docs_here: list[CorpusDoc]
) -> tuple[list[str], list[UnresolvedRef]]:
    """Sidecar-driven resolution. The sidecar's ``status`` field is the authority.

    A reference maps to a document if and only if build_corpus.py recorded
    ``status == "resolved"`` and named the file it wrote. Every other status is
    excluded from the recall denominator and counted separately by reason: those
    references were never downloadable, so no retriever could ever have returned
    them, and scoring them as misses would be a measurement bug.
    """
    by_filename = {d.filename: d for d in docs_here}
    relevant: list[str] = []
    unresolved: list[UnresolvedRef] = []

    for ref in refs:
        if not isinstance(ref, dict):
            continue
        status = (ref.get("status") or "unknown").strip()
        filename = ref.get("filename")
        title = _ref_title(ref)
        doi = ref.get("doi")

        if status != STATUS_RESOLVED:
            unresolved.append(UnresolvedRef(topic, title, doi, reason=status))
            continue

        doc = by_filename.get(filename) if filename else None
        if doc is None:
            # Claimed resolved but the file is gone. Still a corpus gap.
            unresolved.append(UnresolvedRef(topic, title, doi, reason=STATUS_FILE_MISSING))
            continue
        relevant.append(doc.doc_id)

    # Dedupe while preserving order: two references can name the same file only
    # if build_corpus.py double-resolved, and a doc is relevant at most once.
    seen: set[str] = set()
    deduped = [d for d in relevant if not (d in seen or seen.add(d))]
    return deduped, unresolved


def build_label_set(
    corpora_root: Path | None = None,
    topics: Iterable[str] | None = None,
    graded: bool = False,
) -> LabelSet:
    """Build the pooled corpus and per-topic labels from disk.

    Deterministic: same directory contents in, identical LabelSet out.
    Performs no network access and no LLM calls.
    """
    root = Path(corpora_root) if corpora_root else CORPORA_DIR
    label_set = LabelSet(graded=graded, corpora_root=str(root))
    if not root.exists():
        return label_set

    wanted = set(topics) if topics else None

    for corpus_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        topic = corpus_dir.name
        if wanted is not None and topic not in wanted:
            continue

        docs_here: list[CorpusDoc] = []
        for pdf in sorted(corpus_dir.glob("*.pdf")):
            sha = content_sha256_for(pdf)
            doc = CorpusDoc(
                doc_id=sha[:DOC_ID_LEN],
                doc_key=f"{topic}/{pdf.stem}",
                corpus=topic,
                filename=pdf.name,
                size_bytes=pdf.stat().st_size,
                content_sha256=sha,
            )
            # First writer wins so doc_key is stable under pooling; the doc_id
            # is content-addressed so the duplicate is genuinely the same paper.
            label_set.docs.setdefault(doc.doc_id, doc)
            docs_here.append(doc)

        sidecar = _load_sidecar(corpus_dir)
        unresolved: list[UnresolvedRef] = []

        if sidecar is None:
            # No sidecar: the denominator is unrecoverable and every file on disk
            # is taken at face value as a resolved reference.
            references_total = None
            relevant = [d.doc_id for d in docs_here]
            matcher = MATCHER_NONE
        elif _sidecar_is_authoritative(sidecar):
            references_total = len(sidecar)
            relevant, unresolved = _resolve_by_status(topic, sidecar, docs_here)
            matcher = MATCHER_SIDECAR
        else:
            # Sidecar present but statusless (an older format). Fall back to the
            # lenient title-token guess, and say so -- see _sidecar_matches_doc.
            references_total = len(sidecar)
            relevant = [d.doc_id for d in docs_here]
            unresolved = [
                UnresolvedRef(topic=topic, title=_ref_title(ref), doi=ref.get("doi"))
                for ref in sidecar
                if not any(_sidecar_matches_doc(ref, d) for d in docs_here)
            ]
            matcher = MATCHER_TITLE_TOKEN

        label_set.topics[topic] = TopicLabels(
            topic=topic,
            relevant_doc_ids=relevant,
            references_total=references_total,
            unresolved=unresolved,
            matcher=matcher,
        )

    return label_set


# ---------------------------------------------------------------------------
# Cache -- content-hash keyed, following scripts/eval/pipeline_cache.py
# ---------------------------------------------------------------------------


def corpora_fingerprint(root: Path) -> str:
    """SHA over every corpus file's relative path and size.

    Sizes rather than bytes: the corpus is ~40 PDFs and re-hashing all content on
    every cache probe would defeat the point of the cache. Content still enters
    the doc ids themselves, so a swapped-but-same-size file changes the built
    LabelSet's fingerprint even if it does not change this one.
    """
    digest = hashlib.sha256()
    if not root.exists():
        return "missing"
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel.endswith(".DS_Store") or "__pycache__/" in rel:
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def load_or_build(
    corpora_root: Path | None = None,
    topics: Iterable[str] | None = None,
    graded: bool = False,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> tuple[LabelSet, bool]:
    """Return ``(label_set, cache_hit)``. Reuses cached labels when the corpus
    fingerprint is unchanged, rather than re-walking and re-hashing PDFs."""
    root = Path(corpora_root) if corpora_root else CORPORA_DIR
    cdir = Path(cache_dir) if cache_dir else CACHE_DIR

    key_payload = json.dumps(
        {
            "schema": LABELS_SCHEMA_VERSION,
            "corpora": corpora_fingerprint(root),
            "topics": sorted(topics) if topics else None,
            "graded": graded,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
    cache_path = cdir / f"{key}.json"

    if use_cache and cache_path.exists():
        try:
            return _from_dict(json.loads(cache_path.read_text())), True
        except (json.JSONDecodeError, OSError, KeyError):
            pass  # corrupt cache entry -- rebuild

    label_set = build_label_set(root, topics=topics, graded=graded)
    if use_cache:
        cdir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(label_set.to_dict(), indent=2, sort_keys=True))
    return label_set, False


def _from_dict(payload: dict) -> LabelSet:
    label_set = LabelSet(
        graded=payload.get("graded", False),
        corpora_root=payload.get("corpora_root", ""),
    )
    doc_fields = {f for f in CorpusDoc.__dataclass_fields__}
    for d in payload.get("docs", []):
        # Ignore unknown keys so an older cache file loads instead of exploding.
        doc = CorpusDoc(**{k: v for k, v in d.items() if k in doc_fields})
        label_set.docs[doc.doc_id] = doc
    for t in payload.get("topics", []):
        label_set.topics[t["topic"]] = TopicLabels(
            topic=t["topic"],
            relevant_doc_ids=list(t["relevant_doc_ids"]),
            references_total=t["references_total"],
            unresolved=[UnresolvedRef(**u) for u in t.get("unresolved", [])],
            matcher=t.get("matcher", MATCHER_NONE),
        )
    return label_set


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build and report retrieval ground-truth labels")
    ap.add_argument("--corpora-root", default=str(CORPORA_DIR))
    ap.add_argument("--topic", action="append", dest="topics")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true", help="Dump the full label set as JSON")
    args = ap.parse_args()

    label_set, hit = load_or_build(
        Path(args.corpora_root), topics=args.topics, use_cache=not args.no_cache
    )
    if args.json:
        print(json.dumps(label_set.to_dict(), indent=2, sort_keys=True))
        return 0

    rep = label_set.resolution_report()
    print(f"[labels] corpora_root      : {label_set.corpora_root}")
    print(f"[labels] cache             : {'HIT' if hit else 'MISS (rebuilt)'}")
    print(f"[labels] pooled corpus     : {rep['pooled_corpus_size']} documents")
    print(f"[labels] topics            : {rep['n_topics']} ({rep['n_topics_with_labels']} with labels)")
    print(f"[labels] references resolved  : {rep['references_resolved']}")
    print(f"[labels] references unresolved: {rep['references_unresolved_excluded']} (EXCLUDED from denominator)")

    if rep["denominator_recoverable"]:
        print(f"[labels] references attempted : {rep['references_attempted']}")
        print(f"[labels] resolution rate      : {rep['resolution_rate']:.1%}")
    else:
        print("[labels] references attempted : UNKNOWN")
        print("[labels] resolution rate      : UNKNOWN -- not reported.")
        print(
            f"[labels] WARNING: no '{REFERENCES_SIDECAR}' sidecar for: "
            f"{', '.join(rep['topics_missing_denominator'])}"
        )
        print(
            "[labels] WARNING: build_corpus.py does not persist the reference list it "
            "started from, so the resolution denominator is unrecoverable from disk. "
            "Reporting resolved/resolved would show 100% by construction; refusing."
        )

    if rep["references_unresolved_by_reason"]:
        print("[labels] corpus gaps by recorded reason:")
        for reason, n in rep["references_unresolved_by_reason"].items():
            print(f"    {reason:<28} {n}")

    if rep["topics_using_lenient_matcher"]:
        print(
            "\n[labels] *** WARNING: LENIENT TITLE-TOKEN FALLBACK IN USE ***\n"
            f"[labels] topics: {', '.join(rep['topics_using_lenient_matcher'])}\n"
            "[labels] These corpora have a references.json with no per-reference "
            "'status' field, so resolution is GUESSED from filename token overlap. "
            "That guess is known to over-credit: on the four corpora that do carry "
            "statuses it called 21 non-resolved references resolved. Recall for "
            "these topics is INFLATED. Re-run build_corpus.py to write a "
            "status-bearing sidecar."
        )

    if rep["empty_topics"]:
        print(f"[labels] empty topics (0 labels): {', '.join(rep['empty_topics'])}")

    print("\n[labels] per-topic:")
    for topic in sorted(label_set.topics):
        t = label_set.topics[topic]
        rate = "n/a" if t.resolution_rate is None else f"{t.resolution_rate:.1%}"
        flag = "  <-- LENIENT" if t.uses_lenient_matcher else ""
        print(
            f"    {topic:<12} relevant={len(t.relevant_doc_ids):>3}  "
            f"unresolved={len(t.unresolved):>3}  rate={rate:<7} "
            f"matcher={t.matcher}{flag}"
        )

    print(f"\n[labels] fingerprint: {label_set.fingerprint()}")
    if os.environ.get("NOESIS_LLM_KILL_SWITCH") or os.environ.get("EVAL_REPLAY_ONLY"):
        print("[labels] (kill switch set -- this module never makes LLM or network calls anyway)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
