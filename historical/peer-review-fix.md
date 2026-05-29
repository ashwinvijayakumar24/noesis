# Noesis — Peer Review Panel Implementation Plan

**Last updated:** May 12, 2026
**Status:** Implementation-ready spec. No code written yet.
**Prerequisite:** `improvements.md` Phase 1 (structured outputs via `response_format`) must be complete first — all new nodes will use `client.beta.chat.completions.parse()`.

---

## Current State Diagnosis

### What exists today

```
graph.py node order:
extract_structure → extract_claims → categorize_claims → literature_search
  → citation_mapping → detect_gaps → external_source_discovery
  → structural_checks → generate_reviewer_feedback → synthesize_report
```

**`generate_reviewer_feedback_node` (reviewer_feedback.py) does:**
- Single LLM call, single monolithic reviewer voice
- Produces: `feedback_type` (strength/weakness/question/suggestion), severity, section_reference
- Hardcodes `reviewer_persona = "reviewer_2"` — no actual persona differentiation
- Good: has idempotency guard, QA attachment via `draft_anchor_qa.py`, per-claim context building
- Bad: `json.loads(response.choices[0].message.content)` — no schema enforcement, crashes on malformed JSON

**Stage 1 editing (`stage1_editing.py`):**
- Called at `draft_processing.py:477` during upload
- gpt-5-mini mechanical pass: grammar, citation style, formatting, structural notes
- **Status unknown**: verify output surfaces in UI before building anything new (see Step 0 below)

### What's missing vs real peer review

| Real venue process | Noesis today |
|---|---|
| Editor desk check (scope fit, fatal flaws) | Missing |
| 3-4 independent specialist reviewers | 1 monolithic voice |
| Structured review (Summary/Strengths/Weaknesses/Questions/Rating/Confidence) | Flat `feedback_items` list |
| Reviewer specialization (methodology expert, novelty expert, etc.) | None |
| Meta-review / area chair synthesis | Missing |
| Recommendation (Accept/Major Revision/etc.) | Missing |
| Venue-specific norms (ICLR vs CHI vs Nature) | Not implemented |

---

## Target Architecture

### New graph topology

```
extract_structure
    → extract_claims
        → categorize_claims
            → literature_search
                → citation_mapping
                    → detect_gaps
                        → external_source_discovery
                            → structural_checks
                                → editor_pass (gpt-5-mini, ~1s)
                                    ↓
                          ┌─── Send: reviewer_novelty ──────┐
                          ├─── Send: reviewer_methodology ──┤
                          ├─── Send: reviewer_coverage ─────┤ fan-in
                          └─── Send: reviewer_clarity ───────┘
                                    ↓ (all 4 complete)
                               meta_reviewer
                                    ↓
                            synthesize_report
```

Each reviewer = a **separate LangGraph node** parameterized by `reviewer_type`. Nodes run in true async parallel via LangGraph `Send` API. This is what makes each reviewer an independent "agent" — they see the same upstream state but execute independently with different prompts, focus areas, and context slices.

**Latency math:**
- Editor pass: ~1s (gpt-5-mini)
- 4 reviewers in parallel: latency = slowest reviewer, ~8–12s (same as current single call)
- Meta-reviewer: +5–8s (one LLM call after fan-in)
- Net vs current: +6–9s total for 4× the review depth

---

## Step 0: Verify Stage 1 Before Writing Any New Code

**Do this first. Estimated time: 1–2 hours.**

Stage 1 editing exists but its surfacing in the UI is unconfirmed. If it's silently dropped, the two-pass framing is false.

### Verification checklist

```bash
# 1. Check Stage 1 is awaited (not fire-and-forget)
grep -n "run_stage1_editing\|stage1" services/backend/app/services/draft_processing.py
# Should see: await run_stage1_editing(...) AND result stored somewhere

# 2. Check Stage 1 result is returned in draft analysis response
grep -n "stage1\|grammar_issues\|formatting_issues" services/backend/app/api/routes/drafts.py

# 3. Check frontend renders Stage 1 output
grep -rn "stage1\|grammar_issues\|formatting_issues\|Stage1" services/frontend/src/
```

**Expected findings (and what to fix if wrong):**

| Finding | Fix |
|---|---|
| `run_stage1_editing` called but result not stored/returned | Store result in `draft_analysis.analysis["editing_feedback"]`, return in GET `/drafts/{id}/analysis` |
| Result stored but not in API response shape | Add/keep `editing_feedback` key in analysis response |
| API returns it but frontend doesn't render it | Render it in `EditingPassTab.tsx` from the Draft Analysis page |
| Everything works | Document it, proceed to Step 1 |

---

## Step 1: Pydantic Schemas for All New Agents

**File:** `app/workflows/draft_analysis/schemas.py` (add to existing or create)

```python
from pydantic import BaseModel, Field
from typing import Literal

# ── Editor Pass ──────────────────────────────────────────────────────────────

class EditorPassOutput(BaseModel):
    proceed_to_review: bool
    fatal_flaws: list[str] = Field(default_factory=list)
    scope_appropriate: bool
    writing_quality: Literal["publishable", "needs_revision", "major_revision"]
    notes: str

# ── Individual Reviewer ───────────────────────────────────────────────────────

class ReviewerOutput(BaseModel):
    reviewer_id: Literal["novelty", "methodology", "coverage", "clarity"]
    summary: str = Field(description="2-3 sentence summary of paper from this reviewer's POV")
    strengths: list[str] = Field(description="Genuine strengths, not filler praise")
    weaknesses: list[str] = Field(description="Specific weaknesses with section references")
    questions_to_authors: list[str] = Field(description="Questions reviewer NEEDS answered to improve score")
    limitations_to_address: list[str]
    rating: int = Field(ge=1, le=10, description="ICLR scale: 1-2=strong reject, 3-4=weak reject, 5=borderline, 6-7=weak accept, 8-9=strong accept, 10=award")
    confidence: int = Field(ge=1, le=5, description="1=not my area, 5=expert in this exact area")
    recommendation: Literal["accept", "minor_revision", "major_revision", "reject"]

# ── Meta-Review ───────────────────────────────────────────────────────────────

class MetaReviewOutput(BaseModel):
    overall_recommendation: Literal["accept", "minor_revision", "major_revision", "reject"]
    decision_rationale: str
    must_address: list[str] = Field(description="Blocking items — required for acceptance")
    nice_to_address: list[str] = Field(description="Non-blocking suggestions")
    consensus_strengths: list[str]
    consensus_weaknesses: list[str]
    reviewer_agreement_level: Literal["high", "medium", "low"]
    score_summary: dict[str, int] = Field(description="reviewer_id → rating")
```

**Add to `DraftAnalysisState` (state.py):**

```python
# New fields to add
editor_decision: EditorPassOutput | None
reviewer_outputs: Annotated[list[ReviewerOutput], lambda a, b: a + b]  # reducer for fan-in
meta_review: MetaReviewOutput | None
```

The `Annotated[list[...], lambda a, b: a + b]` reducer is how LangGraph merges parallel node outputs. Each parallel reviewer appends to the list; fan-in waits until all 4 complete.

---

## Step 2: Editor Pass Node

**File:** `app/workflows/draft_analysis/nodes/editor_pass.py`

**What it does:** Fast pre-screen (gpt-5-mini, ~1s) before committing to full reviewer panel. Real journals do this — if the paper is obviously out of scope or has fatal flaws, don't waste reviewer time.

**Prompt focus:**
- Is this paper structurally complete enough to review? (has abstract, introduction, methods/approach, results/findings, conclusion/discussion)
- Are there immediately fatal flaws? (single anecdote presented as evidence, fabricated citations, plagiarism signals, single-paragraph paper)
- Is writing at a baseline publishable level or does it need substantial revision first?
- Would this paper be in scope for a general CS/HCI/biomedical venue? (not scope-gating to a specific venue — just checking it's research, not a blog post)

**Key behavior:** If `proceed_to_review = False`, graph routes to `report_synthesis` directly and skips the reviewer panel. The synthesis node handles the desk-reject case with an appropriate message.

**Context provided:**
- Draft structure (sections, word count)
- First 2000 chars of draft content (abstract + intro)
- Stage 1 results if available (grammar/structural issues already found)

**Cost:** gpt-5-mini, ~500 tokens. Negligible.

---

## Step 3: Reviewer Panel Node (Single Node, 4 Agents)

**File:** `app/workflows/draft_analysis/nodes/reviewer_panel.py`

One function handles all 4 reviewer types. LangGraph `Send` calls it 4 times in parallel with different `reviewer_type` in state.

### Routing function (in graph.py)

```python
from langgraph.types import Send

def route_to_reviewer_panel(state: DraftAnalysisState):
    editor = state.get("editor_decision")
    if editor and not editor.proceed_to_review:
        return "synthesize_report"  # desk reject path

    reviewer_types = ["novelty", "methodology", "coverage", "clarity"]
    return [
        Send("reviewer_panel_node", {**state, "reviewer_type": rt})
        for rt in reviewer_types
    ]
```

### Reviewer configurations

Each reviewer gets a different system prompt focus AND a different slice of the upstream analysis state.

**Reviewer: Novelty & Significance**
- System focus: contribution clarity, novelty over prior work, venue appropriateness, whether claimed contributions match actual work
- Context provided: paper type, target venue, draft intro + conclusion, claim list (types: `contribution`, `empirical`)
- Key rubric: Is the novelty claim justified? Is this incremental or significant? Would acceptance advance the field?
- Rating calibration: "Be honest — if the contribution is incremental, rate 4-5. Do not default to 6-7."

**Reviewer: Methodology & Technical Soundness**
- System focus: experimental design, statistical validity, baselines, ablations, reproducibility
- Context provided: claims of type `empirical`/`experimental`, citation quality per claim (are methodology claims supported?), structural checks output
- Key rubric: Appropriate baselines? Statistical significance reported? Ablations? Hyperparams/seeds for reproducibility? Confounds?
- Does NOT see: literature gap analysis (not its job), formatting issues

**Reviewer: Related Work & Coverage**
- System focus: literature gaps, missing citations, positioning accuracy, conflicting evidence
- Context provided: full gap detection output, external source discovery output, claims of type `citation_needed`/`comparative`, related work section text
- Key rubric: Missing important papers? Positioning accurate? Conflicting results acknowledged? Citations actually support their claims?
- This reviewer is fed the gap analysis output directly — it is the "human voice" for what the automated analysis found

**Reviewer: Clarity & Reproducibility**
- System focus: writing clarity, figure/table quality, reproducibility from paper alone, limitations honesty
- Context provided: structure (has_abstract, has_limitations, section list), word count, figure captions if available (Phase 3+)
- Key rubric: Can experiments be reproduced? Abstract accurate? Figures clear? Limitations honest?
- Does NOT need: claim citations, gap analysis

### Context building per reviewer

```python
def build_reviewer_context(state: DraftAnalysisState, reviewer_type: str) -> str:
    base = f"""
DRAFT METADATA:
- Paper type: {state.get('paper_type', 'unknown')}
- Target venue: {state.get('target_venue', 'general')}
- Word count: {state.get('structure', {}).get('word_count', 'unknown')}
- Sections present: {', '.join(s.get('type','?') for s in state.get('structure', {}).get('sections', []))}

DRAFT CONTENT (truncated):
{state.get('draft_content', '')[:4000]}
"""

    if reviewer_type == "novelty":
        return base + _build_novelty_context(state)
    elif reviewer_type == "methodology":
        return base + _build_methodology_context(state)
    elif reviewer_type == "coverage":
        return base + _build_coverage_context(state)
    elif reviewer_type == "clarity":
        return base + _build_clarity_context(state)
```

### Node implementation

```python
async def reviewer_panel_node(state: DraftAnalysisState) -> dict:
    reviewer_type = state["reviewer_type"]
    config = REVIEWER_CONFIGS[reviewer_type]
    context = build_reviewer_context(state, reviewer_type)

    result = await client.beta.chat.completions.parse(
        model="gpt-5.2-chat-latest",
        max_completion_tokens=2500,
        response_format=ReviewerOutput,
        messages=[
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": context},
        ],
    )

    reviewer_output = result.parsed
    # Persist to DB
    supabase.table("reviewer_panel_outputs").insert({
        "draft_id": state["draft_id"],
        "reviewer_id": reviewer_type,
        "summary": reviewer_output.summary,
        "strengths": reviewer_output.strengths,
        "weaknesses": reviewer_output.weaknesses,
        "questions_to_authors": reviewer_output.questions_to_authors,
        "limitations_to_address": reviewer_output.limitations_to_address,
        "rating": reviewer_output.rating,
        "confidence": reviewer_output.confidence,
        "recommendation": reviewer_output.recommendation,
    }).execute()

    return {"reviewer_outputs": [reviewer_output]}
    # LangGraph reducer appends to list — fan-in collects all 4
```

### Rating calibration (critical — prevents 6-7 clustering)

Every reviewer system prompt includes this calibration block:

```
RATING CALIBRATION (use the full scale honestly):
- 10: Award quality, exceptional contribution
- 8-9: Strong accept — clear contribution, solid execution, ready to publish
- 6-7: Weak accept — above threshold but has notable issues
- 5: Borderline — compelling but with a fundamental concern
- 3-4: Weak reject — below threshold, significant issues
- 1-2: Strong reject — fundamental flaws, out of scope, or incomplete

At major venues (ICLR, NeurIPS, CHI), roughly:
- 10-15% of papers reviewed score 8+
- 20-30% score 6-7
- 40-50% score 4-5
- 15-20% score 1-3

If you are inclined to give a 6, ask yourself: would this paper be accepted at the target venue as-is?
If not, it is a 5 or below.
```

---

## Step 4: Meta-Reviewer Node

**File:** `app/workflows/draft_analysis/nodes/meta_reviewer.py`

Runs after all 4 parallel reviewers complete (LangGraph fan-in). Acts as area chair: synthesizes, resolves conflicts, gives a decisive recommendation.

**Context provided:**
- All 4 `ReviewerOutput` objects (formatted as structured summaries)
- Brief draft context (abstract + paper type)
- Score summary table

**Key prompt instructions:**
- Do NOT average ratings — synthesize qualitatively
- Explicitly surface reviewer conflicts ("Reviewer A rates novelty strong; Reviewer C flags a key missing citation that undermines this claim")
- `must_address` = blocking items that, if fixed, could change the recommendation
- `nice_to_address` = non-blocking suggestions
- Be decisive — "borderline with clear path to acceptance" is acceptable; "it depends on reviewer preference" is not

**DB persistence:**

```python
supabase.table("meta_reviews").insert({
    "draft_id": state["draft_id"],
    "overall_recommendation": meta.overall_recommendation,
    "decision_rationale": meta.decision_rationale,
    "must_address": meta.must_address,
    "nice_to_address": meta.nice_to_address,
    "consensus_strengths": meta.consensus_strengths,
    "consensus_weaknesses": meta.consensus_weaknesses,
    "reviewer_agreement_level": meta.reviewer_agreement_level,
    "score_summary": meta.score_summary,
}).execute()
```

---

## Step 5: Graph Wiring Changes

**File:** `app/workflows/draft_analysis/graph.py`

```python
# Add new imports
from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node
from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node
from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node

# Register new nodes
workflow.add_node("editor_pass_node", editor_pass_node_with_progress)
workflow.add_node("reviewer_panel_node", reviewer_panel_node)  # called 4x in parallel
workflow.add_node("meta_reviewer_node", meta_reviewer_node_with_progress)

# Change edges:
# OLD: structural_checks → generate_reviewer_feedback → synthesize_report
# NEW: structural_checks → editor_pass → [conditional] → reviewer_panel ×4 → meta_reviewer → synthesize_report

workflow.add_edge("structural_checks_node", "editor_pass_node")

# Conditional routing after editor pass
workflow.add_conditional_edges(
    "editor_pass_node",
    route_to_reviewer_panel,  # returns list of Send() OR string "synthesize_report"
    {
        "reviewer_panel_node": "reviewer_panel_node",
        "synthesize_report": "synthesize_report_node",
    }
)

# Fan-in: after all parallel reviewer_panel_node invocations complete
workflow.add_edge("reviewer_panel_node", "meta_reviewer_node")
workflow.add_edge("meta_reviewer_node", "synthesize_report_node")

# Remove old edge
# workflow.add_edge("structural_checks_node", "generate_reviewer_feedback_node")  # REMOVE
```

**Progress tracking additions:**
```python
async def editor_pass_node_with_progress(state):
    await publish_progress(draft_id, "editor_pass_start", 77, "Running editorial check...")
    result = await editor_pass_node(state)
    await publish_progress(draft_id, "editor_pass", 80, "Editorial check complete")
    return result

async def meta_reviewer_node_with_progress(state):
    await publish_progress(draft_id, "meta_review_start", 90, "Synthesizing reviewer panel...")
    result = await meta_reviewer_node(state)
    await publish_progress(draft_id, "meta_review", 95, "Review synthesis complete")
    return result
```

---

## Step 6: Database Migrations

**File:** `migrations/021_reviewer_panel.sql`

```sql
-- Per-reviewer structured outputs
CREATE TABLE IF NOT EXISTS reviewer_panel_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,  -- 'novelty' | 'methodology' | 'coverage' | 'clarity'
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

-- Meta-review / area chair output
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

-- Add reviewer_id to existing reviewer_feedback for legacy compatibility
ALTER TABLE reviewer_feedback
    ADD COLUMN IF NOT EXISTS reviewer_id TEXT DEFAULT 'legacy';

-- Editor pass decision stored in draft_analysis.analysis_metadata
-- No new table needed — add to existing JSONB column:
-- analysis_metadata.editor_decision = { proceed_to_review, fatal_flaws, ... }

-- RLS
ALTER TABLE reviewer_panel_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own reviewer panel outputs"
    ON reviewer_panel_outputs FOR SELECT
    USING (draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid()));

CREATE POLICY "Users can read own meta reviews"
    ON meta_reviews FOR SELECT
    USING (draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid()));
```

---

## Step 7: API Response Changes

**File:** `api/routes/drafts.py`

Add to draft analysis GET response:

```python
# Fetch reviewer panel outputs
panel_outputs = supabase.table("reviewer_panel_outputs")\
    .select("*")\
    .eq("draft_id", draft_id)\
    .execute()

# Fetch meta review
meta_review = supabase.table("meta_reviews")\
    .select("*")\
    .eq("draft_id", draft_id)\
    .limit(1)\
    .execute()

# Fetch editor decision from draft_analysis.analysis_metadata
# (already fetched in existing code — just extract the key)

return {
    ...existing fields...,
    "editing_feedback": analysis_payload.get("editing_feedback"),
    "editor_decision": analysis_metadata.get("editor_decision"),
    "reviewer_panel": panel_outputs.data,                        # list of 4
    "meta_review": meta_review.data[0] if meta_review.data else None,
}
```

---

## Step 8: Frontend Changes

**File:** `services/frontend/src/components/draft-analysis/ReviewerFeedbackTab.tsx`

New layout (top to bottom):

```
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: EDITORIAL CHECK                                    │
│ [collapsible] Grammar: 2 issues | Citations: 1 issue        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ EDITOR DECISION                                             │
│ ✓ Proceed to review    Writing: Publishable                 │
│ Notes: Abstract is complete. Methods section is present.   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ AREA CHAIR SUMMARY                         MAJOR REVISION   │
│ Reviewer Scores:                                            │
│ Novelty: 7/10  Methods: 5/10  Coverage: 6/10  Clarity: 8/10│
│ Agreement: Medium                                           │
│                                                             │
│ Must Address:          Consensus Strengths:                 │
│ • [item 1]             • [strength 1]                       │
│ • [item 2]             • [strength 2]                       │
│                                                             │
│ Nice to Address:                                            │
│ • [item 1]                                                  │
└─────────────────────────────────────────────────────────────┘

[ Novelty 7/10 ] [ Methodology 5/10 ] [ Coverage 6/10 ] [ Clarity 8/10 ]

┌─────────────────────────────────────────────────────────────┐
│ Reviewer: Methodology & Technical Soundness                 │
│ Rating: 5/10  Confidence: 4/5  → Major Revision            │
├─────────────────────────────────────────────────────────────┤
│ Summary                                                     │
│ This paper presents a federated learning approach but...   │
├─────────────────────────────────────────────────────────────┤
│ Strengths                    Weaknesses                     │
│ • [strength]                 • [weakness + section ref]     │
│ • [strength]                 • [weakness + section ref]     │
├─────────────────────────────────────────────────────────────┤
│ Questions to Authors                                        │
│ 1. How were baseline models selected? Were SOTA methods...  │
│ 2. Table 2 shows p=0.05 — was this pre-registered?         │
├─────────────────────────────────────────────────────────────┤
│ Limitations to Address                                      │
│ • The current evaluation uses a single dataset...           │
└─────────────────────────────────────────────────────────────┘
```

**Key frontend components to create/modify:**

1. `EditorDecisionCard.tsx` — new component, collapsible, shows fatal flaws if any
2. `MetaReviewCard.tsx` — new component, score table + must-address + consensus
3. `ReviewerPanelTabs.tsx` — tabs by reviewer, each shows structured review card
4. `EditingPassTab.tsx` — shows grammar/citation/formatting issues from `editing_feedback`
5. Peer review surface — render `EditorDecisionCard`, `MetaReviewCard`, and `ReviewerPanelTabs` before legacy actionable feedback

---

## Step 9: Venue-Specific Calibration (Optional Enhancement)

Add `target_venue` field to draft upload form. Maps to reviewer prompt tweaks:

```python
VENUE_ADJUSTMENTS = {
    "iclr": "Heavily weight reproducibility, SOTA baselines, ablation studies, and open-source code.",
    "neurips": "Weight mathematical rigor, theoretical contributions, and empirical breadth.",
    "chi": "Weight study design validity, participant recruitment, and qualitative rigor. HCI contributions include systems, studies, and theories — not just empirical results.",
    "nature": "Weight broader societal impact, replication, and whether the finding would be newsworthy to the broader scientific community.",
    "medical": "Weight clinical validity, ethics board approval, patient safety, and whether findings would change clinical practice.",
    "general": "",  # no adjustment
}
```

If `target_venue` not provided, default to `"general"`.

---

## Execution Order

| Step | What | Time estimate | Prerequisite |
|---|---|---|---|
| **Step 0** | Verify Stage 1 surfaces in UI | 1–2 hrs | Nothing |
| **Step 1** | Pydantic schemas for all reviewer types | 2–3 hrs | improvements.md Phase 1 complete |
| **Step 2** | Editor pass node | 3–4 hrs | Step 1 |
| **Step 3** | Reviewer panel node (all 4 agents) | 1 day | Steps 1–2 |
| **Step 4** | Meta-reviewer node | 3–4 hrs | Step 3 |
| **Step 5** | Graph wiring | 2–3 hrs | Steps 2–4 |
| **Step 6** | DB migration | 1 hr | Step 5 |
| **Step 7** | API response changes | 2 hrs | Step 6 |
| **Step 8** | Frontend panel UI | 1–2 days | Step 7 |
| **Step 9** | Venue calibration (optional) | 2–3 hrs | Steps 1–5 |
| | **Total** | **~4–5 days** | |

---

## Cost Per Draft Analysis (After This Change)

| Component | Model | Tokens (est.) | Cost |
|---|---|---|---|
| Editor pass | gpt-5-mini | 1k in, 300 out | ~$0.0002 |
| Reviewer: Novelty | gpt-5.2 | 3k in, 1.5k out | ~$0.005 |
| Reviewer: Methodology | gpt-5.2 | 4k in, 1.5k out | ~$0.006 |
| Reviewer: Coverage | gpt-5.2 | 3k in, 1.5k out | ~$0.005 |
| Reviewer: Clarity | gpt-5.2 | 2.5k in, 1.5k out | ~$0.004 |
| Meta-reviewer | gpt-5.2 | 5k in, 2k out | ~$0.008 |
| **Total panel** | | | **~$0.028** |
| Current single reviewer | gpt-5.2 | 5k in, 3k out | ~$0.009 |
| **Net increase** | | | **~$0.019/analysis** |

At Pro tier (20 analyses/month): $0.38/user/month added cost. Negligible vs $12/month plan.

---

## What the Eval Harness Needs to Score This (Pillar 3 connection)

Once the panel is live, add these to `tests/eval/`:

- `test_eval_reviewer_panel_coverage.py` — do all 4 reviewers cover their specialty areas? (precision: does methodology reviewer actually discuss methodology?)
- `test_eval_rating_calibration.py` — track rating distribution over time. Flag if mean > 6.8 (clustering) or if any reviewer never uses 1-4 range across the golden set.
- `test_eval_meta_review_consistency.py` — does meta-review recommendation match the reviewer score distribution? (4 weak reject scores + meta says "accept" = bug)
- `test_eval_reviewer_vs_openreview.py` — compare Noesis reviewer outputs to real OpenReview human reviews on same papers (rubric overlap via LLM-as-judge). This is the gold-standard eval for this feature.
