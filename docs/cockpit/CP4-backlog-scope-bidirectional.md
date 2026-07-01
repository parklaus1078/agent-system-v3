# CP4 — 백로그/창발 범위 + 채널↔지도 양방향 + per-ticket throttle

먼저 `docs/cockpit/README.md`와 `docs/living-cockpit-design.md`의 **Steer 어휘(reprioritize/scope) + 레이아웃 + 열린 질문 #2,#6**을 읽어라.
**전제**: CP1(throttle) · CP2(채널) · CP3(steer).

## Goal
조종석을 Agile하게 완성: 백로그 재정렬·창발적 범위 추가, 채널과 지도의 양방향 결속, 티켓 단위 자율도.

## 빌드
- **`reprioritize`** (steer op 추가): "결제 먼저" → 티켓 우선순위 재정렬. **열린 질문 #2 기본값 = 티켓 노드 `data.order`**
  (별도 backlog 엔티티 X). 자율 루프가 다음 실행 티켓을 `order`로 선택. 지도/홈 목록 정렬에도 반영.
- **`scope`** (steer op 추가): "다국어도 추가" → 새 `ticket` 생성(기존 create + planning 흐름 재사용, status=planning).
  창발적 범위 = 실행 결과/대화가 새 일감을 낳음.
- **채널↔지도 양방향**:
  - 메시지의 `refs:[node_id]`를 chip으로 렌더, 클릭 시 지도 노드 하이라이트.
  - 지도 노드 클릭 → 채널이 그 노드 thread(해당 노드를 ref하는 메시지)로 필터.
  - steer/op 적용 시 영향 노드 하이라이트(기존 `ProjectMap` highlightIds 재사용).
- **per-ticket throttle** (열린 질문 #6): CP1의 전역/프로젝트 throttle에 **티켓별 오버라이드**(`ticket.data.autonomy`).
  해석 우선순위: ticket → project → global. 보드/티켓 헤더에 작은 다이얼.

## 결정/기본값
- 우선순위는 `data.order`(정수, 작을수록 먼저). 드래그 재정렬(Phase 4 드래그 인프라 재사용 가능)도 같은 `order` 갱신.
- thread 필터: 노드를 직접/간접 ref하는 메시지(간단히 직접 ref부터).

## 깨지 마라
- Phase 4의 드래그 위치 영속(`data.pos`)과 충돌 없이 — `order`는 별개 필드.
- steer op 추가는 CP3의 라우팅/실행 골격 위에. 새 라이프사이클 만들지 말 것.
- per-ticket throttle 해석이 CP1 동작을 회귀시키지 않게(미설정 시 project→global로 폴백).

## Done when
- reprioritize가 `order` 갱신 + 자율 루프 다음-선택/목록 정렬 반영(테스트). scope가 새 티켓 생성(테스트).
- 메시지 ref 클릭→노드 하이라이트, 노드 클릭→채널 필터(vitest). per-ticket throttle 오버라이드(테스트: ticket>project>global).
- 백엔드 pytest + tsc/vitest 그린. spec 진행 로그에 CP4 기록 + "Living cockpit v1 완료" 정리.

## Out of scope (후속/비목표)
멀티유저 동시 조종 · 음성 · 무감독 완전자율 · SSE 스트리밍 · 메시지 검색 고도화 · redirect 즉시 abort.
