# Plan 05 — Per-Agent Output Gates + Determinism + Eval Thresholds

**Goal:** Lock in reliability. Every agent/node validates its own output against
a schema + a quality gate before passing downstream. Non-deterministic variance
is bounded. Regressions are caught automatically by the Plan 00 scoreboard.

**Prereq:** Plans 00–04 (gates wrap the features once they exist).

## Principles
- Fail-closed where a bad output would mislead the researcher (already partly
  done: `draft_publish_gate.py` FAIL_CLOSED). Extend consistently.
- Every adverse/specific finding must carry verbatim evidence (anchor or source
  quote) or be dropped. No evidence → no claim.

## Changes
1. **Schema gates per node.** Audit each node in
   `app/workflows/draft_analysis/nodes/`. Ensure each returns through a Pydantic
   schema (most already use `schemas.py`). Add validation where missing; on
   invalid output, retry once then degrade gracefully (empty + logged warning),
   never emit malformed partial data.
2. **Evidence gate (cross-cutting helper).** One shared validator: a finding with
   an `anchor_text`/`text_snippet` must be a verbatim substring of the draft
   (reuse `_is_verbatim_anchor` from `draft_analysis_langgraph.py`); a citation
   verdict must carry a source quote. Apply in: diagnostic_findings,
   reviewer_panel, citation verify (Plan 04), revision tasks.
3. **Determinism controls.** Pin temperature low on judge + scoring nodes.
   For nodes prone to variance (domain audit, gap detection), prefer
   deterministic triggers where feasible (memory: deterministic domain-trigger
   audit already killed high-value-catch variance — extend that pattern).
4. **Eval thresholds in `run_eval.py`** (Plan 00): per-dim minimums; CI exits
   non-zero on regression. Add as a pre-push / CI check:
   - mean overall ≥ 8.5, hallucinations = 0, no dim mean < 7.5.
5. **Run-to-run stability test.** Add to the eval: run the same draft×corpus 3×;
   assert overall variance ≤ 0.5 and the SAME high-severity findings appear all 3.

## Acceptance
- [ ] Every node has schema validation; malformed output never propagates (unit tests).
- [ ] Evidence gate strips any unanchored/unsourced finding (test with a planted bad finding).
- [ ] `run_eval.py` enforces thresholds and fails on a seeded regression.
- [ ] 3× stability run: variance ≤ 0.5, identical high-severity findings.
- [ ] `pytest services/backend/tests/ -q` green.

## Verify
```
docker exec noesis-backend python scripts/eval/run_eval.py --stability 3
pytest services/backend/tests/ -q
```
