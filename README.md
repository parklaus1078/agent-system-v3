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
                                                       대상 git 레포(ASV3_TARGET_REPO_DIR)
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

# 2) 프론트
cd ../web
npm install
```

---

## 데모 실행 (가장 빠른 길 — `simulated`)

터미널 2개가 필요하다.

```bash
# ── 0) executor가 커밋할 대상 레포 1개 준비 (한 번만) ──
mkdir -p /tmp/asv3-target && git -C /tmp/asv3-target init -q \
  && git -C /tmp/asv3-target commit -q --allow-empty -m init

# ── 1) 데모 그래프 시드 (project p1: 목표 + 티켓 t-crud/t-gate/t-pay/t-sync) ──
cd api
DATABASE_URL="sqlite+pysqlite:///./dev.db" .venv/bin/python seed_demo.py

# ── 2) 백엔드 (API :8099) ──
DATABASE_URL="sqlite+pysqlite:///./dev.db" ASV3_AGENT_MODE=simulated \
  ASV3_TARGET_REPO_DIR=/tmp/asv3-target \
  .venv/bin/python -m uvicorn app.main:app --port 8099
```

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

## 환경변수

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DATABASE_URL` | `sqlite+pysqlite:///:memory:` | SQLAlchemy URL. 데모는 `sqlite+pysqlite:///./dev.db` 권장(영속). `postgresql+psycopg://…`면 Postgres |
| `ASV3_AGENT_MODE` | `simulated` | `simulated`(stub, 쿼터 0) 또는 `real`(`claude -p`) |
| `ASV3_TARGET_REPO_DIR` | `.` | executor가 step마다 commit하는 **대상 git 레포** 경로 |
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
```

---

## 문서

- 설계 spec: [`docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md`](docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md)
- 사용자 흐름(시퀀스): [`docs/user-flows-sequence-diagrams.md`](docs/user-flows-sequence-diagrams.md)
- E2E 테스트 결과 / 결함: [`docs/user-flows-e2e-findings.md`](docs/user-flows-e2e-findings.md) · [`docs/defects.md`](docs/defects.md)
