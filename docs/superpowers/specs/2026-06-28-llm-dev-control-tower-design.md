# LLM Dev Control Tower — 설계 (greenfield, v1)

- 작성일: 2026-06-28 (KST)
- 상태: **설계 확정, Kay 리뷰 대기** → 승인 시 구현 계획(writing-plans)으로
- 방식: **greenfield** (새 레포·새 멘탈모델). 기존 `agent-system-v2`는 참조만, 코드 계승 안 함.
- 출처: Kay와의 brainstorming 세션(2026-06-28) + 기존 `agent-system-v2` 회고/갭분석 + `~/llm_wiki` 결정 문서.

---

## 0. 한 줄 정체성

> **LLM 개발의 통제탑.** 거친 목표("Todo 앱 만들어")를 주면, 시스템이 LLM을 **작고·보이고·리뷰 가능한 step**으로 일하게 하고, 일하는 동안 **살아있는 지도**(목표→티켓→step→코드영역→테스트→결정)를 짓는다. 뭔가 깨지면 지도가 *어디를 볼지* 답한다. 지도에서 뽑은 스코프 컨텍스트가 사람과 LLM을 objective에 묶어두고, 끝난 프로젝트는 교훈만 개인 위키로 승격한다.

## 1. 해결하려는 진짜 문제

Kay가 Claude/Codex로 큰 프로젝트를 만들 때의 핵심 고통:

1. **블랙박스**: specific하지 않은 task(예 "Todo 앱")를 주면 LLM이 블랙박스 안에서 이것저것 하고 결과물 + 텍스트 덩어리만 던짐 → ⓐ *어디서부터 QA*할지, ⓑ *버그가 어느 부분*인지 판단 불가.
2. **컨텍스트 유실**: 프로젝트가 클수록 LLM이 한 세션에 full 컨텍스트를 못 담음 → 사람도 LLM도 main objective를 잃음.

→ ⓐⓑ는 **칸반으로 LLM을 작은 단위로 몰고**(가시성·통제), 유실은 **필요할 때 정확한 컨텍스트 chunk를 돌려주는 구조**(LLM Wiki/지도)로 푼다.

**기존 시스템이 off-pitch였던 이유**: *자율성(autonomy)* 을 최적화했지만, Kay가 실제로 원한 건 정반대인 *가시성·통제(visibility & control)*. 그래서 본 재설계는 **통제·추적·외과적 디버그**를 1차 가치로 둔다.

## 2. 두 목적 (설계를 지배)

| 목적 | 내용 | 영향 |
|---|---|---|
| 주 | Kay의 실용적 LLM 개발 통제 | 단일 사용자 로컬, 모든 step에 Kay 리뷰 게이트 |
| 부 | Web Dev → **AX Engineer 커리어 전환** 포트폴리오 | **LangGraph·RAG/pgvector를 *load-bearing*으로** 채택(장식 아님) |

## 3. Decision Log (이 세션에서 확정)

| # | 결정 | 선택 | 근거 |
|---|---|---|---|
| D1 | 시스템의 본질 | 자율 실행기 ❌ → **LLM 개발 통제탑** | §1 |
| D2 | 통제 강도 | **계획 먼저 → step마다 정지·리뷰** (가장 짧은 목줄) | 가시성 최대 |
| D3 | 1차 화면/QA 단위 | **살아있는 기능↔코드 지도** (버그→책임 코드 역추적) | 고통 ⓐⓑ |
| D4 | 기억 구조 | **프로젝트별 격리 그래프(지도=컨텍스트 통합) + 개인 cross-project 위키로 교훈 승격** (3겹 스코프) | 컨텍스트 유실·프로젝트 충돌 방지 |
| D5 | 실행 주체 | **시스템이 step을 자동 실행** (단, 헤드리스·견고하게) | Kay가 자동화 원함; 통제는 step 경계·게이트·지도에서 |
| D6 | 빌드 전략 | **greenfield** (새 레포) | 깨끗한 멘탈모델 |
| D7 | 저장 | **Postgres + pgvector** — 지도=관계형 nodes/edges, 기억=pgvector RAG | 정확성(지도) + 의미검색(기억) + 학습 목적 |
| D8 | 지도의 진실원천 | **git diff** (에이전트 주장 아님) | 지도가 거짓말 안 함 |
| D9 | 라이프사이클 런타임 | **LangGraph StateGraph + PostgresSaver** (티켓 단위만) | interrupt(정지)·cycle(재실행)·checkpoint(durable)가 요구와 1:1 |
| D10 | v1 범위 | **한 티켓 수직 슬라이스** (걷는 해골) | 8-phase 과욕 회피 |

> **불변 규칙**: 지도(노드/엣지)는 **관계형**으로 저장한다. RAG/벡터는 *텍스트 회상*에만 쓰고, 지도 탐색에는 절대 쓰지 않는다(퍼지함 = 우리가 탈출하려는 바로 그것).

## 4. v1 걷는 해골 (한 티켓 수직 루프)

```
1. 목표 입력 ("Todo 앱: 할일 CRUD")              → 티켓 1개
2. PLAN: 에이전트가 작은 step 목록 제안          → Kay가 분해 승인 (게이트)
3. 각 STEP을 시스템이 자동 실행(헤드리스)         → step 1개 = commit 1개 → git diff
4. diff에서 touched 파일/심볼 추출               → 지도 노드·엣지 자동 생성/갱신
5. step 끝 → 정지. Kay가 diff + 지도조각으로 리뷰 → ✅승인 / ✏️수정요청 / ⏸인수
6. 다음 step … 반복                              → 티켓 완료
성공 판정: 기능↔코드 지도가 살아있고, "'할일 추가' 버튼 버그" → 어느 step/파일인지 역추적됨
```

## 5. 스택 (greenfield, 일부러 minimal·known)

| 층 | 선택 | 이유 |
|---|---|---|
| 백엔드 | **Python + FastAPI** | 에이전트 헤드리스 호출·git 제어·async |
| 저장 | **Postgres + pgvector** | 지도=관계형 nodes/edges, 기억=벡터 RAG |
| 라이프사이클 | **LangGraph StateGraph + PostgresSaver** | 티켓 step 루프의 상태기계(durable·HITL) |
| 실행 | **헤드리스 CLI step 호출** (`claude -p` / codex, 출력+diff 캡처) | tmux pane 긁기(옛 깨진 곳) 폐기. 결정적 |
| 버전관리 | step마다 git commit (대상 프로젝트 레포) | diff = 지도의 진실원천 |
| 프론트 | **React + Vite + 그래프 뷰 라이브러리**(React Flow류) | 지도가 1차 화면 |

**구분**: **통제탑(이 시스템)** 과 **대상 프로젝트(만들어지는 Todo 앱)** 는 별개. 통제탑이 대상 프로젝트 디렉토리(=그 자체로 git 레포)를 조작하고, step마다 거기에 commit한다. 그래프는 그 레포의 commit/파일을 가리킨다.

## 6. 데이터 모델 — 작업 그래프 (지도)

프로젝트별 그래프 1개. 노드 6종 + 엣지. 엣지는 git diff에서 *기계적으로* 생성.

**노드**

| 노드 | 뜻 |
|---|---|
| `Objective` | 프로젝트 목표(루트) |
| `Ticket` | 작업 단위 (재귀 분할 가능) |
| `Step` | 티켓 아래 원자적 실행 단위 (에이전트 1회 = 1 step = 1 commit) |
| `CodeRegion` | 파일 또는 `파일:심볼/함수` |
| `Test` | 특정 영역을 덮는 테스트 |
| `Decision` | 기록된 "왜"(선택·트레이드오프) → 끝나면 위키 승격 후보 |

**엣지 (방향)**

```
Objective ─has→ Ticket ─subdivides→ Ticket        (재귀)
Ticket ─has→ Step
Step ─touches→ CodeRegion                          ← git diff에서 자동 (진실원천)
Step ─adds/covers→ Test
CodeRegion ─tested_by→ Test
Step·Ticket ─decided→ Decision
Step ─produced→ commit(sha)
```

**핵심 메커니즘 3개**

1. **diff → 지도 (자동·정확)**: step 끝 → commit → diff 파싱 → 바뀐 파일/심볼 → `CodeRegion` 노드 찾기/생성 → `Step ─touches→ CodeRegion`. 멱등·결정적(같은 commit 재실행 = 같은 엣지) → 지도를 git에서 재구성 가능.
2. **버그 → 어디 볼지 (고통 ⓐⓑ)**: 증상(파일/UI요소/기능) → 역방향 `CodeRegion ←touches─ Step ←has─ Ticket → Decision/이력`.
3. **스코프 컨텍스트 → objective 유지**: step 실행 시 프롬프트 = `Objective(고정 핀) + 티켓 spec/acceptance + 티켓이 소유한 CodeRegion + 이웃 Decision (+ 필요시 pgvector 회상)`. **전체 레포 아님.** 그래프 이웃 = 정확한 컨텍스트 chunk.

**3겹 스코프 (D4)**

```
~/llm_wiki  (개인 2nd brain, 영속·cross-project)  ←── 프로젝트 종료 시 "교훈(Decision)만" 승격
      ▲ pgvector RAG로 당겨씀
 ┌────┴─────┐  ┌──────────┐  ┌──────────┐
 │ A_graph  │  │ B_graph  │  │ C_graph  │   ← 프로젝트별 격리된 지도+컨텍스트
 └──────────┘  └──────────┘  └──────────┘
```

프로젝트 그래프는 서로 완전히 격리(A 끝나고 B 해도 충돌 없음). 공유되는 건 위층의 "교훈" 한 겹뿐.

**pgvector 기억층**: `Decision` + cross-project 교훈을 임베딩 → 의미검색으로 컨텍스트 패킷·cross-project 회상. (지도 노드/엣지는 관계형, 벡터 아님.)

## 7. Stepwise 실행 루프 — LangGraph StateGraph

티켓 1개 = StateGraph 1 실행. State = `{objective, ticket, steps[], current, decisions, ...}`.

```
StateGraph(TicketState)
  plan ──interrupt(분해 승인)──> execute_step
  execute_step ──> review              ← interrupt()  = step 정지 게이트
  review ──approve──> (남은 step? execute_step : END)
  review ──changes──> execute_step      (코멘트 주입 재실행; 사이클)
  review ──takeover─> ingest_diff ──> review
  checkpointer = PostgresSaver          # durable·resumable
```

**노드별 책임**
- `plan`: Planner 에이전트(헤드리스) 호출 → 작은 step 목록(구조화 출력: 의도·acceptance·예상범위) → `interrupt`로 Kay 분해 승인 대기 → 승인분만 `Step` 노드(pending).
- `execute_step`: 스코프 프롬프트(§6-③) 조립 → 헤드리스 실행(권한 사전인가, 대상 레포 워크트리) → 파일 작성 → **commit 1개** → diff 캡처 → 그래프 갱신 + 에이전트 요약 → `Decision` 노드.
- `review`: `interrupt()`로 정지. Kay가 diff + 지도조각 + 결정 + acceptance 보고 3택.
- `ingest_diff`: Kay 수동 편집(⏸인수)의 diff를 먹어 그래프 갱신.

**LangGraph 기능 ↔ 요구 매핑**

| 요구 | 기능 |
|---|---|
| step마다 정지·리뷰 | `interrupt()` (HITL) |
| 수정요청 → 재실행 | 조건부 엣지 + 사이클 |
| 정전/재시작에 이어가기 | `PostgresSaver` 체크포인트 |
| plan/exec/review 분기 | 조건부 엣지 |

**경계**: LangGraph는 **티켓 라이프사이클만** 몬다. API·그래프 저장·diff 파싱·에이전트 호출은 평범한 백엔드가 담당(앱 전체 오케스트레이션을 떠안기지 않음 — 옛 과욕 회피).

## 8. UI — 지도 중심

**대원칙**: 지도가 홈. 배관 0(tick 버튼·파일경로·API주소 노출 없음). LangGraph 상태를 구독해 *살아있게* 표시(stale 없음, 수동 Refresh 없음).

**화면 (2고도)**

1. **프로젝트 지도 (홈, zoom-out)**: 그래프 캔버스. 중앙 `Objective`, 가지로 `Ticket`들(step 진행도 N/M + 상태색: planning/executing/⏸리뷰대기/done/blocked). `CodeRegion` 레이어 토글. 한눈에 "어디·뭐 도는 중·뭐 막힘".
2. **티켓 레인 (zoom-in)**: step 타임라인. 각 step 카드(pending/running/⏸리뷰대기/done/blocked). 정지한 step이 전면.
3. **리뷰 페인 (게이트, 주 작업면)**: 좌 = diff(하이라이트), 우 = 이 step이 만든 지도 조각 + 에이전트 결정/왜 + acceptance, 하단 = ✅승인/✏️수정요청/⏸인수.
4. **버그 추적 제스처**: 파일/심볼/컴포넌트 클릭·검색 → 지도가 소유 step→티켓→결정 경로 하이라이트 + 해당 commit/diff로 점프.

## 9. 에러 처리

- **step 실패**(에이전트 에러/비정상 종료): step → `blocked`, 캡처된 stdout/stderr 노출 → 재시도/인수. 조용한 실패 없음.
- **원자 commit** → 나쁜 step은 `git revert` 한 방 + 엣지 제거.
- **빈 diff**: "변경 없음" 플래그 → Kay 판단.
- **구조화 출력 깨짐**(planner/executor): 검증 + 제한적 재프롬프트, 그래도면 노출.
- **rate-limit/API 에러**: 정직하게 노출 → 재시도 (v1 자동재개 없음).
- **프로세스 사망**: PostgresSaver 체크포인트 → 재시작 시 마지막 정지점부터 resume.

## 10. 테스트

- `diff→그래프 추출기`: diff 입력 → 올바른 CodeRegion 노드/엣지 (순수함수).
- `버그추적 쿼리`: 시드 그래프에서 역추적 검증.
- `LangGraph 라이프사이클`: **stub executor**(결정적, 쿼터 0)로 plan/execute/review·interrupt/resume·수정루프 상태전이 검증.
- `컨텍스트 스코프 조립기`: 그래프+step → 프롬프트에 *이웃만* 들어가는지.
- **simulated executor 모드**: 실제 헤드리스 에이전트를 *알려진 diff를 쓰는 stub*으로 교체 → 전체 루프 E2E를 쿼터 없이.
- 프론트: 지도는 그래프 API에서 렌더; 리뷰 페인 3액션 컴포넌트 테스트.
- **v1 인수 기준**: "Todo CRUD" 티켓 1개가 plan→step들→리뷰→done 완주, 이후 지도가 "'할일 추가' 버튼은 어느 step/파일?"에 역추적으로 답함.

## 11. 비목표 (v1에서 명시적으로 뺌, YAGNI)

- rate-limit 자동재개(Haiku 파싱·cron) — 에러 노출 후 수동 재시도로 충분.
- 인터랙티브 tmux 세션·라이브 pane 스트리밍(SSE) — 헤드리스 + 리뷰 게이트로 대체.
- 자기진화 스킬 자동 생성/설치 — 위키 승격까지만, 스킬화는 나중.
- 멀티 사용자·SaaS·K8s·외부 통합(Slack/Notion/Jira).
- cross-project 교훈 승격의 자동화 — v1은 수동/반자동.
- persona/brain 대규모 카탈로그 — v1은 단일 executor면 충분(필요 시 1~2개).

## 12. Open Questions (구현 계획에서 확정)

- 헤드리스 에이전트 호출의 정확한 인터페이스: `claude -p --output-format json` vs Agent SDK; 구조화 출력(plan·step 요약) 스키마.
- `CodeRegion`의 입도: 파일 단위로 시작? 심볼(함수) 단위까지? (v1은 파일+선택적 심볼 권장.)
- diff→심볼 추출 방법: 언어별 파서 vs 휴리스틱(헝크 헤더). v1 최소: 파일 단위 + 헝크.
- 대상 프로젝트 레포 위치·격리(워크트리/디렉토리 규약), 백업(`pg_dump` + 레포 git).
- LangGraph `interrupt`/resume를 FastAPI 요청-응답과 잇는 패턴(웹 리뷰 게이트 ↔ 그래프 일시정지).
- pgvector 임베딩 모델(로컬 vs API) — v1은 가볍게, 학습 목적상 실제 임베딩 1개.
```
