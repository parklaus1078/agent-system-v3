import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Execution runs in-request (synchronous) under test by default, so assertions can read the
# resulting state right after the call. The async (background-thread) path is exercised
# explicitly by test_lifecycle_async.py, which flips this on for its duration.
os.environ["ASV3_ASYNC_EXEC"] = "0"
# Hermetic DB/checkpointer: set BEFORE app is imported so app/__init__'s load_dotenv(override=
# False) can't pull in a developer's api/.env Postgres URL / durable checkpointer (which would
# leak LangGraph checkpoint state across runs and make message/lifecycle assertions flaky).
# setdefault, so the gate command's explicit values still win.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ASV3_CHECKPOINTER", "memory")
# Force the deterministic offline embeddings in tests — else a developer's api/.env
# (ASV3_EMBEDDINGS=huggingface) leaks in via load_dotenv and every RAG-touching test crashes
# with ModuleNotFoundError (sentence-transformers/torch aren't in the test venv). setdefault so
# an explicit `ASV3_EMBEDDINGS=huggingface pytest ...` can still opt in.
os.environ.setdefault("ASV3_EMBEDDINGS", "")

from app.db import Base  # noqa: E402


@pytest.fixture()
def session():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401  (register tables)

    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
