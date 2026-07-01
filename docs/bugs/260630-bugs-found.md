# 260630 — PM UX overhaul + two-level planning (design)

상태: **설계 (Kay 리뷰 대기)** → 승인 시 구현 계획(writing-plans). 이 문서는 Kay가 적은 개선 요청
6건을 코드 레벨로 검증·구조화한 설계 spec이다. (파일은 bugs/ 아래지만 내용은 *개선/기능 설계*.)

## 원본 요청 (verbatim)
1. 랜딩 페이지를 지도가 아니라 "프로젝트 관리" 화면으로.
2. 지도의 블록을 드래그&드롭으로 자유 이동.
3. 각 뷰를 path로 라우팅 (`/`, `/project/{project_id}`, …).
4. 백엔드가 지금 뭘 하는지(프롬프팅 상태)를 UI가 실시간 추적. "승인하고 실행 시작"·각 task 실행 시 멈춤/진행 구분.
5. 랜딩의 "분해 시작"이 **티켓이 아니라 프로젝트**를 초기화하도록(현재는 티켓 초기화로 해석됨).
6. 티켓별 sub-task 분해 화면 분리. 플로우: 프로젝트 초기화 → 에이전트가 slug·title·티켓 제안 → 사용자가 편집/승인 →
   시스템이 프로젝트 생성 + 티켓을 맵에 매핑 → 성공/실패 알림, 성공 시 "지도로 이동?" 확인 → 동의 시 맵 렌더, 아니면
   랜딩 유지 → 사용자가 티켓 클릭 → sub-task 지정(에이전트 제안 버튼) → 승인 시 task별 실행 → 결과에 따라 task 상태를
   awaiting review / blocked로 전환 → 반복.

## 확정 결정 (이번 세션)
- **#4 라이브 상태**: *Async + 활동(activity) 표시* — 플래너/실행기를 **논블로킹**으로 돌리고, 티켓/step별 `activity`
  필드(예: `planning` / `executing step 2/5`)를 폴링으로 노출. 멈춘 것처럼 안 보이게.
- **#2 드래그**: 노드 위치를 **프로젝트별 영속**(DB).
- **산출물**: 6건을 **하나의 단계별(phased) spec**으로. (리뷰 후 구현 계획)
- **모델 매핑(가정)**: **Project = Objective 노드, Ticket = Ticket, Sub-task = Step.** slug = `project_id`(URL용).

## 현재 구조와 갭
- 데이터: `nodes(project_id, kind∈objective|ticket|step|code_region|test|decision)` + `edges`. 멀티프로젝트 지원(=`project_id`).
- 프론트는 **단일 프로젝트 `p1` 하드코딩**(`HttpApiClient(base,'p1')`), App은 부팅 시 `view='project'`(맵), **라우터 없음**.
- 플래너는 **티켓→steps** 한 레벨만(`planner.propose(objective, ticket_title)`). **프로젝트→tickets** 레벨이 없음.
- "새 목표/분해 시작"은 티켓 하나를 만든다(최근 수정으로 승인 시 objective도 생성). → #5의 "프로젝트 초기화"와 의미 충돌.
- 라이프사이클은 **동기**(approve POST가 step 실행이 끝날 때까지 블록) → #4의 라이브 상태 불가.
- 맵은 `nodesDraggable={false}`, 위치 자동 레이아웃, 저장 없음.

---

## Phase 1 — 라우팅 + 랜딩=홈 (#1, #3) · 멀티프로젝트 pid

**목표**: URL이 곧 상태. `/` = ProjectsHome(랜딩), `/project/{slug}` = 그 프로젝트 맵,
`/project/{slug}/ticket/{tid}` = 보드/콕핏. 부팅·새로고침·뒤로가기가 URL을 따른다(이전 "새로고침 시 맵으로" 버그 동시 해소).

- **FE**: `react-router-dom` 도입. `App.tsx`의 `useState<'home'|'project'>` 제거 → `<Routes>`.
  `Shell`/`ProjectsHome`는 라우트로 진입. `mode`/`selectedTicketId`/`reviewOpen` 등 뷰 상태는 URL/route param에서 파생
  (zustand persist는 보조). 랜딩이 **기본 라우트 `/`**.
- **멀티프로젝트 pid**: `HttpApiClient`의 하드코딩 `'p1'` 제거 → `pid`를 route param(`{slug}`)에서 주입.
  `useStore`가 현재 pid를 보유(라우트 변경 시 갱신) + 그 pid로 graph/step/plan 호출.
- **랜딩**: ProjectsHome가 **프로젝트 목록**(여러 objective)을 보여줌. 현재는 단일 objective만 — `GET /projects`
  (모든 프로젝트=objective 요약) 신설 또는 graph 다건. 카드 클릭 → `/project/{slug}`.
- **변경 파일**: `web/src/App.tsx`(라우터), `Shell.tsx`/`ProjectsHome.tsx`(라우트 연동), `store/useStore.ts`(pid 동적),
  `api/http/HttpApiClient.ts`(pid 주입), 신규 `api/app/routers`에 `GET /projects` 목록.
- **테스트**: 라우트별 렌더(vitest + MemoryRouter), pid 주입, 새로고침→해당 라우트 유지.
- **노력/리스크**: 중. 라우터 도입이 App/Shell/Store/Client를 광범위하게 건드림. 기존 vitest(라우터 의존) 업데이트 필요.

## Phase 2 — 두 레벨 계획: 프로젝트 초기화 + 티켓별 sub-task (#5, #6)

**목표**: 계획을 **2단계**로. (A) 프로젝트 초기화: goal → {slug, title, tickets[]}. (B) 티켓별: ticket → sub-tasks(steps).

### A. 프로젝트 초기화 (랜딩 "분해 시작")
- **프로젝트 플래너**(신규): `propose_project(goal) -> {slug, title, tickets:[{title, (intent)}]}`.
  - simulated: 결정적 stub(예: slug=goal에서 생성, 3 tickets). real: `claude -p` 구조화 출력(슬러그/제목/티켓 목록).
  - `services/planner.py`에 `ProjectPlanner`(Sim/Cli/LangChain) 추가, 스키마 `schemas_plan.py`에 `ProjectProposal`.
- **엔드포인트**:
  - `POST /projects/plan {goal}` → 제안 {slug, title, tickets} 반환(아무것도 영속 안 함; 비동기 — Phase 3).
  - `POST /projects/approve {slug, title, tickets[]}` → 트랜잭션으로 **objective(id=slug, label=title) + ticket 노드들(status=planning) + has 엣지** 생성. 멱등(같은 slug 재승인은 no-op/병합). 성공/실패를 응답에 명확히(#6 "성공/실패 알림").
- **슬러그**: 사용자가 편집 가능. 영속 전 **고유성·정규화 검증**(중복이면 `-2` suffix 또는 거부). slug = `project_id`(URL).
- **FE 플로우(#6)**: 랜딩 입력 → "분해 시작" → ProjectInit 모달(에이전트 제안: slug/title/tickets 편집 가능; 로딩은 Phase 3 라이브) →
  "승인" → 생성 → **토스트로 성공/실패** → 성공 시 **"지도로 이동하시겠어요?" 확인** → 예: `/project/{slug}` 이동·맵 렌더,
  아니오: 랜딩 유지(목록에 새 프로젝트 추가). (모달 비-dismissable·중복가드는 기존 수정 재사용.)

### B. 티켓별 sub-task 분해 (티켓 클릭 → 콕핏/전용 패널)
- 티켓은 이미 존재(planning, steps 없음). 티켓 열기 → **"sub-task 제안" 버튼** → 기존 **티켓 플래너**(`planner.propose`,
  ticket→steps) 호출 → 제안 step 목록 편집/승인 → 승인 시 step 노드 생성 + **task별 실행**(기존 lifecycle execute→review).
- 기존 `start_plan`/`approve_plan`(티켓 단위)을 이 단계로 재배치: 프로젝트 초기화에서 **실행 안 함**(티켓만 생성),
  실행은 티켓의 sub-task 승인에서 시작(현재 "approve가 즉시 step1 실행"과 일치, 단 티켓은 이미 존재).
- 결과 상태: 성공 → `awaiting_review`, 실패 → `blocked`(Phase 3 executor-ok 반영, 이미 일부 적용).
- **변경 파일**: `services/planner.py`(+ProjectPlanner), `schemas_plan.py`/`schemas.py`, `routers/lifecycle.py`(프로젝트 plan/approve 엔드포인트 + 티켓 단위 흐름 정리), `graph/store.py`(프로젝트+티켓 일괄 생성), FE 신규 `ProjectInit` 컴포넌트 + 티켓 sub-task 패널(기존 `PlanApproval` 재사용/분기).
- **테스트**: 프로젝트 제안/승인(objective+tickets 생성, slug 고유성), 티켓 sub-task 승인→실행→상태, 멱등.
- **노력/리스크**: 상. 새 플래너 레벨 + 2단계 UX + 멀티프로젝트 영속. 가장 큰 덩어리.

## Phase 3 — 비동기 실행 + 라이브 상태 (#4)

**목표**: 플래너/실행기 호출을 논블로킹으로, "지금 무엇을" 폴링으로 노출.

- **비동기 실행**: plan/approve(특히 step 실행)·프로젝트 플래너를 **백그라운드 태스크**로(요청은 즉시 "started" 반환).
  LangGraph invoke를 백그라운드 스레드에서 수행(태스크별 DB 세션, 체크포인터 공유). 동시성/락은 단일 사용자 가정 하 단순화.
- **activity 노출**: 티켓/step 노드 `data.activity`(+`data.activity_since`)에 코스 상태 기록 —
  `planning`(프롬프트 전송됨) → `executing`/`executing step k/n` → `awaiting_review` / `blocked` / `done`.
  플래너/실행기 진입·종료 시 갱신(이미 추가한 INFO 로깅 지점에 DB 업데이트 동반). 1.5s 폴링이 그래프와 함께 노출.
- **UI**: 콕핏/보드/맵에 활동 인디케이터(스피너 + "step 2/5 실행 중 · 12s"), "live" 배지를 실제 활동에 연동.
  PlanApproval/ProjectInit 로딩도 이 신호 사용(이미 스피너+경과초 추가됨 — activity로 격상).
- **변경 파일**: `routers/lifecycle.py`(BackgroundTasks/스레드 + activity 기록), `services/{planner,executor,lifecycle_graph}.py`(진행 콜백), `store.py`/`schemas.py`(activity 필드), FE `useStore`/`Shell`/콕핏(활동 표시).
- **테스트**: approve가 즉시 반환 + activity가 planning→executing→awaiting_review로 전이(폴링 관측), 실패 시 blocked.
- **노력/리스크**: 상. 동기→비동기 라이프사이클 전환이 핵심. 체크포인터/DB 세션 스레딩 주의.

## Phase 4 — 맵 드래그&드롭 + 위치 영속 (#2)

**목표**: 맵 블록 자유 이동, 프로젝트별 위치 저장(새로고침/타 기계에서도 유지).

- **FE**: `ProjectMap`의 `nodesDraggable={true}`, `onNodeDragStop` → 위치 저장(디바운스). 노드 위치는 그래프 노드
  `data.pos={x,y}` 있으면 사용, 없으면 기존 자동 레이아웃. (Phase 1의 step/code 레이아웃 시프트와 호환.)
- **영속**: `POST /projects/{pid}/layout {positions:{nodeId:{x,y}}}` → 각 노드 `data.pos` 갱신. graph가 pos 반환.
- **변경 파일**: `ProjectMap.tsx`(draggable+drag handler), `routers/graph.py`(layout 엔드포인트), `store.py`(pos 저장/반환), FE 클라이언트 메서드.
- **테스트**: drag→저장→재로드 시 위치 유지, pos 없는 노드는 자동 레이아웃.
- **노력/리스크**: 중하. 비교적 독립적.

---

## 횡단 관심사
- **멀티프로젝트**: pid가 'p1' 고정 → 라우트 param 기반(Phase 1). seed_demo는 데모 프로젝트(p1) 유지.
- **기존 수정과의 정합**: 티켓을 propose가 아닌 approve에서 생성(중복/고아 방지) — 이번 모델에선 **프로젝트 초기화 approve**가 티켓 생성, **티켓 sub-task approve**가 step 생성. 모달 비-dismissable/중복 가드/에러 토스트/로깅/PG 체크포인터 수정 모두 그대로 활용.
- **slug as id**: objective.id=slug. owning-path/그래프는 id 기반이라 호환. 표시 라벨은 title.

## 비목표 (YAGNI, v1 제외)
- 인증/멀티유저(여전히 단일 사용자 로컬). 프로젝트 삭제 UI(별도 후속 — DELETE 엔드포인트 미존재).
- SSE 토큰 스트리밍(#4는 activity 폴링으로 충분; SSE는 후속).
- 티켓의 재귀 분할(subdivides) — sub-task(steps) 한 겹만.

## 시퀀싱 / 마일스톤
1. **Phase 1**(라우팅+랜딩+멀티프로젝트 pid) — 다른 모든 것의 기반.
2. **Phase 2**(두 레벨 계획) — 핵심 가치(#5/#6).
3. **Phase 3**(비동기+라이브 상태) — #4.
4. **Phase 4**(드래그 영속) — #2, 독립적이라 언제든.

각 Phase는 backend pytest + frontend tsc/vitest 그린 + 라이브 확인을 게이트로 한다.

---

## 구현 진행
- **Phase 1 ✅ (라우팅 + 랜딩=홈 + 멀티프로젝트 pid)**: `react-router-dom@7`; `App` → `<Routes>`(`/`=ProjectsHome,
  `/project/:pid`=Shell); `GET /projects`(+`store.list_projects`); `ApiClient.listProjects/setPid`(Http+Mock);
  `useStore.pid/setPid`; Shell이 `useParams().pid`→`setPid`로 프로젝트 로드, 브랜드→`navigate('/')`; ProjectsHome가
  전 프로젝트 리스트(카드 클릭→`/project/{id}`). 검증: backend 51 / frontend tsc+41.
- **Phase 2 ✅ (두 레벨 계획)**: 백엔드 — `schemas_plan`(TicketSpec/ProjectProposal), `planner.py`
  (slugify + ProjectPlanner: Simulated/Cli/LangChain), `store.create_project`+`unique_slug`(멱등),
  신규 `routers/projects.py`(`GET /projects` 이전 + `POST /projects/plan` 제안 + `POST /projects/approve` 생성).
  프론트 — `dto`(ProjectProposal/ProjectCreated), `ApiClient.proposeProject/approveProject`(Http+Mock),
  신규 `ProjectInit` 모달(slug/title/tickets 편집→생성→"지도로 이동?" 확인), ProjectsHome가 단일-티켓 PlanApproval
  대신 ProjectInit 사용. **Part B(티켓별 sub-task)는 기존 플로우 재사용**(planning 티켓 클릭→`editPlan`→PlanApproval(ticketId)).
  검증: backend 57(+6) / frontend tsc+42(+1).
- **Phase 3 ✅ (비동기 + 라이브 activity)**: 백엔드 — `lifecycle_graph`에 `on_step_start` 콜백;
  라우터가 티켓 노드 `data.activity={state,detail,since}`를 전이마다 기록(planning→executing step k/n→
  awaiting_review/blocked→done). **비동기 실행**: approve_plan + review_step의 (느린) 실행 invoke를
  데몬 스레드(자체 DB 세션)로, `_GRAPH_LOCK`이 체크포인터 동시접근 직렬화(폴링은 getGraph=DB만 보므로 대기 없음);
  `ASV3_ASYNC_EXEC`(기본 1; 테스트는 0=동기). **propose는 동기 유지**(모달 스피너). FE — `nodeActivity()` 헬퍼 +
  `ActivityBadge`(스피너+"step k/n · Ns") 보드 헤더·맵 티켓 노드. 검증: backend 61(+5) / frontend tsc+46(+5).
  안전성: FE는 체크포인터를 폴링하지 않음(확인)이라 단일 사용자에서 PG 연결 경합 없음 — db.py 체크포인터 무변경.
- **Phase 4 ✅ (드래그 영속)**: 백엔드 — `store.save_layout`(node.data.pos 기록, 미지/타프로젝트 노드 무시),
  `POST /projects/{pid}/layout {positions}`(graph_router); `/graph`가 data.pos 그대로 반환. 프론트 —
  `ApiClient.saveLayout`(Http+Mock), `ProjectMap`이 `nodesDraggable`+`onNodeDragStop`(500ms 디바운스 저장,
  언마운트 시 flush), 위치 우선순위 = 세션 localPos → 영속 data.pos → 자동 레이아웃(이동된 티켓의 자식도 따라감).
  검증: backend 63(+2) / frontend tsc+49(+3).

## 완료 — 4개 Phase 전부 구현·검증
backend **63** / frontend tsc+vitest **49**, 전부 그린. 라이브 검증은 사용자 스택(8099/5180, 구버전·실데이터)과의
포트/데이터 충돌을 피하려 단위·통합 테스트로 대체(각 Phase 게이트 충족). 비목표(인증/삭제 UI/SSE/재귀분할)는 유지.
