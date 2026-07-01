# 260630 — PostgresSaver "the connection is closed" → silent in-memory fallback

발견: real 모드 + Postgres 체크포인터(`ASV3_CHECKPOINTER=postgres`/`auto` + postgres `DATABASE_URL`)로
"분해 시작" 시 로그에 `ERROR asv3.db | PostgresSaver unavailable; using in-memory checkpointer` +
`psycopg.OperationalError: the connection is closed`. 앱은 MemorySaver로 graceful fallback 하므로
플랜은 진행되지만, **설정한 Postgres 영속성(재시작 간 lifecycle 상태 유지)이 적용되지 않음.**

- 심각도: 🟠 MED (graceful degrade이지만 의도한 durable Postgres가 동작 안 함)
- 상태: ✅ FIXED (라이브 Postgres에 검증)

## 근본원인
`api/app/db.py` `make_checkpointer`:
```python
cp = PostgresSaver.from_conn_string(_libpq_url(DATABASE_URL)).__enter__()
cp.setup()
```
`PostgresSaver.from_conn_string(...)`는 **컨텍스트 매니저**(generator 기반)를 반환한다. `.__enter__()`로
연결을 열고 saver를 얻지만, **그 CM 객체를 아무도 참조하지 않아** 곧 GC됨 → CM의 정리 코드(`with
Connection.connect(...) as conn:` 종료)가 실행되어 **연결을 닫아버림**. 다음 줄 `cp.setup()`(및 이후 모든
사용)이 닫힌 연결을 만나 `OperationalError: the connection is closed` → except가 잡아 MemorySaver로 폴백.
기존 코드의 잠재 버그였고, Postgres를 실제로 쓰기 시작하니 드러남.

## 수정
긴 수명의 연결을 직접 열고 **모듈 전역으로 참조를 유지**(GC 방지). PostgresSaver가 요구하는 연결 옵션
(`autocommit=True, prepare_threshold=0, row_factory=dict_row`)으로 생성:
```python
from psycopg import Connection
from psycopg.rows import dict_row
_PG_CONN = Connection.connect(_libpq_url(DATABASE_URL), autocommit=True, prepare_threshold=0, row_factory=dict_row)
cp = PostgresSaver(_PG_CONN); cp.setup()
```
`_PG_CONN`을 전역에 보관 → 프로세스 수명 동안 연결 유지. (psycopg3 Connection은 스레드 안전 — 동시 작업은
직렬화. 단일 사용자 로컬에선 충분; 고동시성이면 ConnectionPool로 업그레이드.)

위치: `api/app/db.py` `make_checkpointer` (+ `_PG_CONN` 전역).

## 검증
라이브 Postgres(`postgresql+psycopg://ct:ct@localhost:5432/controltower`, 사용자 venv)에서:
체크포인터 타입 = `PostgresSaver`(폴백 아님), `gc.collect()` 후 `get_tuple()` 정상 → 연결 유지 확인.

## 적용
**백엔드를 재시작**하면 Postgres 체크포인터가 동작(durable). 폴백으로 in-memory에 있던 진행 중 lifecycle
상태는 재시작 시 사라지므로, 재시작 후 해당 티켓은 다시 plan/approve 하면 됨.
