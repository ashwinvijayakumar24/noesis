"""Retrieval eval CLI.

RESULTS ARE APPEND-ONLY. This repo has already destroyed its eval history once:
``scripts/eval/run_eval.py:385`` does ``scoreboard_path.write_text(...)``, which
overwrites in place, so every prior scoreboard is gone and no trend line exists.
This harness writes JSONL, one record per run, and never rewrites a byte that is
already on disk.

Every record carries the relevance unit, retriever name, k, and a config hash, so
results produced under different configurations can never be silently compared.

Runs end to end with ``--retriever mock``: no database, no network, no LLM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

# Importable however it is invoked: as a module from the repo root, as
# `-m retrieval.run_retrieval_eval` from scripts/eval, or as a bare script path.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.retrieval import labels as labels_mod  # noqa: E402
from scripts.eval.retrieval import queries as queries_mod  # noqa: E402
from scripts.eval.retrieval.adapters import (  # noqa: E402
    EVAL_PROJECT_ID,
    MockRetriever,
    RetrievedDoc,
    Retriever,
    build_retriever,
    db_document_id,
    keyword_degradation_snapshot,
    production_embed_fn,
    reset_keyword_degradation,
)
from scripts.eval.retrieval.metrics import (  # noqa: E402
    DEFAULT_METRICS,
    UNIT_DOCUMENT,
    VALID_UNITS,
    evaluate_run,
)

EVAL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_PATH = EVAL_DIR / "results" / "retrieval_eval.jsonl"

HARNESS_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Config hash
# ---------------------------------------------------------------------------


def config_hash(config: dict) -> str:
    """Stable hash over everything that makes two runs incomparable.

    The relevance unit is in here deliberately: a document-unit NDCG and a
    chunk-unit NDCG are different quantities, and nothing downstream should be
    able to average them together by accident.
    """
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Append-only writer
# ---------------------------------------------------------------------------


def append_result(record: dict, path: Path) -> Path:
    """Append one JSON record as a line. Never truncates, never rewrites."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # "a" -- the whole point
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return path


def read_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def db_doc_id_map(label_set: labels_mod.LabelSet) -> dict[str, str]:
    """``{database document id -> label doc_id}``.

    See adapters.db_document_id for why this translation is mandatory rather
    than cosmetic: the two id spaces never overlap, so an unmapped run scores a
    flat zero on every metric and looks like a terrible retriever instead of a
    broken join.
    """
    return {
        db_document_id(doc.content_sha256): doc.doc_id
        for doc in label_set.docs.values()
        if doc.content_sha256
    }


def _remap(results: list[RetrievedDoc], id_map: dict[str, str]) -> list[RetrievedDoc]:
    """Translate DB document ids to label doc ids, dropping anything unmappable.

    An unmappable id is a chunk from a document that is in the index but not in
    the label corpus. It is a legitimate distractor, not an error, and dropping
    it is correct: it can never be relevant to any query. The count is reported
    so a join that maps *nothing* is impossible to miss.
    """
    out: list[RetrievedDoc] = []
    for r in results:
        mapped = id_map.get(r.doc_id)
        if mapped is None:
            continue
        out.append(RetrievedDoc(
            doc_id=mapped,
            chunk_id=r.chunk_id,
            score=r.score,
            rank=r.rank,
            section_id=r.section_id,
            text=r.text,
        ))
    return out


def run_eval(
    retriever: Retriever,
    query_list: list[queries_mod.Query],
    label_set: labels_mod.LabelSet,
    unit: str = UNIT_DOCUMENT,
    k: int = 10,
    chunk_oversample: int = 5,
    metrics: list[str] | None = None,
    remap_db_ids: bool = False,
) -> dict:
    """Execute retrieval for every query and score it. Pure function of inputs."""
    qbt = queries_mod.queries_by_topic(query_list)
    qrels = label_set.qrels(qbt)
    id_map = db_doc_id_map(label_set) if remap_db_ids else {}

    raw: dict[str, list] = {}
    rows_returned = 0
    rows_mapped = 0
    for q in query_list:
        results = retriever.retrieve(q.text, k * chunk_oversample)
        rows_returned += len(results)
        if remap_db_ids:
            results = _remap(results, id_map)
        rows_mapped += len(results)
        raw[q.query_id] = results

    empty_runs = sum(1 for qid in qrels if not raw.get(qid))
    unresolved = sum(len(t.unresolved) for t in label_set.topics.values())
    result = evaluate_run(
        qrels_dict=qrels,
        raw_results=raw,
        corpus_doc_ids=set(label_set.docs),
        unit=unit,
        k=k,
        metrics=metrics,
        unresolved_count=unresolved,
    )

    joinable = sorted(set(qbt) & {t for t, v in label_set.topics.items() if v.relevant_doc_ids})
    return {
        "result": result,
        "qrels": qrels,
        "raw": raw,
        "retrieval_health": {
            "rows_returned": rows_returned,
            "rows_joined_to_corpus": rows_mapped,
            "queries_with_empty_run": empty_runs,
            "db_id_map_size": len(id_map),
        },
        "n_queries_built": len(query_list),
        "joinable_topics": joinable,
        "topics_with_queries": sorted(qbt),
        "topics_with_labels": sorted(
            t for t, v in label_set.topics.items() if v.relevant_doc_ids
        ),
    }


#: Exit code for a run whose numbers cannot be trusted. Distinct from 1 (usage
#: error) so CI can tell "the harness broke" from "the harness worked and the
#: measurement is void".
EXIT_INVALID_RUN = 3


def run_verdict(degradation: dict, run_out: dict, retriever_name: str) -> dict:
    """Decide whether this run's numbers may be quoted at all.

    A retrieval run that completes while a silent-failure path fired has produced
    a plausible zero, not a measurement. Reporting it as a low score would be
    worse than reporting nothing, because a low score invites tuning against an
    artefact. So the run is marked invalid and the CLI exits non-zero.
    """
    reasons: list[str] = []

    if degradation.get("degraded"):
        reasons.append(
            f"KEYWORD_SEARCH_DEGRADED is set ({degradation.get('failure_count')} "
            f"failure(s), last: {degradation.get('last_error')}). The keyword RPC "
            "failed and the error was swallowed; any keyword or hybrid number in "
            "this run is an artefact of that failure."
        )

    health = run_out.get("retrieval_health") or {}
    scored = run_out["result"].n_queries_scored
    if scored:
        if health.get("rows_returned") == 0:
            reasons.append(
                f"the {retriever_name} retriever returned 0 rows for all {scored} "
                "scored queries. A retriever that returns nothing is a broken "
                "connection or a broken RPC, not a recall of 0.0."
            )
        elif health.get("rows_returned") and health.get("rows_joined_to_corpus") == 0:
            reasons.append(
                f"{health['rows_returned']} rows were returned but NONE joined to a "
                "corpus document id. The label/index id spaces are not aligned, so "
                "every metric here is a join bug, not a retrieval result."
            )

    return {"valid": not reasons, "reasons": reasons}


def build_record(
    run_out: dict,
    label_set: labels_mod.LabelSet,
    query_list: list[queries_mod.Query],
    retriever_name: str,
    unit: str,
    k: int,
    chunk_oversample: int,
    metrics: list[str],
    seed: int | None,
    include_misses: bool,
    timestamp: str | None = None,
    degradation: dict | None = None,
) -> dict:
    config = {
        "harness_version": HARNESS_VERSION,
        "relevance_unit": unit,
        "retriever": retriever_name,
        "k": k,
        "chunk_oversample": chunk_oversample,
        "metrics": sorted(metrics),
        "graded": label_set.graded,
        "seed": seed,
        "labels_fingerprint": label_set.fingerprint(),
        "queries_fingerprint": queries_mod.fingerprint(query_list),
    }
    result = run_out["result"]
    kill, kill_var = queries_mod.kill_switch_active()
    degradation = degradation if degradation is not None else keyword_degradation_snapshot()
    verdict = run_verdict(degradation, run_out, retriever_name)
    return {
        "valid": verdict["valid"],
        "invalidated_by": verdict["reasons"],
        "degradation": degradation,
        "retrieval_health": run_out.get("retrieval_health", {}),
        "run_id": None,  # filled below from content, so identical runs collide visibly
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash(config),
        "config": config,
        **result.to_dict(include_misses=include_misses),
        "resolution_report": label_set.resolution_report(),
        "join": {
            "n_queries_built": run_out["n_queries_built"],
            "joinable_topics": run_out["joinable_topics"],
            "topics_with_queries": run_out["topics_with_queries"],
            "topics_with_labels": run_out["topics_with_labels"],
        },
        "environment": {
            "python": platform.python_version(),
            "llm_kill_switch": kill_var if kill else None,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(record: dict) -> None:
    cfg = record["config"]
    print("\n" + "=" * 68)
    print("  RETRIEVAL EVAL")
    print("=" * 68)
    print(f"  retriever      : {cfg['retriever']}")
    print(f"  relevance unit : {cfg['relevance_unit']}   (see RELEVANCE.md)")
    print(f"  k              : {cfg['k']}  (chunk oversample x{cfg['chunk_oversample']})")
    print(f"  config hash    : {record['config_hash']}")
    print(f"  labels/queries : {cfg['labels_fingerprint']} / {cfg['queries_fingerprint']}")

    rr = record["resolution_report"]
    print("\n  -- ground truth ------------------------------------------------")
    print(f"  pooled corpus            : {rr['pooled_corpus_size']} docs")
    print(f"  references resolved      : {rr['references_resolved']}")
    print(f"  references unresolved    : {rr['references_unresolved_excluded']} (EXCLUDED from denominator)")
    if rr["denominator_recoverable"]:
        print(f"  references attempted     : {rr['references_attempted']}")
        print(f"  resolution rate          : {rr['resolution_rate']:.1%}")
    else:
        print("  resolution rate          : UNKNOWN -- denominator not recoverable from disk")
        print(f"                             (no references.json for: {', '.join(rr['topics_missing_denominator'])})")

    join = record["join"]
    print("\n  -- scale -------------------------------------------------------")
    print(f"  queries built            : {join['n_queries_built']}")
    print(f"  queries with labels      : {record['n_queries']} ({record['n_queries_scored']} scorable)")
    print(f"  relevant judgments       : {record['n_relevant_total']}")
    if not join["joinable_topics"]:
        print("  JOIN                     : EMPTY -- no manuscript has both queries and labels.")
        print(f"     topics with queries : {join['topics_with_queries'] or 'none'}")
        print(f"     topics with labels  : {join['topics_with_labels'] or 'none'}")
    else:
        print(f"  joinable topics          : {', '.join(join['joinable_topics'])}")

    print("\n  -- metrics -----------------------------------------------------")
    if record["n_queries_scored"] == 0:
        # Zeros here would be an artefact of having nothing to score, and would
        # be indistinguishable from a retriever that returns nothing useful.
        for name in sorted(record["metrics"]):
            print(f"  {name:<24} n/a  (no scorable queries)")
    else:
        for name in sorted(record["metrics"]):
            print(f"  {name:<24} {record['metrics'][name]:.4f}")

    print("\n  -- failure attribution -----------------------------------------")
    fb = record["failure_breakdown"]
    print(f"  total misses             : {fb.get('total_misses', 0)}")
    depth = cfg["k"] * cfg["chunk_oversample"]
    print(f"    retrieval_failure      : {fb.get('retrieval_failure', 0)}  "
          f"(in the corpus, but not in the {depth} chunks the retriever was asked for)")
    print(f"    ranking_failure        : {fb.get('ranking_failure', 0)}  (retrieved, below k)")
    print(f"    unresolved             : {fb.get('unresolved', 0)}  (no corpus doc id)")
    print(f"  excluded upstream        : {fb.get('unresolved_references_excluded_upstream', 0)}  (corpus gaps, never retrievable)")

    gaps = rr.get("references_unresolved_by_reason") or {}
    if gaps:
        print("  corpus gaps by reason    : " + ", ".join(f"{r}={n}" for r, n in gaps.items()))
    if rr.get("topics_using_lenient_matcher"):
        print("\n  !! LENIENT TITLE-TOKEN MATCHER used for: "
              + ", ".join(rr["topics_using_lenient_matcher"]))
        print("     Those topics have no status-bearing references.json; their "
              "resolution is GUESSED from filenames and their recall is INFLATED.")

    print("\n  -- run integrity -----------------------------------------------")
    deg = record.get("degradation") or {}
    health = record.get("retrieval_health") or {}
    if deg.get("checked"):
        print(f"  KEYWORD_SEARCH_DEGRADED  : {deg.get('degraded')}"
              f"  (failures={deg.get('failure_count')})")
    else:
        print(f"  KEYWORD_SEARCH_DEGRADED  : UNKNOWN -- {deg.get('note')}")
    if health:
        print(f"  rows returned            : {health.get('rows_returned')}")
        print(f"  rows joined to corpus    : {health.get('rows_joined_to_corpus')}")
        empty = health.get("queries_with_empty_run") or 0
        scored = record["n_queries_scored"] or 1
        print(f"  queries with empty run   : {empty} of {record['n_queries_scored']}")
        if empty and empty / scored >= 0.5:
            print("\n  !! WARNING: the retriever returned NOTHING for "
                  f"{empty / scored:.0%} of scored queries. The degradation flag is "
                  "clean, so this is real behaviour and not a swallowed error -- but "
                  "the aggregate metrics below are dominated by empty result sets and "
                  "describe coverage, not ranking quality.")

    if not record.get("valid", True):
        print("\n  " + "!" * 64)
        print("  RUN INVALID -- DO NOT QUOTE THESE NUMBERS")
        for reason in record.get("invalidated_by", []):
            print(f"    - {reason}")
        print("  " + "!" * 64)
    print("=" * 68)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Retrieval eval harness (append-only results). See RELEVANCE.md."
    )
    ap.add_argument("--retriever", default="mock", choices=["mock", "dense", "keyword", "hybrid"])
    ap.add_argument("--unit", default=UNIT_DOCUMENT, choices=list(VALID_UNITS))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--chunk-oversample", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0, help="MockRetriever seed")
    ap.add_argument("--plant-rate", type=float, default=0.0,
                    help="MockRetriever: fraction of relevant docs planted at top")
    ap.add_argument("--project-id", default=EVAL_PROJECT_ID,
                    help="Project the eval corpus was ingested under "
                         f"(default: {EVAL_PROJECT_ID}, matches scripts/eval/ingest.py)")
    ap.add_argument("--inspect", type=int, default=0, metavar="N",
                    help="Print the top hits and labels for the first N scored "
                         "queries. A number nobody has eyeballed is a number "
                         "nobody should trust.")
    ap.add_argument("--corpora-root", default=str(labels_mod.CORPORA_DIR))
    ap.add_argument("--exports-dir", default=str(queries_mod.EXPORTS_DIR))
    ap.add_argument("--topic", action="append", dest="topics")
    ap.add_argument("--max-per-topic", type=int)
    ap.add_argument("--results-path", default=str(DEFAULT_RESULTS_PATH))
    ap.add_argument("--metric", action="append", dest="metrics")
    ap.add_argument("--no-misses", action="store_true", help="Omit the per-miss list from the record")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Do not append to the results file")
    args = ap.parse_args(argv)

    metrics = args.metrics or DEFAULT_METRICS

    label_set, cache_hit = labels_mod.load_or_build(
        Path(args.corpora_root), topics=args.topics, use_cache=not args.no_cache
    )
    print(f"[eval] labels: {len(label_set.docs)} docs, {len(label_set.topics)} topics "
          f"({'cache hit' if cache_hit else 'rebuilt'})")

    query_list = queries_mod.build_query_set(
        Path(args.exports_dir), topics=args.topics, max_per_topic=args.max_per_topic
    )
    print(f"[eval] queries: {len(query_list)}")

    if args.retriever == "mock":
        relevant_by_query = {}
        qbt = queries_mod.queries_by_topic(query_list)
        by_id = {q.query_id: q for q in query_list}
        for topic, qids in qbt.items():
            rel = label_set.topics.get(topic)
            if rel:
                for qid in qids:
                    relevant_by_query[by_id[qid].text] = rel.relevant_doc_ids
        retriever: Retriever = MockRetriever(
            doc_ids=sorted(label_set.docs),
            seed=args.seed,
            relevant_by_query=relevant_by_query,
            plant_rate=args.plant_rate,
        )
    elif args.retriever == "dense":
        retriever = build_retriever(
            "dense", project_id=args.project_id, embed_fn=production_embed_fn()
        )
    else:
        retriever = build_retriever(args.retriever, project_id=args.project_id)

    # Clear first so the flag reflects THIS run rather than process history.
    reset_keyword_degradation()

    run_out = run_eval(
        retriever=retriever,
        query_list=query_list,
        label_set=label_set,
        unit=args.unit,
        k=args.k,
        chunk_oversample=args.chunk_oversample,
        metrics=metrics,
        remap_db_ids=args.retriever != "mock",
    )

    record = build_record(
        run_out=run_out,
        label_set=label_set,
        query_list=query_list,
        retriever_name=retriever.name,
        unit=args.unit,
        k=args.k,
        chunk_oversample=args.chunk_oversample,
        metrics=metrics,
        seed=args.seed if args.retriever == "mock" else None,
        include_misses=not args.no_misses,
    )
    record["run_id"] = hashlib.sha256(
        f"{record['config_hash']}\0{record['timestamp']}".encode("utf-8")
    ).hexdigest()[:12]

    _print_summary(record)

    if args.inspect:
        _print_inspection(run_out, query_list, label_set, args.inspect, args.k)

    if args.dry_run:
        print("\n[eval] --dry-run: nothing written.")
    else:
        path = append_result(record, Path(args.results_path))
        n = len(read_results(path))
        print(f"\n[eval] APPENDED record {record['run_id']} -> {path} ({n} records total)")

    if os.environ.get("NOESIS_LLM_KILL_SWITCH") or os.environ.get("EVAL_REPLAY_ONLY"):
        print("[eval] kill switch honoured: no LLM or network calls were made.")

    if not record["valid"]:
        # The record is still written -- an invalid run is itself a finding, and
        # silently dropping it would leave a gap in the append-only history.
        print(f"[eval] exiting {EXIT_INVALID_RUN}: this run's numbers are void.")
        return EXIT_INVALID_RUN
    return 0


def _print_inspection(
    run_out: dict,
    query_list: list[queries_mod.Query],
    label_set: labels_mod.LabelSet,
    n: int,
    k: int,
) -> None:
    """Dump top hits vs. labels for N queries, for manual sanity-checking."""
    titles = {d.doc_id: d.doc_key for d in label_set.docs.values()}
    qrels = run_out["qrels"]
    by_id = {q.query_id: q for q in query_list}
    shown = 0
    print("\n" + "=" * 68)
    print("  HAND-CHECK: top hits vs. cited references")
    print("=" * 68)
    for qid, rels in qrels.items():
        if shown >= n:
            break
        shown += 1
        q = by_id[qid]
        pooled: dict[str, float] = {}
        for r in run_out["raw"].get(qid, []):
            if r.doc_id not in pooled or r.score > pooled[r.doc_id]:
                pooled[r.doc_id] = r.score
        ranked = sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        print(f"\n[{q.topic}] {q.text[:150]}")
        print(f"  {len(rels)} cited references in corpus. Top {len(ranked)}:")
        for i, (doc_id, score) in enumerate(ranked, 1):
            mark = "REL " if doc_id in rels else "    "
            print(f"   {i:>2}. {mark} {score:.4f}  {titles.get(doc_id, doc_id)[:90]}")


if __name__ == "__main__":
    raise SystemExit(main())
