# UI 빌드 핸드오프 프롬프트 — Claude Code CLI용

> 사용법: **v3 레포(`~/agent-system-v3`)에서 Claude Code CLI를 열고**, design 산출물을
> `docs/design/wireframes/`(PNG) · `docs/design/mockups/`(HTML/React)에 넣은 뒤,
> 아래 `--- PROMPT ---` 블록을 그대로 붙여넣는다.
>
> - 이미지는 Claude Code가 **경로 참조로 읽는다**(프롬프트 안에 경로를 적거나 클립보드로 붙여넣기).
> - 더 통제된 방식을 원하면, 이 프롬프트로 바로 구현하지 말고 먼저 **구현 계획(writing-plans)**
>   을 만든 뒤 그 계획을 실행시키는 걸 권장(우리 시스템 철학 "step마다 정지"와 동일).

---

--- PROMPT ---

# Goal: LLM Dev Control Tower의 **v1 프론트엔드 UI**를 design 산출물대로 구현

너는 `~/agent-system-v3`에서 작업하는 시니어 프론트엔드 엔지니어다.

## 0. 먼저 읽어라 (순서대로)
1. `docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md` — 시스템 설계(특히 §6 데이터 모델, §7 라이프사이클, §8 UI). **유일한 기능 진실원천.**
2. `docs/superpowers/specs/2026-06-28-llm-dev-control-tower-ui-brief.md` — UI 의도·화면·상태·안티패턴.
3. `docs/design/wireframes/llm-dev-control-tower.html` — **단일 번들 HTML 목업**(모든 화면 포함). 브라우저로 열어 화면별 레이아웃/상태/인터랙션을 그대로 따른다.

> 충돌 시 우선순위: **와이어프레임(시각) > ui-brief(텍스트) > spec**. 단 *기능/데이터*는 spec(§6/§7/§8)이 최우선.

## 1. 무엇을 만드나
화면 4개(+보조 2개)를 구현한다 — ① 프로젝트 지도(홈) ② 티켓 레인 ③ 리뷰 페인(가장 중요) ④ 버그추적, 보조: 플랜 승인 / 목표 입력. 각 화면의 레이아웃·상태·인터랙션은 ui-brief §5–§8을 따른다.

## 2. 스택·구조 (비협상)
- **React + Vite + TypeScript**, 지도는 **그래프 뷰 라이브러리(React Flow류)**.
- **백엔드는 아직 없다.** UI를 **타입드 목 API(fixtures)** 위에 짓는다 — `src/api/` 에 spec §6 데이터 모델(Objective/Ticket/Step/CodeRegion/Test/Decision + 엣지 + 상태)에 맞는 타입과 **목 데이터 어댑터**를 두고, 화면이 그걸 바인딩하게. 실제 API는 나중에 같은 인터페이스로 교체 가능하게 격리.
- 상태는 "항상 최신"을 전제로 설계(수동 새로고침 UI 금지). 목 단계에선 로컬 상태/타이머로 라이프사이클 전이를 흉내.

## 3. 디자인 규율 (안티패턴 = 전작 v2의 불편함, 절대 금지)
- ❌ 내부 배관 노출: `Worker tick`/`Watcher tick` 버튼, 파일 절대경로, API URL, 액터명.
- ❌ 수동 `Refresh` 의존. ❌ 한 화면에 세로로 쌓인 폼 더미. 
- ✅ 지도가 홈. ✅ 리뷰 페인이 주 작업면(2분할: diff | 지도조각+결정+acceptance, 하단 3액션). ✅ 살아있는 상태색(planning/executing/⏸awaiting-review/done/blocked). ✅ 키보드 친화.

## 4. 작업 순서 (점진적, 화면 단위로 검증)
1. Vite+React+TS 스캐폴드 + 디자인 토큰(컬러/타이포/밀도, 개발자 콘솔 톤) + 목 API/타입.
2. ① 프로젝트 지도(그래프 캔버스, 노드 6종·엣지·상태색, zoom-out).
3. ② 티켓 레인(step 타임라인) ↔ 지도 zoom-in 네비.
4. ③ 리뷰 페인(2분할 + 3액션 + 수정/인수 상태). ← 가장 공들여.
5. ④ 버그추적(노드/검색 → 소유 경로 하이라이트 → diff 점프).
6. 보조: 플랜 승인(step 편집·승인), 목표 입력.
7. 엣지 상태: 빈/로딩/에러/blocked.

각 단계마다 **앱을 실제로 띄워 확인**(스크린샷)하고, 와이어프레임/목업과 대조해 어긋나면 고친다.

## 5. 규율
- 와이어프레임/목업을 **충실히** 재현하되, 우리 컴포넌트 구조로 깔끔히 이식(목업의 인라인 스타일을 토큰/컴포넌트로 정리).
- 작고 외과적인 커밋. **백엔드를 멋대로 발명하지 마라**(목 인터페이스만). 모호하면 추측 말고 질문.
- minimal·unique하되 UX 최우선. 성능·명료성 위해 과한 모션/3D 지양.

## 6. 산출물
동작하는 v1 프론트엔드(목 API 위) + 화면별 스크린샷 + 짧은 구현 요약 + 실제 API 연결 지점(인터페이스) 정리.

시작: §0 문서들 + design 폴더를 읽고, 현 상태와 와이어프레임을 대조한 간단한 구현 계획을 먼저 제시한 뒤 §4-1부터 착수.

--- END PROMPT ---

---

## 참고 (사용자용 메모, 프롬프트엔 넣지 말 것)
- 와이어프레임은 단일 HTML(`docs/design/wireframes/llm-dev-control-tower.html`). Claude Code가 파일을 열어 읽게 하거나, 브라우저로 렌더한 스크린샷을 붙여넣어 특정 화면을 집중시킬 수 있음.
- 더 통제하려면: 이 프롬프트 대신 **writing-plans로 구현 계획**을 만든 뒤 단계 실행(체크포인트마다 정지·리뷰) — 한 방에 다 짓는 것보다 안전.
- 슬래시 커맨드로도 등록 가능: 이 PROMPT 블록을 `~/agent-system-v3/.claude/commands/build-ui.md` 로 저장하면 `/build-ui` 로 재사용.
- 백엔드가 생기면: 목 API 어댑터를 실제 FastAPI 클라이언트로 교체(같은 타입 인터페이스).
