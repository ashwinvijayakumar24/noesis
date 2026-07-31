-- 038_keyword_search_websearch.sql
-- A SECOND keyword-search function. The existing one is NOT touched.
--
-- THE FINDING
--   The first retrieval baseline (docs/MEASUREMENTS.md, Retrieval baseline (superseded), 2026-07-30)
--   measured keyword search at recall@10 = 0.0040 against dense at 0.4221. That
--   looks like a broken retriever. It is not. public.keyword_search_chunks (see
--   migration 037) builds its query with plainto_tsquery, which ANDs every lemma:
--
--       plainto_tsquery('english', 'job shop scheduling')
--         -> 'job' & 'shop' & 'schedul'
--
--   The eval queries are manuscript claims averaging ~20 words, so a chunk has to
--   contain ALL ~20 lemmas to match at all. Reproduced against the local eval
--   database (118 docs / 2124 chunks):
--
--       keyword_search_chunks(<proj>, 'job shop scheduling', 50)              -> 38 rows
--       keyword_search_chunks(<proj>, 'we highlight the superior
--         generalizability of our approach trained on small-scale
--         instances', 50)                                                    ->  0 rows
--
--   55 of the 59 scorable eval queries returned zero rows. This is a
--   query-formulation mismatch, not a lexical-retrieval result, and it matters
--   because a hybrid retriever fusing this leg would be fusing dense with almost
--   nothing.
--
-- OPTIONS CONSIDERED (all measured on the same 59 queries -- see
-- docs/MEASUREMENTS.md, Keyword query formulation, for the full table)
--
--   1. websearch_to_tsquery. Better ergonomics (free-form text, quoted phrases,
--      -exclusion) but it still ANDs bare terms, which is the actual problem.
--      Measured: recall@10 0.0077, still 53 of 59 queries empty. REJECTED --
--      it fixes the input syntax, not the AND semantics.
--
--   2. OR over the query's lemmas. Matches anything, so ts_rank does all the
--      discriminating. Measured: recall@10 0.2643-0.2879 depending on the rank
--      normalisation, 0 of 59 queries empty. CHOSEN.
--
--   3. A coverage floor on top of (2) -- require >= 30% of the query's lemmas to
--      be present in the chunk. Measured: recall@10 0.2643, i.e. IDENTICAL to
--      (2) to four decimals, at ~6x the latency (217ms vs 27ms per query,
--      because the per-row lexeme INTERSECT cannot use the GIN index). REJECTED
--      on measurement: it buys nothing and costs a lot. ts_rank already
--      down-weights chunks that match few query terms; the floor was redundant
--      with the ranking, not additive to it.
--
--   4. IDF-weighted term selection (drop lemmas appearing in >25% of chunks) and
--      an IDF-coverage score. The most principled option and genuinely cheap to
--      compute (9 GIN probes, ~11ms). Measured: recall@10 0.2669, NDCG@10 0.4680
--      vs 0.4960 for the chosen option -- i.e. no better, on 59 queries where a
--      few points is noise, at 4x the latency and several times the complexity.
--      REJECTED for now; the numbers did not earn the machinery. Revisit if the
--      corpus grows enough that ubiquitous domain terms start dominating.
--
-- RANKING: ts_rank(..., 1|32), NOT bare ts_rank and NOT ts_rank_cd.
--   * Flag 32 (rank/(rank+1)) bounds the score into (0,1). This matters
--     downstream: rag_retrieval.hybrid_search computes
--     0.7*similarity + 0.3*keyword_rank, and cosine similarity is already in
--     [0,1]. An unbounded ts_rank silently sets the fusion weights to whatever
--     the raw ranks happen to be. Bounding does not change the ORDER within one
--     query (it is monotonic -- measured: bare ts_rank and ts_rank(...,32) give
--     bit-identical metrics), it makes the score comparable ACROSS queries.
--   * Flag 1 (divide by 1+log(document length)) stops long chunks from ranking
--     high merely for containing more words. Measured (norm 32 -> 1|32):
--     recall@1 0.0339 -> 0.0472, recall@10 0.2643 -> 0.2841, MRR 0.6683 ->
--     0.7460, NDCG@10 0.4578 -> 0.4960. Not worse on any metric.
--   * ts_rank_cd (cover density) was worse on every metric here (recall@10
--     0.2174, NDCG@10 0.3916). Cover density rewards query terms appearing close
--     together, which is the right instinct for a phrase query and the wrong one
--     for a 20-lemma OR where no chunk contains most of the terms.
--
-- WHY A NEW FUNCTION INSTEAD OF REPLACING keyword_search_chunks
--   The retrieval-eval lane is measuring against the existing RPC. Changing it
--   underneath a running measurement would corrupt those results and destroy the
--   before/after comparison this migration exists to justify. The old function
--   stays, byte-identical, until the new one has been shown to be better on more
--   than 59 queries. app/services/rag_retrieval.py selects between them with the
--   KEYWORD_SEARCH_V2 env flag, default OFF.
--
-- RETURN SHAPE is deliberately identical to keyword_search_chunks:
--   (id uuid, document_id uuid, content text, rank real). hybrid_search reads
--   exactly two keys off a keyword row -- chunk.get("id") and chunk.get("rank")
--   -- so this is a drop-in replacement for that caller.
--
-- Idempotent. Apply after 037. Safe to re-run.

DROP FUNCTION IF EXISTS public.keyword_search_chunks_v2(uuid, text, integer);

CREATE OR REPLACE FUNCTION public.keyword_search_chunks_v2(
    proj_id uuid,
    search_query text,
    match_count integer DEFAULT 20
)
RETURNS TABLE(id uuid, document_id uuid, content text, rank real)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    terms text[];
    q tsquery;
BEGIN
    -- to_tsvector does the stopword removal and stemming, so the terms below are
    -- exactly the lemmas the index was built from. Extracting them and rebuilding
    -- the query is what turns the implicit AND into an OR; there is no
    -- "plainto_tsquery but with OR" in Postgres.
    SELECT array_agg(DISTINCT l)
      INTO terms
      FROM unnest(tsvector_to_array(to_tsvector('english', COALESCE(search_query, '')))) AS l;

    -- Empty string, whitespace, pure punctuation, or a query that is nothing but
    -- stopwords ("the of and"). Zero rows is the correct answer and is NOT an
    -- error: rag_retrieval.KEYWORD_SEARCH_DEGRADED must stay clear for it, so
    -- that "matched nothing" and "the RPC is broken" remain distinguishable.
    IF terms IS NULL OR cardinality(terms) = 0 THEN
        RETURN;
    END IF;

    -- Build the tsquery by ESCAPING each lexeme through array_to_tsvector, not by
    -- string-concatenating quote_literal(). quote_literal renders a lexeme
    -- containing a backslash as E'c\\d', and the tsquery parser reads that E as
    -- part of the lexeme, producing the garbage term 'E''c\\d'''. Verified:
    --   quote_literal      -> 'a''b' | 'E''c\\d''' | 'e f' | 'g|h'   (wrong)
    --   array_to_tsvector  -> 'a''b' | 'c\\d'     | 'e f' | 'g|h'   (right)
    -- tsvector's output escaping is exactly what the tsquery parser expects.
    SELECT string_agg(array_to_tsvector(ARRAY[t])::text, ' | ')::tsquery
      INTO q
      FROM unnest(terms) AS t;

    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.content,
        ts_rank(dc.content_tsvector, q, 1|32)
    FROM document_chunks dc
    WHERE dc.project_id = proj_id
      AND dc.content_tsvector @@ q
    -- Ordered by the expression, not by the output column name `rank`: RETURNS
    -- TABLE columns are also plpgsql variables, and `ORDER BY rank` is an
    -- ambiguity waiting to resolve the wrong way. dc.id breaks ties so the
    -- result is deterministic and an eval run is reproducible.
    ORDER BY ts_rank(dc.content_tsvector, q, 1|32) DESC, dc.id
    LIMIT match_count;
END;
$function$;
