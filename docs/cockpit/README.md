# Living Cockpit — CP 구현 프롬프트 (goal commands)

`docs/living-cockpit-design.md`(설계 spec)의 **단계별 롤아웃 CP0–CP4**를 각각 Claude Code에 넘길
**goal 프롬프트**로 분해한 문서들. 사용:

```
/goal @docs/cockpit/CP0-governance.md
```
(각 파일 내용이 그대로 goal이 됨. 한 CP가 끝나고 그린이면 다음 CP로.)

## 순서
- **CP0(거버넌스)** 와 **CP1(throttle/자율루프)** 는 비교적 독립적 — 둘 중 아무거나 먼저.
- CP2(채널) → CP3(steer) → CP4(백로그/양방향)는 이 순서 권장(뒤가 앞을 전제).

## 모든 CP 공통 규약 (각 프롬프트가 이 절을 전제로 함)
1. **먼저 읽어라**: `docs/living-cockpit-design.md` 전체(특히 확정 4결정·해당 CP·열린 질문). 이 spec이 진실의 원천.
2. **기존 걸 갈아엎지 마라**: Plan 1–4 + night-bug 수정 위에 *얹는다*. 재사용 자산:
   async 실행 + `data.activity`(Phase 3), `decision` 노드 + RAG 주입, per-project 실행 락(night #3),
   리비전+ETag/304 폴링(night #4), 리뷰 게이트/takeover 로직.
3. **테스트 게이트 (필수, CP 완료 조건)**:
   - 백엔드: `cd api && DATABASE_URL=sqlite+pysqlite:///:memory: ASV3_AGENT_MODE=simulated ASV3_CHECKPOINTER=memory .venv/bin/python -m pytest` → **전부 그린**. (현재 기준선 74 passed.)
   - 프론트: `cd web && npx tsc --noEmit && npx vitest run` → **그린**. (현재 기준선 54 passed.)
   - 신규 동작엔 **테스트를 추가**하고, 기존 테스트를 깨지 마라. 테스트는 `conftest.py`가 `ASV3_ASYNC_EXEC=0`(동기)로 고정 — 비동기 동작은 테스트 안에서 명시적으로 켠다(`monkeypatch.setenv`).
4. **시뮬레이트 모드 우선**: `ASV3_AGENT_MODE=simulated`에서 네트워크·API 키 없이 결정적으로 동작해야 함.
   새 AI 호출(라우터 등)도 시뮬 stub을 둬 테스트가 결정적이게.
5. **불변식**: 라이브 UI는 체크포인터를 폴링하지 않는다(`getGraph`=DB만). 단일 사용자 가정. `git diff`가 기능↔코드 지도의 진실.
6. **배포(라이브 확인 시)**: api는 호스트에서 `--reload`(자동 반영). web은 prod 빌드라 변경 후
   `docker compose -f docker-compose.hostapi.yml up -d --build web` 필요. UI는 **:8080**(:5180 아님).
7. **브랜치/커밋**: 현재 작업 브랜치 `bug/record`. CP마다 **브랜치를 따로 떼서**(예: `cp0-governance`) 작업.
   커밋은 사람이 한다 — 요청 없으면 커밋하지 말 것.
8. **진행 기록**: CP 완료 시 `docs/living-cockpit-design.md` 하단(또는 별도 진행 로그)에 무엇을 했는지 한 단락 남겨라.

## 핵심 파일 지도 (참고)
- 백엔드: `api/app/routers/{lifecycle,projects,graph}.py`, `api/app/services/{planner,executor,lifecycle_graph,prompt_build}.py`,
  `api/app/graph/{store,diff_ingest,revision}.py`, `api/app/{db,schemas,main}.py`.
- 프론트: `web/src/api/{ApiClient,dto}.ts` + `api/http/HttpApiClient.ts` + `api/mock/MockApiClient.ts`,
  `web/src/store/useStore.ts`, `web/src/components/{Shell,map/ProjectMap,board/TicketBoard,review/*,home/*}`.
- 개입 지점(현재): project-planner(`projects.py`) · ticket-planner & executor(`lifecycle.py _build`).
