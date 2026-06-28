# docs/design — UI 설계 산출물

Claude design이 만든 UI 와이어프레임을 여기에 둔다. 이게 구현(Claude Code)의
**시각 진실원천**이다.

## 현재 산출물 — 단일 번들 HTML 목업
```
docs/design/wireframes/llm-dev-control-tower.html   # 브라우저로 열어서 본다
```
이 한 페이지가 모든 화면(목표 입력 · 플랜 승인 · 프로젝트 지도 · 티켓 레인 ·
리뷰 페인 · 버그 추적)을 담고 있다.

## 규칙
- 구현 시 이 HTML을 **브라우저로 열어** 화면별 레이아웃/상태/인터랙션을 대조한다.
- 충돌 시: **와이어프레임(시각)** 우선. 단 *기능/데이터*는 spec(§6/§7/§8)이 최우선.
- `mockups/` 폴더는 현재 비어 있음 — 분리된 컴포넌트 목업이 생기면 여기에 둔다(선택).

## 구현 입력 문서
- spec: [`../superpowers/specs/2026-06-28-llm-dev-control-tower-design.md`](../superpowers/specs/2026-06-28-llm-dev-control-tower-design.md)
- UI 브리프: [`../superpowers/specs/2026-06-28-llm-dev-control-tower-ui-brief.md`](../superpowers/specs/2026-06-28-llm-dev-control-tower-ui-brief.md)
- **구현 계획**: [`../superpowers/plans/2026-06-29-frontend-ui-on-mock.md`](../superpowers/plans/2026-06-29-frontend-ui-on-mock.md) ← 프론트는 이 plan대로
