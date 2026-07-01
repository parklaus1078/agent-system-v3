# 260629 — Bugs found (manual use) + investigation

Kay가 실제로 잠깐 써보며 발견한 버그/불편점 원본 리스트를, 코드 레벨로 검증(근본원인 `file:line`)하고
ultracode 멀티에이전트 조사로 **관련 버그를 추가 탐색**해 보완한 문서. 상태: `OPEN` / `FIXED` / `WONTFIX`.

> 환경 메모: 대부분 **real 모드(`claude -p`) + 실제 백엔드(HttpApiClient)** 에서 재현. mock 모드는
> 다수 버그를 가림(planner 동기 즉시 반환, 고정 ticketId, sampleDiff 등).

---

## A. Kay가 보고한 항목 (원본 → 검증)

원본:
> 1. Rough Idea 새 목표 입력→분해 시작 시 로딩 모달이 분해 중인지 멈춘건지 구분 안됨.
> 2. 분해 중 모달 바깥 클릭하면 꺼지고, 분해 시작 다시 누르면 또 요청.
> 3. ~3번 누르고 새로고침하니 같은 rough idea가 3개 티켓으로 맵에 떠 있음.
> 4. nav 좌측 버튼(랜딩)으로 가도 프로젝트가 안 보임.
> 5. 그 상태에서 새로고침하면 다시 3개 티켓 맵으로.
> 6. duplicate 티켓 하나 "승인하고 실행 시작" 눌러도 아무 일 없어 보임(실제론 시작).
> 7. 지도에 Task가 맵핑되지 않음.
> 8a. ASV3_TARGET_REPO_DIR가 프로젝트별 디렉토리+git init 대신, 그 경로 자체를 git repo로 만듦.
> 8b/9. awaiting review "전체 리뷰"의 git diff view가 렌더링 안 됨(실제 파일은 변경됨).
> 10. 로그가 안 남아 디버깅 불가(claude -p 호출 여부/진행/상태 라이브 업데이트 X → 여러번 클릭).

| ID | 보고# | 심각도 | 상태 | 한 줄 |
|----|:---:|:---:|:---:|---|
| dup-tickets | 2,3,5 | 🔴 HIGH | ✅ FIXED | propose 시점에 티켓 영속 + 호출마다 새 `t-id` → 중복/고아 티켓 |
| orphan-planning-ticket | (3 일반화) | 🔴 HIGH | ✅ FIXED | 분해 1회+취소만 해도 미승인 planning 티켓이 서버에 영구 잔존 |
| home-requires-objective | 4 | 🔴 HIGH | ✅ FIXED | 새 목표가 Objective를 안 만들어 ProjectsHome이 빔(+맵은 보임) |
| empty-diff-patch | 9 | 🔴 HIGH | ✅ FIXED | `step_detail`가 `patch:""` 하드코딩 → diff 뷰 항상 빈 화면 |
| no-claude-logs | 10 | 🔴 HIGH | ✅ FIXED | claude -p 호출/상태 로그 전무 + 로깅 설정 자체가 없어 INFO 누락 |
| executor-failure-swallowed | 10 | 🔴 HIGH | ✅ FIXED | 실행 실패/no-op도 awaiting_review로 조용히 게이트(블록 처리 없음) |
| legacy-target-repo-single-repo | 8a | 🔴 HIGH | ✅ FIXED | `ASV3_TARGET_REPO_DIR`가 프로젝트별 하위폴더 아닌 단일 공유 repo |
| docker-single-repo | 8a | 🔴 HIGH | ✅ FIXED | compose/entrypoint가 단일 repo를 강제(앱 수정 무력화) |
| modal-dismiss-resends | 2 | 🔴 HIGH | ✅ FIXED | 요청 중 backdrop/Esc로 모달 닫힘 → 재요청 |
| plan-loading-no-liveness | 1 | 🟠 MED | ✅ FIXED | 로딩 모달에 스피너/경과/타임아웃 없음 → 멈춤과 구분 불가 |
| approve-no-feedback | 6 | 🟠 MED | ✅ FIXED | 승인 시 스피너/이동/토스트 없음(+real은 동기 블록) |
| refresh-shows-dup-map | 5 | 🟠 MED | ✅ FIXED | 중복 티켓이 영속되어 새로고침 시 재출현(=dup-tickets 의존) |
| steps-not-on-map | 7 | 🟠 MED | ✅ FIXED | step이 맵에 노드로 안 그려짐(티켓으로 collapse) + Legend는 광고 |
| precedence-docs-vs-code | (문서) | 🟠 MED | ✅ FIXED | 문서는 TARGET가 우선이라는데 코드는 WORKSPACE 우선 |
| approve-enabled-on-empty-plan | (신규) | 🟡 LOW | ✅ FIXED | propose 실패 시 빈 plan을 승인 가능 → 409 |
| goalentry-no-submit-guard | (신규) | 🟡 LOW | ✅ FIXED | 분해 시작 더블서밋 가드 없음 |
| diffview-git-header-noise | (신규) | 🟡 LOW | ✅ FIXED | DiffView가 `diff --git`/`index` 헤더를 본문으로 렌더 |
| stepdetail-none-500 | (신규) | 🟡 LOW | ✅ FIXED | 없는 step id로 `GET /steps/{id}` → 500 |
| cross-project-cr-collision | (신규) | 🟠 MED | ✅ FIXED | 전역 `cr:{path}` id가 프로젝트 간 충돌 → 둘째 프로젝트 코드 노드 누락 |
| code-region-shared-stale | (신규) | 🟠 MED | ✅ FIXED | 같은 파일 여러 step 편집 시 공유 cr 노드라 stale diff(→step에 per-step diff 저장으로 해결) |
| empty-objective-to-planner | (신규) | 🟠 MED | ✅ FIXED | fresh DB에서 planner/프롬프트에 빈 objective 전달 |
| stale-build-artifact | (신규) | 🟡 LOW | ✅ FIXED | `api/build/`에 옛 single-repo `_repo_dir()` 사본이 추적됨 |
| touched-code-attribution | 7 | 🟡 LOW | ✅ FIXED | touches 엣지가 ticket으로 collapse돼 어느 step이 만졌는지 소실(steps-on-map과 함께 해결) |
| test/produced-never-created | (신규) | 🟡 LOW | ⊘ WONTFIX→문서 | backend가 test/tested_by/produced를 안 만드는데 Legend/엣지는 광고 |

(상세 근본원인·수정은 §C. 수정 내역 참조.)

---

## B. 핵심 근본원인 묶음

1. **티켓 생명주기**: `start_plan`이 *propose 시점*에 ticket Node를 commit(`lifecycle.py`), `HttpApiClient.proposePlan`이 호출마다 `t-${Date.now()}`를 새로 mint → 재시도·재진입·취소 모두 고아/중복 티켓. Modal이 요청 중에도 backdrop/Esc로 닫힘.
2. **Objective 부재**: UI 새 목표가 Ticket만 만들고 Objective(프로젝트 루트)를 안 만듦. ProjectsHome은 objective에 게이트 → 빈 화면. planner엔 빈 objective 전달.
3. **Diff 유실**: `apply_step_diff`가 diff 파싱 후 **patch 본문을 버림**(code_region 노드 id만 생성), `step_detail`는 `patch:""` 반환 → 리뷰 diff 항상 빈 화면.
4. **관측성 0**: 로깅 설정 부재 + planner/executor `claude -p` 호출 무로그 + 실행 실패를 awaiting_review로 삼킴.
5. **Repo 시맨틱**: `ASV3_TARGET_REPO_DIR`(legacy)가 단일 공유 repo. compose/entrypoint도 이를 강제. 사용자 의도는 "루트 + 프로젝트별 하위 repo".
6. **맵 표현**: step을 노드로 안 그리고 티켓으로 collapse(설계상 zoom-out) → "task가 맵에 없다". Legend는 Step/Test를 광고.
7. **전역 id 충돌**: `cr:{path}`가 프로젝트 비스코프 → 멀티프로젝트에서 코드 노드 누락.

---

## C. 수정 내역 (2026-06-29)

검증: backend **pytest 51 passed**(신규 회귀 테스트 포함), frontend **tsc 0 + vitest 41**, 격리 백엔드 라이브 확인
(3 propose→0 티켓 / approve→티켓1+objective1 / step diff patch 실재 / 404 / INFO 로그).

| ID | 수정 위치 |
|----|---|
| dup-tickets / orphan / refresh | `lifecycle.py` start_plan: propose 시점 티켓 영속 제거(승인 시 `store.approve_plan`이 생성) · `HttpApiClient.proposePlan`/`ApiClient`/`Mock`: 안정 ticketId 수용 · `Shell.tsx`/`ProjectsHome.tsx`: goal당 id 1회 mint + 전달 |
| modal-dismiss-resends | `Modal.tsx`: `dismissable` prop(요청 중 backdrop/Esc 무시) · Shell/ProjectsHome 플랜 모달 `dismissable={false}` · PlanApproval busy 시 취소/✕ disabled |
| plan-loading-no-liveness | `PlanApproval.tsx`: 스피너 + 경과초 + 90s 타임아웃 → 에러 전환 · `PlanApproval.css` 스피너 |
| approve-no-feedback | `PlanApproval.tsx`: 승인 버튼 스피너+"실행을 시작하는 중…" · `Shell.tsx` onApproved → `selectTicket`(신규 티켓으로 이동) |
| approve-enabled-on-empty-plan | `PlanApproval.tsx`: `disabled={busy||error||steps.length===0}` |
| goalentry-no-submit-guard | `GoalEntry.tsx`: `submitted` ref 가드(버튼+Cmd/Ctrl+Enter) |
| home-requires-objective / empty-objective | `store.approve_plan`: objective 없으면 생성(`{pid}-obj`, label=goal) · `lifecycle.py` start_plan: objective 문자열을 goal로 폴백 · approve_plan: 체크포인트의 ticket_title을 objective/ticket 라벨로 사용 · `ProjectsHome.tsx`: `objective||tickets`로 게이트 |
| empty-diff-patch / git-header-noise / shared-stale | `diff_ingest.parse_diff`: per-file `patch` 보존 + 기존 cr 노드 commit 갱신 · `lifecycle.on_step_committed`: step 노드 `data.diff`에 per-file patch 저장 · `store.step_detail`: 저장된 diff 반환 · `DiffView.tsx`: git 헤더 라인 제거 |
| executor-failure-swallowed | `lifecycle_graph.execute_step`: 결과 로깅 + `res.ok` 전달 · `on_step_committed(ok)`: 실패 시 step `blocked` |
| no-claude-logs | `main.py`: `logging.basicConfig` · `planner.py`/`executor.py`: `claude -p` spawn/exit/rc/elapsed 로깅 · `lifecycle.py`: start_plan/approve_plan/review_step 진입 로그 |
| legacy-target-repo / docker-single-repo / precedence | `lifecycle._resolve_repo_path`: legacy를 `{path}/{pid}` per-project로 · `docker-compose.yml`/`docker-entrypoint.sh`/`hostapi`/`.env.example`/`README`: WORKSPACE 기준 + 단일-repo init 제거 + precedence 정정 |
| steps-not-on-map / touched-code-attribution | `nodeTypes.tsx`: `StepNode` 추가/등록 · `ProjectMap.tsx`: "Step 레이어" 토글 → step 노드 렌더 + 하위 행 시프트 + showSteps 시 step collapse 안 함(touches 실제 귀속) · `ProjectMap.css` `.rf-step` |
| stepdetail-none-500 | `store.step_detail`: 노드 없으면 node:None 반환 · `graph.py`: 404 |
| stale-build-artifact | `git rm -r --cached api/build` + `.gitignore`에 `build/` |

### 미적용 (의도/위험 — 문서화)
- **cross-project-cr-collision** (MED): `cr:{path}` 전역 id가 프로젝트 간 충돌. `cr:{pid}:{path}` 네임스페이싱이 정답이나 `test_store`/seed/위키 참조에 파급 + 단일 프로젝트 앱이라 실사용 영향 낮음 + 시뮬레이터는 `generated/{tid}/`로 이미 완화됨. **deferred + 문서화**.
- **test/tested_by/produced-never-created** (LOW): backend가 test/tested_by/produced 엣지를 안 만드는데 Legend/edge style은 광고. `diff_ingest`에 테스트파일 분류를 넣거나 Legend를 트림해야 함. **deferred(데모는 seed/mock에 존재)**.

### 주의 — 기존 데이터
이번 수정은 **앞으로의** 중복/고아 티켓을 막지만, 버그 발생 전 이미 생긴 중복 티켓(예: 라이브 DB의 색상앱 3개)은 그대로 남아 있다. 깨끗이 하려면 해당 DB를 재시드(`seed_demo.py`)하거나 중복 planning 티켓을 수동 삭제. (삭제 엔드포인트는 아직 없음 — 후속 작업.)
