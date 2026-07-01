# Agent System v3 — LLM Dev Control Tower

> **LLM 개발의 통제탑.** 거친 목표("Todo 앱 만들어")를 주면, 시스템이 LLM을
> **작고·보이고·리뷰 가능한 step**으로 일하게 하고, 일하는 동안 **살아있는 지도**
> (목표→티켓→step→코드영역→테스트→결정)를 짓는다. 뭔가 깨지면 지도가 *어디를 볼지* 답한다.

큰 프로젝트에서 LLM은 블랙박스 안에서 일하고 결과 + 텍스트 덩어리만 던진다 → ⓐ *어디서 QA*할지,
ⓑ *버그가 어디*인지 알 수 없다. v3는 **자율성이 아니라 가시성·통제**를 1차 가치로 둔다:
계획을 먼저 세우고, step마다 멈춰 사람이 리뷰하고, `git diff`(에이전트 주장 아님)로 기능↔코드 지도를 짓는다.

---

## 아키텍처

```
┌─────────────────────────┐        REST/JSON         ┌──────────────────────────────┐
│  web/  (React + Vite)   │  ───────────────────────▶ │  api/  (FastAPI)              │
│  지도/보드/콕핏/리뷰     │  ◀───────────────────────  │  LangGraph 라이프사이클       │
│  Zustand + React Flow    │   1.5s 폴링(live)         │  + LangChain RAG + SQLAlchemy │
└─────────────────────────┘                           └───────────────┬──────────────┘
                                                                        │ headless CLI / commit
                                                                        ▼
                                            프로젝트별 대상 git 레포(ASV3_WORKSPACE_DIR/{project_id})
```

- **`api/`** — FastAPI. 티켓별 **LangGraph StateGraph**(`propose → approve(gate) → execute_step → review(gate) → …`)가
  라이프사이클을 몰고, HITL `interrupt()`로 step마다 멈춘다. `git diff`를 파싱해 작업 그래프(노드/엣지)를 갱신하고,
  Decision은 LangChain RAG(임베딩 + 벡터스토어)로 색인해 다음 step에 회상시킨다. 저장은 SQLAlchemy(SQLite/Postgres).
- **`web/`** — React + Vite + React Flow(지도) + Zustand(상태). 화면 3고도: **지도(Map)** → **칸반 보드(Board)** →
  **콕핏(Cockpit, 좌 rail · 중 step lane · 우 리뷰 페인)**. 리뷰 게이트에서 ✅승인 / ✏️수정요청 / 인수.
- **실행 모드 2가지** (서버 부팅 시 `ASV3_AGENT_MODE`로 결정):
  - `simulated` (기본) — 결정적 stub planner/executor, **쿼터 0**, 데모·테스트·E2E용.
  - `real` — `claude -p` CLI(또는 API 키가 있으면 LangChain) planner/executor. 실제 코딩. step당 ~1–4분.

자세한 사용자 흐름은 [`docs/user-flows-sequence-diagrams.md`](docs/user-flows-sequence-diagrams.md) 참고.

---

## Prerequisites

| 도구 | 버전 | 비고 |
|---|---|---|
| Python | **≥ 3.12** | 백엔드(`api/`). venv 권장 |
| Node.js | **≥ 18** | 프론트(`web/`), Vite 5 |
| git | 최신 | 대상 레포 커밋(진실원천) |
| `claude` CLI **또는** `ANTHROPIC_API_KEY` | — | **`real` 모드에서만** 필요. `simulated` 모드는 불필요 |

> 기본 `simulated` 모드는 외부 LLM/네트워크/API 키가 전혀 필요 없다 — 바로 돌릴 수 있다.
> Postgres/pgvector·HuggingFace 임베딩은 `real` 모드 선택 기능이며 별도 extras로 lazy-import 된다(아래 환경변수 표).

---

## 설치

```bash
# 1) 백엔드
cd api
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # 런타임 + pytest/httpx
# (선택) real 모드 RAG/Postgres: .venv/bin/pip install -e ".[postgres,rag]"
cp .env.example .env                        # 백엔드 환경설정 — 여기서 편집(아래 설명)

# 2) 프론트
cd ../web
npm install
```

> **백엔드 환경설정은 `api/.env` 한 곳에서** 관리한다. api는 부팅 시 `api/.env`를 자동 로드하므로
> (`app/__init__.py`), uvicorn 명령에 환경변수를 길게 나열할 필요가 없다 — `api/.env`만 고치고
> `uvicorn app.main:app` 하면 된다. (CLI/docker-compose로 준 env는 파일보다 우선한다. `api/.env`는
> gitignore됨.) 변수 의미는 아래 [환경변수](#환경변수) 표 참고.

---

## 데모 실행 (가장 빠른 길 — `simulated`)

터미널 2개가 필요하다.

```bash
# ── 1) 데모 그래프 시드 (project p1: 목표 + 티켓 t-crud/t-gate/t-pay/t-sync) ──
#     대상 레포는 따로 만들 필요 없음 — 프로젝트별로 ASV3_WORKSPACE_DIR/{project_id} 에
#     자동 생성·git init 된다.
cd api
.venv/bin/python seed_demo.py

# ── 2) 백엔드 (API :8099) — 설정은 api/.env 에서 ──
.venv/bin/python -m uvicorn app.main:app --port 8099
```
> 기본 `api/.env`(=`.env.example` 복사본)는 `DATABASE_URL=sqlite…/dev.db`,
> `ASV3_AGENT_MODE=simulated`, `ASV3_WORKSPACE_DIR=/tmp/asv3-workspace` 라서 위 데모가 바로 돈다.
> (p1은 `/tmp/asv3-workspace/p1` 에서 작업·커밋.)

```bash
# ── 3) 프론트 (다른 터미널) — 백엔드에 연결 ──
cd web
VITE_API_BASE=http://127.0.0.1:8099 npm run dev
#  → Vite가 출력하는 URL(기본 http://localhost:5173) 을 브라우저로 연다
```

서버가 떠 있는지 확인:

```bash
ss -ltnp | grep -E ':(8099|5173)'                 # 리스닝 포트
curl -s http://127.0.0.1:8099/health              # → {"status":"ok"}
```

### Mock 모드 (백엔드 없이 UI만)

`VITE_API_BASE` 없이 띄우면 브라우저 안의 in-memory 시뮬레이션(`MockApiClient`)으로 동작한다 — 서버·DB·Claude 불필요.

```bash
cd web && npm run dev
```

---

## `real` 모드로 돌리기 (실제 Claude가 코딩)

`simulated`은 stub이 `generated/step_N.ts`만 쓰지만, `real` 모드는 **실제 에이전트 CLI가 대상 레포의 파일을
편집·커밋**하고 그 diff가 지도로 들어온다. 결정적이지 않고 step당 ~1–4분 걸린다(쿼터 소모).

**추가 prerequisites**
- **executor는 항상 CLI를 쓴다** → `claude` CLI가 PATH에 있고 인증돼 있어야 한다(Claude Code OAuth — `claude` 로그인).
  `ANTHROPIC_API_KEY`가 있어도 그건 *planner*만 LangChain API로 보내고, **executor는 여전히 `claude` CLI로 돈다.**
  - planner: `ANTHROPIC_API_KEY` 있으면 LangChain(`ChatAnthropic`), 없으면 `claude -p`(CLI).
  - executor: `claude -p <prompt> --model claude-opus-4-8 --permission-mode acceptEdits` 를 그 **프로젝트의 레포**(`ASV3_WORKSPACE_DIR/{project_id}`)에서 실행.
- (선택) `ASV3_BRAIN=codex`로 두면 executor가 `codex exec`를 쓴다(해당 CLI 필요).
- ⚠️ executor는 `--permission-mode acceptEdits`로 **허락 없이 파일을 편집**한다 → 반드시 **전용/샌드박스 git 레포**를 대상으로 쓰고, step마다 커밋되는 것을 전제로 한다.

**실행** — `api/.env`에서 모드만 바꾸면 된다:

```bash
# api/.env
ASV3_AGENT_MODE=real
ASV3_WORKSPACE_DIR=/home/you/asv3-projects   # 프로젝트별 레포의 루트({root}/{project_id})
ASV3_LLM_WIKI_ROOT=/home/you/llm_wiki        # (선택) 완료 시 Decision 승격
```
```bash
cd api
# (planner를 API로 강제하려면) export ANTHROPIC_API_KEY=sk-ant-...  # 없으면 claude CLI로 폴백
.venv/bin/python -m uvicorn app.main:app --port 8099
```

프론트는 동일: `VITE_API_BASE=http://127.0.0.1:8099 npm run dev`.

**선택 — 실제 임베딩 & 영속 상태(Postgres + pgvector)**
```bash
.venv/bin/pip install -e ".[postgres,rag]"     # psycopg/pgvector + huggingface 임베딩
docker compose -f docker-compose.db.yml up -d   # Postgres+pgvector 컨테이너(아래 Docker 참고)
```
```bash
# api/.env 에 추가/수정
DATABASE_URL=postgresql+psycopg://ct:ct@localhost:5432/controltower
ASV3_AGENT_MODE=real
ASV3_EMBEDDINGS=huggingface
ASV3_CHECKPOINTER=postgres
```
그리고 `cd api && .venv/bin/python -m uvicorn app.main:app --port 8099`.
- `ASV3_EMBEDDINGS=huggingface` → 실제 임베딩(`sentence-transformers/all-MiniLM-L6-v2`, 첫 사용 시 모델 다운로드).
  Postgres URL과 함께면 RAG가 **PGVector**로 영속된다.
- `ASV3_CHECKPOINTER=postgres`(또는 Postgres URL + `auto`) → LangGraph 상태가 **재시작에도 살아남아 resume** 가능.
  (SQLite/`memory`는 프로세스 수명 동안만 유지.)
- `ASV3_LLM_WIKI_ROOT` 설정 시, 프로젝트 완료(전 티켓 done)에 Decision이 그 위키로 승격된다(미설정이면 skip).

> 빠른 점검: `simulated`로 흐름을 먼저 검증(쿼터 0)한 뒤 `ASV3_AGENT_MODE=real`로 바꿔 같은 명령을 돌리면 된다.

---

## Docker

### DB만 띄우기 (권장 — api/web는 호스트에서)

Postgres + pgvector **만** 컨테이너로 올린다. 호스트에서 돌리는 api(특히 `real` 모드 + `ASV3_CHECKPOINTER=postgres`/
`ASV3_EMBEDDINGS=huggingface`)가 `localhost:5432`로 붙는다. (vector 확장은 `db/init/01-extensions.sql`가 자동 생성.)

```bash
docker compose -f docker-compose.db.yml up -d        # 시작 (localhost:5432)
docker compose -f docker-compose.db.yml logs -f db   # 로그
docker compose -f docker-compose.db.yml down         # 정지 (데이터 유지)
docker compose -f docker-compose.db.yml down -v      # 정지 + 데이터 삭제
```

접속 문자열: `DATABASE_URL=postgresql+psycopg://ct:ct@localhost:5432/controltower`
(자격증명/포트는 `.env` 또는 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_PORT`로 덮어쓰기 가능.)

스키마는 api가 부팅 시 자동 생성한다. 데모 그래프를 넣으려면:
```bash
cd api && DATABASE_URL="postgresql+psycopg://ct:ct@localhost:5432/controltower" .venv/bin/python seed_demo.py
```

### api만 호스트 + db·web는 컨테이너 (`real` 모드 권장 토폴로지)

`real` 모드는 api가 `claude` CLI를 써야 해서 **컨테이너 밖(호스트)**에서 돌아야 하지만, **db와 web은 컨테이너 안에서 돌려도 된다.**
web 컨테이너는 SPA가 **호스트 api를 직접 호출**하도록 빌드되고(CORS는 `*`로 열려 있음), db는 `localhost:5432`로 노출돼 호스트 api가 붙는다.

```bash
# 1) db + web 컨테이너 띄우기 (web은 기본적으로 http://localhost:8099 의 api를 호출하도록 빌드)
docker compose -f docker-compose.hostapi.yml up -d --build

# 2) api는 호스트에서 — 설정은 api/.env 에 (컨테이너 db를 가리키도록):
#      DATABASE_URL=postgresql+psycopg://ct:ct@localhost:5432/controltower
#      ASV3_AGENT_MODE=real
#      ASV3_CHECKPOINTER=postgres
#      ASV3_WORKSPACE_DIR=/home/you/asv3-projects   # 프로젝트별 레포 루트
cd api && .venv/bin/python -m uvicorn app.main:app --port 8099

# 3) http://localhost:8080 열기
```
- api 포트를 바꾸려면 web 빌드 인자도 맞춰라: `VITE_API_BASE=http://localhost:9000 docker compose -f docker-compose.hostapi.yml up -d --build`.
- 브라우저가 호스트 api를 못 찾으면(드묾) uvicorn을 `--host 0.0.0.0`으로 띄운다.
- `ASV3_CHECKPOINTER=postgres`/`ASV3_EMBEDDINGS=huggingface`까지 쓰려면 호스트 venv에 `pip install -e ".[postgres,rag]"`.

### 풀스택 (web + api + db 한 번에 — Claude 불필요, `simulated`)

```bash
docker compose up --build      # → http://localhost:8080 (web), http://localhost:8000/docs (api)
```
컨테이너엔 Claude 자격증명이 없어 기본 `simulated` 모드로 돈다. 노브는 `.env`(=`.env.example` 복사)로 조절.
이 풀스택의 db는 호스트 포트를 열지 않는다(컨테이너끼리 내부 네트워크로 통신) — 호스트에서 붙으려면 위 **DB만 띄우기**/**api만 호스트** 구성을 쓴다.

---

## 환경변수

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DATABASE_URL` | `sqlite+pysqlite:///:memory:` | SQLAlchemy URL. 데모는 `sqlite+pysqlite:///./dev.db` 권장(영속). `postgresql+psycopg://…`면 Postgres |
| `ASV3_AGENT_MODE` | `simulated` | `simulated`(stub, 쿼터 0) 또는 `real`(`claude -p`) |
| `ASV3_WORKSPACE_DIR` | `<api>/.asv3-workspace` | **프로젝트별** 대상 레포의 루트. 각 프로젝트는 `{루트}/{project_id}`에서 작업·commit(자동 생성·git init) |
| `ASV3_TARGET_REPO_DIR` | (미설정) | `ASV3_WORKSPACE_DIR`의 deprecated 별칭(이것도 프로젝트별 루트 `{path}/{project_id}`). **`ASV3_WORKSPACE_DIR` 미설정 시에만** 사용. 프로젝트별 오버라이드는 Objective `data.repo_dir`(최우선) |
| `ASV3_LLM_WIKI_ROOT` | (미설정) | 프로젝트 완료 시 Decision을 승격할 위키 루트. **미설정이면 승격 skip**(실제 디스크 안 건드림) |
| `ASV3_EMBEDDINGS` | (미설정) | `huggingface`면 실제 임베딩 모델, 아니면 결정적 offline 임베딩 |
| `ASV3_CHECKPOINTER` | `auto` | LangGraph 체크포인터: `memory` / `postgres` / `auto`(Postgres URL이면 postgres) |
| `ASV3_BRAIN` | `claude` | `real` 모드에서 호출할 CLI 이름 |
| `VITE_API_BASE` | (미설정) | **프론트**: 설정하면 실제 백엔드, 미설정이면 mock 모드 |

> `real` 모드 메모: `ANTHROPIC_API_KEY`가 있으면 LangChain planner, 없으면 `claude -p` CLI(Claude Code OAuth)로 폴백한다.
> SQLite + `auto`면 체크포인터는 in-memory(MemorySaver, 프로세스 수명). 영속 resume은 Postgres 필요.

---

## 테스트

```bash
# 백엔드 (in-memory SQLite로 격리 실행)
cd api && DATABASE_URL="sqlite+pysqlite:///:memory:" .venv/bin/python -m pytest

# 프론트
cd web && npm test            # vitest
cd web && npx tsc --noEmit    # 타입체크
cd web && npm run lint        # eslint
```

---

## 프로젝트 구조

```
api/
  app/
    main.py              FastAPI 앱 + CORS/에러 미들웨어
    db.py                엔진/세션/체크포인터
    models.py            Node/Edge 테이블
    routers/             graph.py · lifecycle.py · memory.py (REST 엔드포인트)
    graph/               store.py(그래프 CRUD) · diff_ingest.py(diff→노드/엣지)
    services/            lifecycle_graph.py(StateGraph) · planner.py · executor.py
                         embeddings.py · memory.py(RAG) · promotion.py(위키 승격) · prompt_build.py
  tests/                 pytest (라이프사이클·RAG·diff·회귀 등)
  seed_demo.py           데모 그래프 시드 스크립트
web/
  src/
    App.tsx · components/Shell.tsx        셸/레이아웃
    components/{map,board,cockpit,lane,review,plan,goal,bugtrace,legend,home}/
    store/useStore.ts                     Zustand 상태 + 1.5s 폴링
    api/{ApiClient.ts, http/, mock/}      백엔드 seam (Http=실서버 / Mock=브라우저 시뮬)
    domain/graph.ts                       그래프 도메인 모델
docs/
  superpowers/specs/…                     설계 spec
  user-flows-sequence-diagrams.md         모든 사용자 흐름(시퀀스 다이어그램)
  user-flows-e2e-findings.md              E2E 테스트 결과
  defects.md                              결함 레지스트리(상태·근본원인·수정 위치)
docker-compose.yml                        풀스택(web+api+db, simulated)
docker-compose.db.yml                     DB만(Postgres+pgvector, localhost:5432)
docker-compose.hostapi.yml                db+web 컨테이너 + api는 호스트(real 모드)
web/nginx.conf · web/nginx.static.conf    풀스택용(/api 프록시) · 호스트-api용(정적만)
db/init/01-extensions.sql                 첫 부팅 시 CREATE EXTENSION vector
.env.example                              docker 노브(.env로 복사)
```

---

## 문서

- 설계 spec: [`docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md`](docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md)
- 사용자 흐름(시퀀스): [`docs/user-flows-sequence-diagrams.md`](docs/user-flows-sequence-diagrams.md)
- E2E 테스트 결과 / 결함: [`docs/user-flows-e2e-findings.md`](docs/user-flows-e2e-findings.md) · [`docs/defects.md`](docs/defects.md)
