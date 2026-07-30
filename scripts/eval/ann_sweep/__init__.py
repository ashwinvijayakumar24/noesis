"""HNSW parameter sweep: the recall-vs-latency curve for the vector index.

Production runs `idx_document_chunks_embedding` as HNSW / vector_cosine_ops at
pgvector DEFAULTS (m=16, ef_construction=64) and sets `hnsw.ef_search = 80`
inside `match_document_chunks`. None of those three numbers was chosen: two are
library defaults and one is an arbitrary value someone typed once. This package
turns them into a measured operating point.

Read ANN_SWEEP.md for the results and the recommendation. Read this docstring
for what the numbers mean.

THREE DIFFERENT RECALLS LIVE HERE AND THEY ARE NOT THE SAME NUMBER
    * ``ann_recall_vs_exact``  -- overlap between the index's top-k and an exact
      sequential scan's top-k. A property of the INDEX. Ceiling 1.0 by
      definition, and reaching it means the approximation costs nothing.
    * ``metrics_vs_labels``    -- recall/NDCG/MRR against citation ground truth
      from references.json. A property of the WHOLE SYSTEM (chunker, embedder,
      index, pooling). Its ceiling is far below 1.0 by construction -- see
      retrieval/BASELINE.md.
    * pgvector's own notion of recall, which we never quote.
Conflating the first two is the single easiest way to publish a wrong number, so
every record carries both under distinct keys.

CORPUS FINGERPRINT
    Every record is stamped with (documents, chunks, project_id). 118 docs /
    2124 chunks is a SMALL corpus -- far below the scale where HNSW's asymptotic
    advantage appears. A result measured here does not automatically transfer to
    a corpus 100x larger, and the records say so.
"""
