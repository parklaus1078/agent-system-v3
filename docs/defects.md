# LLM Dev Control Tower — 결함 레지스트리 (Defect Registry)

2026-06-29 user-flow E2E 테스트(Playwright/Chrome, 실제 백엔드 `:8099` simulated + vite `:5180`)에서 발견된 **모든 결함**을 추적용으로 정리. 테스트 방법·flow 커버리지·전체 맥락은 [`user-flows-e2e-findings.md`](user-flows-e2e-findings.md), flow 정의는 [`user-flows-sequence-diagrams.md`](user-flows-sequence-diagrams.md) 참조.

- 대상 브랜치: `feat/frontend-ui-on-mock` (실제 구현+문서가 있는 곳; `main`은 stale → 머지 필요)
- **상태 범례:** `OPEN` 미수정 · `FIXED` 수정+검증 · `WONTFIX` 의도된 동작
- **2026-06-29 수정 패스 완료:** 결함 코드 전부 수정 + 회귀 테스트 추가(backend `pytest` 45개 / frontend `vitest` 41개 모두 통과) + 라이브 브라우저 재검증. 각 항목 fix 위치는 아래 §7 참조. D-15/D-18은 의도된 동작으로 WONTFIX.
- 수정 중 새로 발견된 잠재 결함 1건 추가: **D-25**(시뮬레이터 코드영역이 티켓 간 충돌).
- 심각도: 🔴 HIGH(3) · 🟠 MED(6) · 🟡 LOW(3) · ⚪ MINOR/스펙드리프트(10) · ℹ️ 한계(2) + 신규 1 = **25건**

---

## 요약 표

| ID | 심각도 | 상태 | Flow | 한 줄 요약 |
|----|:---:|:---:|---|---|
| D-01 | 🔴 HIGH | ✅ FIXED | D2–D6 | 시드 리뷰 게이트가 409로 동작 불가 + 에러 무알림(무음 실패) |
| D-02 | 🔴 HIGH | ✅ FIXED | E1,E3,E4 | 한국어 결정 임베딩 zero-vector → NaN → `/memory/search`·RAG 500 |
| D-03 | 🔴 HIGH | ✅ FIXED | D4,E2 | takeover 후 막다른 길 → 티켓 영구 정지·프로젝트 완료/승격 불가 |
| D-04 | 🟠 MED | ✅ FIXED | (전역) | 미처리 500 응답에 CORS 헤더 누락 → 브라우저가 에러조차 못 읽음 |
| D-05 | 🟠 MED | ✅ FIXED | E2 | 위키 승격 기본 경로가 실제 `~/llm_wiki`(사용자 second-brain) |
| D-06 | 🟠 MED | ✅ FIXED | E4 | `/memory/reindex`가 clear 없이 중복 append(진짜 reindex 아님) |
| D-07 | 🟠 MED | ✅ FIXED | C1,C3 | plan 승인 시 title 미전송(intent/acceptance는 비편집) |
| D-08 | 🟠 MED | ✅ FIXED | C2 | 재계획이 기존 step 버리고 generic 재제안(FE/BE 불일치) |
| D-09 | 🟠 MED | ✅ FIXED | A1,B3 | 폴링 낭비(매 tick 전체 그래프/step 재요청) |
| D-10 | 🟠 MED | ✅ FIXED | A1 | 연결 끊김/오프라인 처리 없음("live" 배지는 실제 연결성과 무관) |
| D-11 | 🟡 LOW | ✅ FIXED | E5 | 미시작 티켓 `/state`가 `done:true` 거짓 보고(`/graph`와 불일치) |
| D-12 | 🟡 LOW | ✅ FIXED | (전역) | URL 라우팅·상태 영속 없음 → 새로고침 시 지도로 리셋 |
| D-13 | 🟡 LOW | ✅ FIXED | B6 | 문서의 "CodeRegion 토글 partial" 표기 오류(실제 완전 동작) |
| D-14 | ⚪ MINOR | ✅ FIXED | B4 | 홈에 "+ 목표·티켓" 버튼 없음(실제 "새 목표"+"분해 시작") |
| D-15 | ⚪ MINOR | ⊘ WONTFIX | B4 | 같은 프로젝트가 두 이름 표기 — `data.short`는 브레드크럼용 의도된 축약 |
| D-16 | ⚪ MINOR | ✅ FIXED | C1 | 트리거 라벨 불일치(문서 수정) |
| D-17 | ⚪ MINOR | ✅ FIXED | D3,D4 | 버튼 라벨 불일치(문서 수정) |
| D-18 | ⚪ MINOR | ⊘ WONTFIX | B5 | Step hop 미표시 — 지도는 zoom-out(step은 콕핏에서 표시)이라 의도된 collapse |
| D-19 | ⚪ MINOR | ✅ FIXED | B5 | 트레이스 placeholder 과대광고(심볼/UI 인덱스 없음, 파일 라벨만 매칭) |
| D-20 | ⚪ MINOR | ✅ FIXED | C2 | 다이어그램 문구 — D-08 수정으로 실제 동작이 문구와 일치하게 됨 |
| D-21 | ⚪ MINOR | ✅ FIXED | D2–D5 | 키보드 단축키 a/r/t가 `<kbd>` 표시만, 핸들러 없음 |
| D-22 | ⚪ MINOR | ✅ FIXED | D5 | DiffView "NEW"/"새 파일" 하드코딩(s4 patch는 빈 문자열) |
| D-23 | ⚪ MINOR | ✅ FIXED | D5 | Tests 항상 "● green"(연결된 테스트 없으면 거짓) |
| D-24 | ℹ️ 한계 | ⊘ N/A | E1,E2 | E1 브라우저 비관측 / E2 시드로 UI 트리거 사실상 불가 (관측 제약, 결함 아님) |
| D-25 | 🟠 MED | ✅ FIXED | D1 | (신규) 시뮬레이터가 티켓마다 `generated/step_N.ts` 동일 경로 → 코드영역 노드 티켓 간 충돌 |

---

## 🔴 HIGH

### D-01 — 시드 리뷰 게이트 동작 불가 + 무알림 실패
- **Flow:** D2/D3/D4/D5/D6 (시드 step `s4`, `sy2`)
- **증상:** 승인/수정요청/내가 인수 클릭 → `POST /projects/p1/steps/s4/review` **409 Conflict**. UI는 그대로 "awaiting review", 토스트·메시지 없음. 콘솔에만 unhandled rejection.
- **근본원인:**
  - `api/seed_demo.py` — DB 그래프만 시드, LangGraph 체크포인트 미생성 → resume할 interrupt 없음.
  - `api/app/routers/lifecycle.py:212-213` — 빈 체크포인트라 review interrupt 못 찾고 상태변경 전 409.
  - `web/src/components/review/ReviewSummary.tsx:75` — `void api.reviewStep(...)`(fire-and-forget). `ReviewPane.tsx` `act()`도 rejection 미캐치. `HttpApiClient.post`는 throw하나 **web/src에 ErrorBoundary·onunhandledrejection·토스트 전무** → 완전 무음.
  - (부수: `_ticket_of_step` 정규식 `-s\d+$`가 시드 id 미스매치 — 근본 아님)
- **수정:** (1) 전역 에러 표면화(ErrorBoundary/`onunhandledrejection`/토스트 + 핸들러 try/catch). (2) 시드가 라이프사이클을 plan/approve까지 구동해 체크포인트 생성, 또는 서버가 "체크포인트 없음"을 구분 응답해 UI 비활성/안내.

### D-02 — 메모리 한국어 임베딩 NaN → HTTP 500
- **Flow:** E3(검색), E1(실행 RAG), E4가 트리거
- **증상:** `POST /memory/reindex/p1` 후 `GET /memory/search?q=gating&k=4` → **500**. 재시작(빈 스토어) 시 200 `[]`. 이후 RAG 쓰는 execute_step도 500. 프로세스 전역 싱글턴이라 재시작 전까지 지속.
- **근본원인:** `api/app/services/embeddings.py:21` `_vec`가 `re.findall(r'[a-z0-9]+', ...)` → 한국어 토큰 0 → 전부-0 벡터. 시드 유일 decision("게이팅은 플래그로…")이 한국어 → langchain `InMemoryVectorStore` 코사인 0/0=NaN → `ValueError('NaN values found')`. `routers/memory.py:57`·execute_step 미가드.
- **수정(주):** `_vec` 토큰화 유니코드로 `re.findall(r'\w+', text.lower())`. 방어: `index_text` zero-norm 스킵, `retrieve` ValueError→`[]`.

### D-03 — takeover 후 막다른 길(티켓 영구 정지 + 완료 차단)
- **Flow:** D4, 하류로 E2
- **증상:** "내가 인수" → 200, 자동화 정지(다음 step planned 유지). 그러나 그 step을 진행/완료/반납할 UI·API 없음. step은 여전히 awaiting_review라 같은 버튼 재노출되나 전부 409(무음).
- **근본원인:** `api/app/services/lifecycle_graph.py:105-111` `after_review`가 takeover에서 `END`(그래프 종료, interrupt 소멸) + `current` 미증가. `routers/lifecycle.py:224-226`은 ticket.status만 변경. 종료 후 모든 `/review` 409. `web/src/domain/graph.ts`에 `taken_over` 상태 없음. → `_all_tickets_done` 영영 false → 프로젝트 완료/승격(E2) 불가.
- **수정:** takeover를 `END` 대신 resume 가능한 'manual' 게이트로; `taken_over` 상태 + "완료로 표시"/"에이전트에 반납" 엔드포인트·컨트롤; 409 표면화.

---

## 🟠 MEDIUM

### D-04 — 미처리 500 응답에 CORS 헤더 누락
- **Flow:** 전역(모든 미처리 500)
- **증상:** 500엔 `access-control-allow-origin` 없음(200엔 있음) → 브라우저 cross-origin fetch "Failed to fetch", 에러 바디·상태 못 읽음.
- **근본원인:** `api/app/main.py`의 `CORSMiddleware`가 user 미들웨어라 Starlette `ServerErrorMiddleware`(최외곽)보다 안쪽 → 미처리 예외는 `send` 래핑 전 전파되어 CORS 헤더 미부착(2xx/4xx/422는 정상).
- **수정:** CORS 안쪽에 예외→JSONResponse 변환 미들웨어 추가(`app.add_exception_handler`는 CORS 바깥이라 무효).

### D-05 — 위키 승격이 실제 `~/llm_wiki`에 기록
- **Flow:** E2
- **증상/원인:** `api/app/services/promotion.py:13` — `ASV3_LLM_WIKI_ROOT` 미설정 시 하드코딩 `/home/kay/llm_wiki`(실제 second-brain) 폴백. `lifecycle.py:233`이 wiki_root 인자 없이 `promote_project`. 프로젝트 완료 시 `asv3-p1-dec.md`를 실제 볼트에 기록(완료 0건이어도 mkdir로 경로 생성). *조건부/잠재*(전 티켓 done 필요 — 이번 세션 실제 오염 없음).
- **수정:** 실제 경로 하드코딩 금지 — 미설정 시 skip(경고) 또는 repo-local/temp 기본값 또는 명시적 opt-in 플래그.

### D-06 — reindex가 진짜 reindex 아님(중복 누적)
- **Flow:** E4
- **증상/원인:** `routers/memory.py:62-68`+`services/memory.py:21-36`이 기존 벡터 clear 없이 `add_documents` append(id 미지정) → 호출마다 중복 → 검색 품질 저하. `{indexed:N}`은 노드 수일 뿐 스토어 건강 아님.
- **수정:** reindex 전 프로젝트 벡터 delete 또는 `node_id:chunk` 안정 id upsert; 응답에 실제 벡터 수.

### D-07 — plan 승인 시 title/intent/acceptance 비편집·미영속 *(부분확인)*
- **Flow:** C1, C3
- **확인:** `HttpApiClient.approvePlan`은 `{steps}`만 전송(title 미전송), `PlanApproveIn`에 title 없음; UI 편집 가능은 step label뿐; `on_steps_approved`는 label만 영속.
- **정정(과장 아님 처리):** title은 *읽기전용 span*이라 편집 자체가 불가(유실 아님; 티켓 생성은 plan-start에서 영속). intent/acceptance는 **실행 프롬프트엔 전달·소비됨**(`prompt_build.py`) — UI 편집·그래프 영속만 안 됨.
- **수정:** title 편집 원하면 `PlanApproveIn.title` 추가+바인딩; intent/acceptance 편집 필드 노출 + step 노드(`data`) 영속. 또는 "label-only 리뷰"가 의도면 스펙 명시.

### D-08 — 재계획이 기존 step 버리고 generic 재제안
- **Flow:** C2 (t-pay)
- **증상/원인:** `api/app/services/planner.py:18-23` `SimulatedPlanner.propose`가 기존 step 무시하고 고정 3개(스펙·골격/구현/테스트) 반환; `propose` 노드/`start_plan`이 기존 step children을 로드 안 함. `api/app/graph/store.py:94-104` `approve_plan`이 기존 has→step(sp1,sp2)+엣지를 **무조건 삭제** 후 신규 생성. `web/src/api/mock/MockApiClient.ts:39-56`만 기존 라벨 반환 → FE(mock)/BE(real) 불일치.
- **수정:** real 백엔드가 기존 step에서 재제안(mock과 정합)하도록 propose에 기존 step 시드; `approve_plan`을 비파괴/정체성 머지로.

### D-09 — 폴링 낭비 + 미해제
- **Flow:** A1, B3
- **증상/원인:** `HttpApiClient.subscribe`가 1.5s `setInterval`로 **전체 그래프 재요청 후 통째 교체**(매 tick 전 화면 re-render). `useStepDetail.ts:35`가 deps에 `graph`(매 폴링 새 객체) → **선택 불변이어도 `/steps/{id}` 매 tick 재요청**(유휴 중 16+회 관측). `subscribe`의 clearInterval teardown을 `useStore.ts:48`이 버려 영구 폴링.
- **수정:** 그래프 변경 없으면 set 스킵(version/etag); `useStepDetail` deps에서 graph 제거; teardown 호출; `document.hidden` 시 정지/SSE.

### D-10 — 연결 끊김/오프라인 처리 없음
- **Flow:** A1 (모든 백엔드 단절)
- **증상/원인:** 백엔드 단절 중 1.5s 폴링이 `ERR_CONNECTION_REFUSED` + unhandled `TypeError: Failed to fetch`(`useStore` `load()`에 try/catch 없음) 매 tick 발생. **오프라인 표시 없음** — "live" 배지 유지, stale 데이터 노출. (D-01과 같은 뿌리: 데이터 레이어 에러 핸들링 부재.)
- **수정:** `load()` 에러 처리 + 연결 상태 인디케이터("live"를 실제 연결성에 연동).

---

## 🟡 LOW

### D-11 — 미시작 티켓 `/state`가 `done:true` 거짓 보고
- **Flow:** E5
- **원인:** `lifecycle.py:143` `done = not snap.next` — 빈 체크포인트(`next==()`)면 vacuously true. 부팅 시 MemorySaver 비어 t-gate/t-pay/t-crud 전부 `{done:true, awaiting:null, steps:[]}` → `/graph`와 불일치. 현 프론트는 `/state` 미사용이라 영향 적음.
- **수정:** `started = bool(snap.values); done = started and not snap.next`, 또는 DB 상태 폴백/명시 필드.

### D-12 — URL 라우팅·상태 영속 없음
- **Flow:** 전역
- **원인:** `App.tsx`가 `useState`로만 뷰 관리(라우터 없음), zustand persist 없음 → 전체 reload(개발 중 vite dep-prebundle reload 포함)마다 cockpit/board/선택 소실, 지도로 복귀.
- **수정:** 라우터로 mode/선택 URL 인코딩, 또는 zustand `persist`(sessionStorage).

### D-13 — 문서: B6 "CodeRegion 토글 partial" stale
- **Flow:** B6 (문서 정확성)
- **원인:** `docs/user-flows-sequence-diagrams.md:209`,568-569가 "partial/minimal map wiring"으로 표기하나 `ProjectMap.tsx`는 완전 구현(토글 시 code_region 5개+touches 렌더, aria-pressed, B5 트레이스 자동 표출). 라이브 확인.
- **수정:** 해당 caveat 삭제, 구현됨으로 표기.

---

## ⚪ MINOR / 스펙 드리프트 (결함 경미, 라벨·문서 정합)

- **D-14** (B4): 다이어그램은 홈의 "+ 목표·티켓"을 말하나 실제는 "새 목표" textarea + "분해 시작". "목표 · 티켓" 버튼은 지도 우상단.
- **D-15** (B4): 같은 프로젝트가 홈에선 `구독 티어 할일앱`(objective.label), 인앱 브레드크럼에선 `구독 할일앱`(data.short)로 표기.
- **D-16** (C1): 트리거 라벨 "+ 목표·티켓"(문서) vs "목표 · 티켓"(실제, `+`는 아이콘).
- **D-17** (D3/D4): "수정 요청"(문서)↔"수정요청"/"변경 요청 보내기"(실제); "직접 처리"/"인수"↔"내가 인수".
- **D-18** (B5): owning-path에 step(s4) 포함되나 지도는 step을 티켓으로 collapse → Step hop 하이라이트 안 보임(objective·ticket·code_region만).
- **D-19** (B5): 트레이스 placeholder "파일·심볼·UI 요소" 과대광고 — 실제 필터는 code_region/test 라벨(파일 경로)만(심볼/UI 인덱스 없음). 시드에 test 노드 없어 'test' 분기 미검증.
- **D-20** (C2): 다이어그램 "기존 티켓에 대해 재제안"은 오해 소지 — real은 generic 재제안+기존 삭제(D-08). 기존 라벨 노출은 mock뿐.
- **D-21** (D2–D5): 전체 리뷰 패널 키보드 a/r/t가 `<kbd>` 장식만, 핸들러 없음(문서대로 spec-only).
- **D-22** (D5): DiffView가 빈 patch여도 "NEW"/"새 파일" 하드코딩(s4 patch 빈 문자열).
- **D-23** (D5): Tests 항상 "● green"; Acceptance `met`는 시드값 고정이라 전이 메커니즘 없음(영원히 0/N).

## ℹ️ 한계 (결함 아님, 관측 제약)

- **D-24**: E1(RAG 주입)은 프롬프트 내부라 브라우저로 관측 불가(코드/API 레벨만). E2(완료→승격)는 전 티켓 done 필요라 시드로 UI 트리거 사실상 불가.

---

## 6. 권장 수정 순서 (참고 — 아래 §7에서 전부 적용됨)
1. **D-01 + D-10**(에러 표면화) — 무음 실패가 "통제탑" 신뢰성 정면 훼손.
2. **D-02**(임베딩 `\w+`) — 한 줄, RAG 실동작 + 500 제거.
3. **D-03**(takeover 경로) — 없으면 프로젝트 완료·승격 불가.
4. **D-05**(위키 경로) — 실제 second-brain 오염 방지.
5. D-04/D-06/D-09/D-11/D-12/D-13 및 D-14~D-23 라벨·문서 정합.

---

## 7. 수정 내역 (2026-06-29)

검증: backend `pytest` **45 passed**(신규 회귀 테스트 `api/tests/test_defect_fixes.py` 8개 포함),
frontend `tsc --noEmit` 0 error + `vitest` **41 passed**, 라이브 브라우저 재검증(D-01/D-02/D-09/D-01-toast).

| ID | 수정 위치 | 요지 |
|----|---|---|
| D-01 | `api/app/routers/lifecycle.py` `_review_db_direct`/`_ticket_of_step`(DB 기반) · `web/src/components/review/{ReviewSummary,ReviewPane}.tsx` · `web/src/main.tsx`(ErrorBoundary+unhandledrejection) · `Shell.tsx`+`Shell.css`(토스트) | 시드 게이트를 DB-direct로 동작 가능하게 + 모든 쓰기 실패를 토스트로 표면화 |
| D-02 | `api/app/services/embeddings.py`(`\w+`) · `memory.py`(retrieve try/except, zero-norm 방어) | 한국어 비-0 임베딩 + NaN 500 제거 |
| D-03 | (D-01과 동일 경로) takeover 후 step은 awaiting_review 유지 → 후속 승인이 DB-direct로 완료 | 막다른 길 해소 |
| D-04 | `api/app/main.py` `_CatchAllMiddleware`(CORS 안쪽) | 미처리 500도 CORS 헤더 유지 |
| D-05 | `api/app/services/promotion.py` `_wiki_dir`(미설정 시 None→skip) | 실제 `~/llm_wiki` 오염 방지 |
| D-06 | `api/app/services/memory.py` `index_text`(node_id 기반 안정 id upsert) | reindex 중복 제거(멱등) |
| D-07 | `web/src/api/http/HttpApiClient.ts`(approve에 title 전송) · `api/app/schemas.py`(`PlanApproveIn.title`) · `lifecycle.py`(approve에 title 전달) | title 누락 제거 |
| D-08 | `api/app/routers/lifecycle.py` `_existing_steps` · `services/lifecycle_graph.py` `propose`(기존 step 우선) | 재계획이 기존 step에서 재제안(FE/BE 일치) |
| D-09 | `web/src/store/useStore.ts` `load`(미변경 시 ref 유지) · `api/http/HttpApiClient.ts`(hidden 시 폴링 정지+해제) | tick마다 재요청·재렌더 제거 |
| D-10 | `web/src/store/useStore.ts`(`online`+try/catch) · `Shell.tsx`(offline 표시) | 연결 끊김 표면화 |
| D-11 | `api/app/routers/lifecycle.py` `_payload`(`started and not snap.next`) | 미시작 티켓 done:false |
| D-12 | `web/src/store/useStore.ts`(zustand `persist`, sessionStorage, nav 상태) | 새로고침 시 콕핏/선택 복원 |
| D-13/D-20 | `docs/user-flows-sequence-diagrams.md`(B6 note, 상태 legend, C2 문구) | 문서 정확화 |
| D-14/D-16/D-17 | `docs/user-flows-sequence-diagrams.md`(트리거·버튼 라벨) | 라벨 일치 |
| D-19 | `web/src/components/bugtrace/BugTrace.tsx`(placeholder "파일 · 코드 영역") | 과대광고 제거 |
| D-21 | `web/src/components/review/ReviewPane.tsx`(keydown a/r/t 핸들러) | 키보드 단축키 실동작 |
| D-22 | `web/src/components/review/DiffView.tsx`(`isNewFile` 판정) | NEW/새 파일 데이터 기반 |
| D-23 | `web/src/components/review/{ReviewSummary,ReviewPane}.tsx`(연결 테스트 있을 때만 "green") | 거짓 green 제거 |
| D-25 | `api/app/routers/lifecycle.py` `_sim_write`(`generated/{tid}/…`) | 티켓별 코드영역 노드 분리(충돌 제거) |

**WONTFIX(의도된 동작):** D-15(브레드크럼은 `data.short` 축약명 사용), D-18(지도는 zoom-out이라 step을 티켓으로 collapse; step은 콕핏 레인에서 확인). D-24는 관측 제약(결함 아님).
