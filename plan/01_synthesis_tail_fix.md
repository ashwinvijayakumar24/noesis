# Plan 01 — Synthesis Tail Fix (stop dropping computed signal)

**Goal:** Everything the pipeline already computes — matched citation passages,
external "missed papers", meta-reviewer priorities — must reach the final
export. Today `synthesize_report` keeps only counts + claim lists and throws the
rest away. This is the single highest-impact, lowest-cost fix.

**Prereq:** Plan 00 harness exists (so you can prove the signal now arrives).

## The bug (verified)
`app/workflows/draft_analysis/nodes/report_synthesis.py` (~lines 90–132) builds
`synthesis_report` from `claims_with_citations` but only extracts:
- `citation_quality` counts (strong/moderate/weak/none)
- `unsupported_claims` / `weakly_supported_claims` (claim text only)

It drops, per claim, the `citations[]` array which carries `document_title` +
`content` (the matched corpus/reference passage). It also does not surface
`state["external_sources"]` (the "you missed paper X" results) or the
meta-reviewer's prioritized tasks.

## Changes
1. **report_synthesis.py** — extend `synthesis_report` with:
   - `grounded_citations`: for each claim with citations, include
     `{claim_text, anchor, source_title, matched_passage (content, <=300 chars),
       relevance, reasoning}`. This is the "cite passage Y of paper Z" payload.
   - `external_sources`: pass through `state.get("external_sources", [])`
     (already judge-filtered by `citation_judge`) with the gap/claim each addresses.
   - `meta_priorities`: pull the meta-reviewer's ordered priorities (see below).
2. **Confirm meta priorities reach tasks.** Cross-check with
   `scripts/proof_meta_owns_tasks.py` (memory: meta priorities historically
   dropped from `draft_revision_tasks` — the #1 bottleneck). If the proof script
   shows priorities not owning tasks, wire `meta_reviewer` output → revision
   task ordering here or in the meta node. Keep change surgical.
3. **Export + storage.** Ensure whatever persists `synthesis_report` /
   `draft_analysis` (in `draft_analysis_langgraph.py`) writes the new fields, and
   that `scripts/export_latest_draft_analysis.py` emits them (so the harness sees them).
4. **Frontend (defer / note only).** Do NOT build UI here. Just guarantee the
   data is in the export + DB. Note for a later frontend task that
   `grounded_citations` + `external_sources` should render per-claim.

## Surgical constraints
- Touch `report_synthesis.py`, the persistence in `draft_analysis_langgraph.py`,
  and the export script. Nothing else unless the meta-priority wiring demands it.
- Do not refactor adjacent code. Match existing dict-building style.

## Acceptance (verified via Plan 00 harness)
- [ ] Export JSON for a draft WITH a relevant corpus contains non-empty
      `grounded_citations` with a real `matched_passage` from a corpus doc.
- [ ] Export contains `external_sources` when gaps were found (and they survived `citation_judge`).
- [ ] Export contains `meta_priorities`, and top revision tasks reflect them.
- [ ] Judge "Grounding" + "Actionability" dims rise vs the pre-fix scoreboard.
- [ ] Existing unit tests still pass: `pytest services/backend/tests/ -q`.

## Verify
```
docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --corpus corpus_a
python - <<'PY'
import json,glob; f=sorted(glob.glob("scripts/eval/results/*draft3*"))[-1]
d=json.load(open(f)); sr=d.get("synthesis_report",d)
print("grounded:",len(sr.get("grounded_citations",[])),
      "external:",len(sr.get("external_sources",[])),
      "meta:",len(sr.get("meta_priorities",[])))
PY
```
