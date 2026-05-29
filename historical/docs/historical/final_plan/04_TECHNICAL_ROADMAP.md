# Noesis — Technical Roadmap
*Engineering Skills Framework: Senior Architect + Senior QA + Senior ML Engineer*
*Owner: Ashwin (technical lead)*
*March 2026 — 12-Week Sprint Plan*

---

## ✅ RESOLVED: GPT-5.2 Model Validity (Verified March 10, 2026)

Both model IDs tested live against the OpenAI API from within the `noesis-backend` container:
- `gpt-5.2` ✅ working
- `gpt-5.2-chat-latest` ✅ working
- `max_completion_tokens` ✅ accepted correctly

No fallback needed. All 15 migrated files are correct. This risk is cleared.

---

## Technical Debt Assessment (Risk-Ranked)

| Item | Risk Level | Description | Fix Effort |
|---|---|---|---|
| GPT model ID validity | 🔴 Critical | Product may be 100% broken | 30 min |
| Zero test coverage for core services | 🔴 High | Silent regression risk | 2 weeks |
| User-adjustable RAG settings exposed | 🟡 Medium | Confusing UX, users break their own quality | 2 hours |
| Fixed 1000-token chunk sizes | 🟡 Medium | Poor retrieval on short/long docs | 1 week |
| No WebSocket for analysis progress | 🟡 Medium | Black box UX, 30% abandon during wait | 1 week |
| No browser extension | 🟡 Medium | Workflow silo — #1 activation blocker | 3 weeks |
| CORS configuration for extension | 🟡 Medium | Will block extension auth if not pre-configured | 4 hours |
| Celery task failure visibility | 🟠 Low | Failed tasks silent to users | 3 hours |
| Supabase RLS policies | 🟠 Low | Row-level security needs audit | 1 day |
| No API rate limiting per-endpoint | 🟠 Low | Individual endpoints could be abused | 4 hours |

---

## Sprint 1 (Weeks 1-3): Critical Infrastructure + Browser Extension

### Week 1: Fix Foundation

**Day 1 (Monday) — Emergency validation:**
- [ ] Verify GPT-5.2 model ID in production
- [ ] Deploy all Sprint 01-03 frontend + backend changes to Vercel/AWS
- [ ] Run DB migrations 009 + 010 on production Supabase
- [ ] Remove user-adjustable RAG settings from frontend (RAGSettingsModal.tsx)
- [ ] Verify Stripe checkout works end-to-end (test with $1 transaction)

**Day 2-3 — Remove RAG Settings UI:**
```typescript
// Remove from frontend:
// components/RAGSettingsModal.tsx → DELETE
// Any imports of RAGSettingsModal in ProjectDetail.tsx → DELETE
// Backend endpoint GET/POST /projects/{id}/rag-settings → keep but mark deprecated
// Note: Keep backend endpoint so existing users don't break, just remove the UI
```

**Day 4-5 — WebSocket Progress Streaming:**

The LangGraph workflows already emit step events. Wire up WebSocket:

```python
# services/backend/app/api/routes/drafts.py
# Add WebSocket endpoint alongside existing REST endpoint

@router.websocket("/drafts/{draft_id}/analysis-stream")
async def draft_analysis_stream(
    websocket: WebSocket,
    draft_id: str,
    current_user: dict = Depends(get_current_user_ws)
):
    await websocket.accept()
    try:
        # Subscribe to Celery task progress updates via Redis pub/sub
        async for event in get_analysis_events(draft_id):
            await websocket.send_json({
                "type": event["type"],  # "progress", "complete", "error"
                "step": event["step"],  # "Extracting claims...", "Finding gaps..."
                "progress": event["progress"],  # 0-100
                "data": event.get("data")
            })
    except WebSocketDisconnect:
        pass
```

```typescript
// services/frontend/src/hooks/useAnalysisStream.ts
export function useAnalysisStream(draftId: string) {
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('Initializing...');
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE_URL}/drafts/${draftId}/analysis-stream`);
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.type === 'progress') {
        setProgress(event.progress);
        setStep(event.step);
      } else if (event.type === 'complete') {
        setComplete(true);
      }
    };
    return () => ws.close();
  }, [draftId]);

  return { progress, step, complete };
}
```

**Progress steps to emit:**
1. "Parsing document structure..." (5%)
2. "Extracting claims from your draft..." (20%)
3. "Searching your literature library..." (40%)
4. "Detecting coverage gaps..." (60%)
5. "Generating reviewer feedback..." (80%)
6. "Compiling analysis report..." (95%)
7. "Analysis complete!" (100%)

### Week 2-3: Browser Extension MVP

**Architecture Decision: Chrome Extension Manifest V3**

```
noesis-extension/
├── manifest.json          # MV3 manifest
├── background/
│   └── service-worker.js  # Auth token management, API calls
├── content/
│   ├── overleaf.js        # Overleaf-specific sidebar injection
│   └── google-docs.js     # Google Docs sidebar injection
├── sidebar/
│   ├── sidebar.html       # Extension popup/sidebar UI
│   ├── sidebar.tsx        # React component (bundled)
│   └── sidebar.css
└── options/
    └── options.html       # Settings page (API URL, logout)
```

**manifest.json:**
```json
{
  "manifest_version": 3,
  "name": "Noesis — Pre-Submission Review",
  "version": "0.1.0",
  "description": "Know what Reviewer 2 will say before you submit.",
  "permissions": ["storage", "identity", "activeTab"],
  "host_permissions": [
    "https://www.overleaf.com/*",
    "https://docs.google.com/*",
    "https://api.noesis.is/*"
  ],
  "background": {
    "service_worker": "background/service-worker.js"
  },
  "content_scripts": [
    {
      "matches": ["https://www.overleaf.com/project/*"],
      "js": ["content/overleaf.js"]
    },
    {
      "matches": ["https://docs.google.com/document/*"],
      "js": ["content/google-docs.js"]
    }
  ],
  "action": {
    "default_popup": "sidebar/sidebar.html",
    "default_icon": "icons/noesis-32.png"
  }
}
```

**Auth Strategy:**
```javascript
// background/service-worker.js
// Store Supabase session token in chrome.storage.local
// Inject as Authorization header on all API calls to api.noesis.is

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_AUTH_TOKEN') {
    chrome.storage.local.get('supabase_token', (result) => {
      sendResponse({ token: result.supabase_token });
    });
    return true; // Keep channel open for async response
  }

  if (message.type === 'ANALYZE_DOCUMENT') {
    // Get current document content from content script
    // POST to /api/drafts/analyze-from-extension
    // Return WebSocket stream URL for progress
  }
});
```

**CORS Configuration (backend — do BEFORE building extension):**
```python
# services/backend/app/main.py
# Add chrome-extension:// origins to CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "https://noesis.is",
    "https://www.noesis.is",
    "chrome-extension://*",  # All extension IDs (development)
]

# For production, use specific extension ID:
# "chrome-extension://YOUR_EXTENSION_ID_HERE"
```

**New API Endpoint for Extension:**
```python
# services/backend/app/api/routes/drafts.py
@router.post("/drafts/analyze-from-extension")
async def analyze_from_extension(
    request: ExtensionAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts raw text content from browser extension.
    Returns draft_id for WebSocket progress tracking.
    """
    # Create draft record from raw text
    # Queue Celery analysis task
    # Return draft_id + WebSocket URL
```

**Overleaf Sidebar Injection:**
```javascript
// content/overleaf.js
// Overleaf project pages have a sidebar on the right
// Inject Noesis panel into the existing sidebar structure

function injectNoesisSidebar() {
  const sidebar = document.querySelector('.ide-panel-wrapper-right');
  if (!sidebar) return;

  const noesisPanel = document.createElement('div');
  noesisPanel.id = 'noesis-sidebar-panel';
  noesisPanel.innerHTML = `
    <div class="noesis-header">
      <span>Noesis Review</span>
      <button id="noesis-analyze-btn">Analyze Draft</button>
    </div>
    <div id="noesis-content">
      <p>Click "Analyze Draft" to get pre-submission feedback.</p>
    </div>
  `;
  sidebar.prepend(noesisPanel);

  document.getElementById('noesis-analyze-btn').addEventListener('click', () => {
    // Extract text from Overleaf's CodeMirror editor
    const editorContent = getOverleafEditorContent();
    // Send to background service worker for API call
    chrome.runtime.sendMessage({
      type: 'ANALYZE_DOCUMENT',
      content: editorContent,
      source: 'overleaf'
    });
  });
}

function getOverleafEditorContent() {
  // Overleaf uses CodeMirror 6
  // Access via the editor's DOM or window.overleaf APIs
  const cm = document.querySelector('.cm-content');
  return cm ? cm.textContent : '';
}
```

**MVP Scope for Extension (Week 2-3):**
- ✅ Overleaf sidebar injection
- ✅ "Analyze Draft" button that grabs current document
- ✅ Progress indicator with WebSocket streaming
- ✅ Display top 3 action items inline in sidebar
- ✅ "View Full Analysis" link → opens noesis.is/projects/{id}
- ❌ Google Docs (Phase 2 — different DOM structure)
- ❌ Inline comment insertion (Phase 2)
- ❌ Citation insertion (Phase 2)

---

## Sprint 2 (Weeks 4-6): RAG Quality + Test Coverage

### RAG Adaptive Chunking

Replace fixed 1000-token chunks with document-length-aware chunking:

```python
# services/backend/app/services/rag_ingest.py

def get_chunk_config(page_count: int) -> dict:
    """Return chunking parameters based on document length."""
    if page_count <= 10:
        return {"chunk_size": 1200, "chunk_overlap": 200, "max_chunks": 30}
    elif page_count <= 30:
        return {"chunk_size": 1600, "chunk_overlap": 250, "max_chunks": 40}
    else:
        return {"chunk_size": 2000, "chunk_overlap": 300, "max_chunks": 50}
```

### Section-Aware Chunking with GROBID

```python
def chunk_with_section_awareness(grobid_xml: str, config: dict) -> list[dict]:
    """
    Parse GROBID XML to extract section structure.
    Chunk within sections to preserve semantic boundaries.
    Add section metadata to each chunk.
    """
    sections = parse_grobid_sections(grobid_xml)
    chunks = []

    for section in sections:
        section_chunks = split_text(
            section['content'],
            chunk_size=config['chunk_size'],
            overlap=config['chunk_overlap']
        )
        for i, chunk in enumerate(section_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "section_title": section['title'],
                    "section_type": section['type'],  # abstract, intro, methods, etc.
                    "chunk_index": i,
                    "page_estimate": section.get('page')
                }
            })

    return chunks[:config['max_chunks']]  # Cost ceiling
```

### Test Coverage Strategy

Priority order for test coverage:

**Week 4 — Core Service Tests (Highest Risk):**
```
tests/
├── test_draft_analysis_workflow.py    # Full LangGraph workflow (mock AI calls)
├── test_rag_ingest.py                 # Chunking, embedding, storage
├── test_rag_retrieval.py              # Semantic search, hybrid search
├── test_quota_management.py           # Usage limits, Redis TTL, Stripe gates
└── test_reviewer_feedback.py          # Feedback generation, source grounding
```

**Week 5 — API Integration Tests:**
```
tests/
├── test_api_drafts.py                 # Draft upload, analysis, export endpoints
├── test_api_documents.py              # Document upload, BibTeX import
├── test_api_subscriptions.py          # Stripe checkout, webhook handling
└── test_api_paper_discovery.py        # Discovery quota, external API calls
```

**Week 6 — E2E Tests (Critical Path):**
```python
# tests/test_e2e_critical_path.py
async def test_full_user_journey():
    """
    Tests: signup → create project → upload document →
    analyze document → upload draft → analyze draft →
    view feedback → upgrade to Pro
    """
    # Use real Supabase test project + mock OpenAI calls
```

**Mock Strategy for AI calls:**
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_openai():
    """Mock OpenAI API calls with realistic response structures."""
    with patch('openai.AsyncOpenAI') as mock:
        mock.return_value.chat.completions.create = AsyncMock(
            return_value=MockChatCompletion(
                content=SAMPLE_DRAFT_ANALYSIS_RESPONSE
            )
        )
        yield mock
```

---

## Sprint 3 (Weeks 7-9): Quality + Distribution Infrastructure

### Google Docs Extension (Week 7)
- Same architecture as Overleaf extension
- Different DOM injection strategy (Google Docs uses custom elements)
- Add to Chrome Web Store update

### Dispute Suppression Logic (Week 8)
```python
# services/backend/app/services/reviewer_feedback.py
async def _get_suppressed_feedback_types(draft_id: str, user_id: str) -> list[str]:
    """
    If user has disputed the same feedback type 3+ times,
    suppress it from future analyses.
    """
    result = await supabase.table('user_feedback_on_analysis')\
        .select('feedback_type, count(*)')\
        .eq('user_id', user_id)\
        .eq('reaction', 'dispute')\
        .gte('count', 3)\
        .execute()
    return [r['feedback_type'] for r in result.data]
```

### Performance Optimization (Week 9)
- Use `gpt-4o-mini` for simple claim categorization (40-50% cost reduction)
- Keep `gpt-5.2` (or equivalent) only for complex feedback generation
- Batch embedding generation (currently 1-by-1)

---

## Sprint 4 (Weeks 10-12): Stability + Monitoring

### Observability Stack

```python
# Minimal monitoring without adding complexity
# Add to existing FastAPI app:

import time
import logging
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('noesis_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('noesis_request_latency_seconds', 'Request latency', ['endpoint'])
AI_CALL_COST = Counter('noesis_ai_cost_total', 'Estimated AI API cost', ['model', 'service'])
```

### Celery Task Failure Visibility

```python
# services/backend/app/tasks/document_analysis.py
# Add failure notification to users

@celery_app.task(bind=True, max_retries=3)
def analyze_document_task(self, document_id: str, user_id: str):
    try:
        result = run_analysis(document_id)
        # Notify user via Supabase realtime
        notify_user(user_id, "analysis_complete", {"document_id": document_id})
    except Exception as exc:
        # On final failure, notify user
        if self.request.retries >= self.max_retries:
            notify_user(user_id, "analysis_failed", {
                "document_id": document_id,
                "error": "Analysis failed. Please try uploading again."
            })
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

---

## Engineering Principles for This Phase

1. **No new features without a user request.** If a researcher hasn't asked for it, it doesn't get built.

2. **Browser extension > all other features.** This is the product. Defer everything else.

3. **Test before ship.** Every new backend endpoint gets at least one integration test before merge.

4. **Monitor AI costs weekly.** Add cost tracking to every OpenAI call. Set a $100/month alert.

5. **Fix in place, not with abstraction.** If a service is broken, fix it. Don't refactor it into a new service just because it's messy.

---

## 12-Week Engineering Task Tracker

| Week | Tasks | Owner | Priority |
|---|---|---|---|
| 1 | Verify GPT model, deploy all changes, DB migrations, remove RAG settings UI | Ashwin | 🔴 Critical |
| 2 | WebSocket progress streaming (backend + frontend) | Ashwin | 🔴 Critical |
| 3 | Browser extension: manifest, auth, Overleaf injection, analyze button | Ashwin | 🔴 Critical |
| 4 | Browser extension: sidebar UI, progress display, Chrome Web Store submission | Ashwin | 🔴 Critical |
| 5 | Core service tests (draft workflow, RAG, quota) | Ashwin | 🟡 High |
| 6 | RAG adaptive chunking + section-aware chunking | Ashwin | 🟡 High |
| 7 | API integration tests + E2E critical path test | Ashwin | 🟡 High |
| 8 | Google Docs extension (second target after Overleaf) | Ashwin | 🟡 High |
| 9 | Dispute suppression logic + feedback quality loop | Ashwin | 🟠 Medium |
| 10 | gpt-4o-mini for cheap tasks (cost optimization) | Ashwin | 🟠 Medium |
| 11 | Celery task failure visibility + user notifications | Ashwin | 🟠 Medium |
| 12 | Performance audit + observability + Supabase RLS audit | Ashwin | 🟠 Medium |

---

## What NOT to Build in the Next 12 Weeks

- ❌ Real-time collaboration features
- ❌ Word/DOCX editor integration (beyond export)
- ❌ Grant proposal mode
- ❌ Argument structure visualization (D3.js)
- ❌ Human-in-the-loop claim validation UI
- ❌ Mobile app
- ❌ Email/Slack notification integrations
- ❌ EndNode/RefWorks integration
- ❌ Any new analytics dashboard features
- ❌ Any new referral system features

*The existing feature set is sufficient for validation. Every hour spent on new features is an hour not spent on distribution and user conversations.*



