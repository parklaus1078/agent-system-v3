import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Execution runs in-request (synchronous) under test by default, so assertions can read the
# resulting state right after the call. The async (background-thread) path is exercised
# explicitly by test_lifecycle_async.py, which flips this on for its duration.
os.environ["ASV3_ASYNC_EXEC"] = "0"

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
