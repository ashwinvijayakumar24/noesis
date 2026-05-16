# Codex Task: Verify Draft Analysis Implementation

## What you are verifying

A two-pass draft analysis system was just implemented. Your job is to:
1. Audit the code against the intended architecture below
2. Find anything broken, missing, or incorrectly wired
3. Write and run tests that verify each part works end-to-end (unit + integration where possible)
4. Fix any bugs you find

---

## Intended Architecture

### Pass 1 — Mechanical Editing (runs in `ingest_draft`, before LangGraph)

**File:** `services/backend/app/services/draft_processing.py`

- `run_stage1_editing(full_text, citation_style, paper_type)` fires as `asyncio.create_task` concurrently with structure analysis
- Returns `Stage1EditingOutput` with: `grammar_issues`, `citation_issues`, `formatting_issues`, `structural_notes` (max 15 each)
- Result stored to `draft_analysis.analysis.editing_feedback` in Supabase
- Uses `gpt-5-mini` with `client.beta.chat.completions.parse()` (sync client, no await)
- Frontend reads this via `extractEditingFeedbackPayload()` in `DraftAnalysis.tsx`

**File:** `services/backend/app/services/stage1_editing.py`

- `run_stage1_editing` is `async def` — uses async OpenAI client or sync call (verify which)
- Must return a dict with keys: `grammar_issues`, `citation_issues`, `formatting_issues`, `structural_notes`

---

### Pass 2 — LangGraph Peer Review (14 nodes)

**Entry:** `services/backend/app/services/draft_analysis_langgraph.py` → `analyze_draft_with_langgraph()`
**Graph:** `services/backend/app/workflows/draft_analysis/graph.py`
**State:** `services/backend/app/workflows/draft_analysis/state.py`
**Schemas:** `services/backend/app/workflows/draft_analysis/schemas.py`
**Nodes:** `services/backend/app/workflows/draft_analysis/nodes/`

#### Node execution order:
1. `extract_structure` → `DraftStructure` (sections, word_count, page_count, has_abstract, etc.)
2. `extract_claims` → `List[Claim]` (claim_text, claim_type, section_location, importance_score)
3. `categorize_claims` → claims_by_type dict, primary_claims, supporting_claims
4. `search_literature` → literature_search_results per claim (RAG retrieval)
5. `map_citations` → `List[ClaimWithCitation]` (claim + citations + citation_quality)
6. `detect_gaps` → `List[Gap]` (gap_type, description, severity, affected_claims)
7. `discover_external_sources` → external_sources[] (non-fatal, wrapped in try/except)
8. `citation_judge` → filters low-relevance citations (keep=True/False verdicts)
9. `structural_checks` → structural_feedback[]
10. `editor_pass` → `EditorPassOutput` (proceed_to_review bool, fatal_flaws[], writing_quality, scope_appropriate)
    - If `proceed_to_review=False` → graph routes directly to `synthesize_report`, skipping reviewer panel
11. `reviewer_panel` × 4 **in parallel** via LangGraph `Send` API:
    - reviewer_types: `novelty`, `methodology`, `coverage`, `clarity`
    - Each produces `ReviewerOutput`: summary, strengths[], weaknesses[], questions_to_authors[], limitations_to_address[], rating (1-10), confidence (1-5), recommendation
    - State field `reviewer_outputs` uses `Annotated[List[Dict], add]` reducer for fan-in
12. `reviewer_judge` → scores specificity per reviewer (0.0–1.0); retries if < 0.45; produces `judged_reviewer_outputs`
13. `meta_reviewer` → `MetaReviewOutput`: overall_recommendation, decision_rationale, must_address[], nice_to_address[], consensus_strengths[], consensus_weaknesses[], reviewer_agreement_level, score_summary
14. `synthesize_report` → final synthesis dict

#### Critical async bug that was just fixed:
Nodes `editor_pass`, `reviewer_panel`, `meta_reviewer`, `reviewer_judge`, `citation_judge` previously used `get_openai_client()` (sync) but called `await client.beta.chat.completions.parse()`. This caused `TypeError: object ParsedChatCompletion[...] can't be used in 'await' expression`.

**Fix applied:** All 5 now use `get_async_openai_client()` from `app.core.openai_client`.

**Verify:**
- All 5 node files import `get_async_openai_client`, not `get_openai_client`
- `client = get_async_openai_client()` at module level
- All `await client.beta.chat.completions.parse(...)` calls are now valid (async client)
- The other nodes (`citation_mapping.py`, `claim_extraction.py`, `reviewer_feedback.py`) use sync client without await — verify they are NOT broken

#### DB writes after LangGraph completes:
- `draft_analysis` table: structure, word_count, analysis_metadata (readiness_score, verdict, editor_decision, citation_judge, reviewer_judge)
- `draft_claims` table: one row per claim
- `coverage_gaps` table: one row per gap
- `reviewer_feedback` table: flat feedback rows (converted from meta_review output for backwards compatibility)
- `reviewer_panel_outputs` table: one row per reviewer (draft_id + reviewer_id unique)
- `meta_reviews` table: one row per draft

#### Idempotency:
- `extract_claims` node: checks `draft_claims` table before running LLM
- `reviewer_panel` node: checks `reviewer_panel_outputs` table before running LLM
- `meta_reviewer` node: checks `meta_reviews` table before running LLM

---

### API layer

**File:** `services/backend/app/api/routes/drafts.py`

Key endpoints to verify:
- `GET /drafts/{draft_id}/analysis` must return:
  - `editing_feedback` (from `draft_analysis.analysis.editing_feedback`)
  - `editor_decision` (from `draft_analysis.analysis_metadata.editor_decision`)
  - `reviewer_panel` (array from `reviewer_panel_outputs` table, keyed by draft_id)
  - `meta_review` (from `meta_reviews` table)
  - `readiness_score` (from `draft_analysis.analysis_metadata.readiness_score`)

- `GET /drafts/{draft_id}/all-feedback` must return:
  - `claims[]`, `gaps[]`, `feedback[]` with anchor fields: `line_number`, `text_snippet`, `pdf_coordinates`, `match_confidence`
  - `readiness_score`

---

### Frontend

**Files to verify:**

`services/frontend/src/pages/DraftAnalysis.tsx`:
- `ActiveTab` type must be `'editing_pass' | 'peer_review'` (NOT `'overview' | 'editing'`)
- Default tab: `'peer_review'`
- `DRAFT_PROGRESS_STEPS` must have 7 steps: uploaded, extracting_text, stage1_editing, editor_pass, reviewer_panel, meta_review, finalizing
- Left panel renders tab bar with 2 tabs; tab content switches between `EditingPassTab` and `ReviewerFeedbackList`
- `editorDecision`, `reviewerPanel`, `metaReview` state populated from `api.drafts.getAnalysis()` response

`services/frontend/src/components/draft-analysis/EditingPassTab.tsx` (new file):
- Accepts: `editingFeedback`, `editorDecision`, `paperType`, `citationStyle`
- Renders `EditorDecisionCard` at top (if editorDecision exists)
- Renders Stage 1 info card + 4-metric grid + issue sections below
- `EditorDecision` interface typed properly (no `any`)

`services/frontend/src/components/draft-analysis/ReviewerPanelTabs.tsx` (rewritten):
- Accordion style — NOT horizontal tabs
- All 4 reviewers shown as collapsed cards; click to expand one at a time
- Each card header: reviewer label + recommendation badge + rating/10
- Expanded: summary, strengths/weaknesses 2-col grid, questions, limitations

`services/frontend/src/components/draft-analysis/ReviewerFeedbackList.tsx`:
- Does NOT import or render `EditorDecisionCard`
- Does NOT have `editorDecision` or `onOpenEditingReview` props
- Does render `MetaReviewCard` + `ReviewerPanelTabs` above feedback items when data exists

---

## What to check and test

### 1. Async client fix
- Read all 5 fixed nodes and confirm `get_async_openai_client` is imported and used
- Confirm the other sync nodes (`citation_mapping`, `claim_extraction`, `reviewer_feedback`) still use sync client without await
- Write a unit test that mocks `get_async_openai_client` and confirms each node can be called without raising `TypeError`

### 2. Stage 1 editing wiring
- Confirm `draft_processing.py` fires `run_stage1_editing` as `asyncio.create_task`
- Confirm result stored to `draft_analysis.analysis.editing_feedback`
- Confirm `stage1_editing.py` uses the correct client (sync or async — must match how it's called)
- Write unit test for `run_stage1_editing` with mocked client

### 3. LangGraph graph structure
- Confirm `reviewer_outputs` field in state uses `Annotated[List[Dict], add]` reducer
- Confirm `editor_pass` node routes to `synthesize_report` if `proceed_to_review=False`
- Confirm all 4 reviewer types are sent in parallel via `Send` API
- Confirm `reviewer_judge` node reads from `reviewer_outputs` and writes `judged_reviewer_outputs`
- Confirm `meta_reviewer` reads `judged_reviewer_outputs` (with fallback to `reviewer_outputs`)

### 4. API response shape
- Write a test that mocks the Supabase responses and confirms `GET /drafts/{id}/analysis` returns all required fields: `editing_feedback`, `editor_decision`, `reviewer_panel`, `meta_review`, `readiness_score`
- Confirm `reviewer_panel` is a list of `ReviewerOutput` objects (not empty when `reviewer_panel_outputs` rows exist)

### 5. Frontend TypeScript
- Run `npm run build` in `services/frontend` — must produce zero errors
- Confirm `DraftAnalysis.tsx` has `ActiveTab = 'editing_pass' | 'peer_review'`
- Confirm `EditingPassTab.tsx` exists and has no `any` types
- Confirm `ReviewerPanelTabs.tsx` uses accordion (single `expandedId` state, not tab index)
- Confirm `ReviewerFeedbackList.tsx` has no `EditorDecisionCard` import

### 6. DB schema
- Confirm `reviewer_panel_outputs` table exists with columns: `draft_id`, `reviewer_id`, `summary`, `strengths`, `weaknesses`, `questions_to_authors`, `limitations_to_address`, `rating`, `confidence`, `recommendation`
- Confirm `meta_reviews` table exists with columns: `draft_id`, `overall_recommendation`, `decision_rationale`, `must_address`, `nice_to_address`, `consensus_strengths`, `consensus_weaknesses`, `reviewer_agreement_level`, `score_summary`

---

## OpenAI model rules (do not violate)
- All substantive LLM calls: `model="gpt-5.2"` or `model="gpt-5.2-chat-latest"`
- Stage 1 editing + editor_pass desk check: `model="gpt-5-mini"` (bounded, cheap)
- Always `max_completion_tokens=N`, never `max_tokens`
- Async nodes use `get_async_openai_client()`, sync nodes use `get_openai_client()`

---

## Run existing tests first

```bash
cd services/backend && python3 -m pytest tests/ -v --ignore=tests/e2e -q
```

Expected: 177 passing. 3 pre-existing failures in `test_draft_analysis_v2.py` (about `revision_metadata` / carryover) are known and unrelated to this task — do not fix those.

```bash
cd services/frontend && npm run build && npm run lint
```

Expected: zero build errors.
