# Noesis — Next Steps After Sprint 01 (March 2026 onward)

## Immediate Actions (Before Writing More Code)

### Deploy Sprint 01

1. **Deploy frontend to Vercel** — `git push` → auto-deploy triggers. Verify landing page hero and pricing card render correctly.
2. **Redeploy backend on AWS** — `cd infra && docker-compose down && docker-compose up --build`. All 15 GPT-5.2 files must be in the new image.
3. **Run migrations on production Supabase** (SQL editor, in order):
   - `infra/db-migrations/009_sprint_week1_features.sql`
   - `infra/db-migrations/010_week2_features.sql`
4. **Create Lab tier in Stripe dashboard** → copy Price ID → add `STRIPE_PRICE_ID_LAB` to production `.env`
5. **Upgrade OpenAI to Tier 1** — current 3 req/min limit breaks batch uploads. $5 prepay unlocks Tier 1. Do this before running any load tests.

### Distribution (This Week, Non-Technical)

- **Product Hunt launch** — aim for Tuesday or Wednesday (highest traffic days). Prepare 60-second demo video showing Reviewer 2 framing → claim extracted → citation mapped. No demo video = don't launch yet.
- **Cold outreach** — 30 emails to Georgia Tech assistant professors with active NSF/NIH grants (look up on GT research pages). Subject line: "Peer review before you submit — free for GT researchers". Personal, 3 sentences, direct ask for a 20-min call.
- **arXiv partnership email** — contact@arxiv.org — propose API partnership or co-marketing. Long shot, but zero cost. Frame as: tool that helps researchers cite arXiv papers more accurately.
- **bioRxiv** — info@biorxiv.org — same pitch, life sciences angle.
- **Book 10 PI discovery calls** — goal is not demos, it's listening. Ask: "When did you last get surprised by a reviewer comment you should have caught yourself?" Record answers; these become testimonials and copy.

---

## Sprint 02: Technical Depth (Weeks 4–6)

### Priority 1: Browser Extension MVP (~10–12 hours)

**Why first**: Eliminates the workflow silo critique. Researchers write in Google Docs, Overleaf, Word — Noesis currently requires them to leave. Extension brings the claim-check into their environment.

**Scope:**
- Chrome extension with sidebar panel
- Activation: highlight text in Google Docs or Overleaf → click "Check in Noesis" in context menu
- Sidebar shows top 3 matching citations from user's project library
- Auth: reads stored token from `localStorage` after noesis.is login (no OAuth complexity)
- "Add to library" button in sidebar opens Noesis in a new tab

**Files to create:**
```
extension/
  manifest.json       # Chrome MV3, permissions: tabs, storage, activeTab
  background.js       # Service worker, auth token storage
  content.js          # Injects sidebar, listens for text selection
  sidebar.html        # Embedded iframe panel
  sidebar.css
  sidebar.js          # Calls /rag/search?query=<selected_text>&project_id=<stored>
```

**Backend change needed**: `GET /rag/search` must accept CORS from `chrome-extension://` origin.

---

### Priority 2: Phase 1 RAG Improvements (~8 hours)

**Why**: Analysis quality is the core trust moat. Fixed 1000-token chunks regardless of paper length produces shallow analysis on long papers. This is a structural problem, not a prompt problem.

**Changes:**

**Adaptive chunk sizing** in `services/backend/app/services/rag_ingest.py`:
```python
def get_chunk_config(page_count: int) -> dict:
    if page_count <= 10:
        return {"chunk_size": 1200, "overlap": 200}
    elif page_count <= 30:
        return {"chunk_size": 1600, "overlap": 250}
    else:
        return {"chunk_size": 2000, "overlap": 300}
```
Cost ceiling: max 50 chunks per document regardless of size.

**Remove user-adjustable RAG settings:**
- Delete `RAGSettingsModal.tsx` from frontend
- Remove `PUT /projects/{project_id}/rag-settings` endpoint from `api/routes/rag.py`
- Server now controls chunking — users don't need to tune this

**Section-aware chunking using GROBID:**
- GROBID XML output includes `<div>` tags with `type="abstract"`, `type="introduction"`, etc.
- Parse section structure in `grobid_client.py`, pass section metadata to `rag_ingest.py`
- Each chunk gets `section_title` and `section_type` in metadata — improves retrieval precision

---

### Priority 3: WebSocket Progress Streaming (~6 hours)

**Why**: "Your draft is being analyzed" with a spinner for 2-3 minutes feels like a black box. Real-time step visibility = trust. Users who see progress are less likely to close the tab and never return.

**Steps shown to user:**
1. Parsing document structure
2. Extracting claims (X found)
3. Searching literature for each claim
4. Generating reviewer feedback
5. Building citation map
6. Complete

**Backend:** WebSocket endpoint at `/ws/drafts/{draft_id}/progress` in `main.py`. LangGraph workflow already emits node completion events — wire these to the WebSocket broadcast.

**Frontend:** Replace spinner in `DraftAnalysisModal.tsx` with live step list. Each step shows checkmark on completion, spinner while active. Estimated time remaining based on claim count.

---

### Priority 4: Dispute Suppression Logic (~3 hours)

**Why**: The Helpful/Dispute reaction system is inert right now. Disputes should affect future analyses — otherwise the feature is decorative.

**Logic:**
- Query `user_feedback_on_analysis` in `reviewer_feedback.py` before constructing prompt
- If user has disputed feedback of type X on 3+ prior drafts → add to system prompt: "This user's past analyses show they dispute [X] type feedback. Only surface [X] if confidence is very high."
- Files: `services/backend/app/services/reviewer_feedback.py`, `services/backend/app/services/claim_analysis.py`

---

## Sprint 03: Team + Collaboration (Weeks 7–9)

### Shared Project Workspaces (Lab tier feature)

Lab tier customers pay $49/mo for 5 users — they need shared projects to justify that price. Without this, a PI can't share a project with their postdoc.

**Schema:**
```sql
CREATE TABLE project_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
  invited_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(project_id, user_id)
);
```

**Invite flow**: Owner clicks "Share Project" → enters email → sends invite → invited user gets email with link → accepts → becomes project member. Reuse lab_invites infrastructure.

### Admin Dashboard (Lab/Team tier)

PIs need to see if their lab is actually using the tool. Without usage visibility, they cancel.

- Usage per member: drafts analyzed, papers uploaded, chat messages sent
- Activity heatmap: who's active this week, who hasn't logged in
- File: new `AdminDashboard.tsx` page, gated to Lab/Team users
- Backend: extend `analytics_service.py` to support per-project, per-member aggregation

### Overleaf Plugin (OAuth)

Long lead time — Overleaf requires an integration application and approval. Start now; it won't ship until Month 4 at earliest.

- Submit integration application at overleaf.com/for/publishers
- Build OAuth 2.0 flow connecting Noesis account to Overleaf account
- End state: "Import from Overleaf" in UploadDocumentModal, "Export citations to Overleaf" from DraftAnalysisModal

---

## Signals to Watch (Go / No-Go Triggers)

| Signal | Action |
|--------|--------|
| <5 activated users after first 2 weeks of outreach | Build browser extension immediately, pause everything else |
| Users don't return after first draft analysis | Drop new features → focus on analysis quality + WebSocket streaming |
| 3+ paying users in first 2 weeks | Accelerate Lab team features, begin seed deck draft |
| Any PI says "this would have caught a real reviewer comment" | Use as hero testimonial, send to every future prospect |
| Paper Discovery used by 10+ distinct users | Enable auto-expand: discovered paper → add to library → re-analyze draft |
| >50% of feedback items getting Helpful reaction | Source grounding is working → highlight this in marketing |
| >30% of feedback items getting Dispute reaction | Analysis quality problem → immediately schedule PI calls to diagnose |

---

## Month 2–3 Goals

- **100+ activated users** (uploaded ≥1 paper, analyzed ≥1 draft)
- **$5K MRR** — roughly 400 Pro users at $12/mo, or 100 Lab subscribers at $49/mo, or a mix
- **1 university partnership** — arXiv, Overleaf, or a department-level agreement (GT CS or bioengineering)
- **Seed round conversations started** — first 3 meetings with angels or pre-seed funds focused on research tools or academic software
- **Browser extension live** — in Chrome Web Store, used by 50+ researchers

---

## Notes for Next Session

- Read `WORKING_STATE.md` first to see what's in-progress
- Read `SPRINT_01_SUMMARY.md` for full context on what was built
- Check if migrations 009 + 010 have been run on production before testing any Sprint 01 features
- `STRIPE_PRICE_ID_LAB` env var needed for Lab tier checkout to work
- OpenAI Tier 1 needed before batch upload testing — check account status first
