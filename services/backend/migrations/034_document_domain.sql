-- 034_document_domain.sql
-- RAG contamination fix (issue #3): off-domain library papers were being suggested
-- as sources (e.g. a "glass industry" paper for a sodium-ion battery manuscript).
-- We add a per-document domain classification so retrieval can hard-filter chunks to
-- the manuscript's domain BEFORE they reach scoring / task enrichment.
--
-- NOTE on the RPC: `match_document_chunks` / `match_single_document_chunks` are defined
-- directly in Supabase (not tracked in this repo) and are shared by coverage analysis,
-- citation management, etc. To avoid breaking that shared function, the hard domain
-- filter is enforced in the retrieval layer (app/services/rag_retrieval.py) against the
-- columns added here — NOT by modifying the RPC. NULL domain = "unknown" and always
-- passes the filter, so documents not yet backfilled are never dropped from retrieval.
--
-- Apply in the Supabase SQL editor.

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS domain text,
    ADD COLUMN IF NOT EXISTS domain_tags text[];

CREATE INDEX IF NOT EXISTS documents_domain_idx
    ON public.documents (domain)
    WHERE domain IS NOT NULL;
