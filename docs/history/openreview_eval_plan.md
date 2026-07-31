# Plan: Rebuild Noesis Eval Around Real OpenReview Peer Reviews

> Executor note: this plan was authored by Opus in plan mode. You (Codex 5.5) are the executor. Build node-by-node in the **Build order** section. Use the **Tooling & acceleration** section to parallelize and de-risk. Stop and ask only if a Phase-0 live-API assumption fails in a way the plan doesn't cover.

## Context

Today's eval (`scripts/eval/`) is **circular**: `judge.py --bootstrap-gold` makes GPT write a "gold critique," then GPT scores Noesis output against it — GPT measuring GPT-likeness. It's also **slow** (full 17-node pipeline per cell, 2–3 hrs) and `coverage` is **structurally broken** (corpora hold 1–3 papers, RAG finds nothing, judge scores 3–5). Mean stuck ≈6.97/10 against an uncalibrated 8.5 target for three weeks, partly from operational rot (stale `.pyc`, `docker cp` silently not overwriting, fixes not live during the run that scored them).

**New direction:** replace GPT-written gold with **real human peer reviews from the OpenReview API** as ground truth. Pull papers + reviewer weaknesses/questions/scores, meta-reviews, final accept/reject decisions. Measure whether Noesis recovers what real reviewers actually raised.

**Critical framing (anti-overfit):** Target researchers are **NOT primarily ML/CS**. OpenReview is ML-heavy, so it is a source of *transferable review skill* (text anchoring, severity calibration, methodological scrutiny, decision calibration) — NOT a field template to imitate. Catching a real-but-unraised, grounded issue is a **WIN**, never noise. Field stays a parameter; never tune persona *content* toward ML.

### Decisions locked with user
- **No hard deadline** — build the full system properly. Phase 0 is the recommended first slice (~2 days) but not a gate.
- **Anonymous public read** — unauthenticated `OpenReviewClient`; live-verify anon read in Phase 0.
- **Retire old GPT-gold eval after the new path is proven** — keep `judge.py` gold scoring until new eval lands, then delete.

### Verified facts (live, June 2026)
- ICLR reviews are **public, CC BY 4.0**; all stages (reviews, rebuttals, meta-review, decision) accessible even for rejected papers.
- API v2 base: `https://api2.openreview.net`; client `openreview-py` (pip; Python 3.9+; confirm container Python version in Phase 0).
- Fetch pattern: `client.get_all_notes(invitation=f'{venue_id}/-/{submission_name}', details='replies')`, then filter `submission.details['replies']` by invitation suffix (`Official_Review`, `Meta_Review`/`Decision`).
- ICLR 2024 review content fields: `summary, strengths, weaknesses, questions, soundness, presentation, contribution, confidence, rating` (rating ∈ {1,3,5,6,8,10}); API v2 wraps each in `{'value': ...}`.

### ⚠️ Assumptions to live-verify BEFORE building on them (Phase 0 gate)
1. **Anonymous read works** for `get_all_notes` on a public venue (no 403) — verify with a 1-paper pull.
2. **Exact invitation strings per venue** — ICLR 2024 vs 2023 differ; `submission_name` comes from `client.get_group(venue_id).content['submission_name']['value']`. Don't hardcode.
3. **Field names per venue/year** — `weaknesses`/`questions` exist for ICLR ≥2023; older venues bundle everything in `review`. Detect, don't assume.
4. **Meta-review / decision invitation suffix** — varies (`Meta_Review`, `Decision`, `Acceptance_Decision`). Enumerate reply invitations on one paper and log them.
5. **PDF availability** — `note.content['pdf']['value']` is a relative path under `https://openreview.net/...`; confirm direct download works anonymously.
6. **Rate limits for anon clients** — add polite delay; confirm no throttling at ~15–20 papers.

---

## Tooling & acceleration (for the executor)

Use these to move faster and keep quality high. None are required, but reach for them when they fit:

- **Subagents / parallel workers** — spin up parallel workers for independent build units. Good splits:
  - One worker on the **OpenReview data layer** (Phase 0/1) while another scaffolds the **matcher + judge** (Phase 2/3) against a stubbed gold fixture.
  - A dedicated worker to **hand-label the 30 matcher pairs** (Phase 2) in parallel with matcher code.
  - A read-only **explore** worker to map any backend internals you need (export shape, embedding util, node state) before writing against them.
  - Keep one integrator that owns merges and runs the end-to-end verification; don't let parallel workers stomp shared files (`run_eval.py`, `Makefile`).
- **Skills** — if available in your environment, use a test-writing/QA skill to generate unit tests per new module, and a code-review skill before declaring a phase done. Match existing test patterns in `services/backend/tests/`.
- **Web access** — use it to re-verify the OpenReview API (docs at `https://docs.openreview.net`, client `https://openreview-py.readthedocs.io`) if any Phase-0 assumption fails. Don't guess invitation strings — look them up or enumerate live.
- **Background runs** — full-pipeline eval is slow; run it in the background and poll, while you build the next phase. Cache (Phase 4a) makes reruns cheap.
- **Determinism first** — every LLM call: `temperature=0`. Build the cache layer (Phase 4) early-ish so iteration is fast; without it you'll burn hours re-running the 17-node pipeline.

### Hard constraints (do not violate)
- **GPT-5.2 only:** `model="gpt-5.2"` or `"gpt-5.2-chat-latest"`, **`max_completion_tokens`** (NEVER `max_tokens`), `temperature=0`, pass `**get_completion_params()` (from `app.core.openai_client`). Never `gpt-4o`.
- **Embeddings:** text-embedding-3-small, 1536-dim (reuse the ingest path's util).
- **DB:** Supabase via `supabase.table()` only. No SQLAlchemy, no local Postgres.
- **Runs inside `noesis-backend` Docker container** — the LangGraph pipeline + Supabase client live there. Use the Makefile sync that busts `.pyc` and checksum-verifies (Phase 4c) so the scored bytecode is provably live.
- **Simplicity first** (CLAUDE.md): minimum code for a trustworthy number. No speculative abstraction. Surgical changes — don't refactor working plumbing (`run_harness.py`, `run_eval.py`) beyond what's specified.

---

## Architecture at a glance

```
scripts/eval/
  fetch_openreview.py     # NEW  — pull papers+reviews → on-disk gold JSON
  atomize_reviews.py      # NEW  — LLM: reviewer free-text → discrete weakness-units (cached)
  match.py                # NEW  — embed + cosine pre-filter + LLM confirm (cached)
  judge_openreview.py     # NEW  — scoreboard: recall/precision/decision-corr/halluc/anchor
  mine_failures.py        # NEW  — cluster missed reviewer points → blind-spot report
  node_eval.py            # NEW  — isolate one node, eval vs review slice (fast inner loop)
  pipeline_cache.py       # NEW  — cache full export by (paper_hash, pipeline_version)
  _verify_live.sh         # NEW  — .pyc bust + docker cp + checksum read-back
  openreview/<venue>/<paper_id>.json   # NEW  — gold records (one file/paper)
  cache/                  # NEW  — atomize/, match/, exports/, state/  (all content-hash keyed)
  run_harness.py          # REUSE — full pipeline runner (already works)
  run_eval.py             # ADAPT — orchestrate OpenReview matrix instead of draft×corpus
  # judge.py, build_corpus.py, gold/*.gold.md  — RETIRE after new path proven
```

Reuse: `run_harness.py::run()` for full-pipeline execution; `run_harness.py::_export_result()` for export shape; `get_completion_params()` + GPT-5.2/`max_completion_tokens` convention; existing 1536-d embedding util used in ingest.

---

## Phase 0 — Live API spike + on-disk gold schema (DO FIRST; ~2 days)

**Goal:** Prove anonymous OpenReview pull works end-to-end and lock the gold schema. De-risks every later phase.

**Files:** `scripts/eval/fetch_openreview.py` (new) → `scripts/eval/openreview/<venue>/<paper_id>.json`

**Interfaces**
```python
def fetch_venue(venue_id: str, limit: int = 20, out_dir: Path = ...) -> list[Path]:
    """Anonymous OpenReviewClient(baseurl='https://api2.openreview.net').
    Per submission: resolve submission_name from group; pull replies;
    classify each reply by invitation suffix → review/meta/decision;
    download PDF; write one JSON per paper. Returns written paths."""

def _classify_reply(reply: dict) -> Literal["review","meta","decision","other"]
def _extract_review_fields(reply: dict) -> dict  # tolerant: handles {'value':..} wrap + missing fields
```

**Gold schema (`<paper_id>.json`)**
```json
{
  "paper_id": "...", "venue": "ICLR.cc/2024/Conference",
  "title": "...", "pdf_path": "openreview/ICLR2024/<id>.pdf", "abstract": "...",
  "decision": "Accept (poster)", "accepted": true,
  "reviews": [
    {"reviewer": "anon1", "rating": 6, "confidence": 4,
     "soundness": 3, "presentation": 2, "contribution": 3,
     "summary": "...", "strengths": "...", "weaknesses": "...", "questions": "..."}
  ],
  "meta_review": {"recommendation": "...", "primary_reasons": "..."},
  "raw_reply_invitations": ["...Official_Review", "...Meta_Review", "...Decision"]
}
```

**Acceptance**
- `python scripts/eval/fetch_openreview.py --venue ICLR.cc/2024/Conference --limit 3` writes 3 valid JSONs, ≥3 reviews each, non-empty `weaknesses`, a decision, downloadable PDF — **anonymously**.
- `raw_reply_invitations` logged so assumptions #2/#4 are observable.
- Fails loudly (not silently empty) if a field/invitation is missing.

---

## Phase 1 — Atomize reviewer text into matchable weakness-units

**Goal:** One weakness = one recall unit, with severity weight.

**Files:** `scripts/eval/atomize_reviews.py`; cache `scripts/eval/cache/atomize/`.

```python
def atomize_paper(gold: dict) -> list[dict]:
    """LLM-split reviews into atomic units. Cached by
    sha256(paper_id + reviewer + weaknesses+questions + PROMPT_VERSION)."""
# unit: {"unit_id","reviewer","text","kind":"weakness|question","severity_weight":float}

def compute_severity_weight(rating, confidence, in_meta: bool) -> float:
    """Deterministic (NOT LLM). Base (1 - rating/10), scale by confidence/5,
    ×1.5 if theme appears in meta_review.primary_reasons (cosine ≥0.6). Clamp [0.1,1.0]."""
```
- LLM: `gpt-5.2`, `max_completion_tokens`, `temperature=0`, structured JSON, `**get_completion_params()`. Prompt: "Split into atomic, independently-verifiable concerns; don't merge distinct issues; don't invent; preserve reviewer wording in `text`." `PROMPT_VERSION` constant → bumping busts cache.

**Acceptance**
- Re-run on unchanged gold → **zero** LLM calls (cache hit).
- Spot-check 1 paper: each unit a single concern; 3–8/reviewer typical.
- Weights reproducible across runs.

---

## Phase 2 — Cheap semantic matcher (Noesis item ↔ reviewer unit)

**Goal:** Map without N×M LLM calls.

**Files:** `scripts/eval/match.py`; cache `scripts/eval/cache/match/`.

```python
def match(noesis_items: list[dict], review_units: list[dict]) -> list[Match]:
    """1. Embed both sides (1536-d), batched.
       2. Cosine pre-filter: keep pairs >= COS_THRESHOLD (start 0.55).
       3. LLM confirm ONLY surviving pairs (batched), temp=0.
       4. Cache confirm by sha256(noesis_text+unit_text+PROMPT_VERSION)."""
# Match: {"noesis_id","unit_id","cosine":float,"confirmed":bool,"reason":str}
```
- `noesis_items` = revision tasks + reviewer-panel issues + coverage gaps (text + anchor).
- Confirm prompt: "Same underlying concern? Same topic but different concern = NO." → `{confirmed, reason}`.
- `COS_THRESHOLD`, `PROMPT_VERSION` = module constants. Tune threshold once vs ~30 hand-labeled pairs; record chosen value + precision/recall in a comment.

**Acceptance**
- 15-paper set: confirm calls ≪ N×M (log reduction; target >80% eliminated by cosine).
- Re-run unchanged → ~0 new calls.
- 30 hand-labeled pairs: matcher agreement ≥0.85.

---

## Phase 3 — New judge + scoreboard

**Files:** `scripts/eval/judge_openreview.py`; adapt `run_eval.py` → `results/openreview_scoreboard.json`.

**Metrics (per paper + aggregate)**
1. **Weakness recall (severity-weighted)** = Σ weight(matched) / Σ weight(all units).
2. **Precision/noise** = of Noesis items, fraction that match a reviewer unit OR are grounded in paper text (LLM grounding check vs PDF only).
3. **Decision correlation** = Spearman ρ between Noesis `readiness_score` and `accepted` (≥10 papers).
4. **Hallucination rate** = Noesis claims false vs **paper text only**. Grounded-but-unraised issue NEVER penalized.
5. **Anchor quality** = % tasks with verbatim paper quote (`anchor_text` present + found in PDF text).

```python
def score_paper(export_path: Path, gold: dict, matches: list[Match]) -> dict
def aggregate(per_paper: list[dict]) -> dict   # means + decision ρ
```
- Reuse export shape from `run_harness.py::_export_result` (`durable_revision_tasks`, `reviewer_panel_outputs`, `coverage_gaps`, `analysis.analysis_metadata.readiness_score`).
- Grounding/halluc: `gpt-5.2`, temp=0, paper text chunk-fed; cached by `(claim_hash, paper_hash)`.

**Acceptance**
- Scoreboard JSON: 5 metrics/paper + aggregate, traceable evidence (matched unit_ids, halluc list).
- Decision ρ over ≥10 papers.
- Two consecutive runs on cached outputs differ by 0.

---

## Phase 4 — Fast-iteration infra

**Files:** `scripts/eval/pipeline_cache.py`, `scripts/eval/node_eval.py`, `scripts/eval/_verify_live.sh`; Makefile targets; small `run_harness.py` change to read/write cache.

**4a. Full-pipeline cache**
```python
def cache_key(paper_path: Path, pipeline_version: str) -> str  # sha256(pdf_bytes + version)
def get_cached(key) -> Path | None
def put_cached(key, export_path) -> None
```
- `pipeline_version` = hash of `services/backend/app/workflows/draft_analysis/` dir contents. Unchanged pipeline → never re-runs.

**4b. Node-level eval** — `node_eval.py` runs ONE node from a saved upstream state fixture, evals vs the relevant review slice via `match.py`. Dump `DraftAnalysisState` after each node during one full run → `cache/state/<paper>/<node>.json`; loader rehydrates.

**4c. Ops reliability** — `make eval-openreview` ALWAYS: (1) delete `*.pyc` in source tree before sync; (2) `docker cp` then **md5 read-back compare** host↔container, fail if mismatch; (3) print live `pipeline_version` at run start. Logic in `_verify_live.sh`.

**Acceptance**
- Unchanged pipeline → 2nd `make eval-openreview` does 0 pipeline runs, finishes in minutes.
- `node_eval.py --node detect_gaps --paper <id>` <30s, reports gap-slice recall.
- Edit a node file → checksum read-back PASSES and `pipeline_version` changes.

---

## Phase 5 — Failure-mining loop

**Files:** `scripts/eval/mine_failures.py` → `results/blindspots.md`.

**Procedure (repeatable)**
1. Collect every **missed** reviewer unit across all papers (matches with no `confirmed=True` candidate).
2. Embed misses; cluster (cosine agglomerative ~0.5) into blind-spot categories.
3. LLM labels each cluster (name + exemplar), temp=0, cached.
4. Per cluster, emit a **fix proposal** → concrete locus: which node (`detect_gaps_node`, `diagnostic_findings_node`, a reviewer persona, or a NEW check node between `editor_pass_node` and `reviewer_panel_node` per graph.py routing) + which prompt/check.
5. Re-run after a fix; confirm targeted cluster recall rises without precision dropping.

**Acceptance**
- `blindspots.md` lists clusters ranked by Σ severity-weight, each with named node + concrete change.
- After ONE applied fix, that cluster's recall improves on next run (closed loop).

---

## Phase 6 — Anti-overfitting guardrails

**Files:** additions to `judge_openreview.py`; `scripts/eval/heldout/manifest.json`.

- **Field is a parameter** — tag each paper's field; report metrics overall AND per-field. Never collapse to ML-only.
- **Held-out transfer set** — 3–5 hand-collected **non-ML** papers (even without formal reviews); run Noesis, sanity-check anchor quality + halluc hold. Transfer check, not a recall number.
- **Persona discipline** — fixes may change review *behavior* (anchor/severity/scrutiny), MUST NOT inject ML-specific *content*. `mine_failures.py` output prints this reminder before any prompt edit.

**Acceptance**
- Scoreboard reports per-field breakdown.
- Held-out non-ML papers: 0 hallucinations, anchor quality within 10% of ML set.

---

## Build order

1. **Phase 0** — `fetch_openreview.py` + gold schema. Live-verify all 6 API assumptions FIRST (`--limit 1`, log `raw_reply_invitations`). Gate everything on this.
2. **Phase 4c** — ops Makefile target + `_verify_live.sh` early, so every later run is trustworthy.
3. **Phase 1** — `atomize_reviews.py` + caching + deterministic severity weights.
4. **Phase 2** — `match.py` + hand-label 30 pairs to set threshold.
5. **Phase 3** — `judge_openreview.py` + adapt `run_eval.py` → first real scoreboard.
6. **Phase 4a/4b** — pipeline cache + node-level eval.
7. **Phase 5** — `mine_failures.py`; apply first fix; prove closed loop.
8. **Phase 6** — held-out + per-field reporting.
9. **Retire** old `judge.py` gold scoring + `build_corpus.py` + `gold/*.gold.md` once new path is green.

---

## Honest demo expectation

Do **NOT** promise 8.5 mean — uncalibrated + circular. Realistic first numbers (Phases 0–3, ~15 ICLR papers):
- **Severity-weighted weakness recall ≈ 0.35–0.55.**
- **Decision correlation (Spearman ρ) ≈ 0.3–0.6.**
- **Hallucination rate < 5%** (the trust metric — push toward 0).

**Demo sentence:** "Against real ICLR peer reviews, Noesis recovers ~45% of severity-weighted reviewer-raised weaknesses with under 5% hallucination, and its readiness score correlates with real accept/reject decisions (ρ≈0.5) — measured on human ground truth, not GPT-written gold."

---

## Verification (end-to-end)

```bash
# Phase 0 smoke (anonymous, 1 paper)
python scripts/eval/fetch_openreview.py --venue ICLR.cc/2024/Conference --limit 1

# Full new eval (container, via Makefile that busts .pyc + checksum-verifies)
make eval-openreview LIMIT=15        # -> results/openreview_scoreboard.json

# Fast inner loop
python scripts/eval/node_eval.py --node detect_gaps --paper <id>

# Closed loop
python scripts/eval/mine_failures.py # -> results/blindspots.md

# Determinism: run twice on cached outputs -> identical scoreboard
```
