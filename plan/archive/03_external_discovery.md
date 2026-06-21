# Plan 03 — Fix Weak "Missed Papers" + OpenAlex Citation-Graph Discovery

**Goal:** The "you missed paper X" feature is LIVE but weak (keyword Semantic
Scholar only; judge/domain-gate over-suppress; may die before the report). Make
it reliably surface high-precision missed papers, upgraded with citation-graph
discovery.

**Prereq:** Plans 00 + 01 (so external_sources reach the export and you can score it).

## Current state (verified)
- Graph node `discover_external_sources` runs:
  `detect_gaps → discover_external_sources → citation_judge_node`.
- `app/services/draft_external_source_discovery.py` → `_search_semantic_scholar`
  (keyword search), `_passes_domain_gate`, then `citation_judge` filters.
- `app/services/coverage_analysis.py` → `suggest_papers_for_gaps`.
- Failure modes: (a) keyword S2 misses seminal/recent work; (b) domain gate +
  judge over-suppress → recall collapse; (c) results may not reach final export
  (fixed by Plan 01 — verify).

## Changes
1. **Diagnose suppression first.** Using Plan 00, run a draft with KNOWN missing
   papers (pick one, define expected papers in its `gold/`). Log counts at each
   stage: discovered → passed domain gate → kept by judge → in export. Find where
   recall dies. Fix the over-aggressive stage (loosen gate threshold or make the
   judge keep "plausibly relevant" not just "certainly relevant").
2. **Add OpenAlex citation-graph discovery** (new path in
   `draft_external_source_discovery.py`):
   - From the draft's resolved references (Plan 02), query OpenAlex for:
     papers CITED BY many of the author's refs but absent from the bibliography
     (missing foundational work), and recent papers CITING the author's refs
     (missing recent work).
   - Rank by citation overlap with the author's own reference set → far higher
     precision than keyword search.
   - OpenAlex API is free; batch + cache by work-id.
3. **Merge + dedupe** graph results with keyword S2 results before `citation_judge`.
4. **Tune `citation_judge`** so it scores relevance on a scale and keeps top-N
   per gap rather than binary keep/reject — recall without noise.

## Acceptance (via Plan 00 harness)
- [ ] For the known-gaps draft, ≥1 expected missing paper (from its gold) appears
      in `external_sources` in the final export.
- [ ] Stage-by-stage recall logged; no single stage drops >50% of valid candidates.
- [ ] Citation-graph path returns papers with measurable co-citation overlap (logged).
- [ ] Judge "Coverage" dim rises vs pre-change scoreboard; hallucinated/off-domain
      papers stay at 0 (gate still works).

## Verify
```
docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft<known-gaps> --corpus corpus_a
# confirm expected missing papers present; check stage logs for recall
python scripts/eval/run_eval.py --quick   # Coverage dim up, hallucinations 0
```
