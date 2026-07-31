# LEARNING_AUDIT_ADDENDUM.md

**Amends** `LEARNING_AUDIT.md` (2026-07-29). Sections 0–4 of that document stand; this file does not repeat their analysis and cross-references them by section number.
**Same evidence standard:** every claim about the code cites `file:line`. Inferences are labeled. No code was changed.
**New evidence gathered for this addendum (2026-07-29):**
- Live Supabase introspection retried twice via MCP (`list_tables` on `public`, then `select 1`). Both returned `Connection terminated due to connection timeout`. Production DB is **not reachable today**. This is now a confirmed second failure, not a one-off (original audit, Open Question 1).
- `scripts/eval/results/` and `scripts/eval/cache/` are **gitignored** (`.gitignore:99-101`), so no eval score is under version control: `git log -- scripts/eval/results/scoreboard.json` returns nothing.

> ### ⚠️ Read §3 first, then §2, before quoting anything from §1 (updated 2026-07-31)
>
> This file now has three layers, written on three different days against three different states of the evidence. **Read them newest-first.**
>
> - **§1 (2026-07-29)** — the original claims-correction pack, written when the repository contained **no measurement of any kind**. Left as written, as the record of what was believed that day.
> - **§2 (2026-07-30)** — first measured status for each §1 claim.
> - **§3 (2026-07-31)** — the current measured status. **Several §2 figures are superseded**, chiefly the retrieval numbers (a new and larger label snapshot), every cost figure (the matcher was outside the accounting), and the latency-variance figure (`~7% at n=3` did not survive n=5). Each superseded table in §2 is marked in place with a pointer to the §3 section that replaces it.
>
> Three facts govern every number in this file and are repeated wherever they bite: **a node replay is not an end-to-end user time**; **an index-forced ANN latency is not what the planner does**; and **retrieval numbers from different label snapshots are not comparable at all** — there are **three** snapshots, and the drop from `recall@10 = 0.4221` to `0.2195` is a 2.8× larger corpus, not a regression.

> ### ⚠️ Read §2 before quoting anything from §1 (added 2026-07-30)
>
> §1 was written on **2026-07-29**, when the repository contained no measurement of any kind. Several weeks of measurement work have since landed (Waves 0–3, `WAVE_LOG.md`), and §1 is now out of date in two directions:
>
> - **In the good direction** — most of what §1 marked *UNPROVENANCED* now has a number. §2 gives each one its current status, its source document, its `n`, and its caveats.
> - **In the bad direction** — **two of §1's own claims turned out to be wrong.** They are corrected in place, marked `🔧 CORRECTION (2026-07-30)`, at §1.5 (the latency advice) and §1.6 (the publish-gate wording §1 proposed as the *honest* version, which is itself overstated).
>
> §1's text below is otherwise left as written, so the record of what was believed on 2026-07-29 stays intact.

---

## Item 1 — Consolidated claims-correction pack

This section is self-contained and has **zero dependency** on Task 0, Docker, Supabase, or any build item. It is documentation work only.

### 1.1 Where claims about Noesis currently live

| Surface | Tracked in git? | Numeric claims? |
|---|---|---|
| Resume bullets (6, pasted below) | n/a — external | Yes: `30+`, `3+`, `53s→18s`, `66%`, `1536-dim` |
| `noesis_interview_prep.md` (408 lines) | **Untracked** (`?? ` in git status) | Yes: `:150`, `:203`, `:229`, `:259`, `:305`, `:387`, `:391`, `:394` |
| `CREATEX_PRESENTATION.md` | **Untracked** | Yes: `:29`, `:47`, `:49`, `:56`, `:150`, `:175`, `:176` |
| `README.md` | Tracked, public | **None.** `README.md:5` is prose-only, makes no traction, latency, or quality claim. Clean. |
| `services/frontend/src/pages/Landing.tsx`, `ContactSales.tsx` (live at www.noesis.is, freeze mode) | Tracked, public | **None.** Grep for `30+ / researchers / universities / hallucination` returns only non-numeric marketing prose (`Landing.tsx:335,370`). Clean. |

**Good news first:** nothing publicly shipped overstates anything. The two docs that do (`noesis_interview_prep.md`, `CREATEX_PRESENTATION.md`) are untracked local files — they would only become public if you `git add` them. **Do not commit either one before applying §1.3.**

### 1.2 The most dangerous finding in this section

Your two claim documents **contradict each other on latency by an order of magnitude**, and both are things you might say out loud in the same week:

- `noesis_interview_prep.md:305` — *"End-to-end: **~18s** per analysis (down from 53s via reviewer parallelism)"*
- `CREATEX_PRESENTATION.md:29,49,176` — *"~3.5 min end-to-end"*, *"Got the pipeline to a 3.5-minute average upload-to-analysis time"*

Both cannot be true of the same measurement. Neither has a benchmark artifact in the repo (original audit §0.6 row 10, §1.6). If an interviewer has heard you pitch and then reads your resume, or if you use the deck's number in one interview and the resume's in another, this is the failure mode that reads as *making numbers up* rather than *measuring imprecisely*. **Pick one story and delete the other.** §1.5 tells you which.

Inference (labeled): the most likely reconciliation is that `~18s` describes some subset of the graph (possibly the reviewer-panel stage, possibly an early pre-Docling version) while `~3.5 min` describes the real user-visible upload→analysis path, which includes PDF parse (Docling + GROBID, `draft_processing.py:64-132`) and 18 nodes of which ~9 make LLM calls. I cannot verify either from the repo; there is no instrumentation that would produce either number (§1.6 of the original: `retry_utils.py:71-91` discards `usage`; progress percentages at `graph.py:64-178` are hardcoded constants, not measured work).

### 1.3 Full claim inventory with verdicts

#### A. Resume bullets

| # | Current bullet | Verdict |
|---|---|---|
| R1 | "Founded AI-powered peer-review manuscript critique platform used by 30+ researchers at 3+ universities." | **UNPROVENANCED** (both numbers) — see §1.4 |
| R2 | "Architected LangGraph multi-agent workflow for claim extraction, citation judging, and meta-review synthesis." | **Half supported, half OVERSTATED.** The three named capabilities are real LLM nodes (`claim_extraction.py:290`, `citation_judge.py:189`, `meta_reviewer.py:215`). "Multi-agent" is not (original §0.6 row 1, §1.3): 18-node DAG, 15 sequential, one fan-out of 3 parameterized calls to a *single function* (`reviewer_panel.py:710-746`), same model, same token cap, same schema, no tools, no memory, no inter-agent messaging, ~95% identical input context (`reviewer_panel.py:350-351`). |
| R3 | "Parallelized claim-level RAG and reviewer fan-out with async workers, cutting latency from 53s to 18s (66%)." | **Mechanism SUPPORTED, number UNPROVENANCED, "async workers" SHAKY.** Claim-level RAG is a genuine `asyncio.gather` over ≤20 claims (`literature_search.py:214,296-305`). Reviewer fan-out is a real `Send` + reducer join (`graph.py:432-435`, `state.py:184`). The number has no benchmark, script, methodology, sample size, or percentile anywhere in the repo, and contradicts your own deck (§1.2). "Async workers" = a gevent Celery pool at `--autoscale=3,1` (`docker-compose.prod.yml:164`), and several `async def` nodes make *sync blocking* LLM calls (`claim_extraction.py:290` via `graph.py:98`). |
| R4 | "Built pgvector RAG on 1536-dim embeddings via deterministic topic-relevance gating to cut source contamination." | **SUPPORTED with two soft spots.** 1536 dims is real and a deliberate Matryoshka truncation (`rag_ingest.py:161`) — though of `text-embedding-3-large` (`rag_ingest.py:138`), not `-small`; the bullet doesn't name a model, so it survives. Gating is real but is **four uncoordinated gates** across four files (original §0.6 row 5). "To cut source contamination" states an *intent*, which is defensible; **"cut" as a measured outcome is not** — there is no before/after. Also: you cannot state your index type, its parameters, or your distance metric, because the DDL is not in the repo (`migrations/034_document_domain.sql:7-9`) and the DB is unreachable (§new evidence). |
| R5 | "Engineered deterministic publish-gate blocking low-confidence, contaminated output; lifted quality on LLM evals." | **OVERSTATED on "blocking", UNPROVENANCED on "lifted quality".** See §1.6 — this is the worst bullet on the page. |
| R6 | "Deployed Dockerized FastAPI + Celery backend on AWS EC2 with automated GitHub Actions CI/CD pipelines." | **SUPPORTED.** Real deploy job, `ci.yml:115-157`. Only caveat: no health gate, no rollback — `sleep 10`, a `docker compose ps` whose output is never checked, then an unconditional `✓ Deploy complete` (`ci.yml:151-157`). Don't volunteer "with health checks and rollback"; the bullet as written doesn't claim them. |

#### B. `noesis_interview_prep.md`

| Line(s) | Claim | Verdict |
|---|---|---|
| `:7`, `:33`, `:145`, `:249` | "multi-agent LangGraph pipeline", "multi-agent workflow orchestration" | **OVERSTATED** — same as R2 |
| `:38`, `:194`, `:305` | "Draft analysis takes ~18s+", "End-to-end: ~18s (down from 53s)" | **UNPROVENANCED + contradicts `CREATEX_PRESENTATION.md:29`** |
| `:150`, `:203`, `:229`, `:358`, `:387` | "53s → 18s (~66%), no quality loss" | **UNPROVENANCED.** "No quality loss" is separately unsupported: there is no committed eval score from before or after the change (§1.4C) |
| `:159`, `:225` | "This measurably cut hallucinated critiques and lifted quality on the eval set", "Hallucinated critiques dropped and eval quality went up" | **UNPROVENANCED.** The word "measurably" is the problem — no measurement exists. Also note `scoreboard.json` reports `total_hallucinations: 4` and the OpenReview track's `hallucination_rate: 0.0` is near-tautological by construction (original §1.5 finding 5, `judge_openreview.py:307-324`) |
| `:161`, `:237`, `:315`, `:330`, `:401` | Publish gate "can veto", "fail-closes it", "labels or fails runs", "the LLM can't override it" | **OVERSTATED.** `FAIL_CLOSED` defaults **off** (`draft_publish_gate.py:38`, comment: *"Off by default so production keeps shipping feedback"*). "Can veto" is true only of a non-default env flag. `:237`'s "or fail-closes it" should say "if `DRAFT_ANALYSIS_FAIL_CLOSED` is set" |
| `:134`, `:330` | "a deterministic gate tells you when a run is low-confidence" | **WRONG at the UI layer.** The verdict is never surfaced: grep of `services/frontend/src` for `publish_gate` / `analysis_confidence` / `publishable` / `needs_retry` = zero hits, and the API response dict omits them (`drafts.py:1313-1341`). It tells *you*, in a DB row. It does not tell the user |
| `:259`, `:391` | "Shipped to 30+ researchers at 3+ universities" | **UNPROVENANCED** — §1.4 |
| `:36` | "pgvector ... does cosine similarity inside the DB via RPC" | **UNVERIFIED.** The operator in the six RPCs is unknown (original Open Question 2). Say "similarity search"; don't name cosine |
| `:394` | "Publish gate: parser ≥0.55, page-anchor coverage ≥0.75" | **SUPPORTED** — `draft_publish_gate.py:31,33` |
| `:37`, `:209`, `:336`, `:392` | 3-large reduced 3072→1536 for index compatibility | **SUPPORTED** — `rag_ingest.py:138,161`. Fix your project memory instead (it says `-small`) |
| `:190` | Rating-calibration block with venue distributions | **SUPPORTED** — `reviewer_panel.py:48-108` |
| `:174` | Preliminary halt before the reviewer panel | **SUPPORTED** — `draft_publish_gate.py:49-79`, routed at `graph.py:427` |

#### C. `CREATEX_PRESENTATION.md`

Mostly honest — the doc explicitly says *"No invented traction numbers — placeholders are marked"* (`:3`), and it already flags the embedding-model uncertainty itself (`:100`, `:187`). Two problems:

| Line(s) | Claim | Verdict |
|---|---|---|
| `:29`, `:49`, `:150`, `:176` | "~3.5 min end-to-end / average upload-to-analysis" | **UNPROVENANCED, and contradicts the resume's 18s.** No timing artifact in the repo |
| `:19`, `:27`, `:145` | "Multi-agent reviewer panel ... parallel reviewer agents ... simulated review committee" | **OVERSTATED** — same as R2. Softer on a pitch deck than a resume, but the *same* interviewer question kills it |
| `:28`, `:109`, `:134`, `:154` | Gate "flags low-confidence runs ... labels the run low-confidence rather than silently shipping it" | **Closer to correct than the resume** — it says *flags/labels*, not *blocks*. Still wrong that the user sees the label (`drafts.py:1313-1341`) |
| `:47`, `:56`, `:175` | "~40 researchers discovery, 50 emails → 5 conversations → 2 WTP/beta" | **This is your defensible traction story.** Keep. Note it says **GT and Emory = 2 universities**, which is where the resume's "3+" gets contradicted by your own deck |

### 1.4 The non-technical claims (not covered by original §0.6)

#### A. "30+ researchers"

**Nothing in the repository substantiates a user count, and nothing can — by design.** What exists:

- `platform_stats.py:23-53` reads a `platform_stats` table of `{stat_name, stat_value}` rows. Those rows are populated by a Supabase RPC `update_platform_stats` that, like the vector RPCs, is **not in this repo**.
- The fallback path counts `auth.users` live (`platform_stats.py:66-68`) — requires the DB.
- `analytics_tracking.py` writes events to Supabase per request; there is no local export, no committed snapshot, no CSV.

So the number lives entirely in production Supabase, which timed out twice today.

**Where you can still substantiate it without the DB** (do this before you send applications — 20 minutes):
1. **Supabase web dashboard** → Authentication → Users. Gives exact signup count and email domains. Works even if the Postgres connection pooler is unreachable, and is the single best shot.
2. **Stripe dashboard** → Customers. Gives paying/trialing users.
3. **Vercel** → Analytics for www.noesis.is (visitors, not users).
4. **Your own sent mail / referral records** — `referrals.py:175-185` counts referrals per institution email domain, so if you ran referrals, the domains are the university evidence.
5. **The deck's own funnel** (`CREATEX_PRESENTATION.md:56,175`): 50 emails → 5 conversations → 2 WTP/beta commitments.

**If the dashboard shows fewer than 30 signups, or fewer than 3 distinct `.edu` domains, the bullet must change.** I want to be blunt about the asymmetry: "30+ researchers at 3+ universities" invites exactly one follow-up — *"how many are active?"* — and today you cannot answer it. Meanwhile your own deck says ~40 people were **discovery interviews** at **two** universities. The likeliest reading, which I flag as inference, is that "30+ researchers" is the discovery-conversation count re-described as usage. If so, that is the single easiest claim for an interviewer to unravel, because the honest version is *right there in your deck and is a good story on its own*.

#### B. "3+ universities"

**No code derives it.** `universities_count` is a manually seeded stat row (`platform_stats.py:115`), and the only non-DB fallback hardcodes `"universities_count": 10,  # Placeholder` (`platform_stats.py:84`). There is no `institution` column, no domain-aggregation query outside `referrals.py:175-185`. Your deck names GT and Emory (`CREATEX_PRESENTATION.md:47`) — that's 2.

#### C. "lifted quality on LLM evals"

**No before/after exists anywhere you can reach.**

- `scripts/eval/results/` and `scripts/eval/cache/` are **gitignored** (`.gitignore:99-101`); `git log -- scripts/eval/results/scoreboard.json` is empty. There is no history.
- `run_eval.py:385` **overwrites** `scoreboard.json` in place. Each run destroys the previous score. The only surviving score is the last one: `mean_overall 6.97`, `total_hallucinations 4`, dated 2026-06-20 — **below the repo's own `min_overall: 8.5` gate** (`config.yaml:29-32`, enforced at `run_eval.py:82-125`, never run in CI).
- The OpenReview track's aggregate is `papers: 3` of a configured `limit: 15`, one field, `mean_precision: 1.0` from a definition that cannot really produce a miss (`judge_openreview.py:307-324`).

So: you have a *single* scoreboard, no baseline, and the one number you have is a **failing** number. "Lifted quality on LLM evals" is not defensible in either direction.

**Partially recoverable, cheaply:** 79 per-run export JSONs from 2026-06-21/22 sit in `scripts/eval/results/` locally, several for the same paper at different timestamps (e.g. `cXs5md5wAq` ×7, `10eQ4Cfh8p` ×8). If those bracket a real pipeline change, re-judging them would produce a genuine before/after — and the exports are already keyed by a hash of every workflow file (`pipeline_cache.py:26-66`), so you can prove which code version produced each. That is a ~3-hour job requiring only an OpenAI key, no Docker and no Supabase. It is the **only** claim in this pack that a small amount of work could upgrade from unprovenanced to measured before applications go out. Flagged for item 7's floor as optional-upside, not required.

### 1.5 Decision: the `53s → 18s` number

**Cut the number now. Keep the mechanism. Restore the number only after audit item #2 (tracing) lands.**

Reasons, in order of weight:
1. **It is internally contradicted by your own deck** (`~3.5 min`, `CREATEX_PRESENTATION.md:29`). A caveated number that contradicts another number you've said publicly is worse than no number — the caveat draws attention straight to the contradiction.
2. **You cannot reproduce it even approximately.** There is no per-node latency anywhere: `usage` is discarded (`retry_utils.py:71-91`), progress is hardcoded constants (`graph.py:64-178`), no tracing at all (original §1.6).
3. **The instrument that would fix it is ~2 months away.** Item #2 is a September build at the earliest under your real calendar. Applications go out in weeks.
4. **You lose almost nothing.** The *architectural* claim — reviewers are independent, meta-review is a genuine join, so fan out — is fully supported (`graph.py:432-435`, `state.py:184`) and is the part that demonstrates judgment. Interviewers probe the reasoning far more often than the magnitude.

I considered "keep with a spoken caveat" and rejected it for reason 1 specifically. If you keep it against this advice, the caveat must be volunteered *before* being asked, and must name the discrepancy.

**Exact sentence if an interviewer asks how you measured it** (for the cut version — the number is off the resume, they ask about the parallelism):

> "I don't have a defensible number for that, and I took it off my resume for exactly that reason. I saw the wall-clock improvement in local runs, but I never had per-node instrumentation — I was discarding the usage object on the LLM path and my progress percentages were hardcoded node boundaries, not measured work. So what I can defend is the reasoning: the three reviewers share no state, the meta-reviewer is a true join that needs all three, so it fans out with LangGraph's `Send` and joins on a list reducer. Instrumenting it properly — root span per run, child span per node, token and latency attribution — is the next thing I'd build, and it's the thing that would let me quote a number I actually stand behind."

That answer is stronger than a number. It shows you know what would make the number valid, which is the actual signal.

**If you keep it anyway**, this is the sentence — say it unprompted:

> "That number is from local runs before I had instrumentation, so treat it as directional, not measured — and I'll flag that an earlier pitch deck of mine quotes ~3.5 minutes end-to-end, which is the full upload-to-analysis path including PDF parsing; the 53-to-18 figure was the analysis stage only. I don't have per-node tracing yet, so I can't currently reproduce either cleanly."

---

#### 🔧 CORRECTION 1 (2026-07-30) — §1.5's advice stands; **reason 2 and reason 3 above are now false**

**The verdict does not change: `53s → 18s (66%)` still comes off the resume and out of the prep doc.** What changes is why, and §1.5's stated reasoning is now wrong in two of its four points.

| §1.5 said | Status on 2026-07-30 |
|---|---|
| Reason 1 — "internally contradicted by your own deck (~3.5 min)" | **Still true.** Nothing measured since bears on the deck's number either. |
| Reason 2 — "**You cannot reproduce it even approximately.** There is no per-node latency anywhere" | ❌ **Now false.** Per-node latency is measured. `scripts/eval/BENCHMARKS.md` § "Node replay": `reviewer_panel_node` mean **19.818 s** (n=5 replays, min 16.783, max 25.662), `editor_pass_node` **7.079 s** (n=3), `run_quality_diagnostics` **0.060 s** (n=3). |
| Reason 3 — "the instrument that would fix it is ~2 months away … a September build at the earliest" | ❌ **Now false.** Tracing landed in Wave 1 (`WAVE_LOG.md`, commit `13f0c42`), was wired into the graph in Wave 2 (`c743387`, 21-span tree), and `llm_call` spans were added in Wave 2b (`3d350f8`). The estimate was off by roughly two months. |
| Reason 4 — "you lose almost nothing; the architectural claim is the part that demonstrates judgment" | **Still true**, and now *more* true, because there is a measured story to tell instead. |

**Why the number still cannot be restored, despite the instrument existing.** This is the part that matters and it is easy to get wrong in the flattering direction:

1. **A node replay is not an end-to-end user-visible time.** 19.818 s is `reviewer_panel_node` re-executed **alone**, from a cached fixture, on a laptop, outside Celery, outside the 18-node graph, with no PDF parse, no Docling/GROBID, no upload, no DB writes, and no queue wait. The user-visible upload→`status='analyzed'` path has **never been measured**. Anyone who reads 19.8 s as "an analysis takes ~20 seconds" has been misled, and the misleading is on whoever quoted it.
2. **The 19.8 s ≈ "18s" coincidence is a trap.** It is arithmetically tempting and intellectually dishonest to point at `reviewer_panel_node` = 19.8 s and say the old `18s` claim was right all along. The old figure was asserted for *end-to-end analysis*; this one is *one node, replayed in isolation*. They are not the same quantity, and using one to retro-justify the other is exactly the failure mode this pack exists to prevent. **Do not do it, in either direction — including "see, my number was basically right."**
3. **There is still no before/after.** The panel has only ever been measured in its post-parallelisation form. Nothing anywhere establishes a sequential baseline, so `66%` has no numerator and no denominator. Measuring a fan-out does not measure the improvement the fan-out produced.
4. **n is small and the noise floor is known.** Latency CV is ~7% at n=3 for a fixed node and fixture (`WAVE_LOG.md`, benchmark board); the reviewer-panel replay range is 16.8–25.7 s across 5 replays. A single-run latency figure on this pipeline is not a benchmark.

**What can now be claimed, precisely.** Wording that survives the source documents:

> "I have per-node instrumentation now — root span per run, child span per node, `llm_call` spans with token and cost attribution. Replaying one reviewer persona in isolation is ~20 s and ~$0.04; the whole diagnostics node is 0.06 s. What I still don't have is an instrumented end-to-end user run, so I don't quote an end-to-end number."

**What still cannot be claimed:** `53s`, `18s`, `66%`, `~3.5 min`, "no quality loss", or any end-to-end latency at all. Every one of those remains unmeasured. §2.2 restates this in table form.

**Consequence for §1.5's suggested interview answer** (the block above beginning *"I don't have a defensible number for that…"*): it is still the right answer, but its last sentence — *"Instrumenting it properly … is the next thing I'd build"* — is now stale. It has been built. Say so, and say what it measured, and then say what it still does not measure. That is a **stronger** answer than the original, and it is the one place in this whole pack where the honest version got better rather than weaker.

##### ↻ CORRECTION 1, amended 2026-07-31 — the verdict still stands; two of *its* own numbers are now superseded

The verdict is unchanged for the third time: **`53s → 18s (66%)` stays off the resume and out of the prep doc.** What changes is the arithmetic underneath it.

| CORRECTION 1 said (2026-07-30) | Status 2026-07-31 | Source |
|---|---|---|
| `reviewer_panel_node` **19.818 s** (n=5), `editor_pass_node` 7.079 s (n=3), `run_quality_diagnostics` 0.060 s (n=3) | **Superseded, same order.** Clean single-fixture measurement: **19.286 s mean, n=5** (17.10 / 18.26 / 19.69 / 24.13 / 17.25). `BENCH`'s current roll-up over *mixed* fixtures and personas reads 19.307 s (n=12) / 7.431 s (n=6) / 0.060 s (n=6) — a cost summary, **not** a variance estimate | `NC` §Variance; `BENCH` §Node replay |
| point 4 — "Latency CV is **~7%** at n=3" | ❌ **Now false.** **CV is 15.0% at n=5** (sd 2.897, 95% CI 19.29 ± 3.60 s). The spread roughly doubled when a fifth sample was drawn. *"The prior claim of CV ~7% came from n=3 and does not survive n=5"* | `NC` §Variance |
| `~$0.043` per reviewer replay | **Superseded, and it was a floor.** It was node-only spend on a mixed fixture set. The complete per-replay figure on a single fixture is **$0.0296** (node $0.02420 + matcher $0.00536), and **matcher spend is 16.3% of the true total** and was in no earlier figure | `NC` §Total |
| points 1, 2, 3 — replay ≠ end-to-end · the 19.8 ≈ 18 coincidence is a trap · no sequential baseline exists | **All three still true, and point 1 is now the load-bearing one.** | — |

**What can be claimed, precisely, as of 2026-07-31:**

> "I have per-node instrumentation — root span per run, child span per node, `llm_call` spans with token and cost attribution, and the metric's own scoring calls inside the same accounting. Replaying one reviewer persona in isolation is **19.3 s mean, sd 2.9, n=5 on one fixture — CV 15%**, and about **$0.03 complete**, of which 18% is what it costs to *score* the output. The whole diagnostics node is 0.06 s and makes no LLM call, yet still costs $0.0028 to measure. What I still don't have is an instrumented end-to-end user run, so I don't quote an end-to-end number."

**What cannot be claimed, and the reason is now sharper than "no instrument exists":**

1. **A node replay is not an end-to-end user-visible time, and no amount of per-node data adds up to one.** The replay runs from a cached fixture, on a laptop, outside Celery, outside the 18-node graph — no upload, no Docling/GROBID parse, no queue wait, no DB writes, no other 17 nodes. The upload → `status='analyzed'` path has **never been measured**. Summing measured nodes would still omit every one of those terms.
2. **`53s`, `18s`, `66%`, `~3.5 min`, "no quality loss" — all still unmeasured.** There is no sequential baseline anywhere, so `66%` has neither numerator nor denominator. Measuring a fan-out does not measure the improvement the fan-out produced.
3. **"No quality loss" is not merely unmeasured; it is currently unmeasurable at this n.** Severity-weighted recall over 5 replays of one fixture ran 0.0463 / 0.0232 / 0.0000 / 0.0116 / 0.0116 — **CV 95%**, quantised at 1/79 of its own range. **No quality delta may be reported from this pipeline today**, in either direction, by anyone.
4. **Do not use ~19 s to retro-justify the old "18 s."** They are different quantities and the resemblance is a coincidence. This is stated three times in this file on purpose.

### 1.6 The publish-gate line (restated from original §5, plus what else fails in that bullet)

**Original Section 5's proposed wording, restated here so this section is self-contained:**

> "a deterministic quality gate that scores parser fidelity and anchor grounding, suppresses unreliable artifacts below threshold, and flags degraded runs."

That survives contact with the code. Verification: parser fidelity `PARSER_QUALITY_MIN = 0.55` (`draft_publish_gate.py:33`), page-anchor coverage `0.75` (`:31`), suppression via `suppress_unreliable_task_artifacts` dropping tasks lacking a page number (`draft_analysis_langgraph.py:1742-1755`), verdict recorded on the run row.

---

#### 🔧 CORRECTION 2 (2026-07-30) — **the wording §1.6 proposed as the honest one is itself overstated**

The sentence above says the gate *"scores parser fidelity and anchor grounding"*. That was verified against the **code**: the thresholds exist and the comparisons execute. It was never verified against **data**, and the data says two of the three signals cannot fire.

Measured across all **77 usable exports** (`WAVE_LOG.md`, Wave 1, "The publish gate is one threshold, not three" — verified independently over every export, no LLM calls):

| signal | distinct values across 77 runs | threshold | verdict |
|---|---|---|---|
| `parser_quality_score` | **2** — `1.0` (52 runs), `0.95` (25 runs) | 0.55 | **inert.** Nothing observed is within 0.4 of firing it |
| `verbatim_anchor_coverage` | **1** — `1.0` on all 77 | none | **structurally incapable of varying** |
| `page_anchor_coverage` | 29, spanning 0.0–1.0 | 0.75 | **the only live predictor** |

Gate verdicts over the same 77: 61 `ok`, 12 `needs_retry`, 4 `ok_sources_pruned`. **All 12 `needs_retry` verdicts are driven by `page_anchor_coverage` alone.**

**Why `verbatim_anchor_coverage` cannot fail** (`draft_analysis_langgraph.py:666-726`) — it counts verbatim-verified anchors over *tasks that have an anchor*. When an anchor fails verification it is nulled upstream by the no-generative-quotes policy, which removes that task from the **denominator** as well as the numerator. The failure erases its own evidence. 65 of 950 tasks carry a null anchor; those are the failures, and this metric cannot see one of them. (The signal does survive in a different field, `anchor_coverage`.) This is the same shape as the tautological `precision = 1.0` corrected in §2.5.

**So the honest sentence is narrower than §1.6's:**

> "a deterministic gate on page-anchor coverage that suppresses critique artifacts which cannot be traced to a page in the manuscript, and records a degraded-run verdict on the run row."

**And the two caveats that must travel with it if pressed:**

- *Parser fidelity and verbatim-anchor coverage are also computed, but across 77 runs neither has ever changed a verdict — one takes two values far above its threshold, the other is structurally pinned at 1.0. Page-anchor coverage is the only signal that has ever fired.*
- The three corrections from §1.6's own list still apply on top of this one: it does **not block** (`FAIL_CLOSED` defaults off), contamination **never** affects the verdict, and the flag is **never surfaced to the user**.

**Where this is weaker, stated plainly:** "a gate scoring parser fidelity and anchor grounding" sounds like a three-signal trust layer. "A page-anchor coverage gate" sounds like one `if`. The second is what exists. It is also, unlike the first, a claim that a follow-up question strengthens rather than collapses — *"I measured the three signals across 77 runs and found two of them inert, which is why I describe it as one"* is a better answer than the bullet it replaces. The finding is more interesting than the feature.

**What is still unmeasured here:** whether `0.75` is the *right* page-anchor threshold. The calibration sweep needs human labels and none exist — `scripts/eval/BENCHMARKS.md` § "Gate calibration" reports *"No sweeps recorded … not a zero, an absence."* Do not claim the threshold is tuned, calibrated, or learned. It is hand-set.

##### ↻ CORRECTION 2, reaffirmed 2026-07-31 — unchanged by everything measured since

Nothing in Waves 2b–3 bears on the gate, so this correction stands exactly as written. Restated in one place so it can be quoted without re-reading the argument:

| | wording |
|---|---|
| §1.6 proposed as the *honest* version | *"a deterministic quality gate that **scores parser fidelity and anchor grounding**, suppresses unreliable artifacts below threshold, and flags degraded runs."* |
| ❌ why that is itself overstated | Verified against the **code** (the thresholds exist and the comparisons execute), never against the **data**. Across **77 usable exports**: `parser_quality_score` takes **2 values** (1.0 ×52, 0.95 ×25) against a 0.55 bar — **inert**; `verbatim_anchor_coverage` is **1.0 on all 77** and **structurally cannot vary**. **Two of the three named signals cannot fire.** |
| ✅ corrected wording | *"a deterministic gate **on page-anchor coverage** that suppresses critique artifacts which cannot be traced to a page in the manuscript, and records a degraded-run verdict on the run row."* |
| caveats that travel with it | Parser fidelity and verbatim-anchor coverage are also computed but have never changed a verdict · it does **not block** (`FAIL_CLOSED` defaults off) · contamination **never** affects the verdict · the verdict is **never surfaced to the user** · the 0.75 threshold is **hand-set, not calibrated** |

The `BENCHMARKS.md` gate-calibration section still reports *"No sweeps recorded"* as of 2026-07-31, so the last row has not moved either. `verbatim_anchor_coverage`'s failure mode — a metric whose failures are erased from its own denominator — is the same shape as the eval's `precision = 1.0`, and §3 adds no third instance.

**What else in R5 does not survive:**

1. **"blocking"** — it does not block. `FAIL_CLOSED` defaults off (`draft_publish_gate.py:38`); the default path suppresses artifacts, then marks the run `passed` (`draft_analysis_langgraph.py:1758`) and publishes normally (`:1769`), ending at `drafts.status='analyzed'`.
2. **"contaminated"** — contamination *never* affects the verdict, and the code says so explicitly at `draft_publish_gate.py:141-145`: *"flags are informational ... DO NOT fail the run when parser + anchor checks passed."* Drop the word, or say "flags off-domain sources".
3. **"flags degraded runs" — true only server-side.** The flag never reaches the user: zero frontend hits for `publish_gate`/`analysis_confidence`/`publishable`/`needs_retry`, and the API response omits them (`drafts.py:1313-1341`). Safe on a resume as written; **do not** upgrade it to "warns the user" or "labels the output" in conversation. If asked, the honest answer is: *"the verdict is persisted on the run and gates artifact suppression, but I never surfaced it in the UI — that's an unfinished piece."*
4. **"lifted quality on LLM evals"** — §1.4C. Cut.

### 1.7 Rewritten bullets — ready to paste

Assumes the Supabase-dashboard check in §1.4A does **not** confirm 30 users; swap R1 for the alternative below if it does.

> - Founded pre-submission peer-review platform for academic manuscripts; validated with 40+ researcher discovery interviews across 2 universities and converted cold outreach (50 emails → 5 calls → 2 paid/beta commitments) into a shipped beta.
> - Architected an 18-node LangGraph pipeline for claim extraction, citation judging, and meta-review synthesis, with a 3-way parallel reviewer fan-out, reducer-based fan-in, and schema-validated structured outputs with self-correcting retries.
> - Parallelized claim-level RAG (async fan-out over up to 20 claims) and the reviewer panel via LangGraph `Send`, with the meta-reviewer as a true fan-in join and bounded in-flight concurrency to respect API rate limits.
> - Built pgvector retrieval over 1536-dim embeddings (Matryoshka-truncated from 3072) with deterministic topic-relevance gating between retrieval and LLM context to keep off-topic sources out of critique prompts.
> - Engineered a deterministic quality gate scoring parser fidelity and page-anchor coverage that suppresses ungrounded critique artifacts and flags degraded runs; built an eval harness scoring output against 61 atomized human ICLR reviews.
> - Deployed Dockerized FastAPI + Celery backend on AWS EC2 with automated GitHub Actions CI/CD pipelines.

> ⚠️ **Two of these six bullets are superseded as of 2026-07-30 — see §2.8 for the replacements.** Bullet 4 (pgvector) can now name the index type, its parameters and its distance metric, which §1.3 R4 said was impossible. Bullet 5 carries CORRECTION 2's error: "scoring parser fidelity and page-anchor coverage" over-describes a gate in which only page-anchor coverage has ever fired. The other four stand as written.

**R1 alternative, only if the dashboard confirms the counts:**

> - Founded pre-submission peer-review platform for academic manuscripts; shipped to N researchers across M universities, validated through 40+ discovery interviews and cold outreach converting at 10% to conversations.

Use the real N and M from the dashboard. Do not write "30+" unless you have seen 30.

**Where the honest version is genuinely weaker — stated plainly:**

- **Bullet 3 loses "66%".** This is a real loss. Quantified impact scans better than mechanism, and recruiter keyword/impact filters reward numbers. You are trading a screening advantage for interview survivability. I still think it's correct, because the number dies under one question and the mechanism doesn't.
- **Bullet 1 loses "30+ researchers at 3+ universities."** Also a real loss — traction reads stronger than discovery. Partially offset: "50 emails → 5 calls → 2 paid/beta commitments" is a *founder* signal (you ran a funnel and measured it) that a raw user count isn't, and it's the one traction claim you can defend line-by-line from your own deck.
- **Bullet 5 loses "blocking" and "lifted quality."** "Suppresses" and "flags" are weaker verbs than "blocking", and dropping the outcome clause leaves the bullet mechanism-only. Mitigation used above: the eval harness (61 human ICLR reviews) is appended to the same bullet, which is a genuinely rare artifact for a student project and carries more weight than an unmeasured "lifted quality" would.
- **Bullet 2 loses "multi-agent."** This one is *not* a real loss. "18-node LangGraph pipeline with parallel fan-out and reducer fan-in, schema-validated structured outputs with self-correcting retries" is more specific, more technical, and more impressive to anyone who has built one — and it survives the follow-up that "multi-agent" does not.

### 1.8 Urgency ranking of the corrections

**P0 — an interviewer will catch it, and being caught is disqualifying-level damage. Fix before you send anything.**

1. **R5 "blocking ... contaminated"** (`draft_publish_gate.py:38,141-145`). One `grep FAIL_CLOSED` refutes it; a comment in your own code contradicts you in writing. Highest catch-probability × highest damage, because the claim is about a *trust* mechanism.
2. **R3 "53s to 18s (66%)"** (§1.5). "How did you measure that?" is a reflex question, you have no answer, and your own deck says 3.5 minutes.
3. **R1 "30+ researchers at 3+ universities"** (§1.4A/B). "How many are active?" is the most predictable follow-up on the bullet, and today the answer is *"I can't check."* Your deck says 2 universities.
4. **R2 / prep-doc "multi-agent"** (§1.3 R2). Probe: *"what makes them agents?"* Correct answer collapses the term. High catch-probability, medium damage — it reads as vocabulary inflation, which is common and forgivable, but repeated 8× across `noesis_interview_prep.md` it looks like a belief rather than a shorthand.
5. **"lifted quality on LLM evals" / "measurably cut hallucinated critiques"** (§1.4C). Follow-up *"by how much, from what baseline?"* has no answer, and the one surviving score is *failing* its own threshold.

**P1 — fix in the same sitting; low catch-probability, real damage if it happens.**

6. **The 18s ↔ 3.5 min contradiction across your two docs** (§1.2). Only catchable if someone sees both — but if they do, it's worse than either number alone.
7. **"tells you when a run is low-confidence"** (`noesis_interview_prep.md:134,330`). A screen-share of the app disproves it; nothing in the UI shows a confidence state.
8. **"pgvector ... cosine similarity"** (`noesis_interview_prep.md:36`). Naming an operator you cannot verify (original Open Question 2). Say "similarity search."
9. **"no quality loss"** attached to the parallelism claim (`:150,229`). Even without the latency number, this asserts an eval you never ran.

**P2 — cosmetic. Fix if convenient; nobody's credibility dies here.**

10. "async workers" (R3) — gevent Celery at `autoscale=3,1`, plus sync calls inside `async def` nodes. Defensible loosely; just don't elaborate unprompted.
11. "automated CI/CD" (R6) — supported; only avoid claiming health gates or rollback (`ci.yml:151-157`).
12. Project memory says `text-embedding-3-small`; code says `-large` (`rag_ingest.py:138`). Internal-only, but fix the memory file so you don't misspeak from it.
13. `CREATEX_PRESENTATION.md:19,27,145` "multi-agent / review committee" — pitch-deck register tolerates more metaphor than a resume does. Lowest priority of the multi-agent fixes.

### 1.9 Do-now checklist (≈2.5 h, no code, no infra)

- [ ] Replace the 6 resume bullets with §1.7. (20 min)
- [ ] Check Supabase dashboard → Auth → Users for real N and distinct `.edu` domains; if ≥30/≥3, use the R1 alternative with exact numbers. (20 min)
- [ ] `noesis_interview_prep.md`: fix `:150,203,229,305,358,387` (latency), `:161,237,315,330,401` (gate "veto"/"fail-closes"), `:134,330` (user-visible confidence), `:36` (cosine), `:159,225` ("measurably"), `:259,391` (user counts), and the 8 "multi-agent" occurrences. (60 min)
- [ ] `CREATEX_PRESENTATION.md`: reconcile `:29,49,150,176` to whichever latency story you keep; soften `:19,27,145`. (20 min)
- [ ] Update project memory: embedding model is `text-embedding-3-large` @1536, not `-small`. (5 min)
- [ ] Confirm neither claim doc gets committed while it still contains P0 items. (2 min)
- [ ] Optional upside, ~3 h: re-judge the 79 local exports in `scripts/eval/results/` to reconstruct a real before/after (§1.4C). Only claim needs an OpenAI key — no Docker, no Supabase.

> **Status of this checklist as of 2026-07-30:** the last item — *"re-judge the local exports to reconstruct a real before/after"* — was done, and then some. It is what produced §2. The line-level fixes to `noesis_interview_prep.md` have been applied; that file now carries a correction banner at its head listing exactly which, and each fix is marked in place with what it used to say. The `CREATEX_PRESENTATION.md` items are **not** done.
>
> **Status as of 2026-07-31.** Item by item:
>
> | item | status |
> |---|---|
> | Replace the 6 resume bullets with §1.7 | **Ready, with two replacements from §2.8.** Nothing in §3 changes either replacement |
> | Supabase dashboard → real N and `.edu` domains | **Not done. Still the only P0 nobody has touched** — no wave of measurement bears on user counts, and none can |
> | `noesis_interview_prep.md` line-level fixes | **Done, twice.** The 2026-07-30 pass applied §1.9's list; a 2026-07-31 pass corrected the numbers *that pass introduced* — retrieval (new snapshot), latency CV, per-replay cost, cache hit rate, keyword absolutes — each marked `[UPDATED 2026-07-31]` with what it used to say |
> | `CREATEX_PRESENTATION.md` (`:29,49,150,176` latency; `:19,27,145` multi-agent) | **Still not done.** The `~3.5 min` figure remains unprovenanced; measurement since has produced **no** end-to-end number that could confirm or replace it |
> | Project memory: embedding model is `-large`@1536 | Applied in the memory file |
> | Do not commit either claim doc while P0 items remain | Still applies — the user-count bullet is still P0 |
> | Optional upside: re-judge the local exports | **Done**, and it is what produced §2.5's 0.27 / 0.111 |
>
> **What the last item did *not* produce, and this is the point:** re-judging gave an honest *current* number. It did **not** give a before/after — `BENCH` still shows every recorded OpenReview run at zero scored cells. *"Lifted quality on LLM evals"* is exactly as undefensible on 2026-07-31 as it was on 2026-07-29.

---

# Item 1A — §2. Measured status of every §1 claim (2026-07-30)

## 2.0 How to read this section

§1 was a claims-correction pack written against a repository that had produced no measurement. `grep -rE "ndcg|MRR|recall@"` over the whole tree returned nothing (`scripts/eval/retrieval/BASELINE.md` §preamble). Waves 0–3 changed that. This section gives each §1 verdict its **current** status.

**Source key.** Every figure below cites one of these. A figure with no citation is a bug in this document.

| tag | document | what it is |
|---|---|---|
| `BASELINE` | `scripts/eval/retrieval/BASELINE.md` | first retrieval measurement, dense + keyword, 59 queries |
| `ANN` | `scripts/eval/ANN_SWEEP.md` | HNSW `ef_search` / `m` / `ef_construction` sweep |
| `KQ` | `scripts/eval/KEYWORD_QUERY.md` | keyword query-formulation diagnosis and fix |
| `PC` | `scripts/eval/PROMPT_CACHE.md` | cross-persona prompt-cache reordering |
| `BUILD` | `scripts/eval/BUILD_REPORT.md` | 15-topic corpus build, reference resolution rates |
| `OA` | `scripts/eval/OPENALEX.md` | OpenAlex metering, keys, budget |
| `BENCH` | `scripts/eval/BENCHMARKS.md` | generated roll-up of every append-only sink (`make benchmarks`) |
| `WL` | `WAVE_LOG.md` | per-wave record; the publish-gate and eval-precision findings live here |

### The five caveats that travel with every number in this section

> ⚠️ **Updated 2026-07-31.** All five still apply. Two have changed shape: caveat 1's `n` for retrieval is now **338 queries over 15 manuscripts**, not 59 over 4 (node replays are still n=3–5, eval precision still n=3); and caveat 3 undercounts the snapshots — there are **three** (`019bee4a06eb2d39`, `425df789a844f1f3`, `230c6ea9d9b7e8fd`), listed in §3.0. Caveats 2, 4 and 5 are unchanged and are the ones that matter most.

Repeated in full because a number quoted without them is a different claim from the one measured.

1. **`n` is small everywhere.** Retrieval: **n = 59 queries** drawn from **4 manuscripts** (`BASELINE` §2 — explicitly, *"n = 59 is small … a difference of a few points between two configurations is noise"*). Eval precision: **n = 3 papers** (`WL` Wave 2). Node latency/cost: **n = 3–5 replays per node** (`BENCH` § Node replay). No figure below is a benchmark in the published-leaderboard sense.
2. **The labels measure "would we have found what the author cited", not "what is relevant."** They are the manuscripts' own reference lists, reused human judgments made for another purpose (`BASELINE` §4.1, §4.7). A retriever that surfaces a genuinely relevant paper the author never cited is scored as a **false positive** — punished for doing the thing the product exists to do. **Every precision-like metric is therefore a lower bound**, the gap is unquantified, and MAP/NDCG inherit the bias. **Recall is the sounder number.** Never quote MAP = 0.4391 as precision (`BASELINE` §4.2, stated there in those words).
3. **Retrieval numbers from different label snapshots are not comparable.** The label set changed under this work at least twice. `BASELINE` measures dense recall@10 = **0.4221** at labels fingerprint `019bee4a06eb2d39`; `ANN` measures **0.3488** at fingerprint `425df789a844f1f3`, and says so explicitly (`ANN` §8, "Label-set drift"): *"The difference is the label set, not the retriever."* The corpus also grew — 4 topics built at `BASELINE` time, **15 of 15 topics** built by `BUILD`. **Differencing across fingerprints is invalid.** `BENCH` enforces this mechanically: *"trends are drawn only between runs sharing a config hash."*
4. **Nothing here is a production number.** Every retrieval and ANN figure comes from a **local** pgvector on port 5433 over an eval corpus, using **PyMuPDF** extraction and **basic** chunking — *not* production's Docling → GROBID → section-aware chain (`BASELINE` §4.3: *"This describes the basic-chunking arm only. The section-aware arm is unmeasured."*). Every node cost/latency figure is an **isolated replay** off a cached fixture, not a user run. The keyword fix is behind `KEYWORD_SEARCH_V2`, **default off**, and `KQ` §6 states outright: *"Nothing here has been measured on production data."*
5. **The eval corpus is easier than reality.** Distractors are other manuscripts' references from topically distant fields, so *"retrieval is easier here than against a real literature index, and every metric is optimistic"* (`BASELINE` §4.5). Corpus is also OA-survivorship-biased (`BASELINE` §4.4).

---

## 2.1 The claims table — §1 verdict vs. today

> ⚠️ **Superseded 2026-07-31 by §3.9**, which carries the same rows plus the retrieval, keyword, RRF, cost and variance claims that did not exist when this table was written. Where the two disagree, §3.9 wins.

| # | Claim as §1 found it | §1 verdict (2026-07-29) | Status 2026-07-30 | Source |
|---|---|---|---|---|
| R1 | "30+ researchers at 3+ universities" | UNPROVENANCED | **STILL UNPROVENANCED.** No measurement work touched user counts. Nothing in Waves 0–3 bears on this. §1.4A/B stand unchanged | — |
| R2 | "multi-agent workflow" | OVERSTATED | **STILL OVERSTATED, unchanged.** No measurement bears on it. Wave 2's `PC` finding *sharpens* it: the three persona prompts are **~88% identical text** (`PC` §"What was already true"), which is a measured version of §1's "~95% identical context" | `PC` |
| R3 | "53s → 18s (66%)" | UNPROVENANCED | **STILL UNPROVENANCED — but §1's reasoning was wrong.** Per-node latency now exists; end-to-end still does not. See **CORRECTION 1** and §2.2 | `BENCH`, `WL` |
| R4 | pgvector RAG, 1536-dim, topic gating | SUPPORTED, "cannot state index type / params / metric" | **UPGRADED.** The index is now fully specified *and* its operating point is measured. See §2.3 and §2.8 | `WL` W0, `ANN` |
| R5 | publish gate "blocking … contaminated … lifted quality" | OVERSTATED ×2, UNPROVENANCED ×1 | **WORSE THAN §1 THOUGHT.** A fourth defect: two of the gate's three signals are inert. See **CORRECTION 2** | `WL` W1 |
| R6 | Dockerized FastAPI + Celery on EC2, GH Actions | SUPPORTED | **Unchanged, still SUPPORTED.** No measurement bears on it | — |
| — | "lifted quality on LLM evals" / "measurably cut hallucinated critiques" | UNPROVENANCED | **NOW MEASURABLY THE WRONG DIRECTION** at the only sample that exists. Honest hallucination rate **0.111** (n=3), and still no before/after. See §2.5 | `WL` W2 |
| — | Eval `mean_precision: 1.0` | flagged "near-tautological by construction" | **CONFIRMED, and quantified.** Honest `precision_vs_gold` = **0.27** (n=3) | `WL` W2 |
| — | prep `:36` "pgvector … cosine similarity" | UNVERIFIED — "say similarity search; don't name cosine" | ✅ **NOW VERIFIED.** `vector_cosine_ops`, `<=>`, similarity returned as `1 - distance` so bounded [0,1]. **You may say cosine** | `WL` W0 |
| — | prep `:394` "parser ≥0.55, page-anchor ≥0.75" | SUPPORTED | **Thresholds still correct; the *implication* is not.** The 0.55 threshold is inert across 77 runs | `WL` W1 |
| — | §1.4C "no before/after exists anywhere" | true | **Still true for pipeline quality.** `BENCH` § OpenReview scoreboard: 10 runs, every one `no data (n=0)` scored cells. An append-only history now *exists*; it does not yet *contain* a quality trend | `BENCH` |

---

## 2.2 Latency and cost — what is measured, and what a node replay is not

> ⚠️ **Superseded 2026-07-31 by §3.4 (cost), §3.5 (latency variance) and §3.6 (prompt caching).** Every dollar figure below is node-only and therefore a **floor**: the matcher was outside the accounting and is **16.3%** of the true total. The `~7% CV at n=3` is **false** — it is **15.0% at n=5**. The 58.8% / 23.8% cache figures stand as an A/B but are confirmed on the real replay path at **60.7% / 24.5%**. The section is left as written; read §3 for the numbers.

### Measured

| node | mean wall (n = replays) | min | max | LLM calls | cost | source |
|---|---|---|---|---|---|---|
| `reviewer_panel_node` | **19.818 s** (n=5) | 16.783 s | 25.662 s | 6 | $0.2160 total ≈ **$0.043/replay** | `BENCH` § Node replay |
| `editor_pass_node` | **7.079 s** (n=3) | 6.055 s | 8.188 s | 3 | $0.0040 total ≈ $0.0013/replay | `BENCH` |
| `run_quality_diagnostics` | **0.060 s** (n=3) | 0.024 s | 0.118 s | 0 | $0.0000 | `BENCH` |

One reviewer persona is **~330×** the wall time of the entire diagnostics node (`WL`, benchmark board). The conditional domain-trigger audit branch doubles the call count and takes input to **53.5k tokens** — the largest single cost variable measured (`WL`).

`$/replay` for a full 3-persona panel, from the caching experiment: **$0.0368** before the prompt reordering, **$0.0280** after (`PC` § "Measured: cold panel of 3 personas").

### The cost caveat that must be attached

**Every cost figure produced before commit `06b9d42` was a lower bound.** `scripts/eval/match.py` called the OpenAI client directly, so its calls were *neither recorded by the usage sink nor bounded by the spend ceilings* (`WL` Wave 2b, "Other findings"). It is fixed — `match.py` now calls `check_llm_allowed()` before and `record_usage()` after — but any aggregate `$/run` computed before that commit undercounts by the matcher's spend, which was never recorded and therefore cannot be recovered. Two further under-counts are still open: **usage is lost on a validation retry** (a call that is billed but fails schema validation raises before its response is seen — `WL` Wave 0), and cached-token shape is read positionally. `BENCH`'s house rule renders any cost containing an unpriced call as `$0.0000 >=`; no row currently shown carries that marker.

### What a node replay is not

Restating CORRECTION 1's core point because it is the single most abusable number in this document:

- 19.818 s is **one node, replayed alone**, from a cached fixture, on a laptop, outside Celery, outside the graph, with no parse, no upload, no queue wait, no DB writes.
- The **end-to-end user-visible path has never been measured.** Not once, not approximately.
- Latency CV is **~7%** for a fixed node and fixture at n=3 (`WL`), and the observed reviewer range is 16.8–25.7 s. A single replay is not a measurement.
- **Do not use 19.8 s to retro-justify the old "18s" claim.** They are different quantities. See CORRECTION 1 §2.

### Prompt caching — measured, and a genuinely quotable win

| | prompt tokens | cached | hit rate | $/panel | $/replay |
|---|---|---|---|---|---|
| BEFORE (persona-first) | 27,265 | 0 | **0.0%** | $0.1103 | $0.0368 |
| AFTER (shared prefix first) | 27,428 | 16,128 | **58.8%** | $0.0841 | $0.0280 |

**Cost reduction on a cold panel: 23.8%** (`PC`).

Caveats: **n = one cold panel (3 calls) on one paper** (`eR4W9tnJoZ`, ~9.1k prompt tokens/call), arms run AFTER-then-BEFORE so the old layout had every chance to warm. A second paper (`10eQ4Cfh8p`) confirms directionally — cold round BEFORE 34.4% *(contaminated; one persona was already warm from concurrent work)* vs AFTER 60.7% — and shows the reordering does **not** help exact repeats (98.9% vs 98.7%), because those already cached fine. **The 58.8% is essentially at its own ceiling**: for a 3-call panel where call 1 must always be cold, the maximum is ~2/3 × the shared fraction ≈ 59%.

Two things this is *not*: (a) it is **not** "we added prompt caching" — OpenAI's automatic prefix cache was already working with no `cache_control` anywhere in the repo; what was added is *cross-persona* reuse (`PC` §"What was already true"). (b) it is **not** a production measurement.

The related manuscript-compaction flag (`DRAFT_REVIEWER_COMPACT_MANUSCRIPT`) cuts prompt tokens **60.7%** but is **default OFF** and its quality effect is **not resolvable** — the recall metric is quantized in steps of 0.0116, both arms sit within one step of zero, Welch t ≈ 0.24 at n=4/5 (`PC`). Do not quote the +0.0013 as an improvement; `PC` says so explicitly.

---

## 2.3 Retrieval — the headline numbers, with their ceiling

> ⚠️ **Superseded 2026-07-31 by §3.1.** Its source, `retrieval/BASELINE.md`, now carries its own SUPERSEDED banner: *"Do not quote that file's numbers."* The label snapshot below (`019bee4a06eb2d39`, 118 docs, 4 topics, 59 queries) **no longer exists**; the current one is `230c6ea9d9b7e8fd` — 344 docs / 5,948 chunks / 15 topics / **338 queries**, with **recall@10 = 0.2195 against a ceiling of 0.5199 (42% of attainable)**. **That is not a regression against the 0.4221 below** — it is a 2.8× larger corpus with more distractors and a lower ceiling. Do not difference the two. The ANN subsection's *findings* stand; its **crossover moved 35 → 103** at the new corpus size (§3.7).

**Dense**, relevance unit = document, k = 10, chunk oversample ×5, binary relevance, **n = 59 queries** over **4 manuscripts**, 903 relevant judgments, 118 documents / 2,124 chunks. Labels fingerprint `019bee4a06eb2d39`. Source: `BASELINE` §1, corroborated by `BENCH` (run `1fdb7ff03547`, config `7330ae9c1e22ce33`, two byte-identical runs on disk).

| metric | measured (n=59) | construction ceiling | % of attainable |
|---|---|---|---|
| recall@1 | **0.0896** | 0.1061 | **84%** |
| recall@5 | **0.3051** | 0.5307 | **58%** |
| **recall@10** | **0.4221** | **0.7789** | **54%** |
| recall@20 | **0.5299** | 0.8798 | **60%** |
| **NDCG@10** | **0.6526** | n/a — not capped by label design | n/a |
| **MRR** | **0.8836** | n/a — not capped by label design | n/a |
| MAP | 0.4391 | n/a | n/a — **and never quote this as precision** |

**The ceiling is not optional context; it is part of the number.** Every query inherits its manuscript's *entire* reference list, so a query with 37 relevant documents cannot exceed recall@10 = 10/37. Dense recall@10 of 0.4221 is **54% of the maximum this label design permits**, not 42% of a reachable 100%. `BASELINE` §1: *"Anyone comparing 0.4221 against a published recall@10 from a benchmark with one relevant document per query is comparing two different quantities."* `BENCH` enforces this as a house rule — *"recall@k is reported against its construction ceiling, or explicitly as unknown."*

**Why MRR 0.8836 reads so much better than recall 0.4221.** Hand-checked, not inferred: one strongly on-topic paper dominates rank 1 while the other 7–36 cited references never surface (`WL` Wave 2b, "Other findings"). MRR is measuring "is *something* right at the top", which is a much weaker claim than the number's magnitude suggests.

### 🔧 A labelling error inherited from `BASELINE`

`BASELINE` calls its dense row *"dense (pgvector HNSW, cosine)"*. It is not HNSW. **At `LIMIT ≥ 40` Postgres declines the index entirely and runs an exact sequential scan** — the plan is `Seq Scan → Sort` (`ANN` §0, §1). The eval harness asks for 50 chunks (k=10 × oversample 5), which is past the crossover, so *"`retrieval/BASELINE.md`'s dense row is an exact-scan result wearing an index's name"* (`ANN` §6). The numbers are not wrong; the retriever is misnamed. Production's real call sites pass `match_count` of 3/5/6/10, **below** the crossover, so production **does** use the index (`ANN` §1). This is also a small-corpus artefact that should disappear at scale (`ANN` §7).

### ANN operating point — measured, previously assumed

`ef_search = 80`, `m = 16`, `ef_construction = 64` were never chosen: two are pgvector defaults and one is a value someone typed once (`ANN` §preamble). They are now measured.

- **`ef_search = 80` sits on the knee** at k=10, production's real depth: ANN recall **0.9932** at **1.03 ms p50**, versus 0.9797 at 0.66 ms (`ef_search=40`) and 1.0000 at **16.94 ms** (`ef_search=160`, where the planner abandons the index). **Nothing in the grid dominates it** (`ANN` §3C, §6).
- **`m=16` / `ef_construction=64` is not dominated by an 11-point grid.** ANN@50 0.9837 for 1.14 s of build. `m=32` buys ANN@50 0.9973 for 1.7× the build time and ~30% more query latency and **nothing** on the label metrics — R@10 spans 0.3473–0.3515 across the *entire* grid, a range of 0.004 that is well inside noise at n=59 (`ANN` §4).
- **Index size is identical — 17,408,000 bytes — at every grid point.** A 1536-dim `float4` vector fills an 8 KB page on its own, so `m` has no effect on size here. Any claim that raising `m` "costs disk" is unsupported (`ANN` §4.1).

**Honest framing, which `ANN` §6 states itself:** *"a defensible value was reached by accident, and it is now measured rather than assumed."* Claim the measurement, not the design. And note the latency figures are **index-forced or shallow-k microbenchmarks on 2,124 chunks** — not what the planner does at eval depth, and explicitly non-generalising (`ANN` §7). The exact-scan p50 varied 17.8 / 23.2 / 27.4 ms across three runs — ±25% machine noise that bounds how finely any latency claim here may be read (`ANN` §2).

---

## 2.4 Keyword retrieval — the largest measured delta in this document

> ⚠️ **Absolutes superseded 2026-07-31 by §3.2; the finding stands.** The table below is snapshot `425df789a844f1f3` (59 queries). Re-measured at 338 queries: zero-row queries **321/338 → 0/338**, recall@10 **0.0022 → 0.1447**, a **66×** gap. **Quote the ratio, not either absolute** — both moved with the corpus and the direction did not. Also superseded: the last bullet below says hybrid fusion *"has not been built or measured."* **It has.** RRF was built and **lost** to dense — see §3.3.

The first baseline measured keyword at recall@10 ≈ 0.004 against dense 0.4221 and it looked like a broken retriever. It was not: `keyword_search_chunks` builds its query with `plainto_tsquery`, which **ANDs every lemma**, against manuscript claims averaging ~20 words. A chunk had to contain all ~20 lemmas to match at all.

Same 59 queries, same database, same label set (fingerprint `425df789a844f1f3`), both functions in one process (`KQ` §4):

| | `keyword_search_chunks` (old) | `keyword_search_chunks_v2` (new) |
|---|---|---|
| queries returning **zero rows** | **55 / 59** | **0 / 59** |
| total rows across the run | 6 | 2,950 |
| **recall@10** | **0.0026** | **0.2841** |
| precision@10 | 0.0051 | 0.4339 |
| hit-rate@10 | 0.0339 | 0.9322 |
| MRR | 0.0339 | 0.7460 |
| NDCG@10 | 0.0098 | 0.4960 |
| latency | ~4 ms | ~22–42 ms |

**Caveats, all of which `KQ` states itself:**

- **The v2 function is behind `KEYWORD_SEARCH_V2`, default OFF, and `keyword_search_chunks` is untouched** (its `pg_get_functiondef` hash is identical before and after migration 038). Nothing shipped. Claiming "I fixed keyword search in production" would be false.
- **0.0026 ≠ `BASELINE`'s 0.0040 for the same function.** Different label snapshot; more corpora had been built. The old-vs-new comparison **within one run** is the one to quote (`KQ` §4, caveat 1).
- **Dense was not re-measured under this snapshot.** `BASELINE`'s 0.4221 is from the earlier one, so "keyword v2 reaches ~two-thirds of dense" is *approximate*, not exact (`KQ` §4, caveat 2).
- **The improvement is conditional on the claim carrying domain vocabulary.** Hand inspection (`KQ` §5) shows claims made of generic academic filler retrieve pure noise from the wrong field entirely. Long survey documents also win a document-level lottery because scores are max-pooled over chunks.
- **The choice *among* OR variants is noise-level** and was made on simplicity and latency as much as on the numbers; only the ~100× old-vs-new gap survives the n=59 objection (`KQ` §6).
- **Hybrid fusion has not been built or measured.** `HybridRetriever` remains a deliberate stub (`BASELINE` §1). And `KQ` §6 warns that `hybrid_search`'s existing `0.7×similarity + 0.3×rank` would make the keyword leg contribute **well under 1%** of the combined score, because `ts_rank` values sit between 0.0038 and 0.0071.

---

## 2.5 Eval precision — §1.4C's suspicion, confirmed and quantified

§1 flagged `mean_precision: 1.0` as *"near-tautological by construction."* It was. `judge_openreview.py:307-324` counted an item correct if it matched a gold review unit **OR** its anchor appeared in the PDF **OR** an LLM judged it grounded — so an item no human reviewer raised counted as a hit the moment a model blessed it (`WL` Wave 2).

| metric | shipped scoreboard | honest value |
|---|---|---|
| `mean_precision` → `mean_precision_vs_gold` | **1.0** | **0.27** |
| `mean_hallucination_rate` | **0.0** | **0.1109** |
| `mean_groundedness` | folded into precision | 0.8891 |
| `mean_weakness_recall` | 0.1872 | 0.1872 (unchanged) |

Per paper, distinct matched items over items produced: `rhgIgTSSxW` 7/22 · `miGpIhquyB` 7/24 · `rp5vfyp5Np` 6/30.

**Read:** ~73% of what Noesis raises was raised by no human reviewer, and ~11% points at text not findable in the paper.

**Caveats:**
- **n = 3 papers.** `WL` says it plainly: *"real, not stable."*
- A pair-based numerator reads **0.554** and **double-counts** — one item can match several gold units. Precision must be distinct-items-over-items.
- Caveat 2 from §2.0 bites hardest here: 0.27 is a **lower bound**. An item no human raised may be a genuine finding the reviewers missed, and this metric cannot tell that from a hallucination. What it *can* tell is the 0.111 that points at text not in the paper — that one is unambiguous.
- Recomputed entirely from cached exports and gold on disk; **zero LLM calls**.

**§1.4C's core finding still stands: there is no before/after.** An append-only eval history now exists, but `BENCH` § "OpenReview eval scoreboard" shows 10 runs across 2 pipeline versions with **every single one at `no data (n=0)` scored cells** and a trend of `unknown`. "Lifted quality on LLM evals" remains undefensible in either direction, and is now undefensible next to a *measured* 0.27 and 0.111.

---

## 2.6 The publish gate

Fully covered by **CORRECTION 2** above (n = 77 exports). Summary for the table's sake: `parser_quality_score` takes 2 values and its 0.55 threshold is **inert**; `verbatim_anchor_coverage` is 1.0 on all 77 and **structurally cannot vary**; `page_anchor_coverage` is the only signal that has ever driven a verdict, and drove all 12 `needs_retry` results. The threshold itself is hand-set and **uncalibrated** — the sweep needs human labels and none exist (`BENCH` § Gate calibration: *"not a zero, an absence"*).

---

## 2.7 Corpus and reference resolution

> ⚠️ **Partly superseded 2026-07-31 by §3.8.** The 61.2% and its understated-denominator caveat stand unchanged. The closing paragraph — *"Not yet ingested … do not quote 333 documents as an index size"* — **is superseded**: the corpus has been ingested and the index is now **344 documents / 5,948 chunks**. §3.8 also adds a second unknown this section did not have: for the retrieval *label snapshot*, the resolution rate is not recoverable at all (11 of 26 corpora have no sidecar).

**333 / 544 = 61.2%** across **15 of 15** OpenReview topics (`BUILD`). Verifiable rather than tautological: the four status buckets sum exactly to 544 (333 resolved + 78 `no_openalex_match` + 81 `no_oa_pdf` + 52 `download_failed`), every sidecar's entry count equals its `references_attempted`, the PDF count on disk equals `resolved` in all 15 directories, and **zero** references are left `pending`.

**The denominator is understated, and this is the caveat that must never be dropped.** `544` counts reference entries *as the parser segmented them*. The extractor under-segments: **60 of 544 entries (11%) are long blocks containing two or more distinct works** — one `BQvbL2sFQx` entry merges Goodfellow *et al.* with a Gunasekar reference, and only the second was ever looked up (`BUILD` § "Caveat"). So the true bibliography is **larger than 544** and 61.2% is a rate over what the parser produced. `BUILD` states the prohibition directly: *"it should not be quoted as 'we resolve 61% of the references in these papers.'"* Worst case is `eR4W9tnJoZ` — 12 references parsed, **7 of them (58%) suspected merged blocks**, its 16.7% the least trustworthy per-topic number on both numerator and denominator.

Related, and worth carrying because it is the same class of error §1 was written to catch: **the earlier 55.2% figure was itself a repaired number.** Before Wave 2 the matcher guessed resolution from title-token overlap against filenames and credited **21** references that `build_corpus.py` records as never having downloaded; unresolved went 44 → 65 when the authoritative sidecar replaced the guess, and each of those 21 had been inflating recall (`BASELINE` §3).

Cost, for completeness: the 15-topic build spent a **measured $0.3520** of OpenAlex daily allowance against a ~$0.38 prediction (`BUILD` § Budget); corpus ingestion cost **$0.3410** for 1,426 chunks / 2.62M tokens in 128 s wall clock (`BASELINE` §5). OpenAlex became a metered paid API in Feb 2026; a **free** key raises the daily allowance from $0.10 to $1.00 (`OA` §preamble).

**Not yet ingested.** `BUILD` states *"No ingestion was run and no database was written."* The retrieval index measured in §2.3 is still the **118-document / 2,124-chunk** pooled corpus — 80 OpenReview reference PDFs from 4 topics plus 38 `draft1`–`draft10` documents acting as distractors. **The 15-topic corpus exists on disk; it has not been retrieved against.** Do not quote 333 documents as an index size.

---

## 2.8 Two replacement bullets for §1.7

Bullets 1, 2, 3 and 6 from §1.7 stand as written. These two are superseded.

**Bullet 4 — pgvector.** §1.3 R4 said *"you cannot state your index type, its parameters, or your distance metric, because the DDL is not in the repo and the DB is unreachable."* Both conditions were resolved in Wave 0: the DDL was recovered and versioned (commit `b9c8122` — 3 tables, 11 indexes, 6 RPCs, 310 lines) and live introspection succeeded (PostgreSQL 17.6). You may now say:

> - Built pgvector retrieval over 1536-dim embeddings (Matryoshka-truncated from `text-embedding-3-large`'s 3072) on an HNSW / `vector_cosine_ops` index, with deterministic topic-relevance gating between retrieval and LLM context; measured the index's recall-vs-latency curve across an 11-point `m` × `ef_construction` grid and a 7-point `ef_search` sweep to confirm the operating point.

Defensible follow-ups: `ef_search = 80` is on the knee at production's k (ANN recall 0.9932 @ 1.03 ms p50); the build parameters move label metrics by 0.004 across the whole grid, i.e. they are not a lever at this corpus size. **Do not** claim you *chose* those parameters — two are library defaults; you *measured* them, which is the more interesting claim anyway.

**Bullet 5 — the gate.** Per CORRECTION 2:

> - Engineered a deterministic page-anchor-coverage gate that suppresses critique artifacts which cannot be traced to a page in the manuscript and records a degraded-run verdict; instrumented the gate across 77 archived runs and found two of its three signals inert — one pinned at a constant, one structurally unable to fail — leaving a single live predictor.

That is a weaker feature and a stronger engineering claim than the bullet it replaces, and it is the version that survives a follow-up.

---

## 2.9 Still unmeasured — do not let an adjacent number lend these provenance

> ⚠️ **Superseded 2026-07-31 by §3.10.** Three rows below have since been measured — **hybrid/RRF** (built; it lost), **`KEYWORD_SEARCH_V2` at scale** (66×, still default off), and **prompt-cache on the real replay path** (60.7% / 24.5%) — and four rows have been added that this list did not know to include. Everything else on it is still unmeasured.

This list is the point of the section. Each of these sits next to something that *is* measured, which is exactly what makes it dangerous.

| Claim | Status | Why the adjacent number does not help |
|---|---|---|
| **End-to-end / user-visible latency** | **Unmeasured. Never measured, not once.** | `reviewer_panel_node` = 19.818 s is one node replayed in isolation. The `~18s` and `~3.5 min` figures remain unprovenanced and mutually contradictory |
| **`53s → 18s`, `66%`** | **Unmeasured.** No sequential baseline exists anywhere | Measuring the fan-out's current cost does not measure the improvement it produced |
| **"no quality loss" from parallelisation** | **Unmeasured** | Asserts an eval that was never run, before or after |
| **"lifted quality on LLM evals"** | **Unmeasured, and now sitting next to a measured 0.27 / 0.111** | `BENCH` shows 10 eval runs with zero scored cells and a trend of `unknown` |
| **30+ researchers, 3+ universities** | **Unmeasured.** §1.4A/B unchanged | No measurement work touched user counts. The deck still says 2 universities |
| **Publish-gate threshold `0.75` being correct** | **Unmeasured.** Hand-set | The gate's *behaviour* is measured across 77 runs; its *calibration* needs human labels that do not exist |
| **Production retrieval quality** | **Unmeasured** | Every retrieval number is local pgvector, eval corpus, PyMuPDF + basic chunking |
| **Section-aware chunking arm** | **Unmeasured** | Only the basic-chunking arm was measured; the two are not interchangeable |
| **Hybrid / RRF fusion** | **Not built, not measured** | `HybridRetriever` is a deliberate stub; the keyword leg's fix is default-off |
| **`KEYWORD_SEARCH_V2` in production** | **Unmeasured on production data**, flag default off | The 0.2841 is local eval corpus only |
| **Prompt-cache gain at production scale** | **n = 1 cold panel on 1 paper**, plus 1 contaminated confirmation | 58.8% is at its own structural ceiling for a 3-call panel; it is not a fleet number |
| **Whether items outside the gold set are findings or hallucinations** | **Unmeasured and, under this label design, unmeasurable** | The 0.27 is a lower bound by construction (§2.0 caveat 2) |
| **Whether ANN findings generalise** | **Explicitly not.** `ANN` §7 | 2,124 chunks is far too small; the "Postgres won't use the index" finding should be *expected to disappear* at scale |

**One standing note on register.** §1's closing standard was to say plainly where the honest version is weaker. It applies to §2 as well, and in two places the honest version *is* weaker: the gate is one `if` rather than a three-signal trust layer, and the eval precision the pipeline actually achieves is 0.27, not 1.0. Both are worse features and better engineering stories. The numbers being better in general does not license rounding those two up.

---

# Item 1B — §3. Measured-status refresh (2026-07-31)

## 3.0 Why this section exists, and what it does to §2

§2 was written on **2026-07-30** against the measurement that existed that morning: one retrieval label snapshot (118 documents, 4 topics, 59 queries), an ANN sweep on 2,124 chunks, a keyword-query diagnosis, a prompt-cache A/B, and a node-replay cost table that did not yet count the matcher.

Measurement continued. The corpus was built out to 15 of 15 topics and ingested, the retrieval eval was re-run end to end under a **new label snapshot**, RRF was implemented and measured, the matcher was brought inside the accounting, and latency variance was re-measured at n=5. **Several of §2's figures are therefore superseded — not corrected, superseded: they were right about the thing they measured and that thing no longer exists.**

**Nothing in §1 or §2 has been deleted.** Every superseded table below is marked in place with a pointer here. Where §3 contradicts an earlier section, it says so and says why.

### Source key — additions to §2.0's table

| tag | document | what it is |
|---|---|---|
| `B15` | `scripts/eval/BASELINE_15.md` | the current retrieval baseline: 15 topics, 344 indexed documents, 338 queries, RRF measured |
| `NC` | `scripts/eval/NODE_COST.md` | the first *complete* node-replay cost figure (matcher included) and the n=5 variance measurement |

`BASELINE` (`scripts/eval/retrieval/BASELINE.md`) now carries a **SUPERSEDED** banner at its head, written by its own authors: *"Do not quote that file's numbers."* Two reasons — its dense row was mislabelled as HNSW when the planner was running an exact scan, and its label snapshot no longer exists. §2.3 quotes that file extensively and is superseded with it.

### The three label snapshots — read this before differencing anything

There are **three**, not two. Absolutes do not transfer between them; directions do.

| fingerprint | indexed docs / chunks | topics with labels **and** queries | scorable queries | judgments | measured by |
|---|---|---|---|---|---|
| `019bee4a06eb2d39` | 118 / 2,124 | 4 of 15 | **59** | 903 | `BASELINE` (superseded), `BENCH` runs `1fdb7ff03547` / `a986f65f72f6` |
| `425df789a844f1f3` | 118 indexed, 86 label docs | 4 | **59** | — | `ANN` §8, `KQ` §4. **Never written to `results/retrieval_eval.jsonl`** (`KQ` §4: *"nothing was written"*), which is why `BENCH` reports only two snapshots |
| **`230c6ea9d9b7e8fd`** (current) | **344 / 5,948**; pooled label corpus **345** | **15 of 15** (26 topics pooled, 23 with labels) | **338** | **8,554** | `B15` §1, §3; `BENCH` runs `5ca19da1d093`, `813629e2f023`, `354f3eb41c1c`, `fc317a79f1a8` |

**The single most abusable comparison in this document:** dense recall@10 reads **0.4221** under `019bee4a06eb2d39` and **0.2195** under `230c6ea9d9b7e8fd`. **That is not a regression.** The corpus is 2.9× larger in documents and 2.8× larger in chunks, the average query now inherits **25.3** relevant documents rather than 15.3, and the construction ceiling fell from 0.7789 to **0.5199** with it (`B15` §1, §3). Measured as a fraction of attainable the two are 54% and 42% — still not a like-for-like comparison, because the query set also went from 4 manuscripts to 15. `B15` §1 states the prohibition itself: *"Nothing here should be compared to BASELINE.md at all."* `BENCH`'s house rule enforces it mechanically: *"retrieval numbers are grouped by label snapshot and numbers from different snapshots are not comparable at all."*

---

## 3.1 Retrieval — the current headline, with its ceiling

Relevance unit **document**, k = 10, binary relevance, chunk oversample ×5 (50 chunks requested, max-pooled to documents). **n = 338 scorable queries from 15 manuscripts, 8,554 relevant judgments, 345-document pooled label corpus, 344 indexed documents / 5,948 chunks.** Labels `230c6ea9d9b7e8fd`, queries `1f6c584e8fd6c055`. Source: `B15` §3; corroborated by `BENCH` (run `5ca19da1d093`, config `5d1408923f74702d`).

| metric | measured (n=338) | construction ceiling | % of attainable |
|---|---|---|---|
| recall@1 | 0.0341 | 0.0694 | 49% |
| recall@5 | 0.1365 | 0.2939 | 46% |
| **recall@10** | **0.2195** | **0.5199** | **42%** |
| recall@20 | 0.3062 | 0.7599 | 40% |
| **NDCG@10** | **0.5191** | not capped by label design | n/a |
| **MRR** | **0.7328** | not capped by label design | n/a |
| MAP | 0.2319 | not capped by label design | **never quote as precision** |

**The ceiling travels with the number or the number is a lie by omission.** Every query inherits its manuscript's *entire* resolved reference list, so a query with 37 relevant documents cannot exceed recall@10 = 10/37. The ceiling is the mean over scorable queries of `min(k, |rel_q|)/|rel_q|`. MRR, NDCG@10 and MAP are recorded as `null` for ceiling, **not** as 1.0 — `B15` §3: *"'No ceiling computed' and 'at its ceiling' are different claims."*

**The depth arm, for completeness and for the confound it carries.** `dense_os12` (120 chunks, `plan: seqscan`) reads recall@10 **0.2227** / 43% of attainable and MAP 0.2948. It is *not* better because the plan flipped; it is better because it looked deeper. `B15` caveat 3 states this directly, and the oversample arms are confounded with depth by construction.

**One §2 error is fixed by the corpus growing, not by anyone editing it.** §2.3 flagged that `BASELINE`'s dense row was *"an exact-scan result wearing an index's name."* At 5,948 chunks the harness's default depth of 50 is comfortably below the planner's crossover, so the current dense arm **really is** an HNSW index scan — and the record says so because `retrieval/plan_probe.py` runs an `EXPLAIN` at the depth actually used and stamps `plan` into every result record, rather than anyone inferring it (`B15` §2).

**Caveats that survive from §2.0 unchanged, and one new one:**

- The labels are the manuscripts' own reference lists. This measures *"would we have found what the author cited"*, not *"what is relevant"* — every precision-like metric is a **lower bound**, and recall is the sounder number.
- Local pgvector, PyMuPDF extraction, basic chunking. **Not production's Docling → GROBID section-aware chain, and not a production retrieval number.**
- **New, and it is the largest uncontrolled factor in the absolute numbers:** the query set contains a substantial population of **contentless claims** — e.g. *"We experimentally verified that our method can achieve good results"* — for which no retriever can succeed because the query carries no information. Hand-checked in `B15` §6: on claims carrying domain vocabulary, dense scores 5/5 relevant in the top 5; on contentless ones every arm fails. Filtering those out would raise every number and would **not** be an improvement. `B15` §6: *"the single most likely source of a large apparent 'improvement' that is not one."*

---

## 3.2 Keyword retrieval — the fix holds at 5.7× the scale

`KQ` diagnosed `plainto_tsquery` ANDing every lemma of a ~20-word claim, and fixed it with an OR of the query's lemmas ranked by `ts_rank(…, 1|32)` (`keyword_search_chunks_v2`, migration 038). Re-measured under the current snapshot (`B15` §4):

| | v1 (`plainto_tsquery`) | v2 (OR of lemmas) |
|---|---|---|
| queries returning zero rows | **321 / 338** (95%) | **0 / 338** |
| total rows across the run (k=50) | 60 | 16,900 |
| **recall@10** | 0.0022 | **0.1447** (**66×**) |
| MRR | 0.0311 | 0.6675 |
| NDCG@10 | 0.0110 | 0.3830 |
| MAP | 0.0021 | 0.1439 |
| % of attainable recall@10 | 0% | **28%** |

`KEYWORD_SEARCH_DEGRADED` was **clear for both runs** — these are real results, not a swallowed RPC error, which matters because a swallowed error is exactly how this failure hid in production for the life of the feature.

**Quote the ratio, not either absolute.** `KQ` measured 0.0026 → 0.2841 on snapshot `425df789a844f1f3`; both absolutes moved under the larger corpus and the direction did not (`B15` §4). §2.4's table (0.0026 / 0.2841 / precision@10 0.4339 / hit-rate 0.9322) is snapshot-`425df789a844f1f3` and is superseded as an absolute; its *finding* stands.

**Still default OFF.** `KEYWORD_SEARCH_V2` gates the new function and defaults to off; `keyword_search_chunks` is untouched (identical `pg_get_functiondef` hash before and after 038). **"I fixed keyword search in production" remains false.**

---

## 3.3 RRF — built, measured, and it **loses** to dense

§2.9 listed *"Hybrid / RRF fusion — not built, not measured."* **That row is now closed, and the result is a negative.**

`HybridRetriever` implements `score(d) = Σᵢ 1/(k_rrf + rankᵢ(d))`, fused by rank at document level. Same 338 queries, same labels (`B15` §5):

| | dense (os ×5) | RRF k=60 | Δ |
|---|---|---|---|
| recall@1 | **0.0341** | 0.0305 | **−10.6%** |
| recall@5 | **0.1365** | 0.1198 | **−12.2%** |
| **recall@10** | **0.2195** | 0.2042 | **−7.0%** |
| recall@20 | **0.3062** | 0.2993 | −2.3% |
| MRR | 0.7328 | **0.7335** | +0.1% |
| **NDCG@10** | **0.5191** | 0.4989 | **−3.9%** |
| MAP | 0.2319 | **0.2431** | **+4.8%** |

**Best coverage, worst ranking.** RRF's retrieval failures drop to **5,144** against dense's 6,010 — it genuinely finds more of the corpus — and its ranking failures rise to **1,885** against dense's 936. It pays for the coverage at the top of the list, which is where NDCG@10, recall@10 and a downstream RAG consumer all look. `k_rrf` is a knob with no gradient: across a 60× span (5 → 300) the whole grid moves 0.007 on recall@10, so the deficit is not a tuning problem — it is the keyword leg's error profile. On a contentless claim, an OR over `highlight | superior | generaliz | approach | …` matches most of the corpus, and RRF cannot tell an uninformative vote from an informative one; `B15` §6b shows dense's correct rank-1 hit being pushed out of the top 10 entirely by six such votes.

**Two things this result is not.** (1) It is not a failed build — an unmeasured *"we added hybrid retrieval and it helped"* would have been worse than useless. (2) It is **not** a statement about the fusion production would run: RRF was measured with the keyword leg at `KEYWORD_SEARCH_V2=1`, which is **off** in production, where the leg returns nothing for 95% of queries and fusing with it would be dense scaled by a constant (`B15` caveat 8).

**The honest hedge, in `B15`'s own words:** the recall deltas are 2–12% relative on n=338, which clears the eyeball-noise threshold, but this is one label snapshot on one corpus and the sign could flip where the lexical leg is stronger. *"There is no evidence RRF helps the top of the list here, and the burden of proof was on the fusion."*

---

## 3.4 Cost — the first complete figure, and why every earlier one was a floor

> ⚠️ **This supersedes every dollar figure in §2.2.** Not because they were miscomputed, but because they omitted a whole category of spend.

`scripts/eval/match.py` — which computes the severity-weighted-recall metric — called the OpenAI client directly until 2026-07-30. Its calls were neither recorded by `llm_budget` nor bounded by any spend ceiling. **The margin is unrecoverable, not merely unknown:** the matcher's disk caches store an embedding vector and a `{confirmed, reason}` verdict, with no prompt text, no usage block and no model, so the missing token counts cannot be reconstructed from disk (`NC` §"Every cost figure produced before this run was a lower bound"). The most-quoted prior figure, **$0.21999**, made **6 uncounted matcher calls** and reported $0.00 for all of them.

The first complete measurement (`NC`, run ids `f0af0ecb5365`, `9c11daa01698`, `82092c60b36c`, `dc045ccaaadb`):

| | node | matcher | total |
|---|---|---|---|
| recorded spend | $0.16761 | $0.03255 | **$0.20016** |
| share | 83.7% | **16.3%** | 100% |

**Matcher spend is 16.3% of the complete figure, and it is not uniform** — it scales with how many items a node emits, not with what the node cost:

| node | n | node $ | matcher $ | matcher share | complete $ |
|---|---|---|---|---|---|
| `reviewer_panel_node[methodology]` @ `10eQ4Cfh8p` | 5 | $0.12098 | $0.02682 | 18.1% | $0.14779 → **$0.0296/replay** |
| `editor_pass_node` | 3 | $0.00339 | $0.00297 | **46.7%** | $0.00636 |
| `run_quality_diagnostics` | 3 | $0.00000 | $0.00277 | **100%** | **$0.00277** |

**A node the old accounting reported as free costs $0.00277 to measure, and makes zero LLM calls.** The cheaper the node, the worse the old figure was in relative terms.

**On §2.2's `~$0.043/replay` for `reviewer_panel_node`:** that was node-only spend over a *different fixture mix* — the prior n=5 mixed `10eQ4Cfh8p` with the much larger `9ceadCJY4B`, which alone accounted for 53,535 of 90,215 input tokens. `NC`'s n=5 is deliberately one fixture, so latency variance is measured rather than confounded by fixture size. **Compare per-call, not row totals**, and do not difference the two.

**Still outside the accounting**, and it must be said rather than rounded away: `scripts/eval/atomize_reviews.py` calls OpenAI directly and is neither guarded nor recorded. It contributed **$0.00 to this run** only because its cache was fully warm for all three papers — *"that is luck, not a guarantee"* (`NC`). Two further under-counts from earlier waves remain open: usage is lost on a validation retry, and cached-token shape is read positionally. Separately, **~$0.02 of real spend is simply gone** — a killed process with `NOESIS_LLM_USAGE_LOG` unset died with its usage in memory. True spend for the exercise is ~$0.22 against a recorded $0.20016.

**Standing rule, unchanged and now enforced by `BENCH`'s house rules:** *every dollar amount in this project is a floor.*

---

## 3.5 Latency and quality variance — §2.2's `~7%` did not survive n=5

> ⚠️ **This supersedes the `~7% CV at n=3` figure quoted in CORRECTION 1 reason 4, §2.2 and §1.**

`reviewer_panel_node[methodology]` @ `10eQ4Cfh8p`, **5 replays of one fixture** (`NC` §Variance):

```
17.10  18.26  19.69  24.13  17.25   (seconds)
mean 19.286   sd 2.897   CV 15.0%   95% CI (t, 4 df): 19.29 ± 3.60 → [15.69, 22.89]
```

**The spread roughly doubled once a fifth sample was drawn.** What is defensible: *a latency difference smaller than about ±19% of the mean (~±3.6 s) is not resolvable with n=5 on this node.* The 24.13 s outlier is one sample and there is no basis at n=5 for excluding it.

For the aggregate picture, `BENCH` § Node replay rolls up every replay on disk — but note it **mixes fixtures and personas**, so it is a cost/latency summary and *not* a variance estimate: `reviewer_panel_node` mean **19.307 s (n=12)**, `editor_pass_node` **7.431 s (n=6)**, `run_quality_diagnostics` **0.060 s (n=6)**. §2.2's 19.818 / 7.079 / 0.060 came from an earlier generation of that same file over fewer replays.

**Quality variance remains unresolvable, and no delta may be reported from it.** Severity-weighted recall across the same 5 replays, 79 gold units:

```
0.0463  0.0232  0.0000  0.0116  0.0116     matched units: 4, 2, 0, 1, 1  of 79
mean 0.0185   sd 0.0176   CV 95%
```

The metric is quantised at ~0.0116 per matched unit, so sd ≈ 1.5 quanta and the observed range spans the entire signal. Five draws from the same fixture, same prompt, same model produced anything from zero matches to four. Cause unchanged: `retry_utils` strips `temperature` for every `gpt-5.2*` model and no seed is set anywhere. `NC` states the prohibition: ***"No quality delta is reported from this run, and none should be inferred from it."*** The CV improving from ~172% to 95% is not the measurement tightening — it is the mean happening to land away from zero.

---

## 3.6 Prompt caching — confirmed on the real replay path

§2.2 reported the purpose-built A/B: **0% → 58.8%**, cold-panel cost **−23.8%**, on paper `eR4W9tnJoZ`. That stands as measured. The reorder has since been measured on the *normal* replay path, on a different paper (`NC` §"What the prefix-caching reorder actually bought"), which is the stronger evidence:

| call (paper `10eQ4Cfh8p`) | prompt | cached | hit rate |
|---|---|---|---|
| methodology #1 (nothing warm) | 9,224 | 0 | 0.0% |
| clarity — **persona never sent before** | 8,657 | 8,064 | **93.2%** |
| literature_positioning — ditto | 8,697 | 8,064 | **92.7%** |

The last two rows are load-bearing: those prompts had never been sent, and 8,064 tokens still came back cached. That is the shared prefix and nothing but the reorder puts it there. **8,064 tokens is 87.4% of the methodology prompt**, and it is quantised to OpenAI's 128-token cache block (8,064 = 63 × 128).

Rolled up to a cold three-persona panel: **16,128 cached of 26,578 prompt tokens = 60.7% hit rate**, and costing the cached tokens at the full input rate instead of the cached rate gives a counterfactual uncached panel of $0.10387 against the measured $0.07847 — **24.5% cheaper per cold panel.** Both A/B numbers reproduce within ~2 points.

**Caveats that must travel with it:**
- Still **n = 2 papers, one cold panel each**, on an eval fixture. Not a fleet number, not production.
- **`--repeat` inflates the hit rate.** Repeats read 98.5% because the whole prompt including the persona block is warm. The aggregate `cached_prompt_fraction = 0.788` on that run is 1 cold call and 4 warm ones and is **not** a production figure (`NC`).
- It is **not** "we added prompt caching." OpenAI's automatic prefix cache was already working with no `cache_control` anywhere in the repo; exact repeats already cached at ~99%. What was added is **cross-persona** reuse, which is where the volume is.
- The related `DRAFT_REVIEWER_COMPACT_MANUSCRIPT` flag cuts prompt tokens **60.7%** and is **default OFF**; its quality effect is **not resolvable** (Welch t ≈ 0.24 at n=4/5) and there is a first-principles reason to expect it to *increase* false "not reported" critiques, since the grounding rule tells reviewers to search the whole manuscript before claiming absence.

---

## 3.7 ANN — the crossover moved, exactly as `ANN` §7 predicted it would

§2.3 recorded that at `LIMIT ≥ 40` Postgres declined the HNSW index on the 2,124-chunk corpus, and that `ANN` §7 called this a small-corpus artefact that *"should be expected to disappear"* at scale. It did:

| corpus | chunks | crossover (last `LIMIT` planned as index scan) |
|---|---|---|
| `ANN` (old) | 2,124 | **~35** (bracketed 30 → 40) |
| `B15` (current) | 5,948 | **103** (104 flips to seqscan) |

Corpus ×2.80, crossover ×2.96. Re-determined by binary search over `EXPLAIN` with the RPC's own `hnsw.ef_search = 80`, verified over 10 distinct query vectors at each depth with all 10 agreeing — so the boundary is a property of the cost model, not of the query. `ef_search` shifts it slightly (104 at 40, **103 at 80**, 102 at 160, 100 at 320). `B15` §2 shows the `EXPLAIN` output for LIMIT 50 / 103 / 104 verbatim.

**Consequences.** (a) The harness's default depth of 50 is now genuinely an index scan, which retires §2.3's labelling error. (b) The crossover is **not a constant and must never be cached as one** — it rises roughly linearly with row count, which is why `plan` is measured per run rather than inferred from a remembered threshold.

**What has *not* been re-measured, and must not be silently carried forward:** every ANN latency number — the `ef_search` knee, the `m` × `ef_construction` grid, the p50/p95 columns — is from the **2,124-chunk** corpus (`ANN`). `B15` §caveat 4 is explicit: *"No latency is reported. This document measures quality only."* So:

- `ef_search = 80` sitting on the knee at k=10 (ANN recall 0.9932 at 1.03 ms p50) is a **2,124-chunk** result and remains the operating-point evidence, unrefreshed.
- **Raising `ef_search` past 80 at k=10 makes the query 16× slower** (1.03 ms → 16.94 ms) *because the cost model abandons the index and the plan flips*, not because the index got slower — the index-forced rows show 1.66 ms at the same setting. Quoting the 16× without the mechanism describes a property of the planner as though it were a property of HNSW.
- **An index-forced number is never what production does.** `BENCH` carries this as a per-row label and so does this document.
- Index size is identical (17,408,000 bytes) at all 11 grid points because a 1536-dim `float4` vector fills an 8 KB page on its own. That one *does* generalise on dimensionality; the build-time ordering does not.

---

## 3.8 Corpus and reference resolution

> ⚠️ §2.7's closing paragraph — *"Not yet ingested … do not quote 333 documents as an index size"* — **is superseded.** The corpus has been ingested. The index is **344 documents / 5,948 chunks** across 26 pooled topics (`B15` §1), which is the corpus every number in §3.1–§3.3 was measured against.

The resolution rate itself is unchanged and its caveat is unchanged, because it is a property of the build, not of the index:

**333 / 544 = 61.2%** across **15 of 15** OpenReview topics (`BUILD`). Verifiable rather than tautological: the four status buckets sum exactly to 544 (333 resolved + 78 `no_openalex_match` + 81 `no_oa_pdf` + 52 `download_failed`), every sidecar's entry count equals its `references_attempted`, the PDF count on disk equals `resolved` in all 15 directories, and **zero** references are left `pending`. Measured build cost: **$0.3520** of OpenAlex daily allowance against a ~$0.38 prediction.

**The denominator is understated and the caveat must never be dropped.** `544` counts reference entries *as the parser segmented them*, and the extractor under-segments: **60 of 544 entries (11%) are long blocks containing two or more distinct works** — one `BQvbL2sFQx` entry merges a Goodfellow *et al.* reference with a Gunasekar one and only the second was ever looked up. The true bibliography is **larger than 544**, so the true rate is **lower than 61.2%**. `BUILD` states the prohibition directly: *"it should not be quoted as 'we resolve 61% of the references in these papers.'"* Worst case is `eR4W9tnJoZ` — 12 references parsed, **7 (58%) suspected merged blocks** — whose 16.7% is untrustworthy on both numerator and denominator.

**A second, different unknown that §2.7 did not have.** For the *retrieval label snapshot* specifically, the resolution rate is **not recoverable at all**: 11 of the 26 pooled corpora have no `references.json` sidecar, so the attempted-reference denominator does not exist on disk. `B15` caveat 6 reports it as **unknown rather than substituted**. 211 references are excluded upstream as corpus gaps (`no_oa_pdf` 81, `no_openalex_match` 78, `download_failed` 52) and are out of the recall denominator — the retriever could never have surfaced them.

---

## 3.9 The claims table, refreshed

Same six resume bullets, plus the claims §1 raised separately. This supersedes §2.1 where the two disagree.

| # | Claim as §1 found it | §1 verdict | Status 2026-07-31 | Source |
|---|---|---|---|---|
| R1 | "30+ researchers at 3+ universities" | UNPROVENANCED | **STILL UNPROVENANCED.** No measurement in any wave touched user counts. §1.4A/B stand verbatim | — |
| R2 | "multi-agent workflow" | OVERSTATED | **STILL OVERSTATED.** Sharpened, not rescued: the three persona prompts share a **byte-identical 8,064-token prefix = 87.4% of the prompt**, measured, and ~88% identical text overall. That is a measurement of *how little* separates the "agents" | `NC`, `PC` |
| R3 | "53s → 18s (66%)" | UNPROVENANCED | **STILL UNPROVENANCED.** Per-node latency is measured; end-to-end has never been measured once. See CORRECTION 1 and §3.5 | `NC`, `BENCH` |
| R4 | pgvector RAG, 1536-dim, topic gating | SUPPORTED; "cannot state index type / params / metric" | **UPGRADED and now depth-aware.** Index fully specified (HNSW / `vector_cosine_ops` / `<=>` / `ef_search=80`); operating point measured; and the planner-crossover behaviour is measured at two corpus sizes (35 → 103) | `WL` W0, `ANN`, `B15` §2 |
| R5 | publish gate "blocking … contaminated … lifted quality" | OVERSTATED ×2, UNPROVENANCED ×1 | **WORSE THAN §1 THOUGHT, unchanged by §3.** Two of three signals inert across 77 runs. See CORRECTION 2 | `WL` W1 |
| R6 | Docker/FastAPI/Celery on EC2, GH Actions | SUPPORTED | **Unchanged, still SUPPORTED** | — |
| — | "lifted quality on LLM evals" / "measurably cut hallucinated critiques" | UNPROVENANCED | **STILL UNPROVENANCED, and still no before/after.** `BENCH` now shows **17** OpenReview runs across **3** pipeline versions, **every one at `no data (n=0)` scored cells**, trend `unknown`. An append-only history exists; it does not yet contain a quality trend | `BENCH` |
| — | eval `mean_precision: 1.0` | "near-tautological by construction" | **CONFIRMED and quantified, unchanged.** Honest `precision_vs_gold` **0.27**, hallucination rate **0.111**, **n = 3 papers**; a pair-based numerator would read 0.554 and double-counts | `WL` W2 |
| — | prep `:36` "pgvector … cosine similarity" | UNVERIFIED | ✅ **VERIFIED. You may say cosine** | `WL` W0 |
| — | prep `:394` "parser ≥0.55, page-anchor ≥0.75" | SUPPORTED | **Thresholds correct, implication false.** 0.55 is inert across 77 runs | `WL` W1 |
| — | retrieval quality | did not exist | **MEASURED.** dense recall@10 **0.2195** / ceiling **0.5199** = **42% of attainable**, NDCG@10 0.5191, MRR 0.7328, **n = 338 queries / 8,554 judgments / 344 docs / 5,948 chunks**. Eval corpus, local pgvector, basic chunking — **not a production retrieval number** | `B15` §3 |
| — | keyword / lexical retrieval | did not exist | **MEASURED and fixed behind a default-off flag.** Zero-row queries **321/338 → 0/338**; recall@10 **0.0022 → 0.1447 (66×)** | `B15` §4 |
| — | hybrid fusion | "deliberate stub" | **BUILT AND MEASURED — a negative.** RRF loses to dense: recall@10 **−7.0%**, NDCG@10 **−3.9%**, MAP **+4.8%**. Best coverage, worst ranking | `B15` §5 |
| — | per-run cost | "every figure is a lower bound" | **FIRST COMPLETE FIGURE: $0.20016**, of which **16.3% is matcher spend** every earlier figure omitted. All pre-fix figures remain floors by an **unrecoverable** margin | `NC` |
| — | run-to-run variance | "CV ~7% at n=3" | **SUPERSEDED: CV 15.0% at n=5** on one fixture. Quality variance **unresolvable**; no delta may be reported | `NC` |
| — | reference resolution rate | "≤19.5% upper bound", then 55.2% | **61.2% (333/544) across 15/15 topics** — with an **understated denominator** (11% merged entries), so the true rate is lower. For the *label snapshot*, the rate is **unknown**, not substituted | `BUILD`, `B15` |

---

## 3.10 Still unmeasured — the list that matters most

Supersedes §2.9. Every row here sits next to something that *is* measured, which is precisely what makes it dangerous.

| Claim | Status | Why the adjacent number does not help |
|---|---|---|
| **End-to-end / user-visible latency** | **Never measured. Not once, not approximately.** | Node replay ≠ end-to-end. A replay is one node, from a cached fixture, on a laptop, outside Celery and outside the 18-node graph, with no parse, no upload, no queue wait, no DB writes |
| **`53s → 18s`, `66%`** | **Unmeasured. No sequential baseline exists** | Measuring the fan-out's current cost does not measure the improvement the fan-out produced |
| **"no quality loss" from parallelisation** | **Unmeasured** | Asserts an eval never run, before or after. And quality variance is currently **unresolvable** at n=5 (§3.5), so it could not be run cheaply today either |
| **"lifted quality on LLM evals"** | **Unmeasured** | 17 recorded eval runs, **all** with zero scored cells |
| **Any quality *delta* on this pipeline** | **Unresolvable at present n** | CV 95% on a metric quantised at 1/79 of its range. Needs a seed, a much larger n, or a different metric |
| **30+ researchers, 3+ universities** | **Unmeasured** | No wave touched user counts. The deck still says 2 universities |
| **Publish-gate threshold `0.75` being right** | **Unmeasured. Hand-set** | The gate's *behaviour* is measured across 77 runs; its *calibration* needs human labels that do not exist |
| **Production retrieval quality** | **Unmeasured** | Every retrieval number is local pgvector, eval corpus, PyMuPDF + basic chunking |
| **Section-aware chunking arm** | **Unmeasured** | Only the basic-chunking arm exists in the numbers |
| **RRF as production behaviour** | **Measured, but on a config production does not run** | The fusion was measured with `KEYWORD_SEARCH_V2=1`; production's keyword leg returns nothing for 95% of queries |
| **RRF as a first-stage recall pool feeding a reranker** | **Explicitly not tested** | `B15` §5 names it as the profile the coverage numbers suggest, and *"does not test that claim and does not assert it"* |
| **ANN latency at the current corpus** | **Unmeasured** | Every ANN timing is from 2,124 chunks. `B15` reports no latency at all. The *quality* is re-measured; the *curve* is not |
| **Whether the ANN findings generalise** | **Explicitly no** | The crossover already moved 35 → 103 on a 2.8× corpus — the clearest possible demonstration that these are corpus-size properties |
| **Whether non-gold items are findings or hallucinations** | **Unmeasured and, under this label design, unmeasurable** | 0.27 is a lower bound by construction. The one unambiguous number is the 0.111 |
| **Retrieval quality with contentless claims excluded** | **Unmeasured, and deliberately so** | Filtering them would raise every arm without improving anything. `B15` §6 flags it as the likeliest source of a fake win |
| **True reference-resolution rate** | **Unmeasured; 61.2% is an over-estimate** | 11% of parsed entries merge two or more works, so the denominator is too small |
| **Prompt-cache gain at production scale** | **n = 2 papers, one cold panel each** | 60.7% is near the structural ceiling for a 3-call panel, where call 1 must always be cold |

**Standing note on register, carried from §1 and §2.** Where the honest version is weaker, say so. In §3 it is weaker in three places: **RRF lost**, the eval-corpus recall@10 dropped in absolute terms (because the problem got harder, not because the system got worse — and saying only the second half would be the dishonest version), and the complete cost figure is **higher** than every number quoted before it. All three are better engineering stories than the versions they replace, and none of that licenses rounding any of them up.
