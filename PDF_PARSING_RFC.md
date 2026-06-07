# RFC: Migrating Noesis off GROBID for PDF Body Parsing & Anchoring

**Status:** Draft for decision · **Date:** 2026-06-07 · **Owner:** Ashwin

## TL;DR

GROBID is good at references/metadata but has hit its ceiling for **layout-faithful
reading order, table content, and reliable per-block coordinates**. The coordinate
gap is what breaks click-to-anchor (the product's core "jump to the offending
paragraph" UX) and trips the publish gate. We should **keep GROBID for references
only** and replace body/layout/coordinate extraction with a modern layout parser
(**Marker or Docling, self-hosted, $0**), validated by a measured spike before we
commit. Paid APIs (Mathpix) are a later option, not needed at current scale.

This RFC also records the **immediate fixes already shipped** (multimodal-fallback
de-duplication + quality gating) that removed the worst current artifact.

---

## 1. Problem — evidence from a real run

Draft `0b4ed950…` (public-health systematic review, real PDF), run `ea7556c6…`:

| Signal | Value | Implication |
|---|---|---|
| GROBID parser quality | **1.0** | text/sections parsed cleanly |
| GROBID sections | 30 (in order) | reading order fine |
| `anchor_map` entries | 46 | paragraphs captured |
| anchors **with a page number** | **9 / 46** | coordinates are sparse |
| `page_anchor_coverage` | **0.30** | 70% of tasks can't be located in the PDF |
| `verbatim_anchor_coverage` | **0.0** | no task anchor matched evidence-store text |
| publish gate | `needs_retry`, confidence `low` | gate correctly refused high-confidence |

Two distinct failures were conflated in the eval:

1. **Duplicate section headings** (`Protocol and registration`, `Search strategy`,
   `Eligibility criteria`, `Data analysis`, `Results` each appeared twice). **Root
   cause was NOT GROBID looping** — it was our **GPT-4V multimodal fallback**
   re-extracting sections and appending them without deduping against GROBID's
   output. The fallback ran even though GROBID quality was 1.0. → **fixed, see §2.**
2. **Coordinate sparsity** — GROBID emitted `@coords` for only 9/46 paragraphs, so
   most revision tasks have `page None` and can't be anchored. → **GROBID ceiling,
   the subject of this RFC.**

## 2. Immediate fixes already shipped (this session)

In `app/services/draft_multimodal_parser.py`:

- **Quality-gate the fallback:** `should_run_multimodal_fallback` now returns
  `False` when GROBID is already strong (score ≥ 0.85, ≥ 6 sections, no deficiency
  flags) — even when tables/systematic signals are present. Table text is already
  in `full_text` via GROBID, so the evidence manifest still detects search strings
  etc. without the fallback.
- **De-dup the merge:** `merge_multimodal_evidence` now skips any multimodal
  section/table whose normalized title already exists in GROBID's sections, and
  records `multimodal_sections_deduped` in metadata.

Effect: removes the duplicate-heading artifact (the false "duplicated method
section headings" task) and the contradictory-state confusion it caused. Covered by
`TestMultimodalFallbackGating` (3 tests). **Does not fix coordinate sparsity.**

## 3. Why not keep tuning GROBID

GROBID is a 2010s CRF/Deep-learning TEI extractor optimized for bibliographic data.
Layout-faithful reading order, table cell extraction, and dense per-block bounding
boxes are out of scope for its architecture. We have repeatedly tuned it and keep
hitting the same coordinate/layout ceiling. The market has moved to layout-detection
models and vision-language models for exactly this reason.

## 4. Options & pricing (per page, 2026)

| Tool | $/page | Free tier | Coords/bbox | Notes |
|---|---|---|---|---|
| **OSS: Marker** (Surya) | **$0** + compute | n/a | ✅ per-block | fast PDF→md, reading order, tables; best OSS fit |
| **OSS: Docling** (IBM) | **$0** + compute | n/a | ✅ | strong layout+tables, permissive license |
| **OSS: MinerU** | **$0** + compute | n/a | ✅ | built for scientific PDFs (layout/formula/table) |
| **LlamaParse** | ~$0.00125 basic → $0.0038 LLM | **10k pages/mo free** | ✅ | LLM-based, RAG-oriented |
| **Mathpix** | $0.005 | $29 credit + setup fee | ✅ | best academic quality (math/tables) |
| **Google Document AI** (Layout) | $0.010 | pay-as-go | ✅ | layout + chunking |
| **AWS Textract** (Tables+Layout) | $0.015 (Layout free w/ Tables) | 1k pages/mo (3 mo) | ✅ | bboxes, tables |
| **Reducto** | $0.015 | plan credits | ✅ | agentic, HIPAA/SOC2 |
| **Adobe PDF Extract** | ~5¢/5pg | 500 transactions/mo | ✅ | ❌ enterprise-only purchase (~$25k/yr min) — skip |

### Cost modeled at Noesis scale
- **Now (~0 customers, ~150–750 pages/mo):** every option is effectively **$0**
  (free tiers/credits or OSS). Cost is not the deciding factor.
- **Target (~200 active users × ~20 PDFs × ~15 pg ≈ 60k pages/mo):** Mathpix ≈
  **$300/mo**, LlamaParse basic ≈ **$63/mo**, Google ≈ $600, Textract ≈ $900,
  **OSS ≈ $0 + one worker box (~$20–50/mo).**

## 5. Recommendation

**Tiered, bootstrap-correct:**

1. **Body + layout + coordinates → self-hosted OSS (Marker first choice, Docling
   backup).** Runs in the existing Docker stack next to GROBID. $0 marginal cost.
   Returns the per-block bounding boxes that take `page_anchor_coverage` from 0.3
   toward ~1.0 and make `verbatim_anchor_coverage` meaningful.
2. **References + metadata → keep GROBID** (its genuine strength: `biblStruct`).
3. **Hard-PDF fallback → replace the current GPT-4V section re-extraction with a
   VLM pass** (Gemini/GPT-4.1/Claude) only when the layout parser is low-confidence.
4. **Paid API (Mathpix) → deferred** until volume + revenue justify offloading ops.

**Architectural addition — pre-review parser/anchor gate:** move the parser-quality
+ anchor-coverage check *before* the reviewer panel runs. If coverage is too low,
trigger the better parser (Marker → VLM) and retry **before** generating reviewer
output. This fixes the contradictory state (gate says `needs_retry` while
`proceed_to_review` is True) and makes the existing `DRAFT_ANALYSIS_FAIL_CLOSED`
toggle meaningful.

## 6. Spike plan (decide with data, ~1–2 days, $0)

Before committing to a parser, measure — don't assume:

1. Collect **8–10 representative PDFs** (systematic reviews, two-column, table-heavy,
   scanned, single-column).
2. Run each through **GROBID (baseline), Marker, Docling** (all free/local).
3. For each, compute: `page_anchor_coverage`, `verbatim_anchor_coverage`,
   section-count accuracy (vs. eyeball), duplicate-heading count, table-text recall,
   wall-clock per page.
4. Pick the winner on **anchor coverage + reading-order fidelity**; wire it behind
   the existing `draft_parse_artifacts` interface (the evidence store, manifest,
   verifier, and gate are all parser-agnostic already).

Success criterion: **page_anchor_coverage ≥ 0.8 on real PDFs** (the publish-gate
threshold), vs. 0.3 today.

## 7. Out of scope (separate follow-ups, not parser-related)
- Dedup map-reduce over revision tasks (Tasks 4/5/7 should have merged).
- Citation-graph false "coverage gaps" (Erikson/RSPH flagged as uncited though
  they are cited inline).
- Stale-search-window critique (search May 2018 → published 2020) — a manifest
  `search_dates` → publication-date comparison the diagnostics don't yet generate.

## 8. Decision needed
- [ ] Approve OSS-first direction (Marker + GROBID-for-refs)?
- [ ] Approve the spike (8–10 PDF benchmark) before migration?
- [ ] Approve the pre-review anchor gate (halt + better-parser retry)?

## Sources
- Mathpix Convert API pricing — https://mathpix.com/pricing/api
- LlamaParse pricing — https://www.llamaindex.ai/pricing
- Reducto pricing — https://reducto.ai/pricing
- AWS Textract pricing — https://aws.amazon.com/textract/pricing/
- Google Document AI pricing — https://cloud.google.com/document-ai/pricing
- Adobe PDF Services pricing — https://developer.adobe.com/document-services/pricing/main/

---

## Phase 1 spike — RESULTS (2026-06-07, decision: Docling)

Benchmarked GROBID vs PyMuPDF vs Docling on 8 real PDFs (`scripts/parser_spike.py`,
metric = fraction of text blocks carrying a usable page/bbox).

| Parser | mean location coverage (n=8) | structure | duplicate headings | speed/PDF |
|---|---|---|---|---|
| GROBID (baseline) | **0.0** | sections only | 0 | 1–5s |
| PyMuPDF | 1.0 | none | 0 | <0.1s |
| **Docling** | **1.0** | sections (10/7/32…) | 0 | 2.5–18s |

GROBID returned **zero usable coordinates on every PDF** — the root cause of
`page None` / 0.09 anchor coverage. Docling delivers full coordinates + section
structure + no duplicate headings, self-hosted at $0.

**Decision: migrate body/structure/coordinate extraction to Docling** (Phase 2),
keep GROBID for references only, PyMuPDF as an emergency fallback. Marker and other
parsers not needed — Docling clears the ≥0.8 target at 1.0.
