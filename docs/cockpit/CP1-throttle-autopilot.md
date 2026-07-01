# CP1 — 자율 진행 루프 + Throttle (전역)

먼저 `docs/cockpit/README.md`와 `docs/living-cockpit-design.md`의 **확정결정 #2(Throttle) + Throttle 의미 + "한 사이클"**을 읽어라.

## Goal
오늘의 **강제 per-step 리뷰 게이트**를, 사람이 다이얼하는 **throttle 정책**으로 바꾼다. auto-pilot에선 에이전트가
step→step→티켓까지 **스스로 진행**(조종할 "움직이는 대상"이 생김). 가장 큰 토대.

## 현재 동작 (바꿀 것)
`services/lifecycle_graph.py`의 `review` 노드가 **항상** `interrupt()`로 멈추고, 사람이 approve해야 다음 step으로 간다.
`routers/lifecycle.py`의 `_invoke_async`는 한 step 실행 후 리뷰 게이트에서 멈춘다.

## 빌드
- **Throttle 값**: `auto` · `co-pilot` · `per-step`. 저장: 전역 기본(설정/`ASV3_THROTTLE` env 기본) + 프로젝트별
  (`objective.data.autonomy`). (per-ticket 오버라이드는 CP4.)
- **자율 루프**: throttle이 `auto`면 review 인터럽트를 건너뛰고 다음 step으로 자동 진행 → `_invoke_async` 워커가
  티켓이 끝(전 step done)나거나 막힐 때까지 **루프**(사람 resume 없이). 진행은 기존 `data.activity`로 노출.
- **co-pilot 정지 규칙(명시)**: 평소 자동 진행하되 **반드시 멈추는** 조건 — ① 실행 실패(`blocked`),
  ② 마지막 step 완료 후 최종 리뷰(설정 가능), ③ executor/step이 명시적으로 "리뷰 필요" 신호를 낼 때. 그 외는 auto처럼 진행.
  (간단·결정적 휴리스틱부터. 정교화는 후속.)
- **per-step**: 오늘과 동일(매 step에서 멈춤).
- **배선**: `lifecycle_graph`의 review 분기를 throttle 조건부로(throttle을 graph state 또는 빌드 시 주입). `_invoke_async`
  루프. throttle 읽기/쓰기 엔드포인트(`GET/PUT /projects/{pid}/autonomy` + 전역). 
- **FE**: Shell 토픽바에 **자율도 다이얼**(auto / 부조종 / 매 step), `useStore`에 throttle 상태 + setter, 변경 시 저장.
  실행 중 activity 표시는 기존 `ActivityBadge` 재사용.

## 결정/기본값 (중요)
- **기본 throttle = `per-step`** (= 오늘 동작) — 이래야 기존 테스트가 그대로 그린. auto/co-pilot은 테스트에서 명시적으로 설정.
- 미검토 자동커밋 리스크는 step 단위 커밋 + git 이력 + 사후 리뷰/되돌리기로 완화(설계 "에러/엣지" 참조).

## 깨지 마라
- per-project 실행 락(night #3): 자율 루프도 **실행은 프로젝트 단위 직렬화** 유지. read/propose 락-프리 유지.
- `ASV3_ASYNC_EXEC=0`(테스트 동기) 경로에서 throttle 로직도 동작해야 함.
- 기존 리뷰 흐름(approve/changes/takeover, DB-direct 경로) 보존 — per-step에선 지금과 동일해야.

## Done when
- auto-pilot: 플랜 승인 → (드레인) → **사람 리뷰 호출 없이** 전 step done + 티켓 done (테스트로 검증).
- co-pilot: 정상 step은 자동 진행, `blocked`에서 정지(테스트: 블로킹/실패 executor로 검증).
- per-step(기본): 오늘과 동일, 기존 테스트 전부 그린.
- FE 다이얼로 throttle 변경·저장·반영(tsc+vitest 그린). 백엔드 pytest 그린.
- spec 진행 로그에 CP1 기록.

## Out of scope
채널/메시지(CP2) · steer(CP3) · per-ticket throttle(CP4) · co-pilot 위험판단 정교화(후속).
