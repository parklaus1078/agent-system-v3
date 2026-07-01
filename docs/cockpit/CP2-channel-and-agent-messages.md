# CP2 — 대화 채널 + 에이전트→사람 구조화 메시지

먼저 `docs/cockpit/README.md`와 `docs/living-cockpit-design.md`의 **"에이전트→사람(타입 메시지)" + 확정결정 #3 + 열린 질문 #1**을 읽어라.

## Goal
프로젝트별 **대화 채널**을 만들고, 에이전트가 **타입 있는 메시지**(가정/막힘/결정/리뷰)를 채널에 올리게 한다.
단방향 결재를 양방향 대화로 바꾸는 절반(사람→에이전트 steer는 CP3).

## 빌드
- **메시지 저장 (열린 질문 #1 기본값 = 전용 테이블)**: 신규 `messages` 모델/테이블
  `{id, project_id, type, author('agent'|'user'|'system'), text, refs:[node_id], ts}`. (그래프 노드 오염 대신 단순 조회·정렬.)
- **에이전트 메시지 타입**: `assumption` · `blocked` · `decision` · `review`. 라이프사이클 전이에 배선:
  - 막힘(`on_step_committed` ok=False) → `blocked` 메시지(+선택지 있으면 포함).
  - 결정 발생(`decision` 노드 생성 지점) → `decision` 메시지(노드 ref).
  - per-step throttle(CP1)에서 step이 리뷰 대기 → `review` 메시지(이 메시지의 액션이 곧 승인/수정/인계).
  - (가능하면) executor/planner가 가정을 낼 때 → `assumption` 메시지. v1은 위 3개 필수, assumption은 가능 범위.
  - 메시지 문구 생성은 **CP0 Model 라우팅의 `agent-message-gen` 지점** 사용(없으면 단순 템플릿; simulated에선 결정적 템플릿).
- **엔드포인트**: `GET /projects/{pid}/messages?since={ts|id}` (커서 폴링; 기존 리비전/ETag 패턴 재사용 가능),
  내부 `post_message(...)` 헬퍼. `review` 메시지의 액션은 기존 `POST /steps/{sid}/review`로 연결.
- **FE**: Shell에 **채널 패널**(설계 레이아웃의 우측). 메시지 타입별 렌더(assumption/blocked/decision/review),
  review 메시지엔 승인/수정/인계 버튼(기존 리뷰 로직 재사용). `getGraph`처럼 폴링(또는 since 커서).
- **revision/ETag**: 메시지 추가도 폴링이 싸게 감지하도록(night #4 패턴 확장 또는 별도 since 커서).

## 결정/기본값
- 채널은 프로젝트 단위(한 대화). 노드 thread 필터는 CP4.
- 메시지는 append-only(편집/삭제 없음, v1).

## 깨지 마라
- 기존 리뷰 게이트 동작/테이크오버/DB-direct 경로 — `review` 메시지는 그 **승격**일 뿐 로직 재사용. per-step에선 기존과 동등.
- simulated 모드에서 메시지 생성 결정적. `ASV3_ASYNC_EXEC=0`에서도 메시지가 올바른 시점에 쌓여야.
- 새 테이블은 `init_db`/마이그레이션에 등록(sqlite·postgres 둘 다).

## Done when
- 라이프사이클 전이마다 적절한 타입 메시지가 채널에 쌓임(테스트: blocked→blocked 메시지, 결정→decision 메시지, per-step→review 메시지).
- `GET /messages?since=` 가 증분 반환(테스트). 채널 패널이 타입별로 렌더 + review 액션 동작(vitest+tsc 그린).
- 백엔드 pytest 그린. spec 진행 로그에 CP2 기록.

## Out of scope
사람→에이전트 steer/intent-router(CP3) · 노드↔채널 양방향 필터(CP4) · 메시지 검색/영구보관 고도화(후속).
