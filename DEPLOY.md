# Deploying Control Tower (docker-compose)

One command brings up the whole stack — **web + api + db**:

```bash
docker compose up --build
```

Then open **http://localhost:8080**. (Optional knobs: `cp .env.example .env` and edit.)

## What runs

| Service | Image / build | Port | Role |
|---------|---------------|------|------|
| `web`   | `./web` (Vite build → nginx) | `8080→80` | Serves the SPA and reverse-proxies `/api/*` to the api |
| `api`   | `./api` (FastAPI + LangGraph) | `8000` | REST API + lifecycle; `/docs` for the OpenAPI UI |
| `db`    | `pgvector/pgvector:pg16` | internal | Postgres (graph store) with the `vector` extension |

The browser only talks to `web`; nginx forwards `/api/*` to `api:8000` (same origin, no
CORS). On first boot the api waits for the DB, creates the schema, **seeds the demo
project `p1`**, and initializes the target git repo the executor commits into.

## Defaults (designed to "just work")

- **`ASV3_AGENT_MODE=simulated`** — the lifecycle runs with a deterministic stub executor,
  so plan → approve → review works end to end without any Claude credentials.
- **`ASV3_CHECKPOINTER=memory`** — lifecycle state lives for the server process. The
  **graph data (projects/tickets/steps/decisions) is persisted in Postgres** (volume
  `db-data`); set `ASV3_CHECKPOINTER=postgres` to also persist lifecycle checkpoints.
- **Embeddings** default to offline `DeterministicEmbeddings` + an in-process vector
  store — no model download. Set `ASV3_EMBEDDINGS=huggingface` for real embeddings in
  pgvector (pulls torch; much larger).

## Persistence & reset

State lives in named volumes `db-data` (Postgres) and `api-repo` (target repo). Reset:

```bash
docker compose down -v   # also removes the volumes
```

## Real Claude (advanced, local)

The api image does not ship the `claude`/`codex` CLI or its auth. To drive real agents,
run the api outside the container (or mount the CLI + `~/.claude` and set
`ASV3_AGENT_MODE=real`). The default simulated mode is what makes this deployable anywhere.
