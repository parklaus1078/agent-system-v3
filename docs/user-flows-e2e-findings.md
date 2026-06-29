# LLM Dev Control Tower — User-Flow E2E 테스트 결과 & 문제 기록

[`user-flows-sequence-diagrams.md`](user-flows-sequence-diagrams.md)에 정의된 **모든 user flow(A1, B1–B6, C1–C3, D1–D6, E1–E5 = 21개 + API 직접 호출)** 를 실제 브라우저(Playwright/Chrome)로 end-to-end 구동하고, 발견한 문제를 기록한다.

- 작성일: 2026-06-29 (KST)
- 대상 브랜치: `feat/frontend-ui-on-mock` (실제 구현 + 시퀀스 다이어그램 문서가 있는 브랜치. `main`에는 둘 다 없음 — 아래 *환경 메모* 참조)
- 방법(ultracode): ① 멀티 에이전트가 각 flow의 실제 코드 경로를 읽어 **실행 가능한 테스트 스펙 + 기대값**을 병렬 생성 → ② 메인이 단일 브라우저로 21개 flow를 순차 구동(폴링 re-render에 강하도록 a11y/텍스트 기반) → ③ 발견을 12개 에이전트가 **소스에 대해 적대적으로 재검증**(근본원인·심각도·수정안). 본 문서의 모든 결함은 코드 `file:line`까지 확인됨.

---

## 1. 테스트 환경

| 항목 | 값 |
|---|---|
| 프론트 | `VITE_API_BASE=http://127.0.0.1:8099 vite --port 5180` → **실제 백엔드 사용**(mock 아님) |
| 백엔드 | FastAPI `uvicorn app.main:app :8099`, `DATABASE_URL=sqlite:///./dev.db`, **`ASV3_AGENT_MODE=simulated`** |
| 실행자 | SimulatedPlanner(고정 3 step: 스펙·골격/구현/테스트) + SimulatedExecutor(`generated/step_N.ts` 작성). 쿼터 0, 결정적. |
| 시드 | project `p1`: obj + 티켓 t-crud(done)/t-gate(executing, s4 awaiting_review)/t-pay(planning)/t-sync(blocked, sy2 blocked)/t-new(executing) + decision `dec` + code_region 5개 |

> **왜 simulated + 실제 백엔드인가:** mock 모드는 web→API→lifecycle→DB→memory→wiki의 **서버 절반을 통째로 건너뛴다**(다이어그램의 핵심). simulated 모드는 LangGraph 라이프사이클·DB 기록·diff 인제스트·메모리·승격을 전부 태우면서 `claude -p`만 stub으로 대체하므로, 시퀀스 다이어그램을 *있는 그대로* 검증하기에 맞다.

> **환경 메모(중요):** 작업 시작 시 워킹트리는 `main`이었고, 거기에는 `api/app/*.py`·`web/src/**` 소스와 본 user-flows 문서가 **존재하지 않았다**(컴파일된 `.pyc`와 `web/dist`만 남아 처음엔 소스가 삭제된 것처럼 보였음). reflog 확인 결과 전체 구현과 문서는 모두 `feat/frontend-ui-on-mock` 브랜치(및 origin)에 안전하게 있었고, `main`은 사실상 문서/플랜만 있는 stale 브랜치였다. 테스트는 `feat/frontend-ui-on-mock`을 체크아웃해 진행했다. → **main에 구현 브랜치를 머지해야 한다.**

---

## 2. Flow 커버리지 요약

| Flow | 결과 | 비고 |
|---|---|---|
| **A1** 초기 로드 + 1.5s 폴링 | ✅ PASS | `GET /graph` 1.5s마다 200, 콘솔 에러 0, 라이브 클록 동작 |
| **B1** 지도→보드→콕핏 | ✅ PASS | 티켓 클릭→칸반, "리뷰 시작"→콕핏 |
| **B2** Navigator⇄Cockpit·브레드크럼 | ✅ PASS | aria-pressed 정확. (티켓 선택 상태에서 Navigator는 *보드*로 감 — 다이어그램과 일치하나 직관에 반함) |
| **B3** step 선택→상세 | ✅ PASS | `GET /steps/{id}` 200. 단, 콕핏 우패널은 요약뷰라 diff 미표시(전체 리뷰에서만) + 매 폴링마다 재요청(→ **F11**) |
| **B4** 프로젝트 홈⇄프로젝트 | ✅ PASS | 단, 문서가 말하는 "+ 목표·티켓" 버튼은 홈에 없음 → "새 목표" textarea + "분해 시작" (**§4 사소**) |
| **B5** 버그 추적→소유 경로 | ⚠️ PASS(부분) | owning-path 200·하이라이트·코드 레이어 자동 표출 OK. **Step hop은 지도에서 안 보임**(step이 티켓으로 collapse) + placeholder 과대광고(**§4**) |
| **B6** Legend·CodeRegion 레이어 | ✅ PASS | Legend 팝오버 OK. CodeRegion 토글 **완전 동작**(코드노드 5개+touches) → 문서의 "partial" 표기는 **오류**(**F12**) |
| **C1** 새 목표→제안→편집→승인→실행 | ✅ PASS | 신규 티켓 생성→step1 자동 실행→리뷰 게이트. (planner는 simulated라 항상 동일 3 step) |
| **C2** planning 티켓 재계획 | ⚠️ PASS(결함) | 동작하나 **기존 step을 버리고 generic 재제안**(**F8**) |
| **C3** plan 편집(추가/삭제/순서/이름) | ✅ PASS | 4개 조작 모두 동작. 단, label만 편집 가능(intent/acceptance·title은 노출 안 됨, **F7**) |
| **D1** step 실행 내부(diff→지도) | ✅ PASS | 각 step 커밋의 diff가 `generated/step_N.ts` code_region으로 인제스트됨(라이브 확인) |
| **D2** 리뷰→승인→다음 실행 | ⚠️ 부분 | 인세션 티켓에서는 정상(step done→다음 실행). **시드 게이트(s4)는 409로 동작 불가 + 무알림 실패**(**F1**) |
| **D3** 리뷰→수정요청→재실행 | ⚠️ 부분 | 인세션 정상(같은 index 재실행). 시드는 F1과 동일 409 |
| **D4** 리뷰→인수(takeover) | ⚠️ 부분 | 자동화는 멈추나 **이후 사람이 step을 진행/완료할 UI가 없어 영구 정지 + 프로젝트 완료 차단**(**F10**) |
| **D5** 전체 리뷰 패널 | ✅ PASS | diff/지도조각/acceptance/tests 렌더. 단 시드 step의 액션 버튼은 409(F1) |
| **D6** blocked step 디버그 추적 | ⚠️ PASS(부분) | blocked 뷰 진입·오버레이 OK. 단 "포착된 실패 컨텍스트"는 비어 있음(diff/decision 없음); 시드는 unblock/재실행 경로 없음 |
| **E1** RAG 컨텍스트 주입 | ⚠️ 코드 검증 | 브라우저 비관측(프롬프트 내부). clean 상태에선 OK이나 메모리 오염 후 500(**F2**) |
| **E2** 프로젝트 완료→위키 승격 | ⚠️ 코드 검증 | 시드로는 UI 트리거 사실상 불가(전 티켓 done 필요). + 미설정 시 **실제 ~/llm_wiki에 기록**(**F5**) |
| **E3** 메모리 검색(API) | ❌ FAIL | reindex 후 **HTTP 500**(NaN, **F2**). 빈 스토어 200 `[]`, q 누락 422 |
| **E4** 메모리 reindex(API) | ⚠️ PASS(결함) | `{indexed:1}`이나 호출마다 **중복 append**(clear 없음, **F6**) + 한국어 결정 색인이 스토어 오염 |
| **E5** 체크포인트/resume·sim vs real | ⚠️ PASS(결함) | resume 동작. 단 미시작 티켓 `/state`가 **done:true 거짓 보고**(**F4**) |

✅ 단순 동작 9 · ⚠️ 동작하나 결함/한계 10 · ❌ 실패 1.

---

## 3. 결함 (심각도순) — 모두 소스 `file:line` 검증 완료

### 🔴 HIGH

#### F1 — 리뷰 게이트가 시드 데이터에서 동작 불가 + **무알림 실패** (D2/D3/D4/D5/D6)
- **증상:** 시드 step `s4`(또는 `sy2`)에서 승인/수정요청/내가 인수 클릭 → `POST /projects/p1/steps/s4/review` **409 Conflict**. UI는 그대로 "awaiting review", 에러 토스트·메시지 전무. 콘솔에만 unhandled rejection.
- **근본원인:**
  - `api/seed_demo.py` 는 DB 그래프(`seed_graph`+`apply_step_diff`)만 시드하고 **LangGraph 체크포인트를 만들지 않음** → 시드 티켓엔 resume할 interrupt가 없음.
  - `api/app/routers/lifecycle.py:212-213` `review_step`: 빈 체크포인트에서 review interrupt를 못 찾아 상태 변경 전에 409 raise.
  - `web/src/components/review/ReviewSummary.tsx:75` 승인이 `void api.reviewStep(...)`(fire-and-forget), `ReviewPane.tsx`의 `act()`도 rejection 미캐치. `HttpApiClient.post`는 non-2xx에 throw → **web/src 어디에도 ErrorBoundary·onunhandledrejection·토스트 없음** → 완전 무음.
  - (참고: `_ticket_of_step` 정규식 `-s\d+$`가 시드 id를 못 맞추는 건 부수적 — 근본은 체크포인트 부재. 인세션 티켓(`{tid}-s{n}`)은 정상 200.)
- **영향:** 스펙상 *주 작업면*인 리뷰 게이트가 데모 데이터 전체에서 죽어 있고, 실패가 사용자에게 전혀 보이지 않음.
- **수정:** (1) 모든 쓰기 실패를 표면화 — 핸들러에 try/catch+토스트, 전역 ErrorBoundary/`onunhandledrejection` 추가. (2) 시드가 실제 라이프사이클을 plan/approve까지 구동해 체크포인트를 만들거나, 서버가 "체크포인트 없음"을 구분 가능한 상태로 응답해 UI가 비활성/안내 렌더.

#### F2 — 메모리 레이어 자기-오염 → **HTTP 500** (E3 검색, E1 실행 RAG)
- **증상:** `POST /memory/reindex/p1` 후 `GET /memory/search?q=gating&k=4` → **500**. 재시작(빈 스토어)하면 200 `[]`. 이후 RAG 쓰는 `execute_step`(E1)도 500.
- **근본원인:** `api/app/services/embeddings.py:21` `DeterministicEmbeddings._vec`가 `re.findall(r'[a-z0-9]+', ...)`로 토큰화 → **한국어는 토큰 0개 → 전부-0 벡터**. 시드 유일 decision이 한국어("게이팅은 플래그로…")라 색인 시 zero-vector 1개만 들어감 → langchain `InMemoryVectorStore` 코사인이 0/0=NaN → numpy 백엔드(simsimd 부재)가 `ValueError('NaN values found')` → `routers/memory.py:57`·`execute_step` 모두 미가드 → 500. `MEMORY`는 프로세스 전역 싱글턴이라 한 번 오염되면 재시작까지 지속.
- **수정(주):** `_vec` 토큰화를 유니코드로 — `re.findall(r'\w+', text.lower())` (한국어 라벨에서 5토큰 확인). 방어적: `index_text`에서 zero-norm 문서 스킵, `retrieve`에서 ValueError catch→`[]` 반환.

#### F10 — 인수(takeover) 후 **막다른 길**: 티켓 영구 정지 + 프로젝트 완료 차단 (D4)
- **증상:** "내가 인수" → `POST /steps/{id}/review {takeover}` 200, 자동화 정지(다음 step planned 유지). 그러나 사람이 그 step을 **진행/완료/반납할 UI·API가 없음**. step 노드는 여전히 awaiting_review라 같은 승인/수정요청/인수 버튼이 다시 뜨지만 이제 전부 409(무음).
- **근본원인:** `api/app/services/lifecycle_graph.py:105-111` `after_review`가 takeover에서 `END` 반환(그래프 종료, interrupt 소멸) + `current` 미증가. `api/app/routers/lifecycle.py:224-226`은 ticket.status만 awaiting_review로, step은 그대로. 종료 후 모든 `/review`는 409(`lifecycle.py:212-213`). `web/src/domain/graph.ts`에 `taken_over` 상태 없음, 후속 컨트롤 없음.
- **하류 영향:** 인수된 티켓은 영원히 awaiting_review → `_all_tickets_done`이 참이 될 수 없음 → 해당 프로젝트는 **절대 완료/승격(E2) 불가**.
- **수정:** takeover를 `END` 대신 resume 가능한 'manual' 게이트로; `taken_over` 상태 + "완료로 표시"/"에이전트에 반납" 엔드포인트·컨트롤 추가; 409를 표면화.

### 🟠 MEDIUM

#### F3 — 500 응답에 CORS 헤더 누락 → 브라우저가 에러를 읽지 못함
- **증상:** 500 응답엔 `access-control-allow-origin` 없음(200엔 있음). 브라우저 cross-origin fetch가 "Failed to fetch"로 막힘(에러 바디·상태 못 읽음).
- **근본원인(구조적, 모든 미처리 500에 항상 발생):** `api/app/main.py`의 `CORSMiddleware`는 user 미들웨어라 Starlette `ServerErrorMiddleware`(최외곽)보다 **안쪽**에 위치. 미처리 예외는 `send` 래핑 전에 전파되어 CORS 헤더가 안 붙음(2xx/4xx/HTTPException/422는 정상).
- **수정:** CORS *안쪽*에 예외→JSONResponse 변환 미들웨어를 두어 에러 응답이 CORS 래퍼를 통과하게 함(`app.add_exception_handler`는 CORS 바깥이라 효과 없음).

#### F5 — 위키 승격이 **실제 ~/llm_wiki에 기록** (E2)
- **증상/원인:** `api/app/services/promotion.py:13`이 `ASV3_LLM_WIKI_ROOT` 미설정 시 하드코딩 기본값 `/home/kay/llm_wiki`(= 사용자의 진짜 second-brain: `.obsidian/`·자체 git·실제 결정 문서 존재)로 폴백. `lifecycle.py:233`은 wiki_root 인자 없이 `promote_project` 호출. 프로젝트 완료(전 티켓 done) 시 `asv3-p1-dec.md`를 실제 볼트에 기록(완료 0건이어도 mkdir로 경로 생성).
- **이번 세션 실제 오염 없음**(시드는 미완료 + 재테스트 시 `ASV3_LLM_WIKI_ROOT`를 스크래치로 지정). 잠재/조건부 위험.
- **수정:** 실제 경로 하드코딩 금지 — 미설정 시 승격 skip(경고 로그) 또는 repo-local/temp 기본값, 또는 명시적 opt-in 플래그.

#### F6 — `/memory/reindex`가 진짜 reindex 아님(중복 누적) (E4)
- **원인:** `routers/memory.py:62-68`+`services/memory.py:21-36`가 기존 벡터를 **clear하지 않고** `add_documents`로 append(id 미지정). 호출마다 중복 누적 → 검색 품질 저하. `{indexed:N}`은 decision 노드 수일 뿐 스토어 건강도 아님.
- **수정:** reindex 전 프로젝트 벡터 delete, 또는 `node_id:chunk` 안정 id로 upsert; 응답에 실제 벡터 수 반환.

#### F7 — plan 승인 시 title/intent/acceptance 비편집·미영속 (C1/C2) *(부분 확인)*
- **확인된 부분:** `HttpApiClient.approvePlan`은 `{steps}`만 전송(title 미전송), 백엔드 `PlanApproveIn`에 title 없음; UI에서 **편집 가능한 건 step label뿐**(intent/acceptance 입력 없음); `on_steps_approved`는 label만 영속(step 노드에 intent/acceptance 미기록).
- **과장 정정:** title은 *읽기전용 span*이라 애초에 편집 불가 → "편집된 title 유실"은 발생 안 함(티켓 생성은 plan-start에서 이미 영속). intent/acceptance는 **실행 프롬프트엔 전달·소비됨**(`prompt_build.py`) — 단지 UI 편집·그래프 영속이 안 될 뿐.
- **수정:** title 편집을 원하면 `PlanApproveIn.title` 추가+바인딩; intent/acceptance를 편집 필드로 노출하고 step 노드(`data`)에 영속. 또는 "label-only 리뷰"가 의도면 스펙에 명시.

#### F11 — 라이브 폴링 낭비 + 해제 안 됨 (A1, B3)
- **원인:** `HttpApiClient.subscribe`가 1.5s `setInterval`로 **전체 그래프 재요청 후 통째 교체**(매 tick 전 화면 re-render). `useStepDetail.ts:35`가 effect deps에 `graph`(매 폴링마다 새 객체)를 둬 **선택 안 바뀌어도 `/steps/{id}`를 매 tick 재요청**(유휴 중 동일 요청 16+회 관측). `subscribe`는 clearInterval teardown을 반환하지만 `useStore.ts:48`가 이를 버려 **영구 폴링**(SSE 미구현, 코드 주석 "until SSE").
- **수정:** 그래프 변경 없을 때 set 스킵(version/etag·shallow compare); `useStepDetail` deps에서 graph 제거; teardown 호출; `document.hidden` 시 일시정지/SSE.

### 🟡 LOW

#### F4 — 미시작 티켓의 `/state`가 `done:true` 거짓 보고 (E5)
- `lifecycle.py:143` `done = not snap.next` — 빈 체크포인트는 `next==()`라 vacuously true. 부팅 시 MemorySaver가 비어 t-gate(executing)·t-pay(planning)·t-crud(done) 전부 `{done:true, awaiting:null, steps:[]}` → `/graph`와 불일치. **현 프론트는 `/state`를 안 써서 영향 적음**(low). 수정: `started = bool(snap.values); done = started and not snap.next` 또는 DB 상태로 폴백.

#### F9 — URL 라우팅·상태 영속 없음 → 새로고침 시 지도로 리셋 (A1)
- `App.tsx`가 `useState`로만 뷰 관리(라우터 없음), zustand persist 없음 → 전체 reload(개발 중 vite dep-prebundle reload 포함)마다 cockpit/board/선택 컨텍스트 소실, 지도로 복귀. (관측된 "두 번 마운트"는 StrictMode, "최초 리로드"는 vite dep-optimize — 둘 다 dev 전용; 그러나 수동 새로고침에선 prod에서도 컨텍스트 소실.) 수정: 라우터로 mode/선택 URL 인코딩 또는 zustand `persist`.

#### F12 — 문서: B6 CodeRegion 토글 "partial" 표기가 stale (문서 정확성)
- `docs/user-flows-sequence-diagrams.md:209` 및 568-569가 토글을 "partial/minimal map wiring"으로 표기하나, `ProjectMap.tsx`는 **완전 구현**(토글 시 code_region 노드 5개+touches 엣지 렌더, aria-pressed, B5 트레이스 자동 표출까지). 라이브로 확인됨. → 해당 caveat 삭제하고 구현됨으로 표기.

### 🟠 부가 (관측 기반, F1과 동일 뿌리)

#### F13 — 연결 끊김/오프라인 처리 없음 (A1)
- 백엔드가 잠시 내려간 동안(재시작 갭) 1.5s 폴링이 `net::ERR_CONNECTION_REFUSED` + unhandled `TypeError: Failed to fetch`(`useStore` `load()`에 try/catch 없음)를 매 tick 발생. **UI에 오프라인/끊김 표시 없음** — "live" 배지는 그대로, stale 데이터 유지. ("live"는 실제 연결성과 무관.) 수정: `load()` 에러 처리 + 연결 상태 인디케이터.

---

## 4. 사소한 차이 / 스펙 드리프트 (결함 아님, 문서·라벨 정합)

- **B4 트리거 라벨 불일치:** 다이어그램은 홈의 "+ 목표·티켓"을 말하나 실제는 "새 목표" textarea + "분해 시작". "목표 · 티켓" 버튼은 지도 우상단에 있음(`+`는 아이콘). 또한 같은 프로젝트가 홈에선 `구독 티어 할일앱`(objective.label), 인앱 브레드크럼에선 `구독 할일앱`(data.short) 두 이름으로 표기.
- **C1 트리거 라벨:** 문서 "+ 목표·티켓" ↔ 실제 "목표 · 티켓"(아이콘+텍스트).
- **D3/D4 라벨:** 문서 "수정 요청"↔실제 "수정요청"/"변경 요청 보내기"; 문서 "직접 처리"/"인수"↔실제 "내가 인수".
- **B5 한계:** owning-path 응답에 step(s4)이 있으나 지도는 step을 티켓으로 collapse해 **Step hop이 하이라이트로 안 보임**(objective·ticket·code_region만). 트레이스 placeholder "파일·심볼·UI 요소"는 과대광고 — 실제 필터는 code_region/test 라벨(파일 경로)만 매칭(심볼/UI 인덱스 없음). 시드에 test 노드 없어 'test' 분기 미검증.
- **C2 다이어그램 오해 소지:** "기존 티켓에 대해 재제안"이라 적었으나 실제(real HTTP)는 generic 재제안 + 기존 step 삭제(F8). 기존 step 라벨을 보여주는 건 MockApiClient뿐.
- **키보드 단축키 a/r/t:** 전체 리뷰 패널에 `<kbd>`로 렌더되나 핸들러 없음(문서대로 spec-only).
- **시뮬레이션 표시 한계:** ReviewPane의 DiffView는 빈 patch여도 "NEW"/"새 파일" 하드코딩(s4 patch는 빈 문자열); Tests는 항상 "● green"; Acceptance `met`는 시드값 고정이라 영원히 0/N(전이 메커니즘 없음). E1은 브라우저로 관측 불가(프롬프트 내부), E2는 시드로 UI 트리거 사실상 불가.

---

## 5. 테스트가 남긴 부수효과 (정리 필요)

- `dev.db`에 C1 테스트로 생성된 노드 7개: 티켓 `t-mqz0h4rl`(다크 모드 지원) + step `t-mqz0h4rl-s1..s3` + code_region `cr:generated/step_1..3.ts`. (시드 25노드 → 32노드.) → 정리 권장: 해당 id 삭제 또는 `seed_demo.py` 재시드.
- 테스트용 백엔드/프론트 프로세스(:8099, :5180)는 데모 종료 시 종료.

---

## 6. 우선순위 권고

1. **F1 + F13 (에러 표면화):** 전역 에러 핸들링/토스트 — 리뷰·연결 실패가 무음인 것은 "통제탑"의 신뢰성을 정면으로 해친다. + 시드가 체크포인트를 만들도록 수정(데모 게이트가 실제로 동작해야 함).
2. **F2 (임베딩 토큰화):** 한국어 zero-vector → NaN 500. 한 줄 수정(`\w+`)으로 RAG가 실제로 동작 + 크래시 제거.
3. **F10 (takeover 막다른 길):** 인수 후 진행/완료 경로 — 없으면 프로젝트가 완료·승격 불가.
4. **F5 (위키 경로):** 실제 second-brain 오염 방지(데모/테스트 격리).
5. F3/F6/F11/F4/F9/F12 및 §4 라벨·문서 정합.
