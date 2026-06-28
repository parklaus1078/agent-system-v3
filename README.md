# Agent System v3 — LLM Dev Control Tower

> **LLM 개발의 통제탑.** 거친 목표("Todo 앱 만들어")를 주면, 시스템이 LLM을
> **작고·보이고·리뷰 가능한 step**으로 일하게 하고, 일하는 동안 **살아있는 지도**
> (목표→티켓→step→코드영역→테스트→결정)를 짓는다. 뭔가 깨지면 지도가
> *어디를 볼지* 답한다.

## 왜 v3 (greenfield)

v2는 *자율성(autonomy)* 을 최적화했지만, 실제로 필요한 건 정반대인
**가시성·통제(visibility & control)** 였다. 큰 프로젝트에서 LLM이 블랙박스 안에서
일하고 결과 + 텍스트 덩어리만 던지니 ⓐ *어디서 QA*할지, ⓑ *버그가 어디*인지
알 수 없었던 것이 핵심 고통. v3는 통제·추적·외과적 디버그를 1차 가치로 다시 짓는다.

## 핵심 결정 (요약)

- **계획 먼저 → step마다 정지·리뷰** (가장 짧은 목줄)
- **살아있는 기능↔코드 지도** — `git diff`가 진실원천(에이전트 주장 아님)
- **3겹 기억** — 프로젝트별 격리 그래프(지도=컨텍스트) + 개인 cross-project 위키
- **시스템이 step 자동 실행** (헤드리스, 견고하게)
- 스택: **FastAPI + Postgres/pgvector + LangGraph(StateGraph·HITL interrupt·PostgresSaver) + React 지도 UI**
- **v1 = 한 티켓 수직 슬라이스** (plan → step 자동실행 → step마다 지도 갱신 → 리뷰 게이트)

## 상태

**설계 확정, 구현 전.** 다음 단계는 구현 계획(plan) 작성.

## 문서

- 설계 spec: [`docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md`](docs/superpowers/specs/2026-06-28-llm-dev-control-tower-design.md)
- 전신(v2) 회고·갭분석: `~/agent-system-v2/docs/` (sequence diagrams, spec-conformance gap analysis)
