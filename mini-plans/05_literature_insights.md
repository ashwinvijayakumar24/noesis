# 05 — Literature Insights

**Scope:** "Generate Insights" feature, quota enforcement, staleness, synthesis quality, external paper suggestions.
**Source:** `arch_plan.md` §5, §9.4.

---

## Your Intent
Synthesize the uploaded literature into something useful — themes, gaps, conflicts, methodological patterns. Triggered manually. Show "stale" warning when docs change. Free: 5 regenerations/day. Pro/Team unlimited. **New idea:** insights should also surface ~5 external papers that would strengthen the literature base.

## Current Tech
- Service: `services/backend/app/services/project_insights.py:106-262`. GPT-5.2-chat-latest.
- Route: `POST /projects/{id}/insights/analyze` (`routes/projects.py:555`).
- Celery task: `tasks/insights_analysis.py`.
- Output JSON structure: `research_gaps`, `common_themes`, `methodological_patterns`, `timeline`, `conflicting_findings`, `citation_patterns`, `key_insights`, `summary`.
- Post-trigger: auto-calls `generate_paper_recommendations()` (projects.py:520-542).
- Frontend: `services/frontend/src/components/InsightsTab/index.tsx`; has an `isStale` boolean (line 96).

## How It Works
```
POST /projects/{id}/insights/analyze
  ↓
Check all PDFs are analyzed (fail if any pending)
  ↓
generate_insights_task.delay(project_id)
  ↓
Pull structured extractions from each document's analysis (claims, methods, findings)
  ↓
Single GPT-5.2 call with aggregated context → JSON insights
  ↓
validate_insights() schema check
  ↓
UPDATE projects SET insights = {...}, insights_updated_at = now()
  ↓
Separately: generate_paper_recommendations() runs on insights output
```

## Value to Researchers
A literature review is synthesis, not summaries. Insights are the difference between "here's what each paper says" and "here's what the field is arguing about." This is the *justification* for uploading 30 papers rather than reading them one-by-one.

## What's Working
- ✅ Aggregation + GPT-5.2 synthesis produces structured output.
- ✅ Paper recommendations auto-regenerate when insights regenerate.
- ✅ Schema validation.

## Problems

### 5a. No quota enforcement → cost risk (P0)
- There is **no daily or monthly limit** on insight regenerations. A user could click "regenerate" 100 times and burn ~$5 of GPT-5.2 tokens. **Single worst cost-leak in the codebase today.**
- `quota_management.py` has no `"insights"` operation type. Free/Pro/Team all get unlimited regens.
- Your spec: Free 5/day, Pro/Team unlimited. Fix is ~15 lines of code (mirror the `daily_discovery` Redis pattern):
  ```python
  # Redis key: daily_insights:{user_id}:{date}
  # TTL: 90000s
  # Free: 5/day, Pro/Team: unlimited
  ```

### 5b. "Stale" is frontend-only guessing
- `InsightsTab` has `isStale` in state, but nothing populates it correctly. No backend field like `documents.changed_since_insights` or a comparison of `insights.updated_at` vs. `max(documents.updated_at)`.
- Frontend probably shows "stale" as soon as you upload a new doc, but via naive local comparison.
- **Fix:** add `insights_generated_at` on `projects` (probably already there as `insights_updated_at` — verify), compute staleness server-side in the project fetch: `stale = any(doc.updated_at > insights_generated_at)`.

### 5c. Are insights actually useful? (your question)
**Honest answer: only sometimes, and the copy is the problem.** The schema is solid (gaps, themes, methodological patterns) but the output is often generic because the input aggregation concatenates short GPT analyses of each paper, not the papers themselves. The synthesis is "summaries of summaries."

**Three interventions that would make insights actually useful:**
1. **Feed actual chunks from the shared cache, not pre-analyses.** Give the synthesis prompt raw text snippets from each paper's methods/results, not a distilled paragraph. Re-synthesis on already-synthesized text is where "generic" lives.
2. **Ground each insight in citations.** Every `key_insight` should name the 2-4 papers it's derived from. Without that, researchers can't verify. Current JSON schema doesn't require citation anchors.
3. **Rename "Insights" to "Literature Map" or "Field Overview."** "Insights" overpromises. "Field Overview" is what researchers will judge this by.

Doing all three moves insights from "nice-to-have clicky feature" to "reason they keep the subscription."

### 5d. External paper suggestions (your new idea) not implemented
- Paper recommendations *do* run automatically after insights (`projects.py:520-542`), but the output is a separate `paper_recommendations` object, not inlined into the insights UI.
- Your idea: inside each `research_gap` or `conflicting_finding`, show 1-2 specific papers that would fill that gap. Strictly better UX than a separate "recommended papers" sidebar.
- Requires prompt changes (ask GPT to name which gap each paper addresses) + UI changes (render paper chips inline in each insight card).

### 5e. "Save to literature" from paper recs not wired through BibTeX resolver
When the user saves a recommended paper, it probably calls the same direct-add path that Discover uses, which doesn't go through the shared cache or the BibTeX resolver. See `06_discover_papers.md` §6b for the same root issue.

## Priority
- **P0 (cost leak):** Add insights quota (5/day free, unlimited Pro/Team).
- **P1 (trust):** Rename feature; make each insight cite 2-4 source papers.
- **P1 (quality):** Feed raw chunks into synthesis, not pre-analyses.
- **P2 (UX):** Inline paper recommendations into insight cards.
- **P2:** Robust backend staleness detection.
