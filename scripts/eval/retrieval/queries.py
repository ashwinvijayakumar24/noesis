"""Query-set construction for retrieval eval.

Queries are claims extracted from manuscripts. Claim extraction is an LLM
operation, so this module is **cache-first and never calls an LLM**. It reads
claims that a previous pipeline run already persisted in
``scripts/eval/cache/exports/*.json``.

If the required claims are not cached, this module raises. It does not fall back
to a live call. ``NOESIS_LLM_KILL_SWITCH`` / ``EVAL_REPLAY_ONLY`` are honoured as
a belt-and-braces assertion: with either set, any attempt to reach a non-cache
source raises ``LLMCallBlocked``-style errors loudly rather than quietly costing
money and destroying reproducibility.

Determinism: the same export directory in produces the same query list out, in
the same order, with the same stable ids.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = EVAL_DIR / "cache" / "exports"

#: Claims shorter than this are section headers, fragments, or artefacts -- not
#: retrievable statements. Excluded deterministically.
MIN_CLAIM_CHARS = 40
MAX_CLAIM_CHARS = 600


class QueriesUnavailable(RuntimeError):
    """Raised when the requested queries are not in cache.

    Deliberately fatal. A silent fallback to live extraction would make the
    query set non-reproducible and would bypass the LLM kill switch.
    """


def kill_switch_active() -> tuple[bool, str]:
    """Mirror of app.core.llm_budget's switches, without importing the backend."""
    for var in ("NOESIS_LLM_KILL_SWITCH", "EVAL_REPLAY_ONLY"):
        val = (os.environ.get(var) or "").strip().lower()
        if val in {"1", "true", "yes", "on"}:
            return True, var
    return False, ""


@dataclass(frozen=True)
class Query:
    """One retrieval query."""

    query_id: str        # stable: sha256(topic + normalised text)[:16]
    topic: str           # manuscript this claim came from -- joins to labels
    text: str
    section: str | None = None
    claim_type: str | None = None
    requires_citation: bool = False
    source: str = "exports"

    def to_dict(self) -> dict:
        return asdict(self)


def _normalise(text: str) -> str:
    return " ".join((text or "").split())


def make_query_id(topic: str, text: str) -> str:
    payload = f"{topic}\0{_normalise(text).lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _iter_export_files(exports_dir: Path) -> list[Path]:
    if not exports_dir.exists():
        return []
    return sorted(exports_dir.glob("*.json"))


def _claims_from_export(payload: dict) -> tuple[str | None, list[dict]]:
    meta = payload.get("eval_metadata") or {}
    topic = meta.get("draft_file")
    if isinstance(topic, str):
        topic = Path(topic).stem or None
    claims = payload.get("claims") or []
    return topic, claims if isinstance(claims, list) else []


def build_query_set(
    exports_dir: Path | None = None,
    topics: list[str] | None = None,
    requires_citation_only: bool = False,
    max_per_topic: int | None = None,
) -> list[Query]:
    """Build the query set from cached pipeline exports.

    Deterministic. When a topic appears in several exports (the pipeline was run
    repeatedly), claims are unioned and de-duplicated by ``query_id``, so the
    query set does not depend on which run happened to be read last.
    """
    active, var = kill_switch_active()
    exports = Path(exports_dir) if exports_dir else EXPORTS_DIR

    by_id: dict[str, Query] = {}
    for path in _iter_export_files(exports):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        topic, claims = _claims_from_export(payload)
        if not topic:
            continue
        if topics is not None and topic not in topics:
            continue

        for claim in claims:
            if not isinstance(claim, dict):
                continue
            text = _normalise(claim.get("claim_text") or "")
            if not (MIN_CLAIM_CHARS <= len(text) <= MAX_CLAIM_CHARS):
                continue
            if requires_citation_only and not claim.get("requires_citation"):
                continue
            qid = make_query_id(topic, text)
            if qid in by_id:
                continue
            by_id[qid] = Query(
                query_id=qid,
                topic=topic,
                text=text,
                section=claim.get("section_location"),
                claim_type=claim.get("claim_type"),
                requires_citation=bool(claim.get("requires_citation")),
            )

    # Sort by (topic, query_id) -- independent of filesystem iteration order.
    queries = sorted(by_id.values(), key=lambda q: (q.topic, q.query_id))

    if max_per_topic is not None:
        capped: list[Query] = []
        seen: dict[str, int] = {}
        for q in queries:
            n = seen.get(q.topic, 0)
            if n >= max_per_topic:
                continue
            seen[q.topic] = n + 1
            capped.append(q)
        queries = capped

    if not queries and topics:
        raise QueriesUnavailable(
            f"No cached claims found for topics {sorted(topics)} in {exports}. "
            "Claim extraction requires an LLM call and this harness will not make one"
            + (f" ({var} is set)." if active else ".")
            + " Run the analysis pipeline for these manuscripts first so their claims "
            "land in cache/exports/, then re-run."
        )
    return queries


def queries_by_topic(queries: list[Query]) -> dict[str, list[str]]:
    """``{topic: [query_id, ...]}`` -- the join key into labels.qrels()."""
    out: dict[str, list[str]] = {}
    for q in queries:
        out.setdefault(q.topic, []).append(q.query_id)
    return out


def fingerprint(queries: list[Query]) -> str:
    payload = json.dumps([q.query_id for q in queries], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _main() -> int:
    import argparse
    from collections import Counter

    ap = argparse.ArgumentParser(description="Build the retrieval query set from cached claims")
    ap.add_argument("--exports-dir", default=str(EXPORTS_DIR))
    ap.add_argument("--topic", action="append", dest="topics")
    ap.add_argument("--requires-citation-only", action="store_true")
    ap.add_argument("--max-per-topic", type=int)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    queries = build_query_set(
        Path(args.exports_dir),
        topics=args.topics,
        requires_citation_only=args.requires_citation_only,
        max_per_topic=args.max_per_topic,
    )
    if args.json:
        print(json.dumps([q.to_dict() for q in queries], indent=2))
        return 0

    active, var = kill_switch_active()
    print(f"[queries] source      : {args.exports_dir} (cache only -- no LLM calls)")
    if active:
        print(f"[queries] kill switch : {var} is set")
    print(f"[queries] total       : {len(queries)}")
    print(f"[queries] fingerprint : {fingerprint(queries)}")
    print("[queries] per topic:")
    for topic, n in sorted(Counter(q.topic for q in queries).items()):
        print(f"    {topic:<16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
