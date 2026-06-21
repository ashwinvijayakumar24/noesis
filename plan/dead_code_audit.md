# Dead Code Audit

Generated: 2026-06-21

Scope: report only. No files were deleted. Excluded from deletion candidacy per instruction: `scripts/eval/**`, `services/backend/app/workflows/draft_analysis/**`, root docs/agent files, OpenReview plan/archive paths, `Makefile`, `infra/**`, `.github/**`, and eval gold/legacy judge files.

## FRONTERPHANS

Method: enumerated `services/frontend/src/**/*.ts(x)`, resolved static relative imports/exports plus `import(...)`, then spot-checked candidates with `rg` across `services/frontend/src`. Evidence below means the grep had no active import or JSX usage outside the file itself unless noted.

### High Confidence Candidates

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/frontend/src/components/CompassPage.tsx` | 16731 | Empty outside self: `rg -n "CompassPage|from .*CompassPage|import\\(.*CompassPage" services/frontend/src` | high |
| `services/frontend/src/components/DiscoverTab/index.tsx` | 23157 | Empty outside self for `DiscoverTab`; no `../components/DiscoverTab` import. | high |
| `services/frontend/src/components/DocumentDetailModal.tsx` | 3612 | Empty outside self: `rg -n "DocumentDetailModal|from .*DocumentDetailModal" services/frontend/src` | high |
| `services/frontend/src/components/DraftAnalysisModal.tsx` | 43859 | Empty outside self: `rg -n "DraftAnalysisModal|from .*DraftAnalysisModal" services/frontend/src` | high |
| `services/frontend/src/components/FeedbackButton.tsx` | 9542 | Empty outside self: `rg -n "FeedbackButton|from .*FeedbackButton" services/frontend/src` | high |
| `services/frontend/src/components/InsightsTab/SectionHeader.tsx` | 1632 | Empty outside self: no `SectionHeader` import from `InsightsTab`. | high |
| `services/frontend/src/components/InsightsTab/index.tsx` | 25418 | Empty outside self for `InsightsTab`; no `../components/InsightsTab` import. | high |
| `services/frontend/src/components/LiteratureReviewCompass.tsx` | 10910 | Empty outside self: `rg -n "LiteratureReviewCompass|from .*LiteratureReviewCompass" services/frontend/src` | high |
| `services/frontend/src/components/TagInput.tsx` | 8276 | Empty outside self: `rg -n "TagInput|from .*TagInput" services/frontend/src` | high |
| `services/frontend/src/components/compass/SynthesisQuestionsMindMap.tsx` | 8685 | Empty outside self: no import from `compass/SynthesisQuestionsMindMap`. | high |
| `services/frontend/src/components/draft-analysis/ActionItems.tsx` | 13602 | Empty outside self: no import from `draft-analysis/ActionItems`. | high |
| `services/frontend/src/components/draft-analysis/AnalysisFilters.tsx` | 6641 | Empty outside self: no import from `draft-analysis/AnalysisFilters`. | high |
| `services/frontend/src/components/draft-analysis/CitationsPanel.tsx` | 429 | Empty outside self: no import from `draft-analysis/CitationsPanel`. | high |
| `services/frontend/src/components/draft-analysis/ClaimsPanel.tsx` | 4940 | Empty outside self: no import from `draft-analysis/ClaimsPanel`. | high |
| `services/frontend/src/components/draft-analysis/CoverageGapsTab.tsx` | 17333 | Empty outside self: no import from `draft-analysis/CoverageGapsTab`. | high |
| `services/frontend/src/components/draft-analysis/FeedbackPanel.tsx` | 3807 | Empty outside self: no import from `draft-analysis/FeedbackPanel`. | high |
| `services/frontend/src/components/draft-analysis/GapsPanel.tsx` | 3653 | Empty outside self: no import from `draft-analysis/GapsPanel`. | high |
| `services/frontend/src/components/draft-analysis/OverviewScoreCard.tsx` | 4614 | Empty outside self: no import from `draft-analysis/OverviewScoreCard`. | high |
| `services/frontend/src/components/draft-analysis/PriorityGroup.tsx` | 3996 | Empty outside self: no import from `draft-analysis/PriorityGroup`. | high |
| `services/frontend/src/components/draft-analysis/ReviewerFeedbackTab.tsx` | 21630 | Empty outside self: no import from `draft-analysis/ReviewerFeedbackTab`. | high |
| `services/frontend/src/components/literature/DocumentCard.tsx` | 6404 | Empty outside self: no import from `literature/DocumentCard`. | high |
| `services/frontend/src/components/literature/ImportedRefCard.tsx` | 4948 | Empty outside self: no import from `literature/ImportedRefCard`. | high |
| `services/frontend/src/components/project/ContextPanel.tsx` | 2697 | Empty outside self: no import from `project/ContextPanel`. | high |
| `services/frontend/src/components/project/MainWorkspace.tsx` | 4181 | Empty outside self: `rg -n "MainWorkspace|from .*MainWorkspace" services/frontend/src` | high |
| `services/frontend/src/components/project/Sidebar.tsx` | 9512 | Empty outside self for `project/Sidebar`; `Sidebar` hits are unrelated sidebar components. | high |
| `services/frontend/src/components/ui/BentoGrid.tsx` | 5042 | Empty outside self: no import from `ui/BentoGrid`. | high |
| `services/frontend/src/components/ui/Input.enhanced.tsx` | 6562 | Empty outside self; superseded by `Input.tsx` naming. | high |
| `services/frontend/src/components/ui/Input.tsx` | 3008 | Empty outside self: no import from `ui/Input`. | high |
| `services/frontend/src/components/ui/Modal.tsx` | 2667 | Empty outside self: no import from `ui/Modal`. | high |
| `services/frontend/src/components/ui/Toast.tsx` | 2040 | Empty outside self: no import from `ui/Toast`. | high |
| `services/frontend/src/components/ui/Tooltip.tsx` | 5111 | Empty outside self: no import from `ui/Tooltip`. | high |
| `services/frontend/src/components/ui/index.ts` | 282 | Empty outside self: no imports from `components/ui` barrel. | high |
| `services/frontend/src/hooks/useCountUp.tsx` | 3015 | Empty outside self: no import of `useCountUp`. | high |
| `services/frontend/src/hooks/useProgressTracker.ts` | 3140 | Empty outside self: no import of `useProgressTracker`. | high |
| `services/frontend/src/pages/NotFound.tsx` | 1451 | Empty outside self; `App.tsx` fallback currently redirects with `<Navigate to="/" />`. | high |

### Medium/Low Confidence Or KEEP

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/frontend/src/components/ReferralWidget.tsx` | 7793 | No active import; appears only inside a commented JSX block in `pages/Projects.tsx`. Treat as inactive, but confirm product intent before deleting. | med |
| `services/frontend/src/components/project/MethodologyAnalysisView.tsx` | 15868 | KEEP: dynamic import from `components/project/MainWorkspace.tsx`. | keep |
| `services/frontend/src/components/project/ResearchPlanningView.tsx` | 7062 | KEEP: dynamic import from `components/project/MainWorkspace.tsx`. | keep |
| `services/frontend/src/pages/AnalyticsDashboard.tsx` | 10777 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/AuthCallback.tsx` | 5436 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/ConfirmEmail.tsx` | 3864 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/Demo.tsx` | 5565 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/DocumentAnalysis.tsx` | 24019 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/DraftAnalysis.tsx` | 21795 | KEEP: lazy dynamic import from `App.tsx` and test import. | keep |
| `services/frontend/src/pages/Landing.tsx` | 17465 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/Login.tsx` | 14305 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/Pricing.tsx` | 10576 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/PrivacyPolicy.tsx` | 13835 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/ProjectDetail.tsx` | 35935 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/Projects.tsx` | 15720 | KEEP: lazy dynamic import from `App.tsx`. | keep |
| `services/frontend/src/pages/SignUp.tsx` | 15921 | KEEP: lazy dynamic import from `App.tsx`. | keep |

## BACKEND ORPHANS

Method: parsed Python AST imports for `services/backend/app/**/*.py`, then checked direct module-path greps and symbol-name greps. Excluded `services/backend/app/workflows/draft_analysis/**`.

### High/Medium Confidence Candidates

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/backend/app/services/reviewer1_feedback.py` | 5249 | Empty app import grep: no `app.services.reviewer1_feedback` imports outside tests. Only hits are tests/dynamic test loading and its own function definition. | high |
| `services/backend/app/services/reviewer_feedback.py` | 49892 | Empty app import grep: no runtime import of `app.services.reviewer_feedback`. Name hits are mostly table names or tests; active draft pipeline uses `workflows/draft_analysis/nodes/reviewer_feedback.py`, which is hands-off. | high |
| `services/backend/app/tasks/paper_recommendation_tasks.py` | 1270 | No route/service caller of `generate_paper_recommendations_task`; only imported by `app/tasks/__init__.py`. Celery `include=[...]` omits this module, but `autodiscover_tasks(["app.tasks"])` means registration should be checked before deletion. | med |

### KEEP / False Positives

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/backend/app/services/external_apis/arxiv.py` | 7952 | KEEP: re-exported by `services/backend/app/services/external_apis/__init__.py`; consumed as `ArXivAPI` by `services/backend/app/services/paper_recommendations.py`. | keep |
| `services/backend/app/workflows/document_analysis/nodes/claim_extraction.py` | 7017 | KEEP: re-exported by `workflows/document_analysis/nodes/__init__.py`; graph imports node functions from that package. | keep |
| `services/backend/app/workflows/document_analysis/nodes/findings_extraction.py` | 7422 | KEEP: re-exported by `workflows/document_analysis/nodes/__init__.py`; graph imports node functions from that package. | keep |
| `services/backend/app/workflows/document_analysis/nodes/methodology_extraction.py` | 6931 | KEEP: re-exported by `workflows/document_analysis/nodes/__init__.py`; graph imports node functions from that package. | keep |
| `services/backend/app/workflows/document_analysis/nodes/structure_extraction.py` | 5089 | KEEP: re-exported by `workflows/document_analysis/nodes/__init__.py`; graph imports node functions from that package. | keep |
| `services/backend/app/workflows/document_analysis/nodes/synthesis.py` | 7580 | KEEP: re-exported by `workflows/document_analysis/nodes/__init__.py`; graph imports node functions from that package. | keep |
| `services/backend/app/api/routes/*.py` | varies | KEEP: registered through `from app.api.routes import ...` in `services/backend/app/main.py`, then `app.include_router(...)`. | keep |

## STALE TESTS

No high-confidence stale tests found by missing-module import scan.

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/frontend/src/components/InsightsTab/literatureMap.test.ts` | 3239 | KEEP: sibling `literatureMap.ts` exists; zero inbound is normal for test entrypoints. | keep |
| `services/frontend/src/pages/DraftAnalysis.test.ts` | 1787 | KEEP: imports existing `DraftAnalysis.tsx`; zero inbound is normal for test entrypoints. | keep |
| `services/frontend/src/pricingCopy.test.ts` | 4890 | KEEP: reads existing public/pricing source files; zero inbound is normal for test entrypoints. | keep |
| `services/backend/tests/test_draft_analysis_v2.py` | 19400 | Review later: `_v2` naming suggests superseded coverage, but imports dynamically from existing files and is not stale by missing-module evidence. | low |

## DUPLICATE/SUPERSEDED

| File | Size | Evidence | Confidence |
| --- | ---: | --- | --- |
| `services/frontend/src/components/ui/Input.enhanced.tsx` | 6562 | Parallel implementation next to `Input.tsx`; no inbound imports. | high |
| `services/backend/app/services/reviewer_feedback.py` | 49892 | Legacy service-level implementation overlaps with active `workflows/draft_analysis/nodes/reviewer_feedback.py`; no runtime import of service module. | high |
| `services/backend/app/services/reviewer1_feedback.py` | 5249 | Legacy reviewer-1 service overlaps with current reviewer panel/meta-review workflow; no runtime import of service module. | high |
| `services/backend/tests/test_draft_analysis_v2.py` | 19400 | `_v2` test name suggests historical/superseded coverage, but it still references existing modules; review manually before deleting. | low |
