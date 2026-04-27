# Claude.md: Noesis Draft-Aware Research Intelligence Platform

> **Quick Context (April 2026):** Noesis is a project-centered research workspace for academics. The live product loop is `Literature -> Literature Map -> Discover -> Draft Analysis -> Revision`. Current priority is end-to-end verification and production hardening after the mini-plan implementation pass. Tech: React + FastAPI + Supabase + Celery/Redis + **GPT-5.2**.

## ⚠️ CRITICAL: Current Session Context (April 2026)

### What We Are Working On RIGHT NOW
1. **End-to-end verification** — validating the project workspace flow across literature, Literature Map, Discover, and drafts
2. **Production hardening** — confirm quota behavior, progress states, retry behavior, and deploy wiring
3. **GPT-5.2 discipline** — API uses `max_completion_tokens`, never `max_tokens`

### GPT-5.2 API Breaking Change (IMPORTANT)
All OpenAI calls now use `gpt-5.2` model. GPT-5.2 requires `max_completion_tokens` instead of `max_tokens`:
```python
# ✅ CORRECT for GPT-5.2
response = client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    ...
)
# ❌ WRONG — causes 400 error with GPT-5.2
# max_tokens=2000
```
This was fixed in 15 files (see `GPT52_API_FIX.md`). Do NOT revert to `max_tokens`.

### Document Upload Status
- ✅ Race condition fixed: backend auto-triggers analysis after RAG ingestion completes
- ✅ Multi-select upload: up to 10 PDFs simultaneously with parallel processing
- ✅ Success modal simplified: clean UX, no technical jargon
- ✅ Celery configured for 4 concurrent tasks
- ⚠️ OpenAI rate limits: free tier is 3 req/min — need to upgrade to Tier 1 for batch uploads
- ⚠️ Still testing: verify full project loop and remote CI/CD access end to end

### Design System Reference
Design tokens live in `services/frontend/tailwind.config.js` (source of truth). Key rules:
- Dark charcoal theme (`bg-bg-void: #0F0F14`, `bg-bg-surface: #18181F`)
- Rose-crimson accent (`accent-primary: #E5484D`)
- `border-border-default: rgba(255,255,255,0.08)` for all borders
- Max `rounded-xl` (12px), no `rounded-2xl` or `rounded-3xl`
- 150ms transitions, Inter font, font-semibold (NOT font-bold)

### Dual Tool Workflow
This project is worked on with both **Claude Code** and **Cursor Pro**. See `mini-plans/00_INDEX.md` and the active mini-plan for current state. Always commit before switching tools.

### Current Product Architecture
The current-state product architecture and user flow live in `docs/current-architecture.md`.

## Project Overview

Noesis is a draft-aware research intelligence platform that provides expert academic reviewer-style feedback on research drafts. The platform analyzes user-written manuscripts alongside their literature collections to identify unsupported claims, detect coverage gaps, and map arguments to supporting citations.

### Core Transformation
- **From**: Basic literature review generator
- **To**: Draft-aware research intelligence platform for serious researchers (PhDs, postdocs, faculty)

### Key Principles
- NO auto-writing or rewriting of user drafts
- Focus on critique, positioning, coverage, and defensibility
- Behave like an expert academic reviewer, not a writing assistant
- Maintain trust, transparency, and workflow fit

## Current Architecture

### Technology Stack
- **Frontend**: React 18.3 + TypeScript 5.5, Vite 7.2, TailwindCSS 3
- **Backend**: Python 3.11, FastAPI 0.115, Supabase Python Client, Pydantic v2
- **Database**: Supabase PostgreSQL 15 + pgvector (vector embeddings)
- **Authentication**: Supabase Auth
- **File Storage**: Supabase Storage
- **PDF Processing**: GROBID 0.7.0 (Docker container)
- **AI Services**: OpenAI **GPT-5.2** (analysis, uses `max_completion_tokens`), text-embedding-3-small (embeddings)
- **Infrastructure**: Docker Compose, Vercel (frontend), Nginx
- **Payments**: Stripe (checkout, subscriptions, webhooks)

### Docker Architecture
```yaml
# Local containers (no local database - uses Supabase cloud)
services:
  redis:         Redis 7 (Celery task queue)
  grobid:        GROBID 0.7.0 (PDF processing service)
  backend:       FastAPI application (Python 3.11)
  celery-worker: Celery worker (background tasks)
  frontend:      React + Vite development server (dev only)

# External cloud services (not containerized)
- Supabase: Database (PostgreSQL 15 + pgvector) + Auth + Storage
- OpenAI: GPT-5.2 (analysis) + text-embedding-3-small (embeddings)
```

### Database Schema

#### Core Tables (Existing)
```sql
projects (id, user_id, title, description, rag_settings, created_at, updated_at)
documents (id, user_id, project_id, title, file_url, file_type, status, analysis, metadata)
document_chunks (id, document_id, project_id, chunk_index, content, embedding, metadata)
chat_sessions, chat_messages, literature_reviews, research_questions
methodology_recommendations, paper_recommendations, project_tags, analytics_events
```

#### Draft-Aware Features (✅ Implemented)
```sql
drafts (id, user_id, project_id, title, version, file_url, file_type, status)
draft_analysis (id, draft_id, structure, word_count, analysis_metadata)
draft_claims (id, draft_id, claim_text, claim_type, section_location, importance_score)
coverage_gaps (id, draft_id, gap_type, description, priority, suggested_papers)
reviewer_feedback (id, draft_id, feedback_type, feedback_text, severity, section_reference)
draft_chunks (id, draft_id, project_id, chunk_index, content, embedding, section_type)
```

#### Citation Management (✅ Implemented)
```sql
citations (id, project_id, paper_id, citation_text, citation_style, metadata)
citation_suggestions (id, draft_id, claim_id, suggested_citation_id, confidence_score)
```

## Implemented Features

### ✅ Core Features (Working)
1. **Intelligent Document Management** - PDF upload, GROBID processing, multi-select (up to 10 files), project organization
2. **AI-Powered Paper Analysis** - GPT-5.2 analysis with structured insights (upgraded from GPT-4o)
3. **Research Insights Generation** - Cross-paper synthesis, gap identification
4. **Literature Review Compass** - Structural guidance WITHOUT auto-writing (senior researcher mentorship)
5. **RAG-Based Research Chat** - Citation-grounded conversations
6. **Citation Network Visualization** - Interactive D3.js graphs
7. **Research Question Generation** - AI-generated research questions
8. **Paper Recommendations** - Semantic similarity suggestions
9. **Advanced Search** - Full-text and semantic search (hybrid BM25 + vector)
10. **Analytics & Tracking** - Usage analytics and progress tracking (MAU, DAU, activation, retention)
11. **Quota Management** - Usage limits and cost tracking to prevent cost explosion

### ✅ Draft-Aware Intelligence (Recently Implemented)
1. **Draft Upload & Processing** - PDF, DOCX, TXT support with structure analysis
2. **Claim Extraction** - AI-powered claim identification and categorization
3. **Citation-Claim Mapping** - Maps claims to supporting literature
4. **Coverage Gap Detection** - Identifies missing literature and blind spots
5. **Expert Reviewer Feedback** - Academic critique without rewriting
6. **Integrated RAG Search** - Search across both drafts and literature

### ✅ Smart Citation Management (Recently Implemented)
1. **Real-time Citation Suggestions** - AI suggestions based on draft claims
2. **Multiple Citation Formats** - APA, IEEE, MLA, Chicago, BibTeX support
3. **Citation Strength Indicators** - Relevance and confidence scoring
4. **One-click Citation Insertion** - Proper formatting and insertion
5. **Duplicate Detection** - Citation consolidation and management

### ✅ Export & Integration (Implemented)
1. **BibTeX Citation Export** - Generate .bib files from project documents for LaTeX/Zotero
2. **Draft Analysis PDF Reports** - Comprehensive PDF with claims, gaps, feedback, citations
3. **Multiple Export Formats** - JSON, Markdown, Text for different workflows
4. **Publication-Ready Citations** - Properly formatted for academic writing

### ✅ LangGraph Workflow Orchestration (Fully Implemented)
1. **Draft Analysis Workflow** - Parallel claim processing with conditional routing
2. **Document Analysis Workflow** - Structured extraction pipeline
3. **Checkpoint System** - Resumable workflows with state persistence
4. **Celery Integration** - Background task processing with Redis queue (concurrency=4)
5. **Error Handling** - Graceful failure recovery and retry logic with exponential backoff

### ✅ Growth & Monetization Features (Implemented - February/March 2026)
1. **Paper Discovery Agent** - Auto-discover papers from PubMed, arXiv, Semantic Scholar
2. **Hybrid Search** - Semantic + BM25 keyword search (70/30 weighting) with query expansion and reranking
3. **Referral System** - Unique codes, tracking, stats dashboard
4. **Stripe Integration** - Checkout, subscriptions, webhooks, usage limits
5. **Pricing Tiers** - Free (1 draft/mo, 5 papers), Pro ($12/mo), Team ($20/user/mo, min 3)
6. **Analytics Dashboard** - MAU, DAU, activation rate, retention cohorts, power users
7. **Draft Comparison** - Version diff with improvement score (0-100)
8. **User Feedback System** - 5-star ratings + categorized feedback
9. **Embedding Cache** - Redis-backed, 7-day TTL, 40-50% API cost reduction
10. **Retry Logic** - Exponential backoff for OpenAI + Supabase API failures

## Service Architecture

### Existing Services
```python
# Core services (working)
services/document_analysis.py     # AI analysis of research papers
services/rag_ingest.py           # Document chunking and embedding
services/rag_retrieval.py        # Semantic search and RAG answers
services/literature_compass.py   # Literature review structural guidance (NO auto-writing)

# Draft-aware services (implemented)
services/draft_processing.py     # Draft ingestion and structure analysis
services/claim_analysis.py       # Claim extraction and categorization
services/coverage_analysis.py    # Gap detection and literature mapping
services/reviewer_feedback.py    # Academic feedback generation
services/draft_rag_integration.py # Extended RAG for draft+literature
services/draft_export.py         # Export draft analysis (PDF, JSON, Markdown, Text) - PDF added Jan 2025
services/draft_errors.py         # Error handling for draft processing

# Citation services (implemented)
services/citation_management.py  # Citation suggestions and formatting (BibTeX support added Jan 2025)
services/citation_quality.py     # Citation strength assessment

# Research insight services (implemented)
services/project_insights.py     # Cross-paper synthesis
services/research_questions.py   # AI-generated research questions
services/methodology_recommendations.py  # Methodology suggestions
services/paper_recommendations.py        # Semantic similarity suggestions

# Infrastructure services (implemented)
services/quota_management.py     # Usage limits and cost tracking
services/grobid_client.py        # GROBID PDF processing integration
services/transparency.py         # Transparent analysis explanations
services/transparent_analysis.py # Analysis with reasoning transparency
services/export.py              # Export utilities
services/background_tasks.py    # Async task processing
```

### API Routes
```python
# Core routes (working)
api/routes/projects.py           # Project management
api/routes/documents.py          # Document upload, analysis, BibTeX export
api/routes/chat.py              # RAG chat functionality (GPT-5.2)
api/routes/compass.py           # Literature Review Compass guidance
api/routes/rag.py               # RAG configuration (NOTE: User-adjustable settings to be removed)

# Draft-aware routes (implemented)
api/routes/drafts.py            # Draft management, analysis, PDF export
api/routes/citations.py         # Citation management and suggestions

# Research insight routes (implemented)
api/routes/research_questions.py           # Research question generation
api/routes/methodology_recommendations.py  # Methodology suggestions
api/routes/paper_recommendations.py        # Paper recommendations

# Growth & monetization routes (implemented - Feb/Mar 2026)
api/routes/paper_discovery.py   # Paper discovery agent (PubMed, arXiv, Semantic Scholar)
api/routes/feedback.py          # User feedback (5-star + text)
api/routes/referrals.py         # Referral codes, tracking, stats
api/routes/platform.py          # Platform stats (for landing page)
api/routes/subscriptions.py     # Stripe checkout, subscriptions, webhooks
api/routes/comparisons.py       # Draft version comparison

# Infrastructure routes (implemented)
api/routes/auth.py              # Authentication
api/routes/analytics.py         # Analytics dashboard (MAU, DAU, activation, retention)
api/routes/analytics_tracking.py # Usage tracking
api/routes/search.py            # Advanced search
api/routes/tags.py              # Project tagging
```

### New Services (Feb/Mar 2026)
```python
services/paper_discovery_agent.py  # PubMed, arXiv, Semantic Scholar search + download
services/platform_stats.py         # Real-time platform statistics (researchers, drafts, universities)
services/analytics_service.py      # MAU, DAU, activation rate, retention cohorts
services/stripe_service.py         # Stripe checkout, subscriptions, webhooks
services/retry_utils.py            # Exponential backoff for OpenAI + Supabase
services/embedding_cache.py        # Redis-backed embedding cache (7-day TTL)
services/draft_comparison.py       # Draft version diff + improvement score
```

### Key API Endpoints (Recent Additions - January 2025)

**BibTeX Citation Export:**
```python
GET /projects/{project_id}/export-bibtex
# Returns: .bib file with all document citations
# File: services/backend/app/api/routes/documents.py:892-997
# Service: services/backend/app/services/citation_management.py:524-635
```

**Draft Analysis PDF Export:**
```python
GET /drafts/{draft_id}/export-pdf
# Returns: PDF report with claims, gaps, feedback, citations
# File: services/backend/app/api/routes/drafts.py:809-885
# Service: services/backend/app/services/draft_export.py:270-601
```

**BibTeX Formatter Functions:**
```python
# citation_management.py
generate_bibtex_cite_key(title, authors, year) -> str
format_citation_bibtex(...) -> str
# Returns: Properly formatted BibTeX entries with unique citation keys
```

## Configuration

### Environment Variables
```bash
# Supabase (Database, Auth, Storage - external cloud service)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# OpenAI (AI Analysis - external cloud service)
OPENAI_API_KEY=your_openai_api_key

# Docker Services (local containers)
GROBID_URL=http://grobid:8070
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Application
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=INFO
```

### Key Patterns

#### Database Operations
- Use Supabase client for all database operations
- Store structured data in JSONB columns with GIN indexes
- Use pgvector for embedding storage and similarity search
- Follow existing patterns in `services/rag_ingest.py`

#### AI Integration
- Use existing OpenAI client configuration
- Follow `document_analysis.py` patterns for GPT-4o calls
- Use JSON mode for structured responses
- Include error handling and retry logic
- Store embeddings as 1536-dimensional vectors

#### API Patterns
- Follow existing FastAPI route patterns
- Use Pydantic models for request/response validation
- Include proper authentication via Supabase
- Add comprehensive error handling

## Implementation Roadmap (See IMPLEMENTATION_ROADMAP.md)

### ✅ Recently Completed (February-March 2026)
- LangGraph workflow orchestration (draft + document analysis)
- Celery + Redis background task processing (concurrency=4)
- BibTeX citation export + Draft PDF reports
- Paper Discovery Agent (PubMed, arXiv, Semantic Scholar)
- Hybrid search (semantic + BM25), query expansion, result reranking
- Referral system, testimonials, platform statistics
- Stripe integration (checkout, subscriptions, webhooks)
- Analytics dashboard (MAU, DAU, activation, retention)
- Draft comparison mode (side-by-side, improvement score)
- Embedding cache (Redis, 40-50% cost reduction)
- Retry logic with exponential backoff
- **GPT-5.2 migration** (all files updated to `max_completion_tokens`)
- **Document upload fixes** (race condition, multi-select, simplified modal)

### 🚧 CURRENT PRIORITY: End-to-End Testing (March 2026)

**Goal:** Validate the full user flow works after GPT-5.2 migration and upload fixes.

**Testing Checklist:**
1. [ ] Single document upload → processing → analyzing → analyzed
2. [ ] Multi-file upload (3-5 files simultaneously)
3. [ ] Draft upload and analysis
4. [ ] RAG chat after document analysis
5. [ ] Paper discovery agent
6. [ ] Stripe checkout flow
7. [ ] Referral code generation

**Known blockers:**
- OpenAI Tier 1 needed for parallel batch uploads (currently 3 req/min limit on free tier)
- Rebuild containers after GPT-5.2 changes: `cd infra && docker-compose down && docker-compose up --build`

### ⚠️ Phase 1: Critical RAG Improvements (Pending after testing)
**Goal**: Fix fundamental issues with retrieval quality and document analysis depth

1. **Remove User-Adjustable RAG Settings** ⚠️ CRITICAL
   - Remove RAGSettingsModal.tsx from frontend
   - Remove API endpoints for rag_settings modification
   - Implement server-controlled adaptive chunking based on document size

2. **Implement Adaptive Chunk Sizing**
   - 1-10 pages: chunk_size=1200, overlap=200
   - 11-30 pages: chunk_size=1600, overlap=250
   - 31+ pages: chunk_size=2000, overlap=300
   - Add cost ceiling protection (max 50 chunks per document)

3. **Section-Aware Chunking with GROBID**
   - Extract section structure from GROBID XML
   - Chunk by sections (preserve document structure)
   - Add section metadata to chunks (section_title, page_number)

4. **Improve Document Analysis Depth**
   - Page-length-based analysis tiers (SHORT/MEDIUM/LONG)
   - 14-page papers should get 2-3x more detailed analysis
   - Include specific numbers, datasets, metrics, contributions

5. **Hybrid Search (Semantic + Keyword)**
   - PostgreSQL full-text search + pgvector semantic search
   - Combine results with weighted scores (70% semantic, 30% keyword)

6. **Query Expansion & Reranking**
   - Expand natural language queries into academic terminology
   - Rerank top 20 results to get best 5

### ✅ Phase 2: LangGraph Implementation - COMPLETED
**Goal**: Transform draft analysis from rigid pipeline to adaptive workflow

1. ✅ **LangGraph Setup** - COMPLETE
   - Installed langgraph, langchain-core dependencies
   - Created workflows/draft_analysis/ directory structure
   - Defined DraftAnalysisState schema with checkpointing

2. ✅ **Refactor to LangGraph Nodes** - COMPLETE
   - Converted existing services into workflow nodes
   - Enabled parallel execution (search all claims at once)
   - Added conditional routing (validate if claim count > 50)

3. 🔄 **Real-Time Progress Streaming** - REMAINING
   - WebSocket support for live progress updates
   - Frontend progress component with step-by-step visibility

4. 🔄 **Human-in-the-Loop Validation** - REMAINING
   - Pause workflow for user review of extracted claims
   - Resume capability UI (backend supports resumable workflows)

### 🚧 Phase 3: Advanced Features (2-3 weeks)
**Goal**: Polish, optimize, and differentiate

1. **Performance Optimization**
   - Use GPT-4o-mini for simple tasks (40-50% cost reduction target)
   - Batch embedding generation
   - Response caching

2. **Enhanced Literature Recommendations**
   - Paper graph analysis
   - "Missing classics" detection
   - Recency and diversity analysis

3. **Additional Export Formats** (BibTeX & PDF already complete ✅)
   - Word document export
   - LaTeX editor integration (Overleaf)
   - EndNote/RefWorks integration

### 📋 Future Features (Post-Roadmap)

#### Team Collaboration
- Multi-user project access with role-based permissions
- Real-time activity tracking and notifications
- Invitation system and team management

#### Argument Structure Visualization
- Interactive D3.js argument mapping
- Logical flow analysis with strength indicators
- Visual dependency graphs between claims and evidence

#### Reviewer Simulation
- Mock peer review generation with multiple personas
- Response preparation and revision guidance
- Review readiness assessment

## Development Guidelines

### Code Style
- Follow existing patterns in the codebase
- Use TypeScript for frontend, Python with type hints for backend
- Follow FastAPI async patterns
- Use Pydantic models for data validation
- Include comprehensive error handling

### Database Guidelines
- All data stored in Supabase cloud (no local database)
- Use Supabase Python client for all database operations (not SQLAlchemy)
- Store embeddings in pgvector format (1536 dimensions)
- Use JSONB for structured metadata storage
- SQL migrations stored in `infra/db-init/` and run directly on Supabase

### AI Integration Guidelines
- Use OpenAI GPT-4o for analysis and generation
- Use text-embedding-3-small for embeddings
- Always include confidence scores and error handling
- Follow existing prompt patterns in `document_analysis.py`
- Store AI responses with metadata (model, timestamp, tokens)

### Testing Guidelines
- Write unit tests for core functionality
- Include integration tests for API endpoints
- Test AI integrations with mock responses
- Follow existing test patterns in the codebase

## Common Issues & Solutions

### Supabase Integration
- **Issue**: All database operations go through Supabase, not local PostgreSQL
- **Solution**: Use `supabase.table()` operations, not direct SQL
- **File Storage**: Use `supabase.storage.from_("bucket").upload()` patterns

### Vector Embeddings
- **Dimensions**: Always use 1536 dimensions for pgvector compatibility
- **Models**: text-embedding-3-small (default), text-embedding-3-large (optional)
- **Storage**: Store in Supabase pgvector, not local database

### Docker Development
- **Containers**: Redis, GROBID, backend, celery-worker, frontend (dev only) run locally
- **External Services**: Supabase handles database + auth + storage, OpenAI handles AI/embeddings
- **Environment**: Use docker-compose.yml for development
- **Note**: NO local PostgreSQL - all database operations use Supabase cloud

## File Structure
```
noesis/
├── services/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/routes/          # API endpoints
│   │   │   ├── services/            # Business logic
│   │   │   ├── workflows/           # LangGraph workflows (planned)
│   │   │   ├── core/               # Config, database, logging
│   │   │   └── main.py
│   │   ├── requirements.txt
│   │   ├── pytest.ini
│   │   ├── tests/                  # Unit and integration tests
│   │   └── Dockerfile
│   └── frontend/                   # React + TypeScript app
│       ├── src/
│       │   ├── components/         # React components
│       │   ├── pages/             # Page components
│       │   └── lib/               # Utilities
│       └── package.json
├── infra/
│   ├── docker-compose.yml         # Development containers
│   └── docker-compose.prod.yml    # Production setup
├── .kiro/specs/draft-aware-research-intelligence/
│   ├── requirements.md            # Feature requirements
│   ├── design.md                 # Technical design
│   └── tasks.md                  # Implementation tasks
├── IMPLEMENTATION_ROADMAP.md     # ⭐ 3-phase roadmap (RAG optimization + LangGraph)
├── NEXT_FEATURES_IMPLEMENTATION.md # Next features plan
├── NEXT_FEATURES_TASKS.md         # Next features tasks
├── IMPLEMENTATION_COMPLETE.md     # Current status
├── claude.md                     # Claude Code context file
└── .cursorrules                  # Cursor AI context file
```

## Debugging Tips

### Logs
- Backend logs: `docker logs noesis-backend`
- Frontend logs: Check browser console
- Supabase logs: Check Supabase dashboard

### Database
- Access Supabase dashboard for database queries
- Check pgvector extension: Query `pg_extension` table
- Monitor embeddings: Count records in `document_chunks` and `draft_chunks`

### Services
- Backend API: http://localhost:8000/docs
- GROBID health: http://localhost:8070/api/isalive
- Frontend: http://localhost:5173

## Current Status & Roadmap

### ✅ Completed (Production Ready - March 2026)
- Draft-aware intelligence platform transformation
- **LangGraph workflow orchestration** (draft + document analysis with parallel processing)
- **Celery + Redis background task processing** (concurrency=4)
- Smart citation management system (BibTeX export, multiple formats)
- Export features (BibTeX + Draft PDF reports + JSON/Markdown/Text)
- Literature Review Compass (structural guidance without auto-writing)
- All core literature analysis features
- Quota management and cost tracking
- **Paper Discovery Agent** (PubMed, arXiv, Semantic Scholar)
- **Hybrid search** (semantic + BM25 keyword, 70/30 weighting)
- **Stripe integration** (Free, Pro $12/mo, Team $20/user/mo)
- **Analytics dashboard** (MAU, DAU, activation, retention, power users)
- **Referral system** with viral loop mechanics
- **Draft comparison** mode (version diff + improvement score)
- **Embedding cache** (Redis, 7-day TTL, 40-50% cost reduction)
- **Retry logic** (exponential backoff for all external APIs)
- **GPT-5.2 migration** (all 15 files updated to `max_completion_tokens`)
- **Document upload improvements** (race condition fix, multi-select, simplified modal)
- Production deployment on Vercel + Supabase + AWS

### ⚠️ Known Issues
- **OpenAI rate limits**: Free tier = 3 req/min. Batch uploads require Tier 1 upgrade.
- **RAG Settings**: User-adjustable settings still exposed → planned removal
- **Chunk Sizes**: Fixed 1000-token chunks → adaptive sizing planned
- **Search**: Hybrid search implemented in backend but not fully surfaced in UI

### 🚧 Current Priority: End-to-End Testing (March 2026)
**Focus**: Validate GPT-5.2 migration + document upload fixes work correctly
**After testing**: Deploy frontend Week 2-4 features (PaperDiscoveryModal, ReferralWidget, etc.)
**Then**: Phase 1 RAG improvements (adaptive chunking, remove user settings)

### 📋 Important Notes for Development
- **GPT-5.2**: Use `max_completion_tokens` NOT `max_tokens` for all OpenAI calls
- **Design**: Check `services/frontend/tailwind.config.js` for design tokens before any frontend work
- **Tool workflow**: See `mini-plans/00_INDEX.md` and the relevant active mini-plan for current work state
- **Plan**: Active implementation plans live in `mini-plans/`; historical strategy docs are archived in `docs/historical/final_plan/`
- **Goal**: 100-500 users in 30 days
- **Startup stage**: Seed-stage, targeting Georgia Tech researchers first, then university expansion

This project represents a significant evolution from a basic literature review tool to a comprehensive research intelligence platform. The 30-day goal is 100-500 signups with 50+ activated users (uploaded ≥1 paper + analyzed ≥1 draft). Monetization launches in Month 3 ($5K MRR target). Seed fundraising by Month 6 ($50K MRR, 30K users).
