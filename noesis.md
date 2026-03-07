# Noesis — Interview Preparation Guide

> Everything you need to walk into a technical interview fully prepared. Covers architecture, concepts, challenges, trade-offs, and how to talk about every part of this project.

---

## 1. The 30-Second Pitch

> **"What is Noesis?"**

Noesis is a **draft-aware research intelligence platform** I built from scratch. It behaves like an expert academic peer reviewer — you upload your research papers to build a literature base, then upload your draft manuscript, and the system identifies unsupported claims, detects coverage gaps, maps claims to supporting citations, and gives you structured reviewer-style feedback — before you submit to a journal.

Unlike ChatGPT or writing assistants, it **never rewrites your work**. It critiques it. The core thesis is that researchers need better pre-submission feedback, not AI writing their papers for them.

**Tech:** React + FastAPI + LangGraph + GPT-5.2 + pgvector + Celery/Redis + Supabase + Stripe. Deployed on Vercel + AWS, ~$10-50/month infrastructure at current scale.

---

## 2. Full System Architecture

### The Big Picture (Data Flow)

```
User uploads PDF
    ↓
FastAPI endpoint receives file
    ↓
File stored in Supabase Storage (S3-compatible)
    ↓
GROBID (Docker) extracts structured data
(sections, references, metadata, authors)
    ↓ (fallback: PyMuPDF if GROBID fails)
Adaptive chunking (section-aware, 1200-2000 tokens)
    ↓
OpenAI text-embedding-3-small → 1536-dim vectors
    ↓
Stored in Supabase pgvector (document_chunks table)
    ↓
Auto-trigger: Celery task queued via Redis
    ↓
GPT-5.2 LangGraph workflow (parallel nodes):
  ├── Structure extraction
  ├── Claim extraction
  ├── Methodology extraction
  └── Findings extraction
    ↓
Results stored in Supabase (analysis JSONB column)
    ↓
Document status: uploaded → processing → analyzing → analyzed
```

### Draft Analysis Flow

```
User uploads draft (PDF/DOCX/TXT)
    ↓
GROBID/parsing → chunking → embeddings → draft_chunks table
    ↓
LangGraph Draft Analysis Workflow:
  Node 1: Structure extraction (word count, section map)
  Node 2: Claim extraction (GPT-5-mini, identifies weak/unsupported claims)
     ↓ parallel ↓
  Node 3: Citation mapping (semantic search: claim vs. literature embeddings)
  Node 4: Coverage gap detection (what literature is missing?)
  Node 5: Reviewer feedback (GPT-5.2, peer-review-style critique per claim)
    ↓
All results stored: draft_claims, coverage_gaps, reviewer_feedback tables
    ↓
Frontend renders analysis results
```

---

## 3. Technology Breakdown — Why Each Tool Was Chosen

### FastAPI (Python backend)
**What it does:** Handles all HTTP requests — document upload, auth, analysis triggers, chat.

**Why FastAPI over Flask/Django:**
- Native async/await support — critical for I/O-bound operations like calling OpenAI, Supabase, GROBID simultaneously
- Pydantic v2 for automatic request/response validation and type safety
- Auto-generated OpenAPI docs (Swagger UI at `/docs`) for free
- Much faster than Flask for concurrent workloads

**Key pattern used:**
```python
@router.post("/documents/{id}/analyze")
async def analyze_document(id: str, current_user: dict = Depends(get_current_user)):
    task = analyze_document_task.delay(id, user_id, project_id)
    return {"task_id": task.id}
```

---

### Supabase (Database + Auth + Storage)
**What it does:** Replaces three separate services — PostgreSQL + Auth provider + file storage (like S3).

**Why Supabase over plain PostgreSQL + AWS S3:**
- Single managed service eliminates infrastructure overhead
- Built-in Row Level Security (RLS) for per-user data isolation
- pgvector extension for storing 1536-dimensional embeddings alongside relational data
- Storage with pre-signed URLs for secure file access
- Auth handles JWT tokens, OAuth, email magic links out of the box
- $10/month at current scale

**pgvector specifically:**
- PostgreSQL extension that adds a `vector` column type
- Enables cosine similarity search directly in SQL
- No separate vector database needed (vs. Pinecone, Weaviate)
- Hybrid queries: filter by `user_id` and `project_id`, then rank by embedding similarity

---

### GROBID (Scientific PDF Parsing)
**What it does:** Converts scientific PDFs into structured XML with sections, references, authors, abstracts.

**Why GROBID over plain PDF text extraction (PyMuPDF):**
- Scientific papers have complex layouts — multi-column, figures, footnotes, reference lists
- GROBID is trained specifically on scientific literature (CRF + deep learning models)
- Extracts the reference list as structured data (title, authors, year, DOI) — critical for citation mapping
- Identifies section boundaries (Introduction, Methods, Results, Discussion) — enables section-aware chunking
- PyMuPDF is the fallback when GROBID is unavailable — just raw text, no structure

**How it runs:** Docker container at `http://grobid:8070`, called via REST API. The `/api/processFulltextDocument` endpoint returns TEI XML.

---

### RAG — Retrieval-Augmented Generation

**The core concept:**
RAG = giving an LLM access to a specific knowledge base at query time, rather than relying on what it learned during training. The LLM's answer is grounded in retrieved documents, not hallucinated.

**How Noesis implements RAG:**

**Ingestion (offline):**
1. PDF → GROBID → structured text
2. Text split into chunks (1200-2000 tokens with 200-300 token overlap)
3. Each chunk → OpenAI `text-embedding-3-small` → 1536-dim float vector
4. Chunk + vector stored in `document_chunks` table (pgvector)

**Retrieval (at query time):**
1. User asks a question → embed the query → 1536-dim vector
2. **Hybrid search:** semantic (cosine similarity via pgvector) + keyword (PostgreSQL full-text search, BM25-style)
3. Weight: 70% semantic, 30% keyword — catches both conceptual matches and exact term matches
4. **Query expansion:** LLM rewrites "how does attention work" into academic terms like "self-attention mechanism, transformer architecture, scaled dot-product attention"
5. **Reranking:** Top 20 results → GPT-4o-mini reranks to best 5 based on actual relevance to query
6. Top 5 chunks injected into the GPT-5.2 prompt as context
7. GPT-5.2 answers with citations pointing to specific chunks

**Why this matters:**
- Without RAG, GPT-5.2 would hallucinate citations or reference papers it knows from training
- With RAG, every claim in the chat is grounded in the user's actual literature base
- The model can say "Based on Zhang et al. (2023) in your library..." with confidence

---

### LangGraph (Workflow Orchestration)

**What it is:** A framework from LangChain for building stateful, multi-step AI workflows as directed graphs.

**Why LangGraph over sequential function calls:**
- **Parallel execution:** claim extraction, methodology extraction, structure extraction run simultaneously — not one after another. 3x faster.
- **Conditional routing:** if extracted claims < 3 or > 50, route to a validation node before continuing
- **State management:** each node receives and returns a typed state dict (`DraftAnalysisState`), making data flow explicit and debuggable
- **Checkpointing:** if a node fails midway, the workflow can resume from the last checkpoint (not restart from scratch)
- **Graceful error handling:** a failed node returns errors to the state without crashing the whole pipeline

**State pattern (simplified):**
```python
class DraftAnalysisState(TypedDict):
    draft_id: str
    draft_content: str
    claims: list[Claim]        # populated by claim_extraction node
    citations: list[Citation]  # populated by citation_mapping node
    feedback: list[Feedback]   # populated by reviewer_feedback node
    errors: list[str]
    progress_percentage: int
```

Each node is a pure function: `(state) → updated_state`. The graph connects them.

---

### Celery + Redis (Background Task Processing)

**The problem it solves:** Document analysis (GPT-5.2 with 4 parallel nodes) takes 60-120 seconds. You can't make an HTTP request wait 2 minutes — it would time out.

**How it works:**
1. HTTP request comes in to upload a document
2. File is stored to Supabase Storage (fast, < 1 second)
3. FastAPI immediately returns `200 OK` with a task ID
4. A Celery task is queued to Redis: `analyze_document_task.delay(doc_id, user_id)`
5. Celery worker (separate Docker container) picks up the task from Redis
6. Worker runs the LangGraph analysis pipeline (takes 60-120s)
7. Results written to Supabase
8. Document status polled by frontend: `uploaded → processing → analyzing → analyzed`

**Why Redis as the broker:**
- Redis is an in-memory data store — task queue operations are microsecond-fast
- Celery supports Redis natively as both broker (task queue) and result backend
- Also used as embedding cache (Redis TTL = 7 days for repeated embeddings)

**Concurrency:** Celery worker runs with `--concurrency=4` — 4 documents can analyze in parallel.

**Retry logic:**
```python
@celery_app.task(autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60}, retry_backoff=True)
def analyze_document_task(document_id, user_id, project_id):
    ...
```
If GPT-5.2 returns a rate limit error, Celery waits 60s and retries (up to 3 times with exponential backoff).

---

### Embedding Cache (Redis)
**Problem:** Generating embeddings costs money and takes 100-300ms per API call. The same document chunk may be embedded multiple times if reprocessed.

**Solution:** Before calling OpenAI, check Redis for a cached embedding keyed by a hash of the text. Cache hit → return in <1ms. Cache miss → call OpenAI, store result in Redis with 7-day TTL.

**Result:** 40-50% reduction in embedding API costs at scale.

---

### Stripe (Payments)

**Pricing tiers:**
- Free: 1 draft analysis/month, 5 papers
- Pro: $12/month (unlimited drafts + papers)
- Team: $20/user/month (minimum 3 users, shared literature base)

**Integration:**
1. `POST /api/subscriptions/checkout` → creates Stripe Checkout session
2. User completes payment on Stripe-hosted page
3. Stripe sends webhook to `POST /api/webhooks/stripe`
4. Backend verifies webhook signature → updates subscription in Supabase
5. `usage_limits` table enforced on every draft analysis request

---

### Security Architecture

**Sentry (error monitoring) with research data scrubbing:**
```python
sensitive_keys = ['claim_text', 'draft_text', 'content', 'document_text', ...]
# These are redacted from error reports before sending to Sentry
```
Researchers' unpublished work must never end up in third-party error logs.

**Rate limiting:** SlowAPI middleware on all public endpoints

**CORS:** Configured for production domain only

**Auth:** Supabase JWT tokens. `Depends(get_current_user)` on every authenticated route validates the token against Supabase.

---

## 4. Key Technical Challenges (And How You Solved Them)

### Challenge 1: Race Condition in Document Upload

**Problem:** The document upload flow had a subtle race condition. Here's what happened:
1. FastAPI receives upload → triggers RAG ingestion (background task)
2. Frontend calls `/analyze` endpoint immediately after upload
3. RAG ingestion finishes → sets status to `"ready"`
4. The analyze call had already run (and failed because RAG wasn't complete)
5. Result: documents stuck forever in `"ready"` state

**Root cause:** The frontend was responsible for sequencing ingestion → analysis, but couldn't know exactly when ingestion finished.

**Fix:** Moved the trigger to the backend. After RAG ingestion completes in `rag_ingest.py`, it now automatically queues the analysis Celery task:
```python
# After embedding and storing all chunks
if current_status not in ["analyzing", "analyzed"]:
    analyze_document_task.delay(document_id, user_id, project_id)
```
The backend controls the sequence. The frontend just polls status.

---

### Challenge 2: GPT-5.2 API Breaking Change

**Problem:** After migrating from GPT-4o to GPT-5.2, every single analysis call returned a `400 Bad Request` with:
```
"Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
```

**Scope:** This parameter appeared in 15 different files across services and workflow nodes.

**Fix:** Global find-and-replace with careful manual review:
- `max_tokens=N` → `max_completion_tokens=N` in all 15 files
- Created `GPT52_API_FIX.md` documenting all affected files for team awareness

**Lesson:** When upgrading AI model providers, always test with a single end-to-end call before deploying the migration — API contracts change between model generations.

---

### Challenge 3: LLM Hallucination in Citation Mapping

**Problem:** Early versions asked GPT to suggest citations from the user's papers. GPT would hallucinate paper titles that didn't exist in the library.

**Fix:** Removed LLM from citation suggestion entirely. Instead:
1. Extract the claim's text → generate embedding
2. Compute cosine similarity against all `document_chunks` embeddings
3. Return the top-K chunks by similarity score
4. Never ask GPT to "suggest citations" — only use vector math

Result: 100% of suggested citations actually exist in the user's library. No hallucinations possible.

---

### Challenge 4: Celery Tasks Silently Failing

**Problem:** Document analysis was failing, but Celery was marking tasks as `SUCCESS`. Documents were stuck in `"failed"` status with no retries.

**Root cause:** The exception handler was catching the error, updating the DB status to "failed", but **not re-raising the exception**. Celery saw a clean return value and thought the task succeeded.

```python
# BROKEN (before fix)
except Exception as e:
    supabase.table("documents").update({"status": "failed"}).execute()
    # ← Celery never knew about the failure. No retry triggered.

# FIXED
except Exception as e:
    supabase.table("documents").update({"status": "failed"}).execute()
    raise  # ← Re-raise so Celery retries with exponential backoff
```

**Lesson:** In any task queue system, you must distinguish between "handled gracefully" and "succeeded." Update your DB state, but let the framework know if the task truly failed.

---

### Challenge 5: OpenAI Rate Limits with Parallel Processing

**Problem:** Analyzing 2 documents simultaneously = 8 GPT API calls = exceeds the free tier limit of 3 requests/minute.

**Short-term mitigation:** Retry logic with 60-second backoff handles the rate limit gracefully.

**Real fix:** OpenAI Tier 1 (add payment method → 500 req/min). Cost: ~$0.01-$0.05 per document analysis.

**Architectural lesson:** When designing background job systems, model your API rate limits explicitly. If the limit is 3 req/min and each job uses 4 calls, your max concurrency is effectively 0.75 jobs/minute. Either throttle, queue with delays, or upgrade the tier.

---

### Challenge 6: Research Data Privacy in Error Monitoring

**Problem:** When a draft analysis fails, Sentry captures the exception with full context — which would include the researcher's unpublished manuscript content.

**Fix:** Custom `before_send` hook that scrubs sensitive keys from all Sentry events before transmission:
```python
sensitive_keys = ['claim_text', 'draft_text', 'content', 'document_text', ...]
```
This was a non-negotiable requirement. Researchers' unpublished work is their IP. It cannot appear in a third-party error aggregation service.

---

### Challenge 7: Chunk Sizing for Academic Papers

**Problem:** Fixed 1000-token chunks don't work well for academic papers. A 2-page methods section chunked into 1000-token pieces loses context — you get chunks that reference "the model described above" with no idea what model.

**Solution (in progress):** Adaptive chunk sizing based on document length:
- 1-10 pages: 1200 tokens, 200 overlap
- 11-30 pages: 1600 tokens, 250 overlap
- 31+ pages: 2000 tokens, 300 overlap

**Better solution:** Section-aware chunking — use GROBID's section boundaries to keep Introduction, Methods, Results as coherent units. Don't split across section boundaries.

---

## 5. System Design Decisions & Trade-offs

### Why pgvector instead of Pinecone/Weaviate?

**Decision:** Store vectors in Supabase PostgreSQL with the pgvector extension.

**Trade-offs:**
- ✅ No additional service/cost — vectors live with relational data in one query
- ✅ Filter before search: `WHERE project_id = X AND user_id = Y ORDER BY embedding <=> query_vec LIMIT 5` — filtering happens at the database level, not post-retrieval
- ✅ Transactional consistency — vector and metadata written atomically
- ❌ Not optimized for hundreds of millions of vectors at massive scale
- ❌ Less tunable indexing (Pinecone offers more ANN index options)

**Verdict:** For a startup at this scale (< 10K users, < 1M chunks), pgvector is the right call. Migrate to a specialized vector DB if you hit performance limits.

---

### Why Celery instead of FastAPI BackgroundTasks?

**FastAPI BackgroundTasks** runs in the same process as the web server. If the server restarts (deployment, crash), the task is lost. No retry, no persistence, no monitoring.

**Celery** is a separate worker process with Redis as durable queue. Tasks survive server restarts. Full retry/backoff/monitoring. Can scale horizontally (add more workers).

For a 60-120 second AI pipeline, `BackgroundTasks` is inappropriate. You'd hit HTTP timeouts and lose visibility into failures.

---

### Why LangGraph over a simple sequential pipeline?

**Sequential pipeline:**
```python
claims = await extract_claims(draft)
citations = await map_citations(claims, literature)  # waits for claims
feedback = await generate_feedback(claims, citations)  # waits for both
```

**LangGraph parallel:**
```python
# Runs claim_extraction, structure_extraction, methodology_extraction simultaneously
# 3x faster on the nodes that don't depend on each other
```

The draft analysis has a mix of dependent and independent steps. LangGraph makes the dependency graph explicit in code and handles parallelism automatically.

---

### Why GROBID over PDFMiner / pdfplumber?

| Feature | GROBID | PDFMiner/pdfplumber |
|---------|--------|---------------------|
| Section detection | ✅ ML-based | ❌ Heuristic |
| Reference parsing | ✅ Structured | ❌ Raw text |
| Multi-column layout | ✅ Handles | ❌ Scrambles text |
| Author extraction | ✅ Reliable | ❌ Unreliable |
| Tables | Partial | Partial |
| Requires Docker | Yes | No |

GROBID was purpose-built for scientific literature. The fallback (PyMuPDF) handles edge cases.

---

## 6. Concepts to Be Able to Explain Clearly

### "How does RAG work? Explain it simply."

> "RAG solves a fundamental limitation of LLMs — they only know what they learned during training. If I ask GPT-5.2 about papers uploaded by a specific user to Noesis, it has no idea. RAG fixes this by giving the model access to a private knowledge base at query time.
>
> During ingestion, documents are split into chunks and each chunk is converted into a numeric vector (embedding) that captures its semantic meaning. At query time, the question is also converted to a vector, and we find the chunks that are mathematically closest to the question. Those chunks are then injected into the prompt as context, and the model answers using that context — not its training data.
>
> The key insight is that semantically similar text has similar vectors, even if the words are different. 'attention mechanism' and 'self-attention in transformers' will have very similar embeddings, so a search for one will surface the other."

---

### "What is an embedding?"

> "An embedding is a way of representing meaning as a list of numbers. OpenAI's `text-embedding-3-small` converts any text into a list of 1536 numbers where texts with similar meaning have vectors that point in similar directions. 'Cosine similarity' measures the angle between two vectors — angle of 0° means identical meaning, 90° means completely unrelated. This turns 'find relevant documents' into a math problem."

---

### "What is a vector database and why use one?"

> "A vector database is optimized for similarity search over high-dimensional vectors — finding the K nearest neighbors in a 1536-dimensional space efficiently. We use pgvector, which adds vector support to PostgreSQL, so we don't need a separate database. For very large scale (hundreds of millions of vectors), dedicated systems like Pinecone or Weaviate use more advanced approximate nearest neighbor (ANN) indexing. For our scale, pgvector is perfect."

---

### "What is LangGraph?"

> "LangGraph lets you define multi-step AI pipelines as a directed graph of nodes, where each node is a function that reads from and writes to a shared state object. You define which nodes run in parallel, which run conditionally, and what the data flow looks like. It handles the orchestration so you can focus on what each step does. It also supports checkpointing — saving state between steps so a pipeline can resume from the last successful node instead of restarting from scratch."

---

### "What is Celery?"

> "Celery is a distributed task queue. You define tasks as Python functions decorated with `@celery_app.task`. When you call `task.delay(args)`, it doesn't run the function immediately — it puts a message on a Redis queue. A separate Celery worker process picks up that message and runs the function asynchronously. This lets the HTTP server respond immediately without waiting 2 minutes for an AI pipeline to finish. Celery also handles retries, scheduling, monitoring, and horizontal scaling."

---

### "What is pgvector?"

> "pgvector is a PostgreSQL extension that adds a `vector` column type and operators for vector math. You can store 1536-dimensional float arrays, create indexes for fast similarity search, and write queries like `ORDER BY embedding <=> $1 LIMIT 5` where `<=>` is the cosine distance operator. It turns PostgreSQL into a capable vector database without needing a separate service."

---

### "What is the difference between semantic search and keyword search?"

> "Keyword search (BM25, PostgreSQL FTS) looks for exact or near-exact word matches. If you search 'self-attention', it finds documents with that literal phrase. Semantic search (vector similarity) understands meaning — searching 'how does attention work in transformers' finds documents about 'self-attention mechanisms' even if those exact words don't match.
>
> Keyword search is better for exact terms, acronyms, and proper nouns. Semantic search is better for natural language queries and conceptual exploration. Hybrid search combines both — we weight it 70% semantic + 30% keyword — to get the best of both."

---

## 7. Behavioral Questions & What to Say

### "Tell me about a technical challenge you faced."

Use the **race condition story** (Challenge 1 above). It has a clear problem, root cause analysis, debugging process, and architectural fix. Shows systems thinking.

### "Tell me about a time you had to debug a production issue."

Use the **Celery silent failure** story (Challenge 4). Shows understanding of task queues, distributed systems, and exception propagation.

### "What trade-offs did you make in your architecture?"

Use the **pgvector vs. Pinecone** or **Celery vs. BackgroundTasks** decision. Shows architectural maturity.

### "How did you think about scaling?"

> "The architecture separates concerns so each layer scales independently. The FastAPI server scales horizontally on AWS (add instances). The Celery worker pool scales by adding more worker containers with higher concurrency. Supabase handles database scaling. The embedding cache (Redis) reduces API costs 40-50% as volume grows. The main bottleneck at scale would be the Supabase pgvector index performance at tens of millions of chunks — at that point I'd migrate to a dedicated ANN index."

### "Why did you build this? What's the market opportunity?"

> "Academic researchers spend months writing papers that get rejected because of issues that could have been caught earlier. Peer review is slow (6-12 months for feedback) and opaque. The academic research tools market is $4.9B growing to $12B at 19.8% CAGR. There are 17M researchers globally. Noesis sits at the intersection of LLM capability and a genuine workflow pain point. Competitors like Elicit focus on literature search. We're the first to focus on the draft-critique loop specifically."

---

## 8. Questions They Might Ask You (With Answers)

**Q: How do you prevent the LLM from hallucinating citations?**
> "We don't ask GPT to generate citations — we use pure vector similarity to find relevant chunks from the user's actual library. The LLM can only reference documents that exist in the user's pgvector table. No hallucination possible because no LLM is in the citation retrieval loop."

**Q: How do you handle PDF parsing failures?**
> "Two-layer resilience. GROBID is the primary parser. If GROBID is down or times out, we fall back to PyMuPDF for raw text extraction. GROBID failures are logged and monitored via Sentry. The user still gets analysis, just with less structured metadata."

**Q: How do you secure user data?**
> "Supabase Row Level Security ensures each user can only query their own rows. JWT authentication on every endpoint. Sentry events are scrubbed of draft content before transmission — unpublished research is IP that can't appear in error logs. Rate limiting prevents abuse. CORS restricted to production domain."

**Q: What does 'adaptive chunking' mean?**
> "Chunk size affects retrieval quality. Chunks too small lose context (a paragraph referencing 'the model above' has no idea what model). Chunks too large dilute relevance signals. We adapt chunk size based on document length — longer papers get larger chunks with more overlap to preserve continuity. We also use GROBID's section boundaries to avoid splitting chunks mid-section."

**Q: How does the draft analysis workflow handle partial failures?**
> "LangGraph state is designed for it. Each node writes its errors to a `errors: list[str]` field in the state. If citation mapping fails, claim extraction results are still in state. Reviewer feedback can proceed with whatever partial data is available. The workflow continues with graceful degradation rather than crashing entirely."

**Q: What's your embedding strategy for a 100-page paper?**
> "With 100 pages (~50K words, ~65K tokens), we'd generate roughly 30-40 chunks of ~1700 tokens with 300-token overlap. Each chunk is embedded and stored. At query time, only the top 5 most relevant chunks are retrieved — so the LLM context window isn't overwhelmed. Cost: ~$0.0001 for all embeddings (text-embedding-3-small is very cheap at $0.00002/1K tokens)."

**Q: How does the referral system work?**
> "Each user gets a unique referral code generated on sign-up. When someone signs up via `noesis.is/signup?ref=CODE`, we record the referral in the `referrals` table. When paid plans launch, referrers get 1 free month of Pro when their referred user converts to paid. The referral dashboard shows all-time referrals and conversion status."

**Q: Why Supabase over AWS RDS + Cognito + S3?**
> "At seed stage, engineering time is the scarcest resource. Supabase gives me PostgreSQL + auth + file storage in one managed service for $10/month with no DevOps overhead. AWS gives more control but 3-4 separate services to configure and maintain. I can always migrate to RDS when scale demands it — the Supabase client is just PostgreSQL under the hood."

**Q: What would you change if you were starting over?**
> "I'd implement WebSocket-based real-time progress streaming from day one. Currently, the frontend polls for document status every few seconds — wasteful and creates a laggy UX. With WebSockets, the Celery worker could push progress events directly to the browser (25% → 50% → analysis complete). I'd also implement section-aware chunking from the start rather than retrofitting it, since it fundamentally affects retrieval quality."

---

## 9. The Stack at a Glance (For Quick Reference)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + TypeScript + Vite | SPA, type-safe UI |
| Styling | TailwindCSS 3 + custom tokens | Dark academic design system |
| Animations | Framer Motion | Page transitions, list animations |
| Icons | Heroicons | Consistent icon set |
| Backend | FastAPI (Python 3.11) | Async REST API |
| Validation | Pydantic v2 | Request/response models |
| AI model | GPT-5.2 | Analysis, feedback, reranking |
| Embeddings | text-embedding-3-small | 1536-dim semantic vectors |
| Workflow | LangGraph | Parallel AI pipeline orchestration |
| Task queue | Celery + Redis | Background analysis, retries |
| PDF parsing | GROBID (Docker) | Scientific PDF → structured data |
| PDF fallback | PyMuPDF | Raw text extraction |
| Database | Supabase PostgreSQL 15 | Relational + vector data |
| Vector search | pgvector extension | Cosine similarity over embeddings |
| Auth | Supabase Auth | JWT, OAuth |
| Storage | Supabase Storage | PDF files (S3-compatible) |
| Payments | Stripe | Subscriptions, webhooks |
| Error tracking | Sentry (with data scrubbing) | Production monitoring |
| Rate limiting | SlowAPI | API abuse prevention |
| Cache | Redis | Embedding cache (7-day TTL) |
| Frontend deploy | Vercel | CDN, CI/CD |
| Backend deploy | AWS + Docker Compose | Backend + Celery worker |
| Discovery | PubMed + arXiv + Semantic Scholar APIs | Paper search |

---

## 10. Numbers to Know

| Metric | Value |
|--------|-------|
| Embedding dimensions | 1536 (text-embedding-3-small) |
| Chunk sizes | 1200-2000 tokens + 200-300 overlap |
| Max files per upload | 10 PDFs simultaneously |
| Celery worker concurrency | 4 parallel tasks |
| OpenAI free tier limit | 3 req/min (need Tier 1 for batch) |
| Analysis time (single doc) | ~2 minutes |
| Analysis time (5 docs parallel) | ~2-3 minutes |
| Embedding cache TTL | 7 days |
| API cost reduction with cache | 40-50% |
| Max retries per task | 3 (exponential backoff, 60s first wait) |
| Infrastructure cost | ~$10-50/month |
| Free tier | 1 draft/month, 5 papers |
| Pro tier | $12/month, unlimited |
| Team tier | $20/user/month, min 3 users |
| 30-day user target | 100-500 signups |
| Month 3 MRR target | $5,000 |
| Month 6 MRR target | $50,000 |
