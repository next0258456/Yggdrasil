-- ==============================================================================
-- YGGDRASIL 03-Y7L-NATIVE — POSTGRESQL + PGVECTOR HYBRID SOP SCHEMA (FOR WF-03)
-- ==============================================================================
-- Dùng cho Workflow 03 trên n8n:
--   • Dense Vector Search (pgvector cosine similarity)
--   • Sparse Full-Text / BM25 Search (PostgreSQL tsvector + ts_rank_cd)
--   • Reciprocal Rank Fusion (RRF) gộp Top-K (< 4KB) trong đúng 1 câu SQL
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS y7l_sop_chunks (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    doc_title       TEXT NOT NULL,
    chunk_index     INT NOT NULL,
    department      TEXT DEFAULT 'general',
    content         TEXT NOT NULL,
    embedding       vector(1536) NOT NULL,
    tsv             tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce(doc_title, '') || ' ' || content)
                    ) STORED,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_y7l_sop_chunks_tsv
    ON y7l_sop_chunks USING GIN (tsv);

CREATE INDEX IF NOT EXISTS idx_y7l_sop_chunks_embedding_hnsw
    ON y7l_sop_chunks USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION y7l_hybrid_search_sop(
    query_text      TEXT,
    query_embedding vector(1536),
    top_k           INT DEFAULT 3,
    rrf_k           INT DEFAULT 60
)
RETURNS TABLE (
    id              BIGINT,
    doc_id          TEXT,
    doc_title       TEXT,
    chunk_index     INT,
    department      TEXT,
    content         TEXT,
    dense_rank      BIGINT,
    bm25_rank       BIGINT,
    rrf_score       DOUBLE PRECISION
)
LANGUAGE sql
STABLE
AS $$
    WITH dense_hits AS (
        SELECT
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding ASC) AS rnk
        FROM y7l_sop_chunks c
        ORDER BY c.embedding <=> query_embedding ASC
        LIMIT GREATEST(top_k * 5, 20)
    ),
    bm25_hits AS (
        SELECT
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('simple', query_text)) DESC
            ) AS rnk
        FROM y7l_sop_chunks c
        WHERE c.tsv @@ plainto_tsquery('simple', query_text)
        ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('simple', query_text)) DESC
        LIMIT GREATEST(top_k * 5, 20)
    ),
    combined AS (
        SELECT
            COALESCE(d.id, b.id) AS id,
            d.rnk AS dense_rank,
            b.rnk AS bm25_rank,
            (
                COALESCE(1.0 / (rrf_k + d.rnk), 0.0) +
                COALESCE(1.0 / (rrf_k + b.rnk), 0.0)
            )::DOUBLE PRECISION AS rrf_score
        FROM dense_hits d
        FULL OUTER JOIN bm25_hits b ON d.id = b.id
    )
    SELECT
        c.id,
        c.doc_id,
        c.doc_title,
        c.chunk_index,
        c.department,
        c.content,
        comb.dense_rank,
        comb.bm25_rank,
        comb.rrf_score
    FROM combined comb
    JOIN y7l_sop_chunks c ON c.id = comb.id
    ORDER BY comb.rrf_score DESC
    LIMIT top_k;
$$;
