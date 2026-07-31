# Noesis

Noesis reads an academic manuscript and critiques it the way a reviewer would. You upload a draft PDF; an 18-node LangGraph pipeline extracts its structure, claims and references, retrieves related work from a project corpus, checks citations against what the cited papers actually say, runs a panel of reviewer personas over the text, and returns a report of weaknesses, unsupported claims and coverage gaps. It does not rewrite the draft.

## Status: frozen

**There is no running product.** The AWS backend has been torn down. `www.noesis.is` serves a marketing-only page behind the `VITE_FREEZE_MODE` flag (`services/frontend/src/config/site.ts`); every backend-dependent route redirects to a contact page. Do not clone this expecting a deployable service.

What is active is the measurement work. Most of the recent history in this repo is an evaluation and instrumentation effort against the pipeline, and that part runs locally today.

## Architecture

| Piece | What |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Jobs | Celery + Redis |
| Analysis | 18-node LangGraph workflow, `services/backend/app/workflows/draft_analysis/graph.py` |
| Data | Supabase Postgres with pgvector (HNSW, cosine, 1536-dim); a local pgvector container for eval |
| PDF parsing | GROBID and Docling sidecars, PyMuPDF fallback |
| Frontend | React 19, TypeScript, Vite, Tailwind |

## Running it locally

Compose uses **profiles** because the dev machine allocates Docker ~8.2 GB and GROBID plus Docling are multi-GB emulated `linux/amd64` images. Starting everything at once OOMs.

Defined profiles: `core`, `parse`, `app`, `full`.

```bash
cd infra

docker compose --profile core up -d               # redis + local pgvector only
docker compose --profile parse up -d              # GROBID + Docling
docker compose --profile app --profile parse up -d  # the application
```

**`--profile app` alone fails.** `celery-worker` lives in `app` and declares `depends_on: grobid`, but `grobid` is only in `parse`, and Compose does not auto-enable a dependency's profile:

```
$ docker compose --profile app config --services
service "celery-worker" depends on undefined service "grobid": invalid compose project
```

Always pass both. `--profile full` will not fit in 8 GB and is reference only. Details and the memory table: `infra/README-profiles.md`.

## Evaluation harness

Everything under `scripts/eval/`. It is the most active part of the repo.

- `retrieval/` — retrieval eval against labelled corpora, with construction ceilings and query/label fingerprints
- `node_eval.py`, `trace_report/` — replay a single graph node, with spans, tokens and cost
- `loadgen/` — open- and closed-loop load generation over the graph
- `ann_sweep/` — HNSW `ef_search` / `m` / `ef_construction` sweeps and planner probes
- `judge.py`, `judge_openreview.py`, `atomize_reviews.py` — scoring against gold critiques and atomized ICLR reviews
- `gate_calibration/` — publish-gate threshold sweeps
- `benchmarks.py` — regenerates the tracked benchmark board from every local measurement sink

```bash
make benchmarks         # regenerate BENCHMARKS.md + benchmarks.json
make benchmarks-check   # fail if the tracked board is stale against local sinks
```

The board is deliberately timestamp-free, so an unchanged rerun produces an empty diff. Do not hand-edit it.

### Spend guardrails — read before running anything

The harness makes real OpenAI calls. `services/backend/app/core/llm_budget.py` enforces four environment variables; without them a run will spend money without asking.

| Variable | Effect |
|---|---|
| `NOESIS_LLM_KILL_SWITCH` | truthy — every LLM call raises `LLMCallBlocked` |
| `EVAL_REPLAY_ONLY` | truthy — same, for replay-only runs |
| `NOESIS_LLM_MAX_CALLS` | integer ceiling on calls |
| `NOESIS_LLM_MAX_SPEND_USD` | float ceiling on cumulative recorded spend |

Set a ceiling before any paid run. Set the kill switch for anything that should be pure replay.

## What is measured

Every figure below carries its `n` and its caveat. That is the house rule of this project, and a number without both is not quotable. Full board: [docs/BENCHMARKS.md](docs/BENCHMARKS.md); the running record and derivations: [docs/MEASUREMENTS.md](docs/MEASUREMENTS.md).

| Figure | n | Caveat |
|---|---|---|
| Graph latency p50 **63.75 s**, 99.5% of it LLM wait | 3 real GPT-5.2 runs, closed loop c=1 | **Graph** wall time only. Excludes upload, storage, PDF parsing and publish writes; parsing alone is larger than what is included. Never user-visible latency. |
| Reviewer-panel parallelism cuts graph wall time **1.48× / 32.5%** | A/B, 20 per arm | Against an Amdahl ceiling of **52%**, set by a measured 52% parallel fraction. The often-repeated `53s → 18s (66%)` is arithmetically unreachable and no historical serial baseline exists. |
| Dense retrieval **recall@10 = 0.2195**, ceiling **0.5199**, so **42% of attainable** | 338 scorable queries, 345-doc label corpus | Scoped to label snapshot `230c6ea9d9b7e8fd`. Numbers from different snapshots are not comparable — `0.4221 → 0.2195` is two different questions, not a regression. Measured on local pgvector with PyMuPDF, not production's parsing chain. |
| Keyword v2 takes zero-row queries from **321/338 to 0/338** | 338 queries | Behind `KEYWORD_SEARCH_V2`, default off. Nothing shipped to production. |
| Node + matcher cost **$0.20016** across 4 replay runs | 4 runs | **A lower bound.** The matcher bypassed the spend guardrails for most of the project's history and its calls were never recorded, so every cost figure in this repo is a floor. |
| Closed-loop benchmarking understates p99 by **8.2×–9.6×** | matched-throughput open vs closed loop | Coordinated omission, demonstrated on this graph: closed loop c=8 reports p99 17.45 s where open loop reports 142–168 s. |
| Judge `precision_vs_gold` **0.27**, hallucination rate **0.111** | 3 papers | The 0.27 is itself a lower bound under the label design; 0.111 is the unambiguous number. |

### What is not measured

End-to-end user-visible latency — never, not once. Any quality delta before/after any change: unresolvable at present `n`, because `temperature` is stripped for `gpt-5.2*` models and there is no seed. Production retrieval quality. Whether the publish gate's 0.75 threshold is right. User counts.

## Tests

```bash
cd services/backend && python3 -m pytest tests/ -q     # 1139 collected
python3 -m pytest scripts/eval -q                      # 736 collected, from repo root
```

## Documentation

- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — the generated benchmark board, every measurement with its `n`
- [docs/MEASUREMENTS.md](docs/MEASUREMENTS.md) — what is measured, what is not, and what each number cost to establish
- [docs/EVAL_GUIDE.md](docs/EVAL_GUIDE.md) — running the harness
- [docs/history/](docs/history/) — wave logs, plans and audits
- [infra/README-profiles.md](infra/README-profiles.md) — compose profiles and memory budget
- [AGENTS.md](AGENTS.md) — guide for coding agents working in this repo
