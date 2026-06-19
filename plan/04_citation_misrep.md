# Plan 04 — Citation Misrepresentation Check ("cited paper doesn't support claim")

**Goal:** The category moat. Detect when the author cites a paper that does not
actually support — or contradicts — the claim it's attached to. Reviewer 2's
nightmare finding. Few competitors do this well.

**Prereq:** Plans 00, 01, 02 (need resolved references with abstracts/content).

## The idea
For each inline citation in the draft: (claim text + citation marker) → resolve
the cited paper (Plan 02 gives metadata + abstract; fetch full text only when
needed) → ask: does this source support the claim as stated?
Verdicts: `supports | partial | unrelated | contradicts | overclaim`.

## Changes
1. **Map inline citations to claims.** Claims already carry
   `has_inline_citation` (see `nodes/claim_extraction.py`). Extend extraction to
   capture WHICH reference key each inline marker points to, linking claim →
   resolved reference (from Plan 02).
2. **New node** `verify_citations` (after `extract_references` / before or beside
   `map_citations`). For each (claim, cited_ref) pair:
   - Use the cited paper's abstract (cheap). Escalate to full-text fetch ONLY for
     pairs flagged `partial`/`contradicts` at the abstract level (cost control).
   - GPT-5.2 structured verdict + REQUIRED verbatim evidence quote from the cited
     source. No quote → no adverse verdict (anti-hallucination guard).
3. **Severity:** `contradicts` / `overclaim` = high-severity revision task.
   `unrelated` = medium. Feed into revision tasks + synthesis_report as
   `citation_verdicts`.
4. **Anchor** each finding to the verbatim claim text in the draft (reuse the
   existing anchoring utilities).

## Anti-hallucination (critical for this feature's credibility)
- A misrepresentation verdict MUST cite an exact quote from the cited source.
- If the source can't be resolved/fetched, emit `unverifiable` — never guess.
- Judge (Plan 00) hard-fails any verdict lacking source evidence.

## Acceptance (via Plan 00 harness)
- [ ] For a draft where a citation is deliberately mismatched (craft one in
      `gold/` with the expected verdict), the node returns the correct verdict
      with a verbatim source quote.
- [ ] `citation_verdicts` present in export; high-severity ones become revision tasks.
- [ ] Zero verdicts without source evidence (judge confirms 0 hallucinations).
- [ ] Cost bounded: full-text fetch only on flagged pairs (logged count).

## Verify
```
docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft<misrep-test> --no-corpus
# confirm citation_verdicts with verbatim evidence; check escalation count in logs
```
