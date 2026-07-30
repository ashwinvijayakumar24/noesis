"""CLI: run the HNSW sweep end to end and print the two tables.

    cd scripts/eval
    python3 -m ann_sweep.run_ann_sweep --what all

Everything appends to ``scripts/eval/results/ann_sweep.jsonl``.

WHAT IT DOES, IN ORDER
    1. Snapshot the table's index set.               <- the "before" evidence
    2. Exact sequential scan: ground truth + ceiling latency.
    3. ef_search sweep against the EXISTING production index (no rebuilds).
    4. m x ef_construction sweep: build, measure, drop, one at a time.
    5. Snapshot again and compare. A mismatch is a hard failure, not a warning.

Step 5 is the one that matters most for everything measured in this repo AFTER
this sweep: a stray index changes results invisibly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.ann_sweep import embeddings as emb_mod  # noqa: E402
from scripts.eval.ann_sweep import sweep as sweep_mod  # noqa: E402
from scripts.eval.ann_sweep.grid import (  # noqa: E402
    PRODUCTION_EF_SEARCH,
    build_grid,
    ef_search_grid,
)
from scripts.eval.ann_sweep.index_ops import (  # noqa: E402
    drop_created_indexes,
    find_stray_sweep_indexes,
    snapshot_indexes,
    snapshot_signature,
    verify_restored,
)
from scripts.eval.ann_sweep.search import SearchSpec  # noqa: E402
from scripts.eval.ann_sweep.sweep import QuerySet, corpus_fingerprint  # noqa: E402
from scripts.eval.retrieval import labels as labels_mod  # noqa: E402
from scripts.eval.retrieval import queries as queries_mod  # noqa: E402
from scripts.eval.retrieval.adapters import (  # noqa: E402
    EVAL_PROJECT_ID,
    RetrievedDoc,
    db_document_id,
    production_embed_fn,
)
from scripts.eval.retrieval.metrics import UNIT_DOCUMENT, evaluate_run  # noqa: E402

#: The manuscripts whose reference PDFs are the 118 documents currently in the
#: local index. Other directories exist under scripts/eval/corpora/ because a
#: parallel lane is downloading more PDFs; those are NOT ingested yet, and
#: including them would silently inflate the miss counts with documents the
#: index has never seen. Kept explicit so the mismatch is visible rather than
#: absorbed. n = 59 queries at this setting.
BASELINE_TOPICS = ["10eQ4Cfh8p", "9ceadCJY4B", "ApjY32f3Xr", "BQvbL2sFQx"]

#: Document-level k for the label metrics, and the chunk oversample that feeds
#: it. Both mirror retrieval/BASELINE.md so the two are comparable.
LABEL_K = 10
CHUNK_OVERSAMPLE = 5


def _load_db():
    from scripts.eval import db  # noqa

    return db


def build_scorer(label_set, query_list, k: int = LABEL_K):
    """Return ``{query_id: [Hit]} -> metrics dict`` using the retrieval harness.

    The id translation is mandatory, not cosmetic: labels key documents by
    sha256(pdf)[:16] and the database keys them by uuid5(namespace, sha256).
    Skipping it scores a flat 0.0 on every metric while looking healthy.
    """
    qbt = queries_mod.queries_by_topic(query_list)
    qrels = label_set.qrels(qbt)
    id_map = {
        db_document_id(doc.content_sha256): doc.doc_id
        for doc in label_set.docs.values()
        if doc.content_sha256
    }
    corpus_doc_ids = set(label_set.docs)
    unresolved = sum(len(t.unresolved) for t in label_set.topics.values())

    def score(hits: dict) -> dict:
        raw: dict[str, list[RetrievedDoc]] = {}
        joined = 0
        returned = 0
        for qid, rows in hits.items():
            docs: list[RetrievedDoc] = []
            for i, h in enumerate(rows, start=1):
                returned += 1
                mapped = id_map.get(h.document_id)
                if mapped is None:
                    continue
                joined += 1
                docs.append(
                    RetrievedDoc(doc_id=mapped, chunk_id=h.chunk_id, score=h.similarity, rank=i)
                )
            raw[qid] = docs
        result = evaluate_run(
            qrels_dict=qrels,
            raw_results=raw,
            corpus_doc_ids=corpus_doc_ids,
            unit=UNIT_DOCUMENT,
            k=k,
            unresolved_count=unresolved,
        )
        out = result.to_dict(include_misses=False)
        out["relevance_unit"] = UNIT_DOCUMENT
        out["rows_returned"] = returned
        out["rows_joined_to_corpus"] = joined
        out["note"] = (
            "recall/NDCG/MRR against CITATION LABELS -- a property of the whole "
            "system. Not the same quantity as ann_recall_vs_exact."
        )
        return out

    return score


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def _fmt(x, nd=4):
    return "n/a" if x is None else f"{x:.{nd}f}"


def print_ef_table(records: list[dict], n_queries: int, title: str) -> None:
    print("\n" + "=" * 126)
    print(f"  {title}   n = {n_queries} queries")
    print("=" * 126)
    hdr = (f"{'ef_search':>10} {'ANNrec@50':>10} {'ANNrec@10':>10} "
           f"{'R@1':>7} {'R@5':>7} {'R@10':>7} {'R@20':>7} {'NDCG@10':>8} {'MRR':>7} "
           f"{'p50 ms':>8} {'p95 ms':>8}  {'plan':<28}")
    print(hdr)
    print("-" * 126)
    for r in records:
        if r.get("status") != "ok":
            print(f"{r['params'].get('ef_search'):>10}  {r.get('status')}: {r.get('error')}")
            continue
        a = r.get("ann_recall_vs_exact") or {}
        m = (r.get("metrics_vs_labels") or {}).get("metrics", {})
        lat = r.get("latency_server_ms") or {}
        prod = "  <- PRODUCTION" if r["params"].get("is_production_reference") else ""
        print(
            f"{r['params']['ef_search']:>10} {_fmt(a.get('recall@50')):>10} {_fmt(a.get('recall@10')):>10} "
            f"{_fmt(m.get('recall@1')):>7} {_fmt(m.get('recall@5')):>7} {_fmt(m.get('recall@10')):>7} "
            f"{_fmt(m.get('recall@20')):>7} {_fmt(m.get('ndcg@10')):>8} {_fmt(m.get('mrr')):>7} "
            f"{_fmt(lat.get('p50_ms'), 3):>8} {_fmt(lat.get('p95_ms'), 3):>8}  "
            f"{str(r.get('plan_index_used') or 'SEQ SCAN (no index)'):<28}{prod}"
        )


def print_build_table(records: list[dict], n_queries: int) -> None:
    print("\n" + "=" * 126)
    print(f"  m x ef_construction SWEEP   n = {n_queries} queries")
    print("  Query columns are measured with enable_seqscan=off: the planner declines every")
    print("  HNSW index at this corpus size, so without forcing every row would be the same seq scan.")
    print("=" * 126)
    print(f"{'m':>4} {'ef_con':>7} {'build s':>9} {'size':>10} {'ANNrec@50':>10} {'ANNrec@10':>10} "
          f"{'R@10':>7} {'NDCG@10':>8} {'MRR':>7} {'p50 ms':>8} {'p95 ms':>8}")
    print("-" * 118)
    for r in records:
        p = r["params"]
        b = r.get("build") or {}
        if r.get("status") != "ok":
            print(f"{p.get('m'):>4} {p.get('ef_construction'):>7}  {r.get('status').upper()}: "
                  f"{(r.get('error') or '')[:80]}")
            continue
        a = r.get("ann_recall_vs_exact") or {}
        m = (r.get("metrics_vs_labels") or {}).get("metrics", {})
        lat = r.get("latency_server_ms") or {}
        prod = "  <- PRODUCTION" if p.get("is_production_reference") else ""
        print(
            f"{p['m']:>4} {p['ef_construction']:>7} {_fmt(b.get('build_seconds'), 2):>9} "
            f"{str(b.get('index_size_pretty')):>10} "
            f"{_fmt(a.get('recall@50')):>10} {_fmt(a.get('recall@10')):>10} "
            f"{_fmt(m.get('recall@10')):>7} {_fmt(m.get('ndcg@10')):>8} {_fmt(m.get('mrr')):>7} "
            f"{_fmt(lat.get('p50_ms'), 3):>8} {_fmt(lat.get('p95_ms'), 3):>8}  "
            f"{str(r.get('plan_index_used') or 'SEQ SCAN (no index)'):<28}{prod}"
        )


def print_planner_choice(record: dict) -> None:
    print("\n" + "=" * 126)
    print("  PLANNER CHOICE BY LIMIT -- does Postgres use the HNSW index at all?")
    print("=" * 126)
    for row in record["planner_choice_by_k"]:
        used = row["index_used"] or "SEQ SCAN -- index NOT used (exact search)"
        print(f"    LIMIT {row['k']:>4}  ->  {used}")
    print("  " + record["note"])


def print_exact(record: dict, n_queries: int) -> None:
    m = (record.get("metrics_vs_labels") or {}).get("metrics", {})
    lat = record.get("latency_server_ms") or {}
    latc = record.get("latency_client_ms") or {}
    print("\n" + "=" * 118)
    print(f"  EXACT SEQUENTIAL SCAN (no index) -- the recall = 1.0 ceiling   n = {n_queries} queries")
    print("=" * 118)
    print(f"  plan index used        : {record.get('plan_index_used')}  (None == seq scan, as required)")
    print(f"  ANN recall vs exact    : 1.0000 by definition")
    print(f"  recall@10 vs labels    : {_fmt(m.get('recall@10'))}")
    print(f"  NDCG@10 vs labels      : {_fmt(m.get('ndcg@10'))}")
    print(f"  MRR vs labels          : {_fmt(m.get('mrr'))}")
    print(f"  server p50 / p95 (ms)  : {_fmt(lat.get('p50_ms'), 3)} / {_fmt(lat.get('p95_ms'), 3)}")
    print(f"  client p50 / p95 (ms)  : {_fmt(latc.get('p50_ms'), 3)} / {_fmt(latc.get('p95_ms'), 3)}")
    print(f"  method                 : {record.get('latency_method')}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HNSW recall-vs-latency sweep (append-only results)")
    ap.add_argument("--what", default="all", choices=["all", "exact", "ef", "build"])
    ap.add_argument("--project-id", default=EVAL_PROJECT_ID)
    ap.add_argument("--table", default="document_chunks")
    ap.add_argument("--topic", action="append", dest="topics", default=None)
    ap.add_argument("--k", type=int, default=sweep_mod.DEFAULT_SEARCH_K)
    ap.add_argument("--repetitions", type=int, default=sweep_mod.DEFAULT_REPETITIONS)
    ap.add_argument("--warmup", type=int, default=sweep_mod.DEFAULT_WARMUP)
    ap.add_argument("--ef-search", type=int, action="append", dest="ef_values", default=None)
    ap.add_argument("--m", type=int, action="append", dest="m_values", default=None)
    ap.add_argument("--ef-construction", type=int, action="append", dest="efc_values", default=None)
    ap.add_argument("--build-ef-search", type=int, default=PRODUCTION_EF_SEARCH,
                    help="ef_search held fixed during the build sweep so the two "
                         "sweeps vary one family at a time (default: production's 80)")
    ap.add_argument("--results-path", default=str(sweep_mod.DEFAULT_RESULTS_PATH))
    ap.add_argument("--dry-run", action="store_true", help="Do not append to the results file")
    args = ap.parse_args(argv)

    topics = args.topics if args.topics is not None else BASELINE_TOPICS
    results_path = None if args.dry_run else args.results_path

    label_set, cache_hit = labels_mod.load_or_build(topics=topics)
    query_list = queries_mod.build_query_set(topics=topics)
    print(f"[sweep] topics  : {', '.join(topics)}")
    print(f"[sweep] labels  : {len(label_set.docs)} docs, {len(label_set.topics)} topics "
          f"({'cache hit' if cache_hit else 'rebuilt'}) fp={label_set.fingerprint()}")
    print(f"[sweep] queries : {len(query_list)}  fp={queries_mod.fingerprint(query_list)}")

    vectors = emb_mod.load_or_embed(
        [(q.query_id, q.text) for q in query_list], embed_fn=production_embed_fn()
    )
    qs = QuerySet(
        query_ids=[q.query_id for q in query_list],
        embeddings=[vectors[q.query_id] for q in query_list],
        fingerprint=queries_mod.fingerprint(query_list),
    )
    scorer = build_scorer(label_set, query_list)

    spec = SearchSpec(table=args.table, project_id=args.project_id)
    db = _load_db()

    with db.get_connection() as conn:
        conn.autocommit = False
        before = snapshot_indexes(conn, spec.table, spec.schema)
        print("\n[sweep] INDEX SET BEFORE:")
        for line in snapshot_signature(before):
            print(f"    {line}")

        strays = find_stray_sweep_indexes(conn, spec.table, spec.schema)
        if strays:
            print(f"\n[sweep] removing strays from a previous interrupted run: {strays}")
            drop_created_indexes(conn, strays, spec.schema)
            before = snapshot_indexes(conn, spec.table, spec.schema)

        corpus = corpus_fingerprint(conn, spec)
        print(f"\n[sweep] corpus  : {corpus.documents} documents / {corpus.chunks} chunks "
              f"(project {corpus.project_id})")

        exact_ids = None
        exact_rec = None
        if args.what in ("all", "exact", "ef", "build"):
            print("[sweep] exact sequential scan (ground truth) ...")
            exact_ids, exact_rec = sweep_mod.run_exact_baseline(
                conn, spec, qs, corpus, k=args.k,
                repetitions=args.repetitions, warmup=args.warmup,
                scorer=scorer, results_path=results_path,
            )

        planner_rec = None
        ef_out = None
        ef_forced_out = None
        if args.what in ("all", "ef"):
            planner_rec = sweep_mod.probe_planner_choice(
                conn, spec, qs, corpus, ef_search=PRODUCTION_EF_SEARCH,
                results_path=results_path,
            )
            # (a) what production executes -- planner free to choose
            ef_out = sweep_mod.run_ef_search_sweep(
                conn, spec, qs, corpus, ef_search_grid(args.ef_values),
                exact_chunk_ids=exact_ids, k=args.k, force_index_scan=False,
                repetitions=args.repetitions, warmup=args.warmup,
                scorer=scorer, results_path=results_path,
                progress=lambda s: print(f"[sweep] {s}"),
            )
            # (b) what the index does -- planner forced onto it and left with
            # no alternative index to fall back to
            hnsw_name = next(
                (i.name for i in before
                 if " USING hnsw " in i.definition and spec.column in i.definition),
                None,
            )
            ef_forced_out = sweep_mod.run_ef_search_sweep(
                conn, spec, qs, corpus, ef_search_grid(args.ef_values),
                exact_chunk_ids=exact_ids, k=args.k, force_index_scan=True,
                keep_index=hnsw_name,
                repetitions=args.repetitions, warmup=args.warmup,
                scorer=scorer, results_path=results_path,
                progress=lambda s: print(f"[sweep] {s}"),
            )

        build_out = None
        if args.what in ("all", "build"):
            build_out = sweep_mod.run_build_sweep(
                conn, spec, qs, corpus,
                build_grid(args.m_values, args.efc_values),
                exact_chunk_ids=exact_ids, k=args.k, ef_search=args.build_ef_search,
                repetitions=args.repetitions, warmup=args.warmup,
                scorer=scorer, results_path=results_path,
                progress=lambda s: print(f"[sweep] {s}"),
            )

        # ---- restoration proof ------------------------------------------
        leftover = (build_out.created_indexes if build_out else [])
        if leftover:
            print(f"\n[sweep] dropping {len(leftover)} index(es) created by this run: {leftover}")
            drop_created_indexes(conn, leftover, spec.schema)

        report = verify_restored(conn, before, spec.table, spec.schema)
        print("\n[sweep] INDEX SET AFTER:")
        for line in report.after:
            print(f"    {line}")

        if exact_rec:
            print_exact(exact_rec, len(qs))
        if planner_rec:
            print_planner_choice(planner_rec)
        if ef_out:
            print_ef_table(
                ef_out.records, len(qs),
                "ef_search SWEEP (A) -- PLANNER FREE, i.e. exactly what production executes",
            )
        if ef_forced_out:
            print_ef_table(
                ef_forced_out.records, len(qs),
                "ef_search SWEEP (B) -- enable_seqscan=off, i.e. the HNSW index itself",
            )
        if build_out:
            print_build_table(build_out.records, len(qs))

        print("\n" + "=" * 118)
        if report.restored:
            print("  INDEX SET RESTORED: before == after, no ann_sweep_* strays. VERIFIED.")
        else:
            print("  !! INDEX SET NOT RESTORED -- every later measurement on this table is suspect")
            print(f"     added  : {report.to_dict()['added']}")
            print(f"     removed: {report.to_dict()['removed']}")
            print(f"     strays : {report.strays}")
        print("=" * 118)
        if not args.dry_run:
            print(f"  results appended to {results_path}")

        return 0 if report.restored else 4


if __name__ == "__main__":
    raise SystemExit(main())
