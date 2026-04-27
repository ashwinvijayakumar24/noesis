# Noesis Current Architecture

## Summary

Noesis is a project-centered research workspace for academics. The live product loop is:

1. sign in
2. create a project
3. build the literature base
4. generate a Literature Map
5. discover missing papers
6. upload a draft
7. analyze the draft against the project literature
8. iterate with new papers and revised drafts

The main workspace is the current `ProjectDetail` path. The draft deep-review experience lives on the dedicated draft analysis page.

## Product Surfaces

### Authenticated Workspace

- `Projects`
  - dashboard of project containers
- `ProjectDetail`
  - the live project workspace
  - tabs: `Literature`, `Discover`, `Drafts`, `Literature Map`
- `DraftAnalysis`
  - full-page analysis experience for one draft version

### Supporting Surfaces

- `Landing`
- `Pricing`
- `Privacy`

## Core User Flow

### 1. Create a Project

Projects are the durable container for:

- literature
- Literature Map outputs
- Discover recommendations
- drafts
- revision history

### 2. Build Literature

Users add papers through:

- PDF upload
- BibTeX import
- Zotero import
- saving recommendations from Discover or Literature Map

Documents converge into one literature system:

- analyzed PDFs become full-text evidence with embeddings and structured analysis
- unresolved BibTeX or discovered items remain metadata-only
- document retry, rename, export, filtering, and save paths all belong to the same literature surface

### 3. Generate a Literature Map

The Literature Map is the project-level synthesis layer. It combines:

- freshness and quota state
- a deterministic Coverage Snapshot
- field overview and grounded key insights
- research gaps and conflicts
- top-level and inline recommended papers

The Literature Map becomes stale when the analyzed literature changes. Freshness is determined on the server.

### 4. Discover Missing Papers

Discover is the acquisition surface for papers not yet in the project library.

It supports:

- recommendation generation
- search-driven discovery
- pagination
- save
- dismiss

Saved papers flow into the same `documents` table and refresh the rest of the project state through the normal literature pipeline.

### 5. Upload and Analyze a Draft

Draft upload captures manuscript context before processing:

- `paper_type`
- `citation_style`

Draft analysis is split conceptually into:

- Stage 1: editing and mechanical review
- Stage 2: reviewer-style substantive critique

The draft analysis view should surface:

- editing feedback
- reviewer feedback
- coverage gaps
- citation and evidence issues
- external papers for gaps
- version-over-version carryover and resolved items

### 6. Iterate

The product loop is:

- save missing papers
- refresh the Literature Map when stale
- upload a revised draft
- compare versions
- confirm which issues were resolved

## Backend Architecture

### Primary Route Domains

- `projects`
  - project container
  - project bundle
  - Literature Map generation and retrieval
  - BibTeX project import and export
- `documents`
  - PDF upload
  - document retry
  - document export and metadata updates
- `paper_recommendations`
  - Discover generation
  - search
  - pagination
  - save and dismiss
- `drafts`
  - draft upload
  - analysis lifecycle
  - WebSocket progress
  - all-feedback and gap paper lookup
- `subscriptions`
  - billing and plan checkout
- `auth`
  - auth and quota summary

### Shared Services

- `quota_management`
  - canonical per-user enforcement source
- `stripe_service`
  - syncs billing state into enforced quota state
- `progress_tracking`
  - shared progress snapshots for polling-based workflows
- `project_insights`
  - Literature Map synthesis and validation
- `paper_recommendations`
  - recommendation generation and context grouping
- draft-analysis services
  - draft processing
  - stage 1 editing
  - reviewer feedback
  - draft comparison
  - coverage analysis

## Data Model Boundaries

### Core Records

- `projects`
  - container for the workspace and Literature Map state
- `documents`
  - canonical literature records for PDFs, imports, and saved recommendations
- `document_chunks`
  - embedding-backed retrieval substrate for analyzed full text
- `paper_recommendations`
  - Discover inventory plus Literature Map recommendation context
- `drafts`
  - manuscript versions with upload context
- `draft_analysis`
  - structured outputs for a draft version
- `reviewer_feedback`
  - normalized per-item critique and resolution state
- `user_quotas`
  - single source of truth for enforced plan limits

### Draft Analysis Record Split

- `structure`
  - extracted manuscript structure
- `analysis`
  - substantive outputs like `editing_feedback`
- `analysis_metadata`
  - runtime, scoring, and processing details

## Processing Model

### Polling Workflows

- document analysis
- Literature Map generation

These expose `status` plus progress snapshots.

### Streaming Workflow

- draft analysis

This remains the real-time workflow and uses the draft analysis WebSocket stream.

### Synchronous Actions

- project creation
- save recommendation
- dismiss recommendation
- rename/update metadata
- export

## Public Interface Expectations

### Project Bootstrap

- `GET /projects/{id}/bundle`
  - project metadata plus attached documents

### Literature Map

- `POST /projects/{id}/insights/analyze`
  - starts Literature Map generation
- `GET /projects/{id}/insights`
  - single source of truth for Literature Map UI state

### Discover

- `POST /paper-recommendations/projects/{id}/generate`
- `POST /paper-recommendations/projects/{id}/search`
- `GET /paper-recommendations/projects/{id}`
- `POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}`

### Drafts

- `POST /drafts/upload`
- `GET /drafts/{id}/all-feedback`
- `POST /drafts/{id}/gaps/{gap_id}/find-papers`
- `GET /drafts/{id}/analysis-stream`

## UX Rules

### Trust

- private by default
- files stay in the user workspace
- files are not used to train models

### Long-Running Work

- document analysis and Literature Map use polling plus progress
- draft analysis uses WebSocket progress
- structured errors should expose the next action, not just raw failure text

### Quotas

Quotas are per user, not per project.

Current plan model:

- Free
  - 30 PDFs/month total
  - 30 BibTeX refs/month total
  - 2 draft analyses/month
  - 5 Discover actions/day
  - 5 Literature Map refreshes/day
- Pro
  - 100 PDFs/month total
  - 100 BibTeX refs/month total
  - 20 draft analyses/month
  - 50 Discover actions/day
  - unlimited Literature Map refreshes
- Team
  - effectively unlimited usage

## Acceptance Shape

If the architecture is functioning correctly, a user should be able to:

1. create a project
2. upload or import literature
3. generate a Literature Map
4. save missing papers into the project library
5. upload a draft with manuscript context
6. receive editing and reviewer-style analysis
7. revise and re-upload
8. see what resolved and what still persists
