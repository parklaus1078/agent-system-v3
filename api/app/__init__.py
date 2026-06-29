"""Load `api/.env` before anything reads os.environ.

Runs on first import of the `app` package — i.e. before `app.db` (which reads DATABASE_URL
at import) or `app.routers.*` (which read ASV3_* at request time). So configuration lives
in one `api/.env` file instead of a long inline env list on every uvicorn command.

`override=False`: real environment variables (CLI / docker-compose) still WIN over the file,
so the same image works in containers and the file is just the convenient host default.
"""

from pathlib import Path

from dotenv import load_dotenv

# api/.env  (this file is api/app/__init__.py -> parents[1] == api/)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
