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

REPO="${ASV3_TARGET_REPO_DIR:-/data/target-repo}"
mkdir -p "$REPO"
if [ ! -d "$REPO/.git" ]; then
  echo "[entrypoint] initializing target repo at $REPO"
  git -C "$REPO" init -q
  git -C "$REPO" config user.email demo@control-tower.local
  git -C "$REPO" config user.name "Control Tower"
  printf '# Control Tower target repo\n' > "$REPO/README.md"
  git -C "$REPO" add -A
  git -C "$REPO" commit -q -m "init"
fi

echo "[entrypoint] starting: $*"
exec "$@"
