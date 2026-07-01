# CP3 — Steer: Intent-router 핵심 연산

먼저 `docs/cockpit/README.md`와 `docs/living-cockpit-design.md`의 **"Steer 어휘" + 확정결정 #4(Intent-routed) + 열린 질문 #3,#4**를 읽어라.
**전제**: CP2(채널)와 CP0(model 라우팅의 `intent-router` 지점)이 있어야 함.

## Goal
사람이 채널에 친 자유 NL을 **고정 그래프 연산**으로 라우팅해 실행한다. 사람→에이전트 방향의 조종.

## 빌드
- **엔드포인트**: `POST /projects/{pid}/steer {text}` → intent router가 `{op, scope, args}`로 분류 → 해당 연산 실행
  → 결과를 채널 메시지로 append(사용자 메시지 + 시스템 결과). 비차단(실행은 background, read/propose는 락-프리).
- **intent router**: CP0 Model 라우팅의 `intent-router` 지점 엔진 사용. **simulated 라우터**(규칙 기반)도 구현해
  `ASV3_AGENT_MODE=simulated`/테스트에서 결정적이게(SimulatedPlanner와 같은 패턴).
- **이번 CP의 op (핵심 4종)**:
  - `redirect` — "결제는 Stripe로" → 대상 ticket/step 재계획. **열린 질문 #3 기본값 = 현재 step 끝나고 적용**
    (진행 중 step은 끝낸 뒤 영향 subtree 재계획; plan diff를 채널/지도에 표출). 즉시 중단(abort)은 후속.
  - `constrain`(pin) — "auth 건드리지 마" → `decision`/constraint 노드 생성 + 하위 전파(기존 RAG 주입 재사용).
  - `answer` — 에이전트 질문(blocked 메시지)에 답 → 막힌 노드 unblock하고 진행.
  - `control` — pause / resume / throttle 변경(CP1 throttle 재사용).
- **감사성**: 각 연산은 어떤 노드를 누구의 어떤 지시로 바꿨는지 흔적(메시지 ref + 노드 data 이력).
- **FE**: 채널 하단 **steer 입력창**(상시). 전송 → `/steer`, 낙관적 사용자 메시지 표시, 결과 메시지 수신.

## 결정/기본값
- 분류 실패/모호 → 추측 금지, `clarify` 메시지로 되물음.
- scope 해석(어느 ticket/step 대상): 명시 참조(@/현재 선택) 우선, 없으면 라우터가 추정하되 모호하면 clarify.

## 깨지 마라
- per-project 실행 락 / async 경로 / 기존 재계획(propose→approve) 로직 재사용 — 별도 새 라이프사이클 만들지 말 것.
- `constrain`은 기존 `decision` 노드 + `prompt_build`/RAG 주입 메커니즘을 그대로 사용.

## Done when
- `POST /steer` 가 NL을 op로 라우팅(simulated 라우터로 결정적 테스트: "use Stripe"→redirect, "don't touch auth"→constrain, 답변→unblock, "pause"→control).
- redirect가 대상 티켓 steps를 재계획(diff), constrain이 노드+전파 생성, answer가 blocked 해제, control이 throttle/pause 반영(테스트).
- 채널 steer 입력 동작(vitest+tsc 그린). 백엔드 pytest 그린. spec 진행 로그에 CP3 기록.

## Out of scope
`reprioritize`/`scope`(CP4) · redirect 즉시 abort(후속) · 노드↔채널 양방향(CP4).
