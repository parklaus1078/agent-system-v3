#!/usr/bin/env bash
# Boot: wait for the DB, create the schema, seed the demo project once, prepare the
# target git repo the simulated executor commits into, then exec the server.
set -euo pipefail

echo "[entrypoint] waiting for the database..."
python - <<'PY'
import os, time
from sqlalchemy import create_engine
url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres"):
    for i in range(60):
        try:
            create_engine(url).connect().close()
            print("[entrypoint] database is up")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[entrypoint] db not ready ({i}): {type(exc).__name__}")
            time.sleep(2)
    else:
        raise SystemExit("[entrypoint] database never came up")
else:
    print(f"[entrypoint] non-postgres DATABASE_URL ({url!r}); skipping wait")
PY

echo "[entrypoint] creating schema + seeding demo project if empty..."
python - <<'PY'
from app.db import SessionLocal, init_db
from app.models import Node
init_db()
db = SessionLocal()
empty = db.query(Node).filter(Node.project_id == "p1").count() == 0
db.close()
if empty:
    print("[entrypoint] seeding demo project p1")
    import runpy
    runpy.run_path("/app/seed_demo.py", run_name="__main__")
else:
    print("[entrypoint] project p1 already present; skipping seed")
PY

# Workspace ROOT only — the app creates + git-inits each project's repo at
# {workspace}/{project_id} on first run (lifecycle._ensure_git_repo), so we just ensure
# the root exists (no single shared repo).
WS="${ASV3_WORKSPACE_DIR:-/data/workspace}"
mkdir -p "$WS"

echo "[entrypoint] starting: $*"
exec "$@"
