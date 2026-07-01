# CP0 — 거버넌스: Rules 주입 + Model 라우팅

먼저 `docs/cockpit/README.md`(공통 규약)와 `docs/living-cockpit-design.md`의 **"거버넌스" 섹션 + 열린 질문 #6–#9**를 읽어라.

## Goal
모든 AI 호출의 *무엇을(rules)* 과 *누가(brain/model)* 를 사람이 관리하는 두 설정 축을 만든다. 독립적·토대 성격.

## 빌드 (A: Rules)
사람이 작성하는 표준 규칙을, 해당 개입 지점의 프롬프트에 **실제 주입**한다.
- **Coding rules** → `executor` 프롬프트. `api/app/services/prompt_build.py`의 `build_step_prompt`에 RAG 옆
  `# Rules (coding)` 섹션 추가.
- **Planning rules** → `project-planner` + `ticket-planner` 프롬프트(`api/app/services/planner.py`의 각 propose).
  planner가 자체 프롬프트를 만들므로, rules 텍스트를 인자로 주입(예: `propose(..., rules: str = "")`)하거나
  공용 프리픽스 헬퍼로.
- **저장/스코프**: 전역 기본 + 프로젝트별 오버라이드(append/merge). 전역은 파일/DB, 프로젝트별은
  `objective.data.rules = {coding, planning}`. 헬퍼 `resolve_rules(db, pid) -> {coding, planning}`.
- **시드**: `docs/general_coding_rules.md`를 전역 coding-rules 초기값으로 임포트.
- **엔드포인트**: `GET/PUT /projects/{pid}/rules`(+전역). 프론트 **Rules 페이지**(라우트 `/project/:pid/rules` 또는
  설정 영역)에서 coding/planning 텍스트 편집·저장.
- **열린 질문 #7 기본값**: v1은 **전문(full-text) 주입 + 사이즈 가드**(예: 너무 크면 경고/잘라내기). RAG 선별 주입은 후속 TODO로 명시만.

## 빌드 (B: Model 라우팅)
개입 지점별로 엔진을 고르는 라우팅 테이블로, 현 `ASV3_AGENT_MODE`/`ASV3_BRAIN`/하드코딩 모델 + "키 있으면 API" 암묵 분기를 대체.
- **개입 지점**: `project-planner` · `ticket-planner` · `executor` (+ CP2/CP3에서 쓸 `intent-router` · `agent-message-gen` 자리도 테이블에 미리 정의).
- **설정 단위**: 지점 → `{transport, model, ...}`. transport 값: `claude-cli` · `codex-cli` · `anthropic-api` · `openai-api` · `local` · `simulated`.
- **이번에 실제 배선할 transport**: 기존에 동작하는 것 — `claude-cli`(CliPlanner/CliExecutor) · `codex-cli`(CliExecutor brain=codex) · `anthropic-api`(LangChain*) · `simulated`. `openai-api`/`local`은 **어댑터 인터페이스 + "미구성" 표시**까지만(후속 확장점). 무엇을 실제 배선했고 무엇을 stub했는지 로그/문서로 분명히.
- **resolver**: `resolve_engine(point, pid) -> {transport, model}`. `routers/projects.py`와 `lifecycle.py(_build)`가 env 대신 이걸 읽어 planner/executor를 만든다.
- **저장/스코프**: 전역 기본 프로필 + 프로젝트별 오버라이드(`objective.data.models`). **열린 질문 #8 기본값**: API 키는 DB 평문 저장 금지 — env(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`)로 두고 페이지엔 **가용/상태만** 노출.
- **엔드포인트**: `GET/PUT /projects/{pid}/models`(+전역) + `GET /models/available`(transport별 health: 키/CLI 존재 확인). 프론트 **Models 페이지**: 지점×엔진 표, 지점별 선택 + health/test 버튼.

## 결정/기본값 요약
- per-ticket 스코프(#6)는 v1 제외 — global + project만.
- 새 AI 호출 없음(라우터는 CP3) — 이번엔 *기존* planner/executor 배선만 라우팅화 + rules 주입.

## 깨지 마라
- `ASV3_AGENT_MODE=simulated` 경로(키·네트워크 없이 동작) 유지 — `simulated`를 transport의 한 값으로 흡수하되 기존 시뮬 동작 보존.
- 기존 planner/executor 시그니처를 바꾸면 `lifecycle.py`/`projects.py`/관련 테스트도 같이 갱신. 기존 백엔드 테스트 그린 유지.

## Done when
- 전역+프로젝트 rules가 실제로 executor/planner 프롬프트에 주입됨(테스트: rules 텍스트가 빌드된 프롬프트에 포함되는지; `resolve_rules` 병합 단위 테스트).
- model 라우팅 테이블로 지점별 엔진이 선택되고 `_build`/`plan_project`가 그 값을 사용(테스트: resolver가 전역/프로젝트 오버라이드를 정확히 해석; 잘못된 transport는 안전 폴백/에러).
- Rules·Models 페이지에서 보기·편집·저장이 동작(vitest + tsc 그린). 백엔드 pytest 그린.
- spec 진행 로그에 "CP0 완료 + 실제 배선/ stub 범위" 기록.

## Out of scope (다른 CP)
intent-router 실제 호출(CP3) · agent-message-gen 실제 생성(CP2) · throttle(CP1) · per-ticket 스코프(후속).
