# Mini-Plans Index

Split of `arch_plan.md` into per-issue documents. Each file below covers one feature area or cleanup category. Edit each in isolation; the priority list here is the global ordering.

## Files

| # | File | Scope |
|---|---|---|
| 00 | **INDEX** (this file) | Global priority list + navigation |
| 01 | `01_auth_and_signin.md` | Supabase OAuth, branded consent screen, landing vs login |
| 02 | `02_projects_and_tags.md` | Project limits (Pro = 999 bug), document-level tags |
| 03 | `03_literature_upload_pdf.md` | PDF path: GROBID, parallel upload, retry button, exports |
| 04 | `04_literature_upload_bibtex.md` | BibTeX path: resolver, unresolved-ref exclusion, malformed input |
| 05 | `05_literature_insights.md` | "Insights" feature: quota leak, staleness, rename, citation anchors |
| 06 | `06_discover_papers.md` | Discovery staging, dismissal tracking, save-flow, gating |
| 07 | `07_draft_analysis.md` | Core feature: R1/R2 split, Stage 1/2, pre-upload Q, external pull, privacy |
| 08 | `08_quotas_and_plan_tier.md` | Cross-cutting quota bugs, Stripe webhook, per-project vs per-user |
| 09 | `09_cross_cutting_trust_ux.md` | Error surfaces, progress visibility, OpenAI rate limits, privacy copy |
| 10 | `10_answered_questions.md` | Shared paper cache, image parsing stacks, competitive benchmarks |
| 11 | `11_cleanup_dead_code.md` | Unused services, components, migration conflict |
| 12 | Completed | Old `.md` files archived under `docs/historical/` |

## Global Priority List

### P0 — must fix before outreach
1. Insights quota enforcement → `05_literature_insights.md` §5a
2. Plan-aware quotas (Stripe webhook) → `08_quotas_and_plan_tier.md`
3. Privacy copy on draft upload → `07_draft_analysis.md` §7f + `09_cross_cutting_trust_ux.md` §10.5
4. Fix Pro project limit (999 → 10) → `02_projects_and_tags.md`
5. Commit pending deletions and archival cleanup

### P1 — core feature gaps impacting demo quality
6. Draft — Reviewer 1 / Reviewer 2 persona split → `07_draft_analysis.md` §7b
7. Draft — Stage 1 (gpt-5-mini) / Stage 2 (gpt-5.2) separation → `07_draft_analysis.md` §7a
8. Draft — pre-upload questions → `07_draft_analysis.md` §7c
9. Draft — external paper pull per gap → `07_draft_analysis.md` §7d
10. Draft — per-item resolution state (v1→v2 UI) → `07_draft_analysis.md` §7e
11. Discover — staging table + save-on-click via BibTeX resolver → `06_discover_papers.md` §6b
12. Discover — dismissal tracking → `06_discover_papers.md` §6c
13. Insights — rename + citation anchors + raw chunks → `05_literature_insights.md` §5c
14. Upload — retry button on failed documents → `03_literature_upload_pdf.md` §3c
15. BibTeX — exclude `resolution_status='unresolved'` from draft analysis → `04_literature_upload_bibtex.md` §4a
16. OAuth branded consent screen → `01_auth_and_signin.md`

### P2 — quality and completeness
17. Figure/table extraction → `10_answered_questions.md` §9.2 + `03_literature_upload_pdf.md` §3b
18. Feedback categories: add `reproducibility` and `limitations` → `07_draft_analysis.md` §7i
19. Document-level tags → `02_projects_and_tags.md`
20. `.txt` export format → `03_literature_upload_pdf.md` §3f
21. Tab gating: Discover requires ≥1 document → `06_discover_papers.md` §6e
22. Insights → Discover pre-population → `06_discover_papers.md` §6f
23. Stepwise progress visibility → `09_cross_cutting_trust_ux.md` §10.4
24. Structured BibTeX parse errors → `04_literature_upload_bibtex.md` §4e

### P3 — cleanup
25. Delete 3 unused backend services → `11_cleanup_dead_code.md`
26. Delete 5 unused frontend components → `11_cleanup_dead_code.md`
27. Consolidate RAG + claim duplicates → `11_cleanup_dead_code.md`
28. Rename `017_draft_comparisons.sql` to resolve duplicate numbering → `11_cleanup_dead_code.md`
29. Archive stale planning docs under `docs/historical/` and remove root-level drift
30. Decide fate of `api/routes/rag.py` and `api/routes/compass.py` → `11_cleanup_dead_code.md`

## Source
Full audit with executive summary table: `arch_plan.md` at the repo root.
