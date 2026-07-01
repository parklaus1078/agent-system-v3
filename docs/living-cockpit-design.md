# Living Cockpit — 대화형 조종석 (design)

상태: **설계 (Kay 리뷰 대기)** → 승인 시 구현 계획(writing-plans). 기존 Plan 1–4 + 260630/night-bug
수정 위에 얹는 인터랙션 모델 재설계. 코드 변경 전 단계.

## 문제 (왜 이 설계인가)
현재 시스템은 **세 개의 단방향 게이트**(① 프로젝트 분해 승인 ② 티켓별 step 계획 승인 ③ step별 리뷰)로만
사람이 관여한다. 전부 "에이전트 제안 → 사람 승인"이고, 계획은 승인 순간 **얼어붙고** 이후엔 실행만 흐른다.
→ "상호작용"이 아니라 "결재". 사람이 계획에 개입하는 실질 지점은 ②(티켓 sub-task) 하나뿐.

목표: **Agile 프로덕트 개발에서 기존 티켓 도구(Jira/Linear) 대비 유의미한 워크플로 개선.**

## 확정 결정 (Kay)
1. **테제 — Living cockpit**: 사람이 자율 에이전트를 *살아있는 인과 지도* 위에서 실시간 조종. 고정 게이트가
   아니라 "언제든 개입".
2. **자율도 — Throttle**: 전역/티켓별 다이얼 (auto-pilot ↔ co-pilot ↔ per-step). 신뢰가 쌓일수록 위임을
   늘리는 Agile식 점진 위임.
3. **조종 표면 — 대화 채널이 주, 지도는 live 뷰/진실의 원천**. 카드를 손으로 갱신하지 않는다 — 대화하면
   provenance 붙은 구조가 저절로 쌓인다.
4. **엔진 — Intent-routed**: 자유 NL 입력을 *고정된 그래프 연산 vocabulary*로 라우팅(예측·감사 가능,
   지도가 진실). 에이전트 출력도 타입 있는 구조화 메시지.

제품 한 줄: **"살아있는 인과 지도를 앞에 두고 에이전트와 나누는 대화."**
(Cursor류 = 코드 짜주는 챗도 아니고, Jira류 = 손으로 채우는 보드도 아님.)

## 인터랙션 모델

### 한 사이클
에이전트가 throttle만큼 자율 진행 → 채널에 narrate + 지도에 live 반영 → 결정/모호/위험 지점에서(throttle에
따라) 채널에 *질문하고 정지/진행* → 사람이 언제든 steer 메시지 → intent router가 그래프 연산으로 변환 →
영향 subtree 재계획/갱신 → 계속.

### Steer 어휘 (사람 → 에이전트, intent-routed)
자유 NL → {연산, 대상 scope}로 라우팅. 모든 연산은 구조화되어 노드 이력에 남아 **감사 가능**.

| 의도 | 효과 |
|---|---|
| `redirect` | "결제는 Stripe로" → 해당 ticket/step 재계획 (plan diff 제시 후 진행) |
| `constrain`(pin) | "auth는 건드리지 마" → decision/constraint 노드 부착, 하위로 전파 (RAG가 이미 step 프롬프트에 주입) |
| `reprioritize` | "결제 먼저" → 백로그 재정렬, 다음 실행 선택 변경 |
| `scope` | "다국어도" → 새 ticket 생성 (emergent scope) |
| `query`/why | "왜 이렇게 했어?" → 인과 그래프 + decision으로 답 (read-only) |
| `answer` | 에이전트 질문에 답 → 막힌 노드 unblock |
| `control` | pause / resume / throttle 변경 |

### 에이전트 → 사람 (타입 있는 메시지) — "진짜 개입"의 심장
- `assumption` — "Stripe로 가정" (co-pilot: 확인 정지 / auto: 진행하며 알림 → 사후 수정 가능)
- `blocked` — "스키마 충돌 — (a)…/(b)… 어느 쪽?" (선택지 제시)
- `decision` — "X로 결정(이유…)" → 지도 decision 노드로 박힘
- `review` — 기존 step 리뷰 게이트가 이 채널 메시지로 승격
→ 단방향 결재가 **양방향 대화**로 전환.

### Throttle 의미
- **auto-pilot**: 멈추지 않음. `assumption`/`decision`만 알림(사후 수정 가능).
- **co-pilot**: 되돌리기 어렵거나(외부 영향·스키마 변경) 큰 결정·모호 지점에서만 정지·질문.
- **per-step**: 매 step 리뷰(= 오늘 동작).
프로젝트/티켓별로 다이얼. 신뢰가 쌓이면 올린다.

### 예시 한 컷
```
🤖 step 2/4 실행 중…  assumption: 결제는 Stripe로 갈게요.
🧑 아니, Paddle로. 그리고 auth는 손대지 마.
🤖 redirect → ticket "결제" 재계획(steps 2개 교체, diff↓)
   constraint → "auth 불가" pin (하위 전파). 계속할게요 ▶
```

## 레이아웃 (초안 — 시각 목업으로 더 다듬을 수 있음)
```
┌───────────────────────────────────────────────────────────────┐
│ Control Tower · {프로젝트}     [자율도: 부조종 ▼]   live ⏱  ✎  │  topbar: throttle 다이얼 + activity
├──────────────────────────────────────────┬────────────────────┤
│                                            │  대화 채널          │
│         살아있는 인과 지도 (live)           │  🤖 assumption …    │
│   objective → ticket → step → code         │  🧑 …               │
│   (실행 중 노드 activity, decision pin)     │  🤖 blocked (a)(b)  │
│   ← 노드 클릭 시 채널이 그 노드 thread로 필터 │  ───────────────    │
│                                            │  > 무엇이든 지시…    │  ← 상시 입력(steer)
└──────────────────────────────────────────┴────────────────────┘
```
- 지도 ↔ 채널은 **한 상태의 두 뷰**: 채널 메시지는 노드 chip을 참조하고, 메시지에 작용하면 해당 노드가
  하이라이트/갱신. 노드 클릭 → 채널이 그 노드의 thread로 필터.

## 아키텍처 — 기존 자산 위에 얹기 (갈아엎지 않음)
재사용:
- **async 실행 + `data.activity`**(Phase 3): 자율 루프의 절반(에이전트가 스스로 굴러가며 진행 노출).
- **`decision` 노드 + RAG 주입**: `constrain` 전파가 이미 구현됨(step 프롬프트에 결정/제약 주입).
- **리뷰 게이트 / takeover**: `review` 채널 메시지로 승격(로직 재사용).
- **revision/ETag 폴링**(night-bug #4): 채널/지도 live 갱신의 저비용 전송(추후 SSE로 격상 가능).

신규 컴포넌트:
1. **채널 + intent-router 엔드포인트**: `POST /projects/{pid}/steer {text}` → LLM이 {op, scope, args}로
   분류 → 해당 그래프 연산 실행 → 결과를 채널 메시지로 append. 채널 메시지는 신규 테이블 또는 노드
   (`kind="message"`) — *데이터 모델 결정 필요(아래 열린 질문)*.
2. **자율 진행 루프**: step→step 자동 진행(오늘의 "매 step 정지" 제거), throttle 정책이 정지/질문 지점 결정.
   기존 lifecycle_graph의 review 인터럽트를 throttle 조건부로.
3. **steer 적용기**: redirect → 영향 ticket/step 재계획 + plan diff; constrain → decision 노드 + 전파;
   reprioritize → 백로그 순서(노드 `data.order` 또는 별도 우선순위); scope → 신규 ticket.
4. **채널↔지도 양방향**: 메시지의 노드 참조(ids) + 지도 노드 클릭→채널 필터.

데이터 모델 추가(잠정): 채널 메시지(type, author, text, refs[], ts), 노드 `data.order`(우선순위),
`constraint`(= decision 노드 재사용 가능), throttle 설정(objective.data.autonomy / ticket.data.autonomy).

## 거버넌스 — 규칙(Rules) & 모델 라우팅 (Kay 리뷰 추가)
라이브 조종(steer/throttle)과 **별개의 "설정" 축**: 모든 AI 호출이 *어떻게 동작할지*를 사람이 관리하는 페이지들.
둘 다 기본 **전역 기본값 + 프로젝트별 오버라이드**(per-ticket 오버라이드는 후속 — 열린 질문 #6).

### A. Rules 페이지 — 에이전트가 따르는 규칙 관리
- **Coding rules** (→ `executor` 프롬프트): `docs/general_coding_rules.md`(DRY/KISS/YAGNI/SOLID/가독성/…) 같은
  코딩 원칙. **현재 이 파일은 정적이고 어디에도 자동 주입되지 않음** → 이 페이지가 *관리 + 실제 주입*을 담당.
- **Planning rules** (→ `project-planner` + `ticket-planner` 프롬프트): 분해 규칙 — 티켓 크기, "좋은 step"의 기준,
  수용기준 컨벤션, "한 step = 한 커밋 = 독립 리뷰 가능" 등. 프로젝트/티켓 세분화 품질을 사람이 통제.
- **저장/스코프**: 마크다운 텍스트(편집·버전). 전역 기본 + 프로젝트별 오버라이드(append/merge). 전역은 파일/DB,
  프로젝트별은 `objective.data.rules` 또는 별도 rules 엔티티.
- **주입**: `services/prompt_build.py`에서 RAG 컨텍스트와 *나란히* "# Rules" 섹션으로 추가. 코딩룰→executor 프롬프트,
  플래닝룰→planner 프롬프트.
- **decisions/`constrain`과의 구분**: decisions = *창발적·핀된* 제약(에이전트/사람이 작업 중 박음); rules = *상시·사람이
  작성한* 컨벤션. 둘 다 프롬프트로 흘러가되 출처·수명이 다름.
- **시드**: 현 `general_coding_rules.md`를 전역 coding-rules 초기값으로 임포트.

### B. Model routing 페이지 — 개입 지점별 brain/모델
- **개입 지점(intervention points)별**로 엔진을 선택·설정. 지점 목록:
  `project-planner` · `ticket-planner` · `executor` · (신규) `intent-router`(steer 분류) · `agent-message-gen`
  (assumption/blocked/decision 문구 생성) · (선택) `review-summarizer`.
- 각 지점 → **{provider·transport, model, settings}**. transport 후보:
  **claude CLI · codex CLI · Anthropic API · OpenAI/codex API · local(OpenAI 호환 / ollama) · simulated(결정적, 오프라인·테스트)**.
- **현 상태 일반화**: 지금은 `ASV3_AGENT_MODE`(sim|real) + `ASV3_BRAIN`(claude|codex) + 하드코딩 `claude-opus-4-8`이
  전역 한 곳에만 있고 "API 키 있으면 API 아니면 CLI" 같은 암묵 분기가 박혀 있음 → 이를 **명시적 라우팅 테이블**로 대체.
  `routers/projects.py`·`lifecycle.py(_build)`가 env 대신 이 설정을 읽어 brain/model 주입(신규 지점도 동일 테이블에서).
- **스코프**: 전역 기본 프로필 + 프로젝트별 오버라이드. 지점별 **health/test 버튼**(키·CLI 가용성 확인).
- **비밀키**: API 키 등은 별도 안전 저장(열린 질문 #8) — 페이지엔 선택/상태만 노출.

### 둘의 관계
**Model routing = *누가*(어느 brain) 호출하나, Rules = *무엇을*(어떤 컨벤션) 주입하나.** 함께 모든 AI 호출의 동작을
사람이 통제 — 조종석의 "운전(steer)" 옆에 놓인 "정비/세팅" 축. (steer로 즉흥 지시, rules/model로 상시 정책.)

## 데이터 흐름 (steer 한 번)
`사람 입력 → /steer → intent 분류(op, scope) → 그래프 트랜잭션(노드/엣지 변경 + 이력) → revision bump →
채널 메시지 append → 폴링이 지도+채널 갱신 → (필요시) 자율 루프가 영향 step 재실행`

## 에러/엣지
- intent 분류 실패/모호 → 에이전트가 `clarify` 메시지로 되물음(추측 금지). 
- 동시 steer vs 실행: night-bug #3의 per-project 실행 락 위에서 — steer(읽기/계획)는 락-프리, 실행만 직렬화.
- 미검토 커밋 리스크(auto-pilot): 모든 커밋은 step 단위 + git 이력 + 사후 리뷰/되돌리기 가능으로 완화.

## 테스트 전략
- intent 라우팅: NL 샘플 → 기대 op/scope (분류 단위 테스트).
- steer 효과: redirect→steps 교체, constrain→decision+전파, reprioritize→순서, scope→ticket 생성.
- 자율 루프 + throttle: auto는 안 멈춤(폴링 관측), co-pilot은 위험 지점에서 정지, per-step은 오늘과 동일.
- 채널↔지도 일관성, 동시성(steer 중 실행) 회귀.
- 프론트: 채널 렌더/입력, 노드 클릭→필터, throttle 다이얼, plan diff 표시.

## 단계별 롤아웃 (제안)
- **CP0 — 거버넌스(Rules 주입 + Model routing)**: 독립적이고 토대 성격이라 먼저 가도 좋음. coding/planning rules를
  `prompt_build`/planner에 주입(general_coding_rules 시드) + 개입 지점별 model 라우팅 테이블로 env 분기 대체.
- **CP1 — 자율 진행 루프 + throttle(전역)**: 오늘의 게이트를 throttle 정책으로. (가장 큰 토대)
- **CP2 — 채널 + 에이전트→사람 구조화 메시지**: assumption/blocked/decision/review를 채널로. (양방향)
- **CP3 — Steer(intent-router) 핵심 연산**: redirect/constrain/answer/control. (사람→에이전트)
- **CP4 — reprioritize/scope + 채널↔지도 양방향 + 티켓별 throttle**: 백로그·창발 범위·정밀 조종.
각 CP는 backend pytest + tsc/vitest 그린 + 라이브 확인을 게이트로.

## 비목표 (v1 제외)
멀티유저 동시 조종·권한, 음성 입력, 무감독 완전 자율, 토큰 스트리밍 SSE(폴링으로 충분; 후속), 채널 영구
보관/검색 고도화.

## 열린 질문 (리뷰에서 정할 것)
1. 채널 메시지 저장: 신규 테이블 vs 그래프 노드(`kind="message"`)? (지도 일관성 vs 단순성)
2. 우선순위 표현: 노드 `data.order` vs 별도 backlog 엔티티?
3. `redirect` 재계획 시 진행 중 step 처리: 즉시 중단·교체 vs 현재 step 끝나고 적용?
4. intent 라우터: 별도 경량 LLM 호출 vs 실행 에이전트와 동일 brain? (→ Model routing 페이지의 `intent-router` 지점으로 설정화)
5. auto-pilot에서 `assumption`을 어디까지 자동 진행할지(되돌리기 비용 임계).
6. Rules/Model 스코프에 **per-ticket 오버라이드**까지 둘지, 아니면 global+project만(v1)?
7. Rules 주입 형태: **전문(full text) 주입 vs RAG로 관련 부분만 선별** 주입? (general_coding_rules는 444줄 → 매 프롬프트 전문 주입은 토큰 비용↑)
8. Model routing/비밀키 저장: DB 설정 테이블 vs env + `objective.data`. API 키 안전 저장 위치(평문 금지).
9. local model transport는 **OpenAI 호환 엔드포인트**로 통일할지(ollama/llama.cpp 등 한 인터페이스).

---

## 진행 로그

### CP0 — 거버넌스(Rules 주입 + Model 라우팅) — 완료 (2026-07-01)

두 설정 축(*무엇을* rules / *누가* model)을 사람이 관리하도록 구현. 전부 **전역 기본 + 프로젝트별
오버라이드** 스코프(per-ticket는 v1 제외, 열린 질문 #6).

**A. Rules 주입**
- `services/governance.py`에 `resolve_rules(db, pid) -> {coding, planning}`(전역+프로젝트 append 병합 + 사이즈 가드 `MAX_RULES_CHARS=20k`, 열린 질문 #7 기본값 = 전문 주입). 전역은 신규 `settings` 테이블(`rules.global`), 프로젝트는 `objective.data.rules`. `docs/general_coding_rules.md`를 전역 coding 기본값으로 **시드**(순수 읽기 — 저장 안 함, 명시 PUT에서만 영속).
- 주입: `prompt_build.build_step_prompt(..., coding_rules=)` → `# Rules (coding)` 섹션(executor). `planner.py`의 4개 실 planner(Cli/LangChain × project/ticket)가 `planning_rules` 인자를 받아 `# Rules (planning)` 섹션을 프롬프트에 prepend(`with_planning_rules` + 테스트 가능한 `_prompt()` 추출).

**B. Model 라우팅**
- `resolve_engine(db, point, pid) -> {transport, model}` (+다중 지점 묶음 `resolve_all`). 우선순위 **프로젝트 오버라이드 > 전역 프로필 > env 기본**. env 기본은 기존 `ASV3_AGENT_MODE`/`ASV3_BRAIN`/"키 있으면 API" 분기를 그대로 재현 → **`simulated` 경로 보존**. 잘못된/미지원 transport는 안전 폴백(+경고).
- 개입 지점: `project-planner`·`ticket-planner`·`executor`(실배선) + `intent-router`(CP3)·`agent-message-gen`(CP2) 자리만 정의.
- **실제 배선 transport**: `claude-cli`(CliExecutor/CliPlanner) · `codex-cli`(CliExecutor brain=codex) · `anthropic-api`(LangChain*) · `simulated`. **stub(미구성 표시만)**: `openai-api` · `local` — `available_engines()` health에서 `wired:false`로 노출, resolve 시 안전 폴백. 엔진 팩토리 `make_planner`/`make_project_planner`/`make_executor`가 transport→클래스 매핑을 한곳에 모음.
- 배선: `routers/lifecycle.py _build` + `routers/projects.py plan_project`가 env 대신 resolver/팩토리 사용. 비밀키는 DB 평문 저장 안 함 — env(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`), 페이지엔 상태만(열린 질문 #8).

**엔드포인트**(`routers/governance.py`): `GET/PUT /rules`·`/projects/{pid}/rules`, `GET/PUT /models`·`/projects/{pid}/models`, `GET /models/available`.

**프론트**: `/project/:pid/rules`(전역+프로젝트 coding/planning 편집 + resolved 미리보기), `/project/:pid/models`(지점×엔진 표, 전역/프로젝트 스코프 토글, health 칩). Shell 상단에 **Governance** 진입 버튼. API seam(dto/ApiClient/Http/Mock) 확장.

**테스트**: 백엔드 `test_governance.py` 18개(resolve_rules 병합, 프롬프트 주입, resolve_engine 오버라이드/폴백, 엔드포인트) → **pytest 92 passed**. 프론트 seam + 페이지 테스트 11개 → **vitest 65 passed, tsc 그린**.

**메모(테스트 인프라)**: 비동기 실행 테스트(`test_lifecycle_async.py` 등)는 in-memory SQLite + StaticPool(스레드 간 단일 연결 공유)이라 백그라운드 워커 쓰기 ↔ `GET /graph` 폴링 읽기가 **드물게(~10–20%) 충돌**(sqlite "API misuse"/NULL 컬럼)하는 **기존 결함**이 있음(HEAD도 결정적으로 4개 실패). CP0는 이를 악화시키지 않도록 거버넌스 해석을 요청 스레드에서 1회 수행 후 워커에 전달(`gov` 인자)하고 워커 spawn 전 트랜잭션을 commit한다. 근본 해결(연결-스레드 분리)은 shared-cache 시도 시 크래시 → CP0 범위 밖으로 보류. 단발 실행은 통상 green. (후속 권장: 공유 연결 직렬화 락 또는 파일/Postgres 백엔드로 테스트.)

**리뷰 패스(다중 에이전트 적대적 리뷰 → 검증)에서 잡아 수정**: ① codex-cli를 planner 지점 `SUPPORTED`에서 제거(CLI planner는 `claude -p`만 실행 — codex는 executor 전용) + 팩토리에서 brain='codex' planner 생성 제거; ② `_resolve_one`이 미지원 프로젝트 오버라이드를 만나면 env 기본으로 바로 떨어지지 않고 **유효한 전역 티어로 fall-through**; ③ rules 사이즈 가드가 초과 시 **프로젝트 오버라이드를 보존**하고 전역을 잘라냄(`_merge_rule`); ④ seed 읽기가 `UnicodeDecodeError`도 graceful degrade; ⑤ Mock `resolveEngine`이 지점별 supported fallback을 backend와 동일하게 미러; ⑥ 거버넌스 페이지 load effect deps에 `pid` 추가(라우트 `:pid` 변경 시 stale/교차-프로젝트 저장 방지). 백엔드 테스트 92→95, 프론트 65→66.

### CP1 — 자율 진행 루프 + Throttle — 완료 (2026-07-01)

강제 per-step 리뷰 게이트를 사람이 다이얼하는 **throttle 정책**으로 전환. 값 `auto`·`co-pilot`·`per-step`, **기본 `per-step`(= 오늘 동작, 기존 테스트 그대로 그린)**.

**저장/해석**: `governance.py`에 `resolve_autonomy(db, pid)` + get/set(전역=Setting `autonomy.global`/env `ASV3_THROTTLE`, 프로젝트=`objective.data.autonomy`). 우선순위 프로젝트>전역>env>per-step.

**그래프(`lifecycle_graph.py`)**: `build_graph(..., autonomy=)`. review 노드가 throttle 조건부 —
- `per-step`: 매 step `interrupt()`(오늘 그대로).
- `auto`: 성공 step은 인터럽트 없이 **자동 진행** → 그래프가 한 invoke 안에서 티켓 끝까지 self-loop. 실패(`blocked`)에서만 정지.
- `co-pilot`: 자동 진행하되 **① 실패 step ② 마지막 step(최종 리뷰)** 에서 정지(③ 명시적 review-needed 신호는 `state.review_needed` 훅으로 자리만; CP2/CP3). execute_step이 `last_ok`(executor 성공 여부)를 state에 실어 co-pilot 판단에 사용.

**배선(`lifecycle.py`)**: `_resolve_governance`가 autonomy 포함 → `_build`가 그래프에 주입. `_finalize_run`이 auto/co-pilot 실행 뒤 **자동 진행된 step들을 done 처리 + END면 티켓 done/promote**(per-step은 no-op). approve_plan(sync/async) + review_step(sync/async)가 throttle에 따라 `_finalize_run`/`_finalize_review` 선택. **per-project 실행 락 유지**, 워커 spawn 전 commit으로 공유 연결 레이스 회피(CP0와 동일).

**엔드포인트**: `GET/PUT /autonomy`(전역) · `GET/PUT /projects/{pid}/autonomy`.

**프론트**: Shell 토픽바에 **자율도 다이얼**(매 step / 부조종 / 자동, `AutonomyDial`), `useStore`에 `autonomy` 상태 + `setAutonomy`(변경 즉시 저장) + `setPid` 시 `loadAutonomy`. seam 확장.

**테스트**: 백엔드 `test_throttle.py`(resolve_autonomy, auto 끝까지 done(sync+async drain), co-pilot 최종-step/blocked 정지, blocked-step 승인 회귀, per-step 기본 보존, 엔드포인트) → **pytest 107 passed**. 프론트 seam+다이얼 3개 → **vitest 69 passed, tsc 그린**.

**리뷰 패스(다중 에이전트 적대적 리뷰 → 검증)에서 잡아 수정**: ① **(high)** `_finalize_run`이 `blocked` step 승인 시 done 처리 안 함 → auto/co-pilot에서 막힌 step을 사람이 승인해도 무시되고 티켓이 안 끝나던 버그. `approve`면 `blocked`도 done 처리(다른 승인 핸들러와 일관)로 수정 + 회귀 테스트 2개; ② **(low)** throttle을 그래프 클로저가 아니라 **체크포인트 state(`autonomy`)에 저장** — 정지~resume 사이에 다이얼을 바꿔도 `must_stop` 재계산이 흔들려 resume 액션(takeover/changes)이 묻히지 않도록 결정적화; ③ **(low)** `loadAutonomy`에 pid 시퀀싱 가드(빠른 프로젝트 전환 시 stale 응답이 다이얼을 덮어쓰지 않게). 검증 단계에서 허위로 기각: review_needed 미사용(의도된 CP2/CP3 훅), setAutonomy 에러 무시(전역 unhandledrejection 핸들러가 토스트로 노출). 범위 밖/기존결함으로 기록만: `setPid`의 reload 시 선택 초기화(CP1 이전부터 존재), 다이얼이 `levels` 미소비·override clear 어포던스 없음(스펙 3옵션은 충족, v1 단순화).

### CP2 — 대화 채널 + 에이전트→사람 구조화 메시지 — 완료 (2026-07-01)

프로젝트별 append-only **대화 채널**과, 라이프사이클 전이에 배선된 **타입 메시지**(assumption/blocked/decision/review). 단방향 결재를 양방향 대화로 바꾸는 절반(사람→에이전트 steer는 CP3).

**저장(열린 질문 #1 기본값 = 전용 테이블)**: 신규 `messages` 모델 `{id(autoinc), project_id, type, author, text, refs, ts}` (`init_db`가 sqlite·postgres 둘 다 자동 생성). `id`가 `?since=` 증분 커서.

**서비스 `services/channel.py`**: `post_message`·`list_messages(since)`·`post_review_message`(정확 중복 스킵). `gen_text`는 **결정적 템플릿**(한국어) — CP0 `agent-message-gen` 지점이 향후 LLM 생성기가 꽂힐 자리(v1은 워커 hot-path에 DB 읽기 없이 오프라인·결정적).

**배선(`lifecycle.py`)**: `on_step_committed` — 실패(ok=False)→`blocked` 메시지, decision 노드 생성→`decision` 메시지(노드 ref). `_emit_review_message` — 실행이 **리뷰 게이트에서 멈춘 (non-blocked) step**에 `review` 메시지(approve_plan·review_step의 sync/async 4경로 모두). blocked step은 blocked 메시지가 커버하므로 review는 스킵. `review` 메시지의 액션은 기존 `POST /steps/{sid}/review` 재사용 — **per-step 동작 무변경**.

**엔드포인트**: `GET /projects/{pid}/messages?since={id}` (증분 폴링).

**프론트**: Shell 우측 **채널 패널**(`ChannelPanel`, 타입별 렌더 + review 메시지에 승인/수정요청/인수 = `reviewStep` 재사용, 처리된 step은 액션 숨김). 토픽바 **채널 토글**(+미확인 배지). `useStore`에 `messages` + `loadMessages`(since 커서·dedup·pid 가드) + `setPid` 리셋 + 1.5s 폴링. Mock은 gate 시 review 메시지 생성.

**테스트**: 백엔드 `test_channel.py`(post/list/since 단위, blocked→blocked·not review, decision→decision, per-step→review, since 증분, changes 재실행 회귀 2개) → **pytest 115 passed**. 프론트 seam+패널(널-그래프·최신-리뷰-액션 회귀 포함) → **vitest 75 passed, tsc 그린**.

**리뷰 패스(다중 에이전트 적대적 리뷰 → 검증)에서 잡아 수정**: ① **(med)** `changes` 재실행이 새 review 메시지를 안 올리던 버그 — text 기반 dedup이 상수 sim summary 때문에 정당한 재-게이트까지 억제. dedup 제거(게이트당 정확히 1회 emit이므로 진짜 중복 없음) → 재실행마다 fresh review; ② **(low)** `decision` 메시지가 재실행마다 중복 적재 → 노드가 신규/변경일 때만 게시(`dec_is_new`); ③ **(low)** 프론트 review 액션이 그래프 미로딩 시 "처리됨"으로 오표시 → 널-그래프는 액션도 "처리됨"도 안 띄움(로딩=미확정); ④ **(low)** 한 step에 여러 review 프롬프트가 동시 액션 가능 → **step별 최신 review 메시지만** 액션 노출; ⑤ **(low)** "미확인" 배지가 누계였음 → 패널 열림 기준 실제 unread 카운트; ⑥ **(low, 테스트 위생)** `conftest`가 앱 import 전 `DATABASE_URL`/`ASV3_CHECKPOINTER=memory` setdefault로 고정 → bare `pytest`도 hermetic(dev의 `.env` postgres/durable checkpointer 누수 차단). 검증에서 허위 기각: "worker commit이 async를 flaky하게" (실험으로 반증 — 기존 공유연결 레이스, CP2 무관), assumption 미emit(스펙상 선택적 타입). 프론트 3 unhandled error는 기존 ProjectMap d3-drag 티어다운 노이즈(범위 밖).

### CP3 — Steer: Intent-router 핵심 연산 — 완료 (2026-07-01)

사람이 채널에 친 자유 NL을 **고정 그래프 연산**으로 라우팅해 실행(사람→에이전트 조종). CP0(intent-router 지점)·CP1(throttle)·CP2(채널)·기존 재계획/decision/RAG/리뷰 게이트를 재사용.

**intent router(`services/intent.py`)**: `SimulatedIntentRouter`(규칙 기반·결정적, SimulatedPlanner 패턴) — 키워드 우선순위 control>constrain>redirect>answer(문맥)>clarify. `answer`는 **막힌 step(질문)이 있을 때만** — 없으면 clarify(추측 금지). 실모드용 `LangChainIntentRouter`(anthropic-api). 팩토리 `governance.make_intent_router`(intent-router 지점; `SUPPORTED`에서 미배선 claude-cli 제외 — CP0 리뷰 교훈).

**엔드포인트 `POST /projects/{pid}/steer {text, ticketId?, stepId?}`**(`routers/steer.py`): 사용자 `steer` 메시지 기록 → 분류 → 디스패치 → 결과 채널 메시지(system/decision/clarify). scope는 명시 선택 우선, 없으면 활성 티켓/막힌 step 추정.

**op 4종**:
- `redirect` — 대상 티켓 steps 재계획(열린 질문 #3 v1 = 교체; 진행 step abort는 후속). `store.approve_plan` 재사용, plan diff를 system 메시지로.
- `constrain` — `decision`(kind=constraint) 노드 생성 + 티켓에 `decided` 엣지(가시성) + **`MEMORY.index_text`로 RAG 전파**(기존 prompt_build 회상 재사용) + decision 메시지.
- `answer` — 막힌 step을 `resume_step_review`(review 게이트의 재사용 가능한 sync 코어)로 `changes` 재실행 → unblock. 실행은 per-project 락에서 직렬화.
- `control` — pause(=매 step) / resume(=자동) / 자율도 변경 = CP1 `set_project_autonomy` 재사용.

**FE**: 채널 하단 **상시 steer 입력창**(`SteerInput`) → `api.steer` → 즉시 `loadMessages`로 결과 반영. steer/system/clarify 메시지 타입 렌더. Mock은 백엔드 규칙을 미러한 `classifyMock`로 전체 흐름 데모.

**테스트**: 백엔드 `test_steer.py`(라우터 단위 분류, clarify+user 메시지, redirect 재계획+체크포인트, constrain 노드+RAG, answer unblock+guidance, control throttle, throttle 오버매치 회귀) → **pytest 124 passed**. 프론트 seam+입력 → **vitest 80 passed, tsc 그린**.

**리뷰 패스(다중 에이전트 적대적 리뷰 → 검증)에서 잡아 수정**: ① **(high)** `redirect`가 `store.approve_plan`으로 DB step만 바꾸고 **LangGraph 체크포인트를 그대로 둬** 다음 리뷰 resume이 폐기된 옛 계획을 실행하던 desync — 재계획 후 티켓/step을 planning으로 되돌리고 `delete_thread`로 체크포인트 리셋(옛 인터럽트 제거) → 새 계획을 정상 flow로 실행(+회귀 테스트); ② **(med)** `throttle_level`의 'auto'/'자동' 부분문자열 과매칭('automate'/'자동 저장'이 자율도 뒤집음) → **표준 토큰/다이얼 설정**(`auto로`/`자동 모드`/`자동으로`)만 인식(+회귀); ③ **(med)** `answer` 답변 텍스트가 재실행 프롬프트에 안 닿던 blind retry → `review_comment`를 state에 실어 `# Reviewer guidance`로 주입(review_step `changes`에도 이득)(+회귀); ④ **(med, 기존결함)** review 게이트가 없는 blocked step에 `answer`가 조용히 no-op하며 성공 주장 → 여전히 blocked면 정직하게 clarify; ⑤ **(med, FE)** `control`로 자율도 바꿔도 CP1 다이얼이 안 갱신 → subscribe 콜백에 `loadAutonomy` 추가; ⑥ **(low)** blocked step 조회를 활성 티켓에 스코프+결정적; ⑦ **(low)** `control` resume이 무조건 auto(안전 강등) → 오버라이드 clear(전역 기본 상속); ⑧ **(med/low, FE)** Mock의 '매 스텝'→auto 오분류 수정, `classifyMock` 키워드/`steer` scope 인자 백엔드와 정렬. **미해결(문서화)**: answer 재실행이 아직 동기(비차단 background는 후속) — 읽기/제안 락-프리·실행 락 직렬화는 충족. 프론트 3 d3-drag unhandled error는 기존 노이즈(범위 밖).

### CP4 — 백로그/창발 범위 + 채널↔지도 양방향 + per-ticket throttle — 완료 (2026-07-01)

조종석을 Agile하게 완성. CP1~CP3 위에 얹음(새 라이프사이클 없음).

**steer op 2종 추가**(CP3 골격 재사용):
- `reprioritize` — "결제 먼저" → 대상 티켓(라벨 매칭) `data.order`를 맨 앞으로(열린 질문 #2 = ticket `data.order`, 별도 backlog X). `store.next_ticket`이 최저 order non-done 티켓 선택.
- `scope` — "다국어도 추가" → 새 planning 티켓 생성(`store.add_ticket`, order=max+1). 창발적 범위.

**per-ticket throttle**(열린 질문 #6): `resolve_autonomy(db, pid, tid)` = **ticket(`ticket.data.autonomy`) → project → global**. `_build`가 tid 전달. 엔드포인트 `GET/PUT /projects/{pid}/tickets/{tid}/autonomy`. 미설정 시 폴백이라 CP1 무회귀.

**채널↔지도 양방향**: `useStore`에 `highlightIds`(Shell-로컬 → 스토어로 승격, BugTrace와 공유) + `channelFilter` + `focusNode`. 메시지 `refs`를 chip으로 렌더 → 클릭 시 지도 노드 하이라이트(`focusNode` → highlight + 맵 뷰). 지도 노드 클릭 → 채널이 그 노드 ref 메시지로 필터(+필터 해제 chip).

**FE 다이얼**: 보드 헤더에 `TicketAutonomyDial`(티켓 오버라이드 설정, 상속/전용 표시).

**테스트**: 백엔드 `test_backlog.py` 5개(reprioritize order+scope 생성+per-ticket ticket>project>global+티켓 자율도가 라이프사이클 구동) → **pytest 129 passed**. 프론트 seam+채널↔지도+티켓 다이얼 5개 → **vitest 85 passed, tsc 그린**.

**리뷰 패스(16-에이전트 3차원 적대적 리뷰 → 건별 검증, 확정 10건 중 positive 1 제외 9건 수정)에서 잡아 수정**: ① **(high)** `focusNode(stepId)`가 Step 레이어 off일 때 지도를 통째로 dim시켜 **대상 step이 안 보이던** 치명 결함 — 리뷰/blocked/assumption 메시지는 step id를 ref하므로 채널→지도 이동의 핵심 경로가 빈 화면. code 레이어 자동표시를 미러해 **하이라이트가 step이면 Step 레이어 자동 표시**(`effectiveShowSteps`)(+회귀); ② **(med)** `reprioritize`의 `_match_ticket`이 **첫-토큰-승리 + 대소문자 구분** — 공유 토큰('결제') 시 의도와 다른 티켓, 영문 대문자 라벨은 매칭 실패 후 조용히 활성 티켓으로 폴백. **토큰 겹침 스코어링 + 소문자 정규화**(동점은 긴 라벨)로 교체(+회귀 2: 한국어 특정성·영문 대소문자); ③ **(med)** `reprioritize`의 `data.order`가 **지도/레일 정렬에 미반영**(스펙 "목록 정렬 반영") — `orderedTickets`(domain 공유 헬퍼, 백엔드 `ticket_order` 미러)로 ProjectMap+CockpitRail 정렬(+회귀: 정렬 계약 단위); ④ **(med, FE)** 지도 노드 클릭이 채널 닫힘 상태에서 **보이지도·해제되지도 않는 채널필터를 고착** — `channelOpen`을 스토어로 승격하고 `setChannelFilter`가 필터 설정 시 채널을 열어 ✕ 해제를 항상 노출(+회귀 store 단위); ⑤ **(med, FE)** `TicketAutonomyDial`이 상속 티켓에서 외부(project/global) 자율도 변경 뒤 **stale** — 스토어 `autonomy` 구독을 effect deps에 추가해 재조회(+회귀); ⑥ **(low)** `GET .../tickets/{tid}/autonomy`가 비-티켓/부재 tid에 200 반환(PUT은 404) → **PUT과 동일 가드**(+회귀); ⑦ **(low, FE)** 티켓 클릭이 채널을 티켓 id로만 필터해 **빈 스레드로 붕괴**(메시지는 step id ref) → 필터를 그 티켓의 **소유 step/decision까지 확장**(+회귀); ⑧ **(low)** `store.next_ticket` 미배선/미테스트 → **자율루프 다음-선택 계약 단위 테스트** 추가(전체 자율 러너는 v1 비목표라 배선은 후속). **검증에서 결함 아님으로 확인**: "게이트 그린·do-not-break 전부 검증"은 positive(액션 없음). **범위 밖 기록**: 프론트 3 d3-drag unhandled error는 stash로 **HEAD 기준선에서 동일 재현** → 전부 기존 React Flow+jsdom 티어다운 노이즈(CP4 무관). 결과 **백엔드 pytest 133 passed**(신규 4; `test_lifecycle_async` 6개는 기존 공유연결 레이스로 여전히 flaky, 나머지 127 결정적 그린), **프론트 vitest 91 passed·tsc 그린**.

---

## Living cockpit v1 — 완료 요약 (CP0–CP4)

거친 목표 → 작고·보이고·리뷰 가능한 step으로 일하는 **살아있는 인과 지도 + 조종석**이 v1으로 완성됨.

- **CP0 거버넌스**: 모든 AI 호출의 *무엇을*(coding/planning rules 주입) + *누가*(model 라우팅 테이블, 지점별 transport/model). 전역+프로젝트 스코프, Rules/Models 페이지.
- **CP1 Throttle**: 강제 per-step 게이트 → `auto`/`co-pilot`/`per-step` 다이얼. auto self-loop, co-pilot 실패/최종 정지. 기본 per-step(무회귀).
- **CP2 채널**: 프로젝트별 대화 채널 + 타입 메시지(assumption/blocked/decision/review). 라이프사이클 전이 배선, `since` 커서 폴링.
- **CP3 Steer**: 자유 NL → 고정 op(intent-router). redirect/constrain/answer/control. 채널 하단 상시 입력.
- **CP4 백로그/양방향**: reprioritize/scope + 채널↔지도 양방향 + per-ticket throttle.

**최종 게이트**: 백엔드 **pytest 133 passed**(README 기준선 74 → CP0–CP4로 +59; `test_lifecycle_async` 6개는 기존 StaticPool 공유연결 레이스로 flaky, 나머지 127 결정적 그린), 프론트 **vitest 91 passed**(기준선 54 → +37; 3 d3-drag unhandled error는 HEAD 기준선부터 동일 재현되는 React Flow+jsdom 티어다운 노이즈), **tsc 그린**. 각 CP마다 다중 에이전트 적대적 리뷰 + 검증으로 확정 결함 수정(누적 HIGH 3·MED 다수). 브랜치 `cp0-governance`.

**알려진 한계/후속**(v1 범위 밖): ① in-memory SQLite + StaticPool 공유연결 탓 비동기 실행 테스트 ~10–20% flaky(기존결함, 단발 그린; 근본 해결은 연결-스레드 분리) · ② steer `answer` 재실행 아직 동기(background는 후속) · ③ redirect 즉시 abort/무감독 완전자율/SSE/멀티유저/음성/노드 thread 간접-ref는 비목표.
