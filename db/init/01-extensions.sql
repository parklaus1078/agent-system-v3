-- Runs once on first DB init (empty data dir). pgvector backs real-mode RAG memory.
CREATE EXTENSION IF NOT EXISTS vector;
