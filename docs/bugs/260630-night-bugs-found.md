1. Remove + and - signs on git diff view. I can recognize if the lines are added or removed by color. Adding signs are redundant, and confuses the users.
2. Even though a ticket is in executing state, the next task/ticket's state does not change from `planned` to `executing`, which confuses the users if the system froze or in progress.
3. While a ticket is executing, I cannot get suggested list of plans of the other tickets(I can't plan for the next ticket while another ticket's in progress).
4. Sending Request to `*/graph` API consistently looks inefficient and waste the hardware resource of the server application. Is there any alternatives?
5. Tests written under `tests` directory are not interpreted as contents to be listed on `Tests` pane.

---

## 수정 완료 (ultracode: 병렬 진단+적대적 검증 → 순차 구현)

1. **diff +/- 제거** — `web/src/components/review/DiffView.tsx`: 표시 텍스트를 `line.slice(1)`로(선행 마커 제거),
   색상 클래스(`cls`)는 원본 prefix에서 그대로 도출 → 색은 유지, 부호만 제거(컨텍스트 줄 정렬도 보존). + `DiffView.test.tsx`.
2. **실행 중 step이 `planning`에 멈춰 보임** — `routers/lifecycle.py` `on_step_start`가 step 노드 status를
   `executing`으로 설정(이전엔 ticket activity만 갱신, 노드는 커밋 시점에야 awaiting_review). 비동기 approve-next도
   다음 step을 즉시 executing 표시(PLANNED 깜빡임 제거). + 블로킹 executor 통합 테스트.
3. **실행 중 다른 티켓 계획 불가** — Phase 3에서 넣은 단일 `_GRAPH_LOCK`(긴 invoke 전체를 잠금)이 원인.
   **프로젝트별 실행 락**(`_EXEC_LOCKS[pid]`)으로 교체: 실행(invoke)만 프로젝트 단위로 직렬화(공유 repo 보호),
   읽기/propose/get_state는 락-프리 → 한 티켓 실행 중에도 다른 티켓 plan 제안 가능. 체크포인트 안전성은
   PostgresSaver 자체 락(postgres)·thread_id 분리(memory)에 의존. db.py 무변경. + 동시성 테스트(제안 즉시 반환 확인).
4. **`*/graph` 폴링 비효율** — 프로젝트별 **리비전 카운터**(`graph/revision.py`) + SQLAlchemy commit 리스너(`db.py`)로
   노드/엣지 커밋 시에만 증가, `GET /graph`가 약한 ETag로 노출. `If-None-Match` 일치 시 **304**(DB 조회·직렬화 스킵).
   FE(`HttpApiClient`)는 조건부 GET + 304 시 캐시 재사용(폴링 1.5s는 fallback 유지). BOOT nonce로 재시작 시 ETag 무효화.
   CORS `expose_headers=[ETag]`. + backend/FE 테스트. (대안 SSE는 더 큰 변경이라 보류 — 폴링 유지하며 비용만 제거.)
5. **tests/ 파일이 Tests 패널에 안 뜸** — `graph/diff_ingest.py`가 모든 파일을 code_region으로 분류하던 것을,
   테스트 경로(`tests/`·`__tests__/`·`test_*.py`·`*_test.py`·`*.test|spec.[jt]sx?`)는 `kind=test` 노드 +
   `tested_by` 엣지로 분류(상호배타 → code_region과 중복 안 됨). + 분류/멱등 테스트. (단, simulated 모드/seed_demo는
   테스트 파일을 커밋하지 않으므로 데모 p1은 여전히 비어 있음 — 실제 실행에서 테스트 파일 커밋 시 표시됨.)

**검증**: backend **74 passed** / frontend **tsc clean + 54 passed**. 라이브: 호스트 api(8099, --reload)가 `/graph`에
ETag 반환 + 조건부 요청 304 확인, web 컨테이너 재빌드(:8080, `If-None-Match` 포함). 모두 working tree(미커밋).
