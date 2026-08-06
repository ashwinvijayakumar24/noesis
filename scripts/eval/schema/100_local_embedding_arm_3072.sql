-- LOCAL EVAL DATABASE ONLY. Never applied to production, never to Supabase.
--
-- Arm 1 of the embedding lane (see scripts/eval/retrieval/EMBEDDING.md): store
-- text-embedding-3-large at its NATIVE 3072 dimensions instead of the 1536 that
-- rag_ingest.py:316 truncates to, and measure whether the discarded half carries
-- retrievable signal.
--
-- WHY A NEW TABLE AND NOT AN ALTER
--     document_chunks is shared with concurrently running agents on this branch.
--     A re-ingest mints new chunk ids and has already invalidated a day of
--     measurements once (docs/ENGINEERING_LOG.md, "The concurrency incident").
--     This table is additive: document_chunks is never written, never reindexed,
--     and its chunk-id digest is asserted unchanged before and after every run.
--
-- WHY halfvec AND NOT vector
--     Verified on this database (pgvector 0.8.6):
--         HNSW on vector(3072)  -> ERROR: column cannot have more than 2000 dimensions
--         HNSW on halfvec(3072) -> OK
--     So rag_ingest.py's comment ("Fixed at 1536 for pgvector index
--     compatibility") is true for `vector` and false for `halfvec`. halfvec is
--     fp16, which also halves per-component storage -- this arm therefore
--     measures index size and query latency for the quantization question at the
--     same time, for free.
--
-- The id column mirrors public.document_chunks.id one-for-one, so the two arms
-- score the same chunks of the same documents and differ only in the width and
-- the storage type of the vector.

CREATE TABLE IF NOT EXISTS public.document_chunks_3072 (
    id          uuid PRIMARY KEY,
    document_id uuid NOT NULL,
    project_id  uuid NOT NULL,
    embedding   halfvec(3072) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_3072_project_id
    ON public.document_chunks_3072 (project_id);

-- Cosine, matching idx_document_chunks_embedding (vector_cosine_ops) so the two
-- arms are compared under the same distance function and the same index family.
CREATE INDEX IF NOT EXISTS idx_document_chunks_3072_embedding
    ON public.document_chunks_3072 USING hnsw (embedding halfvec_cosine_ops);
