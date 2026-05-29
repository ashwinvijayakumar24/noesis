# Noesis Current Architecture

Last updated: May 10, 2026

For product status and next priorities, read `../current_state.md`. This file describes the current architecture shape.

## Summary

Noesis is a project-centered research workspace for academics. The live loop is:

1. sign in
2. create a project
3. build a literature base
4. generate a Literature Map
5. discover missing papers
6. upload a draft
7. analyze the draft against the project literature and external candidates
8. revise and compare versions

The main workspace is `ProjectDetail`. The full draft deep-review experience lives on `DraftAnalysis`.

## Product Surfaces

### Authenticated

- `Projects`: project list and project creation
- `ProjectDetail`: live workspace with `Literature`, `Literature Map`, `Discover`, `Drafts`
- `DraftAnalysis`: full analysis page for one draft version
- `DraftComparison`: version comparison surface
- `Pricing`: plan selection, pending production Stripe completion

### Public

- `Landing`
- `Demo`
- `Pricing`
- `PrivacyPolicy`
- `Login` / `SignUp`

## Data Boundaries

- `projects`: durable workspace container
- `documents`: canonical literature records for uploaded PDFs, imports, and saved recommendations
- `document_chunks`: embedding-backed full-text retrieval substrate
- `paper_recommendations`: Discover and Literature Map recommendation pool
- `drafts`: manuscript versions plus upload context
- `draft_analysis`: structured analysis payloads, Stage 1 output, metadata
- `draft_claims`: extracted claims and anchors
- `coverage_gaps`: missing evidence or coverage issues
- `reviewer_feedback`: normalized critique and Reviewer 1/Reviewer 2 items
- `draft_comparisons`: v1/v2 comparison outputs
- `user_quotas`: enforced plan limits and usage counters
- `subscriptions`: Stripe billing state

## Backend Domains

### Projects

Primary file: `services/backend/app/api/routes/projects.py`

Responsibilities:

- CRUD project container
- enforce project limits through `get_project_limit()`
- project bundle
- BibTeX import/export
- Literature Map generation and retrieval
- Literature Map quota/staleness/progress payloads

Key Literature Map endpoints:

```text
POST /projects/{id}/insights/analyze
GET  /projects/{id}/insights
```

### Documents

Primary file: `services/backend/app/api/routes/documents.py`

Responsibilities:

- PDF upload
- document analysis queueing
- document metadata updates
- export
- resolution status

Processing path:

```text
Upload -> Supabase Storage -> documents row -> Celery -> GROBID/PyMuPDF -> chunks -> embeddings -> GPT-5.2 analysis
```

### Discover

Current surface: `services/backend/app/api/routes/paper_recommendations.py`

Responsibilities:

- generate recommendations
- search recommendations
- expose paginated recommendation pool
- expose quota status
- save recommendations into the project library

Key endpoints:

```text
POST /paper-recommendations/projects/{id}/generate
POST /paper-recommendations/projects/{id}/search
GET  /paper-recommendations/projects/{id}
GET  /paper-recommendations/projects/{id}/quota-status
POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}
```

Legacy note: `services/backend/app/api/routes/paper_discovery.py` still exists and auto-adds papers. It should be treated as legacy cleanup unless intentionally revived.

### Drafts

Primary file: `services/backend/app/api/routes/drafts.py`

Responsibilities:

- draft upload
- paper type and citation style validation
- draft analysis lifecycle
- all-feedback payload
- WebSocket progress stream
- PDF report export

Key endpoints:

```text
POST /drafts/upload
GET  /drafts/{id}/all-feedback
GET  /drafts/{id}/analysis-stream
GET  /drafts/{id}/export-pdf
```

Draft analysis services:

- `draft_processing.py`
- `stage1_editing.py`
- `reviewer1_feedback.py`
- `reviewer_feedback.py`
- `coverage_analysis.py`
- `draft_external_source_discovery.py`
- `draft_anchor_qa.py`
- `draft_comparison.py`

### Billing And Quotas

Primary files:

- `services/backend/app/services/quota_management.py`
- `services/backend/app/services/stripe_service.py`
- `services/backend/app/api/routes/subscriptions.py`

Quota model:

- per-user, not per-project
- Free: 3 projects, 30 PDFs/month, 30 BibTeX refs/month, 2 drafts/month, 5 Discover actions/day, 5 Literature Map refreshes/day
- Pro: 10 projects, 100 PDFs/month, 100 BibTeX refs/month, 20 drafts/month, 50 Discover actions/day, unlimited Literature Map refreshes
- Team/Enterprise/Admin: effectively unlimited usage with hard caps

Stripe caveat:

The code has checkout, webhook handlers, and quota sync, but production billing is not done. Live price IDs, webhook verification, billing portal behavior, and checkout-to-quota-upgrade testing are still required.

## Processing Model

### Polling / Progress Snapshot

- document analysis
- Literature Map generation

Shared progress helpers live in `services/backend/app/services/progress_tracking.py`.

### Streaming

- draft analysis progress stream

Draft workflow progress is published from `services/backend/app/workflows/draft_analysis/graph.py`.

### Synchronous

- project creation
- document rename/update metadata
- save/dismiss recommendation
- export
- quota-status reads

## AI Model Use

- GPT-5.2 / `gpt-5.2-chat-latest`: substantive document analysis, Literature Map, claim extraction, reviewer critique
- `gpt-5-mini`: Stage 1 mechanical editing
- Embeddings: mostly `text-embedding-3-large` in RAG paths, with 1536-dimensional storage compatibility; some comparison paths use `text-embedding-3-small`

Do not use `max_tokens` in GPT-5.2 calls.

## Frontend Architecture

Primary pages:

- `ProjectDetail.tsx`: workspace tabs and project loop
- `DraftAnalysis.tsx`: full draft review experience
- `Pricing.tsx`: plan copy and checkout trigger
- `Landing.tsx`: GTM positioning
- `PrivacyPolicy.tsx`: privacy/no-training assurances

Primary components:

- `InsightsTab/`: Literature Map
- `DiscoverTab/`: Discover
- `DraftAnalysisModal.tsx`: draft upload/status entry
- `draft-analysis/*`: draft feedback panels, filters, cards, action items
- `literature/*`: literature cards and imported references

Design source: `services/frontend/tailwind.config.js`.

## Known Architectural Gaps

- Production Stripe remains unfinished.
- Collaboration and shared lab workspaces are not implemented.
- Inline editing/Overleaf workflow is not implemented.
- PDF figure/table/caption extraction is weak.
- Exact text anchors and claim support scoring need further work.
- Legacy Discover route should be deleted or fully deprecated.
- Structured error surfaces are inconsistent across frontend workflows.

## Acceptance Shape

A healthy Noesis build lets a researcher:

1. create a project
2. upload/import literature
3. generate a Literature Map
4. save missing papers
5. upload a draft with context
6. receive Stage 1 and reviewer-style feedback
7. jump from feedback to the relevant draft text where possible
8. revise and compare versions
9. understand quota/payment state clearly
