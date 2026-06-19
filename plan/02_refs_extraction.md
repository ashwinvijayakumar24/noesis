# Plan 02 — References-Section Extraction → "You forgot to cite X,Y,Z"

**Goal:** Automatically parse the draft's OWN reference list, resolve each entry
to metadata + abstract, embed it, and use it as a zero-friction per-draft
grounding corpus. Surface: "You cite [refs A,B] but your claim about X is better
supported by [ref C you listed but never cite]" and feed refs into grounding.

**Prereq:** Plans 00 + 01.

## Why
Upload-corpus is friction. Every draft already ships its references. This makes
grounding work with zero user upload and powers citation-accuracy (Plan 04).

## Reuse — the machinery already exists
- `app/services/bibtex_resolution_service.py`: OA PDF search → GROBID →
  GPT-5.2 → embed. This is EXACTLY the resolve-a-reference pipeline. Point it at
  the draft's extracted refs instead of imported BibTeX.
- GROBID is already in the Docker stack (recent commits enable Docling parser).
- `documents` table + `ingest_document` for storing resolved refs.

## Changes
1. **Extract references from the draft.** Add a step (new service
   `app/services/draft_reference_extraction.py`) that pulls the reference list
   from the parsed draft (GROBID/Docling already produces structured refs — check
   `parse_artifact`). Fall back to a regex/LLM pass on the "References" section
   if structured refs absent.
2. **Resolve each ref** via the bibtex_resolution machinery (metadata + abstract
   from OpenAlex/Crossref/Semantic Scholar — abstracts are free, NO PDF download
   needed for grounding). Embed abstracts.
3. **Two products from resolved refs:**
   a. **Grounding corpus** — feed into `literature_search` so claim support can
      match the author's own cited works (precise, guaranteed-relevant).
   b. **"Listed-but-unused" detection** — refs present in the bibliography but
      with no inline citation marker in the body → candidate "you cite this in
      your list but never actually use it" OR (combined with claims) "claim X is
      unsupported but ref C in your own list addresses it — cite it."
4. **New graph node** `extract_references` between `profile_manuscript` and
   `search_literature` (or fold into structure extraction). Store resolved refs
   in state as `resolved_references`.
5. **Surface** in `synthesis_report` (extend Plan 01 fields):
   `unused_references`, `claim_to_own_reference_suggestions`.

## Cost guardrail
- Metadata + abstracts only. Do NOT download + LLM-analyze every ref PDF.
- Embedding cost ≈ pennies/draft. Batch the API calls. Cache by DOI/title.

## Acceptance (via Plan 00 harness)
- [ ] For a draft with a real reference list, `resolved_references` is non-empty
      with abstracts resolved (>70% resolution rate on a real paper).
- [ ] Export contains `claim_to_own_reference_suggestions` linking ≥1 weak claim
      to a paper from the draft's own bibliography.
- [ ] `unused_references` flags refs in the list with no inline marker.
- [ ] Per-draft resolution stays under a sane token/time budget (log it).
- [ ] Works with `--no-corpus` (refs become the corpus).

## Verify
```
docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --no-corpus
# inspect resolved_references + claim_to_own_reference_suggestions in the export
```
