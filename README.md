# Noesis

Noesis reads an academic manuscript and critiques it the way a reviewer would. You upload a draft PDF; an 18-node LangGraph pipeline extracts its structure, claims and references, retrieves related work from a project corpus, checks citations against what the cited papers actually say, runs a panel of reviewer personas over the text, and returns a report of weaknesses, unsupported claims and coverage gaps. **It does not rewrite the draft.**

The companion repo [`reviewer-agent`](https://github.com/ashwinvijayakumar24/reviewer-agent) is an autonomous tool-calling agent built to do the same job, benchmarked head-to-head against this pipeline on identical labels. Both directions are published, including where each one loses.

---

## Status: paused, and open-sourced

**There is no running product.** The AWS backend is torn down. `www.noesis.is` serves a marketing-only page behind the `VITE_FREEZE_MODE` flag (`services/frontend/src/config/site.ts`); every backend-dependent route redirects to a contact page. Do not clone this expecting a deployable service.

Three reasons it stopped, in the order they mattered:

**1. The market moved from both ends at once.** In June 2026 Anthropic shipped Claude Science, whose reviewer agent checks citations and calculations — the same job this pipeline's `citation_judge` and `draft_citation_verification` nodes exist to do. Google's AI co-scientist includes a "virtual peer reviewer" reflection stage. Dedicated startups (Reviewer3 among them) occupy the narrow version. A small team does not out-execute frontier labs on a feature they now ship as a line item.

**2. Trust in AI-assisted review collapsed while we were building for it.** The facts are sharper than the sentiment:

- **ICML 2026 desk-rejected 497 papers** over reviewer LLM-policy violations — 506 reviewers, 795 flagged reviews, caught by a watermark embedded in every submitted PDF ([ICML, 18 Mar 2026](https://blog.icml.cc/2026/03/18/on-violations-of-llm-review-policies/)).
- Pangram Labs estimates **21% of ~70,000 ICLR 2026 reviews were fully AI-generated**, with over half showing some AI involvement ([Pangram, Nov 2025](https://www.pangram.com/blog/pangram-predicts-21-of-iclr-reviews-are-ai-generated)) — a vendor of AI detection, so read it with that interest in view.
- **~60% of researchers say AI *conducting* review is unacceptable**, while 57% accept it *assisting* (Nature survey, n > 5,000). That line — assist, never author — is where a product like this has to live, and it is narrow.
- Venue policy is fragmenting rather than settling: ICLR 2026 requires disclosure, CVPR 2026 bans outright, NeurIPS prohibits on confidentiality grounds while running an opt-in study of AI reviewing.

*My read, not a finding:* reviewer trust fell faster than tooling quality rose. From the outside, a tool that helps you write a better review is now hard to distinguish from one that writes the review for you. That is a positioning problem, and it is not solved by shipping a better model.

**3. Time.** I could not give this the continuous attention a product needs.

**It resumes if the opportunity and the time appear.** Until then it is open source — if the pipeline is useful to you, or you want to make it better, take it.

One irony worth recording: a randomised ICLR 2025 study in *Nature Machine Intelligence* found **27% of reviewers revised their reviews after receiving LLM feedback**. The premise worked. The trust didn't hold.

---

## What is actually interesting here

Not the product. The measurement.

Most of this repo's recent history is an evaluation effort that concluded the pipeline was being *measured* wrongly, and published the corrections:

| Finding | Where |
|---|---|
| **The shipped LLM reranker had never reranked anything.** `gpt-5-mini` is a reasoning model; reasoning consumed its entire 100-token completion budget, returning an empty body into a silent `except`. Found by arithmetic — a rerank arm reproduced its control to **17 significant figures**, which no working reranker can do | [`RERANK.md`](scripts/eval/retrieval/RERANK.md) |
| **The similarity threshold that scores every result was never calibrated.** A source comment specified the study; it was never run. At the deployed 0.55, prefilter recall was **0.202** — four in five true matches never reached the judge. Now calibrated on **n=266** hand-labelled pairs to 0.44 (recall 0.842) | [`CALIBRATION.md`](scripts/eval/ceiling/CALIBRATION.md) |
| **Only 76 of 212 human review units are addressable by any automated reviewer.** The rest need domain expertise or literature knowledge, are requests rather than defects, or are segmentation fragments. Recall against all 212 is a misleading denominator | [`CEILING.md`](scripts/eval/ceiling/CEILING.md) |
| **The PDF is parsed twice on every upload** — the same call, the first result used for one length check and discarded | [`E2E_DOUBLEPARSE.md`](scripts/eval/E2E_DOUBLEPARSE.md) |
| **Resume was dead by construction** — no checkpointer, no `thread_id`. Now proven across real process death: **SIGKILL 27/27**, resumed in a fresh interpreter, recovering **87.6%** of a run's cost | [`CHECKPOINT_RESUME.md`](scripts/eval/CHECKPOINT_RESUME.md) |
| **Cross-encoder reranking works and is unusable** — +3.2% recall@10 for **+13.3 s per query**, 481× the first stage. And the headroom is not in ranking: a *perfect* reranker over the same pool tops out at 0.2982, with dense already at 73.8% of it | [`FIRSTSTAGE.md`](scripts/eval/retrieval/FIRSTSTAGE.md) |

The house rule throughout: **every number carries its `n` and its ceiling, results are append-only and keyed by config hash, and a capability not observed firing in the logs is not a capability.** Several conclusions here were published, re-measured, and then withdrawn at their source. The retractions are left visible on purpose.

---

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

Compose uses **profiles** because the dev machine allocates Docker ~8.2 GB, and GROBID plus Docling are multi-GB emulated `linux/amd64` images. Starting everything at once OOMs.

```bash
cd infra
docker compose --profile core up -d                  # redis + local pgvector only
docker compose --profile parse up -d                 # GROBID + Docling
docker compose --profile app --profile parse up -d   # the application
```

**`--profile app` alone fails.** `celery-worker` lives in `app` and declares `depends_on: grobid`, but `grobid` is only in `parse`, and Compose does not auto-enable a dependency's profile. Always pass both. `--profile full` will not fit in 8 GB and is reference only. Details: [`infra/README-profiles.md`](infra/README-profiles.md).

## Evaluation harness

Everything under `scripts/eval/`. It is the most active part of the repo.

- `retrieval/` — retrieval eval against labelled corpora, with construction ceilings and corpus fingerprints
- `ceiling/` — the label taxonomy and the matcher calibration
- `node_eval.py`, `trace_report/` — replay a single graph node, with spans, tokens and cost
- `loadgen/` — open- and closed-loop load generation over the graph
- `ann_sweep/` — HNSW `ef_search` / `m` sweeps and planner probes
- `judge.py`, `judge_openreview.py`, `atomize_reviews.py` — scoring against gold critiques and atomized ICLR reviews
- `benchmarks.py` — regenerates the tracked benchmark board from every local measurement sink
- `ci_gate.py` — the blocking eval gate: artefact integrity plus a metric-regression check over the sinks tracked in git
- `trace_cases.py` — mines trace spans into eval case stubs, so the suite grows from real behaviour rather than imagination

```bash
make benchmarks         # regenerate BENCHMARKS.md + benchmarks.json
make benchmarks-check   # fail if the tracked board is stale against local sinks
make eval-gate          # the blocking gate, exactly as CI runs it
make trace-cases        # mine spans into scripts/eval/cases/ (append-only)
```

The gate is free, offline and credential-free by construction — everything that costs money or needs a database lives in `eval-nightly.yml` and can never block a merge. It compares a metric only against an earlier run at the *same* config identity, declares which direction is a regression rather than inferring it, and reports missing data as a skip rather than a pass. The tolerances and the evidence behind each one are in [`docs/EVAL_GUIDE.md`](docs/EVAL_GUIDE.md).

`trace_cases.py` closes the detection half of the production-trace → eval-case loop. It does not close the replay half: spans carry metadata, not prompts or state, so a case is a triage record with enough identity to find the failure again, not yet a runnable test. That limit is written into the tool, into every case it emits, and into the guide.

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

Every figure carries its `n` and its caveat. A number without both is not quotable. Full board: [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md); derivations: [`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md); the running narrative including corrections: [`docs/ENGINEERING_LOG.md`](docs/ENGINEERING_LOG.md).

| Figure | n | Caveat |
|---|---|---|
| **User-visible p50 212.82 s** — upload → parse → 18-node graph → first read | 7 complete real runs | Parsing on this host is **bimodal**: a later 4-run measurement with GROBID alone read **117.87 s**, because Docling had been OOM-killing GROBID during the first. CV 36.3%; **no p95 is computed at this `n`, and the harness refuses to.** |
| Graph stage **112.51 s p50**, 99.5% LLM wait | 7 runs | Not comparable to the older 63.75 s graph figure — that ran `stage_only` with persistence gated off, from a cached fixture. ~10% of the gap is accounted for; the rest is bounded, not explained. |
| Reviewer-panel parallelism cuts graph wall time **1.48× / 32.5%** | A/B, 20 per arm | Against an Amdahl ceiling of **52%**. The often-repeated `53s → 18s (66%)` is arithmetically unreachable, and no historical serial baseline exists. |
| **Resume recovers 87.6%** of a run's cost after the reviewer panel | 160 node replays | SIGKILL 27/27 across 9 crash depths, resumed in a fresh interpreter, 0 durable-prefix violations. LangGraph does not await its checkpoint write inline, so "last completed node" is really "last **durable** node". |
| Dense retrieval **recall@10 = 0.2200**, ceiling **0.5199**, **42% of attainable** | 338 scorable queries | Scoped to label snapshot `230c6ea9d9b7e8fd`; snapshots are never differenced. Local pgvector with PyMuPDF, not production's parsing chain. |
| Cross-encoder reranking **+3.2% recall@10** | 338 queries | For **+13.3 s per query**, 481× the first stage. Free and local, so the entire cost is latency. |
| **76 of 212** review units are defect-addressable | 212 hand-labelled | The other 136 need domain expertise or literature knowledge, are requests rather than defects, or are segmentation fragments. Recall against all 212 understates by construction. |
| Matcher calibrated **0.55 → 0.44** | 266 hand-labelled pairs | Prefilter recall 0.202 → 0.842. **No unit count from this pipeline is quotable to the integer** — the confirmation judge disagrees with *itself* at κ 0.75–0.85, so counts carry ±10% bands. |
| Cost **$0.20016** across 4 replay runs | 4 runs | **A lower bound.** The matcher bypassed spend guardrails for most of this project's history, so every cost figure here is a floor. |
| Closed-loop benchmarking understates p99 by **8.2×–9.6×** | matched-throughput open vs closed | Coordinated omission, demonstrated on this graph: closed loop c=8 reports p99 17.45 s where open loop reports 142–168 s. |

### What is not measured

Any quality delta before/after any change — unresolvable at present `n`, because `temperature` is stripped for `gpt-5.2*` models and there is no seed. Production retrieval quality. Whether the publish gate's 0.75 threshold is right. **Whether the four LLM judges inside the pipeline agree with a human** — `reviewer_judge`, `citation_judge`, `analysis_quality_judge` and `meta_reviewer` shape what a user sees, and none has ever been calibrated. User counts.

## Tests

```bash
cd services/backend && python3 -m pytest tests/ -q --ignore=tests/e2e   # 1122 passed, 2 known failures
python3 -m pytest scripts/eval -q                                       # 902 passed
```

## Documentation

- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) — the generated board, every measurement with its `n`
- [`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md) — what is measured, what is not, what each number cost to establish
- [`docs/ENGINEERING_LOG.md`](docs/ENGINEERING_LOG.md) — the running record, including corrections and retractions
- [`docs/EVAL_GUIDE.md`](docs/EVAL_GUIDE.md) — running the harness
- [`infra/README-profiles.md`](infra/README-profiles.md) — compose profiles and the memory budget
- [`AGENTS.md`](AGENTS.md) — guide for coding agents working in this repo

## Contributing

The pipeline is paused, not abandoned. Issues and PRs are welcome, particularly on the things this repo already knows are wrong: the four uncalibrated in-pipeline judges, the double parse, and the embedding model — which the retrieval work identified as the only remaining lever after depth, chunking and reranking were each measured and found near-flat.

If you change something a number depends on, re-run `make benchmarks` and commit the board.

## License

MIT.
