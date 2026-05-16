# Noesis — Master Implementation Plan

**Last updated:** May 12, 2026
**Purpose:** Executable task list. Feed this file as a prompt to Claude Code or Codex to implement each phase. Each task has exact file paths, what to change, and dependencies.

**Repo root:** `/Applications/Ashwin/Programming/Personal Projects/startup/noesis`
**Backend root:** `services/backend/app`
**Frontend root:** `services/frontend/src`

---

## Execution Notes for AI Agents

- Before any phase: run `/claude-mem:smart-explore` on the relevant files to read current state without burning tokens on full file reads
- After each phase's code changes: run `/simplify` to catch quality/reuse issues
- For multi-file code generation: invoke `/full-output-enforcement` to prevent truncated output
- Tasks marked `[PARALLEL]` can be dispatched to separate subagents simultaneously
- Tasks marked `[SEQUENTIAL]` must wait on the prior task in that group
- Always run `cd services/backend && python3 -m pytest tests/ -v` after backend changes
- Always run `cd services/frontend && npx tsc --noEmit` after frontend changes

---

## STEP 0 — Stage 1 Verification (Do First, ~2 hours)

**No new code until this is confirmed working.**

### Tasks

1. Grep for Stage 1 invocation and result handling:
   ```bash
   grep -n "run_stage1_editing\|stage1" services/backend/app/services/draft_processing.py
   grep -n "stage1\|grammar_issues\|formatting_issues" services/backend/app/api/routes/drafts.py
   grep -rn "stage1\|grammar_issues\|Stage1" services/frontend/src/
   ```

2. **Canonical storage contract:** Stage 1 is stored in `draft_analysis.analysis["editing_feedback"]`, not `analysis_metadata.stage1`.

3. **If not in API response:** In `api/routes/drafts.py`, expose it as `editing_feedback` in the GET `/drafts/{id}/analysis` response.

4. **If not rendered in UI:** In `services/frontend/src/pages/DraftAnalysis.tsx`, ensure the `Editing Pass` tab renders grammar/citation/formatting issues from `editing_feedback`.

5. Document result in a comment at top of `draft_processing.py`: Stage 1 fires on upload, result stored at `draft_analysis.analysis.editing_feedback`.

**Exit:** Stage 1 grammar/citation/formatting output visible in UI alongside Stage 2 feedback.

---

## PHASE 1 — Structured Outputs + Eval Foundation (Weeks 1–2)

**Goal:** Eliminate JSON parse crashes. Establish quality measurement baseline.

### 1A — Pydantic Schemas (0.5 day) [SEQUENTIAL: must be first]

**File to create:** `services/backend/app/workflows/draft_analysis/schemas.py`

Create Pydantic v2 `BaseModel` classes for every LLM node output:

```python
# Required models (minimum — expand fields to match current prompt output shapes):
ClaimExtractionOutput       # fields: claims: list[ClaimItem]
StructureExtractionOutput   # fields: sections, word_count, has_abstract, etc.
CitationMappingOutput       # fields: claims_with_citations: list
GapDetectionOutput          # fields: coverage_gaps: list
ReviewerFeedbackOutput      # fields: feedback_items: list, overall_assessment, priority_actions
# Phase 3 additions (add placeholders now, implement later):
EditorPassOutput            # fields: proceed_to_review, fatal_flaws, writing_quality, notes
ReviewerOutput              # fields: reviewer_id, summary, strengths, weaknesses, questions_to_authors, limitations_to_address, rating (1-10), confidence (1-5), recommendation
MetaReviewOutput            # fields: overall_recommendation, decision_rationale, must_address, nice_to_address, consensus_strengths, consensus_weaknesses, reviewer_agreement_level, score_summary
```

Each model uses `model_config = ConfigDict(extra="forbid")` to reject unknown fields.

### 1B — State Migration (1 day) [SEQUENTIAL: after 1A]

**File:** `services/backend/app/workflows/draft_analysis/state.py`

- Convert all `TypedDict` definitions to Pydantic v2 `BaseModel`
- Add `schema_version: int = 1` field to `DraftAnalysisState`
- For parallel fan-in support (Phase 3): add `reviewer_outputs: Annotated[list, lambda a, b: a + b]` field
- Add `editor_decision: EditorPassOutput | None = None`
- Add `meta_review: MetaReviewOutput | None = None`
- Update all node function signatures to accept/return the new typed state
- **Deploy note:** Drain `draft_analysis_checkpoints` table rows during this deploy. No in-flight drafts to protect.

### 1C — response_format on All LLM Nodes (1.5 days) [PARALLEL with 1D once 1B done]

For each file below, replace `json.loads(response.choices[0].message.content)` and all `_extract_json_object()` calls with `client.beta.chat.completions.parse(response_format=<Schema>)`. Access result via `result.parsed`.

Files to modify:
- `services/backend/app/workflows/draft_analysis/nodes/claim_extraction.py:145` → `response_format=ClaimExtractionOutput`
- `services/backend/app/workflows/draft_analysis/nodes/reviewer_feedback.py` → `response_format=ReviewerFeedbackOutput`
- `services/backend/app/workflows/draft_analysis/nodes/citation_mapping.py` → `response_format=CitationMappingOutput`
- `services/backend/app/workflows/draft_analysis/nodes/gap_detection.py` → `response_format=GapDetectionOutput`
- `services/backend/app/workflows/draft_analysis/nodes/structure_extraction.py` → `response_format=StructureExtractionOutput`
- `services/backend/app/services/stage1_editing.py:46` → replace `_extract_json_object` with `response_format`
- `services/backend/app/services/reviewer1_feedback.py:43` → same

Each node: wrap the `client.beta.chat.completions.parse(...)` call in a try/except `ValidationError`. On `ValidationError`, re-prompt once with the error message appended to the user message. Max 2 retries per node, then raise.

### 1D — retry_utils Validation Loop (0.5 day) [PARALLEL with 1C]

**File:** `services/backend/app/services/retry_utils.py`

Add:
1. `retry_on_validation_error(max_attempts=2)` decorator — catches `pydantic.ValidationError`, attaches error string to re-prompt, retries. Wraps the full LLM call + parse.
2. `_OPENAI_SEMAPHORE = asyncio.Semaphore(20)` module-level — wrap all OpenAI async calls with `async with _OPENAI_SEMAPHORE`. Prevents Celery worker dogpile when 4 concurrent workflows run.

### 1E — EmbeddingProvider Abstraction (0.5 day) [PARALLEL with 1C/1D]

**File to create:** `services/backend/app/services/embedding_provider.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class EmbeddingProvider(Protocol):
    dim: int
    model_name: str
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class OpenAIEmbeddingProvider:
    dim = 1536
    model_name = "text-embedding-3-large"
    async def embed(self, texts): ...  # wrap existing embed_chunks logic

class SpecterEmbeddingProvider:  # stub for future use
    dim = 768
    model_name = "specter2"
    async def embed(self, texts): raise NotImplementedError
```

Update all `embed_chunks(...)` call sites in `rag_ingest.py`, `rag_retrieval.py`, `structured_data_storage.py` to use `OpenAIEmbeddingProvider().embed(...)`.

**Also fix:** `services/backend/app/services/draft_comparison.py:44` — change `model="text-embedding-3-small"` to `model="text-embedding-3-large"`. Inconsistency with all other embedding calls.

### 1F — Golden Dataset + Perturbation Generator (2 days, partly founder time) [PARALLEL with 1C/1D/1E]

**Directory to create:** `services/backend/tests/eval/`

Structure:
```
tests/eval/
├── __init__.py
├── conftest.py
├── golden/
│   ├── manuscripts/          # 10 PDFs from OpenReview (ICLR/NeurIPS/CHI 2023-2024)
│   ├── annotations/
│   │   ├── {paper_id}_claims.json      # LLM-bootstrapped, founder spot-checked
│   │   ├── {paper_id}_citations.json   # paper bibliography = ground truth
│   │   └── {paper_id}_feedback.json    # real OpenReview reviews = gold feedback
│   └── manifest.yaml
├── perturbations.py          # adversarial injection script
├── metrics/
│   ├── set_metrics.py        # precision(pred, gold), recall(pred, gold), f1(p, r)
│   ├── fuzzy_match.py        # ROUGE-L, span overlap for text anchors
│   ├── citation_metrics.py   # exact-match P/R on citation sets
│   └── llm_judge.py          # gpt-5-mini rubric scorer (specificity, actionability, non-hallucination)
├── runners/
│   ├── run_claim_extraction.py
│   └── run_citation_mapping.py
├── test_eval_claim_extraction.py   # assert P/R >= baseline values
├── test_eval_citation_exact_match.py
└── baselines/
    └── baseline_metrics.json       # {claim_extraction: {precision: 0.0, recall: 0.0}, ...} — zeroed until first run
```

**`perturbations.py`:** Takes a paper text, injects N false author citations ("Johnson et al. 2024 showed X" where paper doesn't exist) and N numerical contradictions. Returns perturbed text + ground truth injection list. Used for hallucination detection eval.

**Golden set sourcing:** Use `openreview-py` API to pull 10 papers with their reviews. Script: `services/backend/scripts/fetch_golden_set.py`. Target: 6 HCI/ML papers (ICLR, CHI) + 4 biomedical (PLOS open peer review). Store PDFs in `tests/eval/golden/manuscripts/`.

**`llm_judge.py`:** Uses `gpt-5-mini` with `response_format` (not gpt-5.2 — 10× cheaper). Rubric: specificity (0-10), actionability (0-10), reviewer_authenticity (0-10), non_hallucination (0-10). Returns mean score per feedback item.

### 1G — Eval CI Wiring (0.5 day) [SEQUENTIAL: after 1F]

**Files to create:**
- `.github/workflows/eval-pr-gate.yml` — triggers on PR touching `app/workflows/`, `app/services/claim_analysis.py`, `app/services/reviewer_feedback.py`, `app/services/draft_anchor_qa.py`, `app/services/rag_*.py`. Runs 3-manuscript smoke set. Fails CI if any metric drops >5% absolute vs `baseline_metrics.json`.
- `.github/workflows/eval-weekly.yml` — cron `0 8 * * 0` (Sun 3am EST). Rotates 5/10 manuscripts per week. Posts report to `eval-reports/{date}.md`. Opens GitHub issue on regression.
- `services/backend/scripts/run_evals.py` — manual trigger, accepts `--papers N` and `--budget USD` flags.
- `services/backend/scripts/score_against_baseline.py` — reads current metrics + baseline, returns exit code 1 if regression.

**Phase 1 exit criteria:**
- [ ] Zero JSON parse crashes in 7-day staging run
- [ ] `npx tsc --noEmit` passes clean
- [ ] `python3 -m pytest tests/ -v` passes (141+ tests)
- [ ] PR-gate workflow green on a test PR
- [ ] `baseline_metrics.json` written with first real values
- [ ] Embedder abstraction in place, `draft_comparison.py` uses `3-large`

---

## PHASE 2 — PDF Highlighting + HNSW Tuning (Week 3)

Two independent workstreams — dispatch to parallel subagents.

### 2A — PDF Sentence-Level Coordinates [PARALLEL]

**Problem:** GROBID extracts coordinates at section level only. Claim anchoring uses character offsets in plain text. PDF.js needs `{page, x1, y1, x2, y2}`. These coordinate spaces are never reconciled — "view in document" either fails or highlights wrong region.

**Fix:**

1. **`services/backend/app/services/grobid_client.py`**
   - In `process_pdf()` / XML parsing: after extracting section `<div>` elements, also extract `<s>` (sentence) elements with their `coords` attributes
   - GROBID coords format: `"page,x1,y1,x2,y2"` — parse to `{page: int, x1: float, y1: float, x2: float, y2: float}`
   - Return `sentence_coords: list[{text: str, coords: dict}]` per section
   - Store in section dict: `section["sentences"] = [{text, coords}, ...]`

2. **`services/backend/app/services/draft_processing.py`**
   - When building `draft_chunks`, store `sentence_coords` list in `chunk.metadata["sentence_coords"]`

3. **`services/backend/app/services/draft_anchor_qa.py`**
   - In `attach_feedback_qa()` and text anchoring logic: after fuzzy-matching claim text to a sentence, look up that sentence in `sentence_coords`
   - Emit `page_coords: {page, x1, y1, x2, y2}` alongside every anchored claim
   - PDF.js coordinate transform: `y_pdfjs = page_height - y_grobid` (GROBID origin top-left; PDF.js bottom-left)

4. **`services/backend/app/api/routes/drafts.py`**
   - Include `page_coords` in each claim object in the GET analysis response

5. **`services/frontend/src/components/DocumentViewer.tsx`**
   - Add PDF.js highlight layer: when a claim has `page_coords`, render a highlight rect on the correct page
   - On claim click in `ReviewerFeedbackTab`, scroll PDF viewer to that page and flash the highlight
   - Use `react-pdf`'s `customTextRenderer` or overlay `<div>` positioned absolutely over the PDF canvas

### 2B — HNSW Index Tuning [PARALLEL]

**Problem:** HNSW indexes exist but use Postgres defaults (`m=16, ef_construction=64`). `document_claims` uses IVFFLAT (inconsistent). No `ef_search` set at query time (defaults to 40, trades recall for speed).

1. **Write benchmark first** — `services/backend/tests/eval/test_eval_recall_benchmark.py`:
   - Take 500 fixed queries (can bootstrap from existing chunk content)
   - Run both brute-force exact NN and HNSW query
   - Measure recall@10: fraction of true top-10 found by HNSW
   - Record baseline before any index changes

2. **`services/backend/migrations/019_hnsw_retune.sql`** (run during off-hours, Sunday 3am EST):
   ```sql
   -- document_chunks: new tuned index
   CREATE INDEX CONCURRENTLY idx_document_chunks_embedding_v2
       ON document_chunks USING hnsw (embedding vector_cosine_ops)
       WITH (m = 24, ef_construction = 128);
   DROP INDEX CONCURRENTLY idx_document_chunks_embedding;
   ALTER INDEX idx_document_chunks_embedding_v2 RENAME TO idx_document_chunks_embedding;

   -- draft_chunks: same
   CREATE INDEX CONCURRENTLY idx_draft_chunks_embedding_v2
       ON draft_chunks USING hnsw (embedding vector_cosine_ops)
       WITH (m = 24, ef_construction = 128);
   DROP INDEX CONCURRENTLY idx_draft_chunks_embedding;
   ALTER INDEX idx_draft_chunks_embedding_v2 RENAME TO idx_draft_chunks_embedding;

   -- document_claims: migrate IVFFLAT → HNSW
   DROP INDEX CONCURRENTLY idx_document_claims_embedding;
   CREATE INDEX CONCURRENTLY idx_document_claims_embedding
       ON document_claims USING hnsw (embedding vector_cosine_ops)
       WITH (m = 24, ef_construction = 128);
   ```

3. **`services/backend/migrations/03-vector-search-function.sql`** — add to top of each RPC function body:
   ```sql
   SET LOCAL hnsw.ef_search = 80;
   ```

4. **`services/backend/app/services/rag_retrieval.py:67–123`** — add timing around retrieval calls, log `latency_ms`, top score, bottom score to structured log. Used by eval benchmark.

5. Re-run `test_eval_recall_benchmark.py`. If recall@10 drops or latency regresses → rollback via `CREATE INDEX CONCURRENTLY` with old params.

**Phase 2 exit criteria:**
- [ ] "View in document" navigates to correct PDF location and highlights claim text
- [ ] Recall@10 ≥ pre-tune baseline
- [ ] p95 retrieval latency ≤ pre-tune baseline
- [ ] All 3 HNSW indexes rebuilt with `m=24, ef_construction=128`
- [ ] IVFFLAT on `document_claims` replaced with HNSW

---

## PHASE 3 — Peer Review Panel + Agentic Robustness (Weeks 4–6)

### 3A — Editor Pass Node (3–4 hrs) [SEQUENTIAL: must be first in Phase 3]

**File to create:** `services/backend/app/workflows/draft_analysis/nodes/editor_pass.py`

Uses `gpt-5-mini` (fast, cheap ~$0.0003/call). Runs before reviewer panel.

Output schema: `EditorPassOutput` (already defined in `schemas.py` from Phase 1):
- `proceed_to_review: bool`
- `fatal_flaws: list[str]` — e.g. "Missing Methods section", "No experimental results"
- `scope_appropriate: bool`
- `writing_quality: Literal["publishable", "needs_revision", "major_revision"]`
- `notes: str`

Context provided to model: draft structure (sections present, word count) + first 2000 chars of draft (abstract + intro) + Stage 1 results if available.

If `proceed_to_review = False` → graph routes directly to `synthesize_report` with a desk-reject message. Skip the 4-reviewer panel entirely.

Store result: `supabase.table("draft_analysis").update({"analysis_metadata": {**existing, "editor_decision": editor_decision.model_dump()}})`.

### 3B — Reviewer Panel Node (1 day) [SEQUENTIAL: after 3A]

**File to create:** `services/backend/app/workflows/draft_analysis/nodes/reviewer_panel.py`

Single function `reviewer_panel_node(state)` handles all 4 reviewer types. LangGraph `Send` calls it 4× in parallel with different `reviewer_type` injected into state.

**4 reviewer configurations (build as `REVIEWER_CONFIGS` dict):**

| reviewer_type | System prompt focus | Context slice from state |
|---|---|---|
| `"novelty"` | Contribution clarity, novelty vs prior work, venue appropriateness. Rating calibration: "If incremental, rate 4-5 not 6-7." | draft intro/conclusion (2000 chars each), claim list filtered to type=`contribution` |
| `"methodology"` | Experimental design, baselines appropriateness, statistical significance, ablations, reproducibility (hyperparams, seeds, compute). | claims filtered to type=`empirical`/`experimental`, citation quality per claim, structural_checks output |
| `"coverage"` | Missing citations, positioning accuracy, conflicting evidence not acknowledged. Fed gap_detection output directly. | gap_detection output, external_source_discovery output, claims of type=`citation_needed` |
| `"clarity"` | Writing clarity, reproducibility from paper alone, figure/table quality, limitations honesty. | structure (section list, has_abstract, has_limitations), word count, figure captions if available |

All 4 use `response_format=ReviewerOutput` (structured outputs, no parse failures).

**Rating calibration block** (include in every reviewer system prompt):
```
Use the full 1-10 scale honestly. At major venues ~10-15% of papers score 8+, ~25% score 6-7, ~40% score 4-5, ~15% score 1-3.
If you are inclined to give a 6, ask: would this paper be accepted as-is? If not, it is a 5 or below.
```

**Routing function for graph.py:**
```python
from langgraph.types import Send

def route_to_reviewer_panel(state):
    if state.get("editor_decision") and not state["editor_decision"].proceed_to_review:
        return "synthesize_report_node"
    return [Send("reviewer_panel_node", {**state, "reviewer_type": rt})
            for rt in ["novelty", "methodology", "coverage", "clarity"]]
```

**State reducer for fan-in** (in `state.py`, already added in Phase 1):
```python
reviewer_outputs: Annotated[list[ReviewerOutput], lambda a, b: a + b]
```

Persist each reviewer output to `reviewer_panel_outputs` table (see migration 3F).

### 3C — Meta-Reviewer Node (3–4 hrs) [SEQUENTIAL: after 3B]

**File to create:** `services/backend/app/workflows/draft_analysis/nodes/meta_reviewer.py`

Runs after all 4 parallel reviewer nodes complete (LangGraph fan-in automatic via reducer).

Input: `state["reviewer_outputs"]` — list of 4 `ReviewerOutput` objects.

Output schema: `MetaReviewOutput`:
- `overall_recommendation: Literal["accept", "minor_revision", "major_revision", "reject"]`
- `decision_rationale: str` — synthesizes reviewer positions, names conflicts explicitly
- `must_address: list[str]` — blocking items
- `nice_to_address: list[str]` — non-blocking
- `consensus_strengths: list[str]`
- `consensus_weaknesses: list[str]`
- `reviewer_agreement_level: Literal["high", "medium", "low"]`
- `score_summary: dict[str, int]` — `{"novelty": 7, "methodology": 5, ...}`

Key prompt instructions: do NOT average ratings mechanically. Surface reviewer conflicts explicitly. Be decisive — "borderline with clear path to acceptance" is fine, "it depends" is not.

Persist to `meta_reviews` table (see migration 3F).

### 3D — Graph Wiring (2–3 hrs) [SEQUENTIAL: after 3A/3B/3C]

**File:** `services/backend/app/workflows/draft_analysis/graph.py`

Changes:
1. Import 3 new nodes: `editor_pass_node`, `reviewer_panel_node`, `meta_reviewer_node`
2. Register nodes: `workflow.add_node("editor_pass_node", ...)`, `workflow.add_node("reviewer_panel_node", ...)`, `workflow.add_node("meta_reviewer_node", ...)`
3. Add progress wrappers for editor_pass (77→80%) and meta_reviewer (90→95%)
4. Replace edge: `structural_checks_node → generate_reviewer_feedback_node` with:
   - `structural_checks_node → editor_pass_node`
   - `editor_pass_node → conditional(route_to_reviewer_panel)`
   - `reviewer_panel_node → meta_reviewer_node` (fan-in: LangGraph waits for all 4 Send branches)
   - `meta_reviewer_node → synthesize_report_node`
5. Keep `generate_reviewer_feedback_node` in graph for now but mark deprecated — will remove in Phase 4 cleanup

Also in this file: **parallelize `literature_search`** via `Send` API — fan out one `Send` per claim instead of sequential loop. This alone cuts `literature_search` latency from N×3s to ~3s.

### 3E — Selective Reflection on 2 Nodes (0.5 day) [PARALLEL with 3D]

**Files:** `nodes/claim_extraction.py`, `nodes/reviewer_feedback.py` (or `reviewer_panel.py` after Phase 3)

After `client.beta.chat.completions.parse(...)`, add inline quality check:
- Call `gpt-5-mini` with a 3-question rubric: "Are outputs specific? Anchored to sections/claims? Non-generic?"
- If score < 0.6 AND attempts < 2: re-run with failure reason appended to prompt
- If score ≥ 0.6 OR attempts exhausted: continue

**Do NOT add reflection to other nodes** — diminishing returns, latency cost not justified.

### 3F — Database Migrations (1 hr) [PARALLEL with 3D/3E]

**File to create:** `services/backend/migrations/021_reviewer_panel.sql`

```sql
CREATE TABLE IF NOT EXISTS reviewer_panel_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    summary TEXT,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    questions_to_authors JSONB DEFAULT '[]',
    limitations_to_address JSONB DEFAULT '[]',
    rating INT CHECK (rating BETWEEN 1 AND 10),
    confidence INT CHECK (confidence BETWEEN 1 AND 5),
    recommendation TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    overall_recommendation TEXT,
    decision_rationale TEXT,
    must_address JSONB DEFAULT '[]',
    nice_to_address JSONB DEFAULT '[]',
    consensus_strengths JSONB DEFAULT '[]',
    consensus_weaknesses JSONB DEFAULT '[]',
    reviewer_agreement_level TEXT,
    score_summary JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE reviewer_feedback ADD COLUMN IF NOT EXISTS reviewer_id TEXT DEFAULT 'legacy';

ALTER TABLE reviewer_panel_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "reviewer_panel_outputs_select" ON reviewer_panel_outputs FOR SELECT
    USING (draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid()));
CREATE POLICY "meta_reviews_select" ON meta_reviews FOR SELECT
    USING (draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid()));
```

**File to create:** `services/backend/migrations/020_workflow_cost_ledger.sql`

```sql
CREATE TABLE IF NOT EXISTS workflow_cost_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    estimated_cost_usd NUMERIC(10,6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE workflow_cost_ledger ENABLE ROW LEVEL SECURITY;
```

### 3G — Agentic Robustness (1.5 days) [PARALLEL with 3B/3C]

**`services/backend/app/services/llm_budget.py`** (new file):
- `record_llm_call(draft_id, node_name, model, input_tokens, output_tokens)` — writes to `workflow_cost_ledger`
- `MODEL_COSTS = {"gpt-5.2-chat-latest": {"input": 0.015, "output": 0.06}, "gpt-5-mini": {"input": 0.0002, "output": 0.0006}}` (per 1k tokens — update with current OpenAI pricing)
- Call `record_llm_call()` at the end of every LangGraph node that calls an LLM, using `response.usage.prompt_tokens` and `response.usage.completion_tokens`

**`services/backend/app/workflows/draft_analysis/checkpoints.py`**:
- On checkpoint load: check `state.schema_version == 1` (or current). If mismatch: raise `CheckpointVersionError`, force full re-run.

**Idempotency guards** — add DB cache-hit check to these nodes (mirror the pattern from `reviewer_feedback.py`):
- `nodes/claim_extraction.py` — check `draft_claims` table for existing rows with this `draft_id`
- `nodes/citation_mapping.py` — check `citation_suggestions` table
- `nodes/gap_detection.py` — check `coverage_gaps` table

**Circuit breaker** — add `pybreaker` to `requirements.txt`. In `retry_utils.py`:
```python
import pybreaker
_openai_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)
# Wrap all OpenAI calls: @_openai_breaker
```

### 3H — API + Frontend Panel UI (1–2 days) [SEQUENTIAL: after 3F]

**`services/backend/app/api/routes/drafts.py`** — add to GET `/drafts/{id}/analysis` response:
```python
{
    ...existing fields...,
    "editing_feedback": analysis_payload.get("editing_feedback"),
    "editor_decision": analysis_metadata.get("editor_decision"),
    "reviewer_panel": supabase.table("reviewer_panel_outputs").select("*").eq("draft_id", draft_id).execute().data,
    "meta_review": supabase.table("meta_reviews").select("*").eq("draft_id", draft_id).limit(1).execute().data[0] if ... else None,
}
```

**Frontend — new/modified components:**

`services/frontend/src/components/draft-analysis/`

1. **`EditingPassTab.tsx`** — shows grammar_issues/citation_issues/formatting_issues from `editing_feedback`. Badge count per category.

2. **`EditorDecisionCard.tsx`** (new) — shows `proceed_to_review` status, `writing_quality` badge, `fatal_flaws` list if any.

3. **`MetaReviewCard.tsx`** (new) — top-of-page summary: `overall_recommendation` badge (color-coded), score table (4 reviewer ratings), `must_address` + `nice_to_address` lists, `consensus_strengths`.

4. **`ReviewerPanelTabs.tsx`** (new) — 4 tabs (Novelty | Methodology | Coverage | Clarity), each tab shows: rating/confidence badges, summary, strengths/weaknesses columns, questions_to_authors, limitations_to_address.

5. **Peer-review surface** — layout order: `EditorDecisionCard` → `MetaReviewCard` → `ReviewerPanelTabs`, with legacy actionable feedback as fallback/continuation if `reviewer_panel` is empty.

### 3I — Figure Caption Cross-Reference (0.5 day) [PARALLEL with 3H]

**`services/backend/app/services/grobid_client.py`**:
- Extract `<figure>` and `<table>` elements from TEI XML
- Return `figures: list[{id, caption, in_text_refs: list[str]}]` and `tables: list[{id, caption, content_text}]`

**New file: `services/backend/app/services/figure_text_consistency.py`**:
- `check_figure_text_consistency(figures, tables, draft_text) -> list[Inconsistency]`
- Extract all numbers from captions (regex `\d+\.?\d*%?`)
- Find same numbers in surrounding text (±500 chars of figure reference)
- Flag: number in caption but different value in text (within rounding tolerance ±0.5%)
- Return `{figure_id, caption_value, text_value, context}` per inconsistency

Add inconsistencies as new category in `structural_checks` node output. Expose in frontend as "Figure/Text Inconsistencies" section.

**Phase 3 exit criteria:**
- [ ] 4-reviewer panel live, each reviewer produces structured output
- [ ] Meta-review recommendation visible in UI
- [ ] Editor pass gates the panel (desk-reject path tested)
- [ ] Cost ledger recording spend per analysis
- [ ] Idempotency guards on claim_extraction, citation_mapping, gap_detection nodes
- [ ] Circuit breaker active on OpenAI calls
- [ ] `literature_search` running in parallel via Send API
- [ ] `npx tsc --noEmit` clean
- [ ] `python3 -m pytest tests/ -v` passing

---

## PHASE 4 — Post-Outreach Decision (Week 7+)

**Do not start until outreach data is in.** Two paths:

### Path A: PIs want lab collaboration
Build minimal shared workspace:
- `projects` table: add `owner_id`, `collaborators: uuid[]`, `access_level: public|private`
- New route: `POST /projects/{id}/invite` — send email invite, create pending collaborator row
- Frontend: "Share Project" button → invite by email modal
- Viewer role only initially (read analysis, can't upload)
- Estimated: 1 week

### Path B: Researchers want deeper analysis
- Figure vision analysis: `services/figure_vision_analysis.py` — PyMuPDF render figure regions → GPT-4o vision → structured data extraction → cross-reference with text numbers
- New LangGraph node: `figure_analysis_node` — runs in parallel with reviewer panel
- Estimated: 1 week

### Path C: Both
Ship peer review panel first (already done in Phase 3), then collaboration (1 week), then figure analysis.

---

## Deferred (Phase 4+ / Post-Funding)

- **SPECTER2 domain embedder** — +10% recall, requires self-hosted GPU ($50-200/mo), schema migration. Trigger: enterprise lab deal OR recall@10 < 0.85 after HNSW tuning.
- **Overleaf integration** — browser extension/sidebar. Trigger: users complaining about PDF upload friction after regular use.
- **Full figure vision analysis** — GPT-4o per figure, ~$0.10-0.30/paper. Trigger: researchers specifically asking for it.
- **Nightly evals** — upgrade from weekly to nightly. Trigger: $5K MRR.
- **Revision workflow (rebuttal)** — author responds to reviewer questions, runs second analysis. Trigger: validated individual use.

---

## Prompt Caching (Add to Phase 1, 1–2 hrs)

**Not in original plan but high ROI — add to Phase 1.**

OpenAI caches KV states of prompt prefixes > 1024 tokens automatically when the same prefix appears in repeated calls. Current Noesis sends large system prompts + static instructions repeatedly across LangGraph nodes.

**Fix in all 5 node files + `reviewer_panel.py`:**
- Move system prompt to first `messages` entry (role: system)
- Move all static context (paper type instructions, rubric, output format) before dynamic per-draft content
- Keep dynamic content (draft text, claim list) at the END of the user message
- Static prefix > 1024 tokens = cache hit on repeat runs

Estimated cost reduction: 40-60% on repeated analyses of same draft (re-runs, retries). Zero latency penalty on cache hits.

---

## Skill Invocation Reference

When executing tasks in this plan:

| Situation | Skill to invoke |
|---|---|
| Exploring a file before editing | `/claude-mem:smart-explore` — AST-based, token-efficient |
| After completing a phase | `/simplify` — catches redundancy, dead code, quality issues |
| Generating large new files (schemas.py, reviewer_panel.py) | `/full-output-enforcement` — prevents truncated output |
| Planning a sub-problem within a phase | `/claude-mem:make-plan` |
| Executing a multi-step phase | `/claude-mem:do` — dispatches parallel subagents per phase |

## Parallel Subagent Dispatch Guide

When dispatching subagents, group tasks by dependency tier:

**Phase 1 — dispatch 3 parallel subagents after 1A+1B complete:**
- Subagent 1: Tasks 1C (response_format on all nodes)
- Subagent 2: Task 1D (retry_utils) + Task 1E (embedding abstraction)
- Subagent 3: Task 1F (golden set scaffolding) — note founder time needed for manuscript spot-check

**Phase 2 — dispatch 2 parallel subagents:**
- Subagent 1: Task 2A (PDF highlighting — backend + frontend)
- Subagent 2: Task 2B (HNSW tuning — migrations + benchmark)

**Phase 3 — sequential backbone (3A→3B→3C→3D) with parallel side tasks:**
- Main thread: 3A → 3B → 3C → 3D
- Parallel: 3E (reflection) + 3F (migrations) + 3G (robustness) while 3B/3C running
- After 3D done: 3H (frontend) + 3I (figure captions) in parallel
