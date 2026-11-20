# 연저펀 고정 배분 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 연금저축 계좌가 IRP와 같은 고정 배분(같은 종목·비중·점검 주기·밴드)으로 재조정 신호를 받게 하고, 월간 모멘텀 계산을 설정으로 끈다.

**Architecture:** 고정 배분 계산을 계좌와 목표표를 인자로 받는 함수 하나로 일반화하고 두 계좌가 함께 쓴다. `PENSION_STRATEGY` 설정 하나가 연저펀의 전략(고정/모멘텀)을 정하며, 스케줄러·수동 실행·화면이 이 값을 따른다.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, APScheduler, unittest(sqlite 메모리 DB)

**Spec:** `docs/specs/2026-11-20-pension-fixed-allocation-design.md`

## Global Constraints

- 브랜치 `feat/pension-fixed-allocation`에서 작업한다(main에서 분기). 푸시와 NAS 배포는 사용자 요청이 있을 때만.
- 목표표는 하나만 둔다: `PENSION_PORTFOLIO = IRP_PORTFOLIO` (같은 객체).
- 계좌 이름 문자열은 `"연금저축"`, `"IRP"` 그대로.
- 신호 dict의 키는 현행과 같다: `ticker, account_type, signal_date, target_weight, current_weight, weight_diff, current_price, total_assets, target_amount, current_amount, rebalance_amount, rebalance_quantity, action, needs_rebalance`.
- 판정: `weight_diff > band` → SELL, `< -band` → BUY, 그 외 HOLD. 밴드 기본값 `REBALANCE_BAND_PCT`(5.0).
- 모멘텀 관련 코드(`momentum_engine.py`, `adjusted_prices.py`, `calculate_pension_rebalance_signal`, `/momentum/view`)는 지우지 않는다.
- DB 스키마를 바꾸지 않는다. 네트워크·운영 DB 없이 테스트가 돈다.
- 테스트 실행: `python -m unittest test_fixed_allocation test_adjusted_momentum -v`
- 비밀값을 파일이나 로그에 쓰지 않는다.

## Review Focus

- 보유가 전혀 없는 계좌(총액 0): 0으로 나누지 않고 모든 종목이 HOLD, 수량 0.
- 종가가 없는 종목(가격 0): 수량 0, 예외 없음.
- 같은 종목을 두 계좌가 보유: 한 계좌의 계산에 다른 계좌의 수량이 섞이지 않는다.
- `PENSION_STRATEGY = "momentum"`으로 되돌렸을 때: 월간 모멘텀과 Top2 재조정이 이전과 똑같이 돌고, 반기 점검은 IRP만.
- 반기 점검에서 한 계좌 처리 중 예외: 다른 계좌는 계속 점검된다.

---

### Task 1: 설정과 고정 배분 계산

**Files:**
- Modify: `config.py` (포트폴리오 블록 아래)
- Modify: `rebalance_engine.py`
- Create: `test_fixed_allocation.py`

**Interfaces:**
- Produces:
  - `config.PENSION_STRATEGY: str = "fixed"`
  - `config.PENSION_PORTFOLIO` (= `IRP_PORTFOLIO`)
  - `config.fixed_allocation_accounts() -> dict[str, dict]` — 호출 시점의 `PENSION_STRATEGY`를 읽는다
  - `RebalanceEngine.calculate_fixed_rebalance_signal(signal_date, account_type: str, portfolio: dict, band_pct: float = REBALANCE_BAND_PCT) -> list[dict]`
  - `RebalanceEngine.calculate_rebalance_signal(signal_date)` — IRP 래퍼, 시그니처 유지

- [ ] **Step 1: 실패하는 테스트 작성** (`test_fixed_allocation.py`, `test_adjusted_momentum.py`의 `make_db` 방식과 같게)

```python
PORT = {"AAA": {"name": "A", "target_weight": 50.0},
        "BBB": {"name": "B", "target_weight": 30.0},
        "CCC": {"name": "C", "target_weight": 20.0},
        "CASH": {"name": "현금", "target_weight": 0.0}}
# 가격: AAA 10000, BBB 20000, CCC 5000, OLD 10000 (ETFPrice 한 행씩)

class FixedSignalTest(unittest.TestCase):
    def test_within_band_is_hold(self):
        # 연금저축: AAA 52주, BBB 14주, CCC 40주 -> 52/28/20% -> 전부 HOLD
    def test_transition_from_two_holdings(self):
        # 연금저축: AAA 50주(50만), OLD 50주(50만). 목표표에 OLD 없음
        # OLD: target 0, SELL, 수량 50 / AAA: HOLD / BBB: BUY 30만/20000=15주 / CCC: BUY 20만/5000=40주
    def test_other_account_holdings_are_ignored(self):
        # IRP에 AAA 1000주가 있어도 연금저축 계산의 total_assets는 연금저축 보유만
    def test_empty_account_has_no_division_error(self):
        # 보유 없음 -> 모든 신호 HOLD, current_weight 0, rebalance_quantity 0
    def test_missing_price_gives_zero_quantity(self):
        # 목표표에 가격 없는 종목 ZZZ 추가 -> 예외 없이 rebalance_quantity 0
    def test_signal_keys_and_account_type(self):
        # 키 집합이 Global Constraints와 같고 account_type == "연금저축"
    def test_irp_wrapper_matches_generic(self):
        # calculate_rebalance_signal(d) == calculate_fixed_rebalance_signal(d, "IRP", IRP_PORTFOLIO)

class StrategySwitchTest(unittest.TestCase):
    def test_fixed_includes_both_accounts(self):
        # PENSION_STRATEGY="fixed" -> list(fixed_allocation_accounts()) == ["연금저축", "IRP"], 두 값이 같은 객체
    def test_momentum_includes_irp_only(self):
        # config.PENSION_STRATEGY를 "momentum"으로 바꿨다 복원 -> ["IRP"]
```

- [ ] **Step 2: 실패 확인** — `python -m unittest test_fixed_allocation -v` → `AttributeError`/`ImportError`
- [ ] **Step 3: 구현** — `config.py`에 세 이름 추가. `rebalance_engine.py`에 `calculate_fixed_rebalance_signal` 추가하고 `calculate_current_weights`·`calculate_rebalance_signal`의 IRP 고정 로직을 그 함수 호출로 대체(`self.total_assets`는 계속 채운다). 대상 종목 순서는 목표표 순서, 그 뒤에 목표표 밖 보유 종목(티커 정렬).
- [ ] **Step 4: 통과 확인** — `python -m unittest test_fixed_allocation test_adjusted_momentum -v` → 전부 OK
- [ ] **Step 5: 커밋** — `feat(rebalance): account-generic fixed allocation signal`

### Task 2: 스케줄러

**Files:**
- Modify: `scheduler.py` (`_job_calculate_momentum`, `_job_check_rebalance`, `_job_collect_prices`)
- Modify: `test_fixed_allocation.py`

**Interfaces:**
- Consumes: Task 1의 `fixed_allocation_accounts()`, `calculate_fixed_rebalance_signal`
- Produces:
  - `JobScheduler._run_fixed_rebalance(db, account_type: str, portfolio: dict, signal_date) -> list[dict]` — 계산, 저장, 정확도 기록, 텔레그램(`label=account_type`), 웹훅(`"label": account_type`)을 한 계좌에 대해 수행하고 신호 목록을 돌려준다
  - `scheduler.pension_price_map() -> dict` — `"fixed"`면 `PENSION_PORTFOLIO`, 아니면 `PENSION_ETFS`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class SchedulerFixedTest(unittest.TestCase):
    # TelegramNotificationManager, WebhookNotifier, SignalAccuracyEngine은 unittest.mock.patch로 대체
    def test_run_fixed_rebalance_sends_alert_with_account_label(self):
        # _run_fixed_rebalance(db, "연금저축", PORT, d) -> send_rebalance_alert가 label="연금저축"로 1회,
        # 웹훅 payload["label"] == "연금저축", RebalanceSignal 행이 account_type="연금저축"로 저장
    def test_one_account_failure_does_not_stop_the_other(self):
        # _run_fixed_rebalance가 첫 계좌에서 예외를 던지게 patch -> _check_fixed_accounts(db, d)가 두 번째 계좌도 호출
    def test_momentum_job_is_skipped_when_fixed(self):
        # PENSION_STRATEGY="fixed" -> _job_calculate_momentum()이 get_db를 호출하지 않는다
    def test_pension_price_map_follows_strategy(self):
        # "fixed" -> PENSION_PORTFOLIO, "momentum" -> PENSION_ETFS
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
  - `_job_calculate_momentum` 맨 앞: `PENSION_STRATEGY != "momentum"`이면 `logger.info` 후 return.
  - `_job_check_rebalance`: 묵은 시세 가드의 대상을 `fixed_allocation_accounts()` 전체 종목 합집합으로. 계산부를 `_check_fixed_accounts(db, signal_date)`로 옮기고, 그 안에서 계좌별로 `_run_fixed_rebalance`를 try/except로 감싸 호출.
  - `_job_collect_prices`: 연금저축의 `etf_map`을 `pension_price_map()`으로.
- [ ] **Step 4: 통과 확인** — 전체 테스트 OK
- [ ] **Step 5: 커밋** — `feat(scheduler): check both accounts with the fixed allocation`

### Task 3: 수동 실행과 화면

**Files:**
- Modify: `main.py` (`trigger_check_pension_rebalance`)
- Modify: `portfolio_engine.py:112-123`
- Modify: `momentum_view_server.py:209-218`
- Modify: `test_fixed_allocation.py`

**Interfaces:**
- Consumes: Task 1, Task 2의 `_run_fixed_rebalance`
- Produces:
  - `POST /api/v1/jobs/check-pension-rebalance?notify=false` — 응답 `signals[]`에 `name`, `current_price`, `rebalance_quantity` 추가, 최상위에 `"strategy"` 추가
  - `momentum_view_server.target_weights_for(account_type: str, holdings: list[dict]) -> dict[str, float]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class ViewTargetTest(unittest.TestCase):
    def test_pension_targets_come_from_portfolio_when_fixed(self):
        # target_weights_for("연금저축", []) == {t: v["target_weight"] for t, v in PENSION_PORTFOLIO.items()}
    def test_pension_targets_use_top2_when_momentum(self):
        # "momentum": holdings [{"ticker":"X","is_selected":True},{"ticker":"Y","is_selected":False}] -> {"X":50.0,"Y":0.0}
    def test_irp_targets_unchanged(self):

class ManualEndpointTest(unittest.TestCase):
    # fastapi.testclient.TestClient + get_db 의존성 override(sqlite), 스케줄러 시작은 patch
    def test_fixed_response_has_quantities_and_names(self):
        # 응답 strategy == "fixed", 각 signal에 name/current_price/rebalance_quantity 존재
    def test_notify_false_sends_nothing(self):
    def test_notify_true_sends_one_alert(self):
        # send_rebalance_alert 1회, label="연금저축"

class PortfolioPerformanceTest(unittest.TestCase):
    def test_is_selected_false_for_all_when_fixed(self):
        # MomentumScore에 is_selected=True 행이 있어도 "fixed"면 모든 holding의 is_selected는 False
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
  - `main.py`: `"fixed"`면 `calculate_fixed_rebalance_signal(d, "연금저축", PENSION_PORTFOLIO)`, 아니면 기존 함수. `notify=True`이고 `"fixed"`면 `get_scheduler()._run_fixed_rebalance(...)`로 저장·알림까지 한 번에(중복 저장 금지). docstring을 전략 중립으로 고친다.
  - `portfolio_engine.py`: Top2 조회를 `PENSION_STRATEGY == "momentum"`일 때만.
  - `momentum_view_server.py`: 목표 비중 계산을 `target_weights_for`로 빼고 호출.
- [ ] **Step 4: 통과 확인** — 전체 테스트 OK. `python -c "import main, momentum_view_server"`가 예외 없이 끝난다(환경변수 없이 import 가능한지 포함).
- [ ] **Step 5: 커밋** — `feat(pension): manual check and portfolio view follow the fixed allocation`

### Task 4: 문서

**Files:**
- Modify: `config.py`의 `PENSION_ETFS` 주석("듀얼 모멘텀 전략" → 모멘텀 유니버스이며 현재 전략은 `PENSION_STRATEGY`를 따른다는 설명)
- Modify: `README.md`에 전략 스위치와 전환 절차 3줄(설계 문서의 "전환 절차"를 가리킨다)

- [ ] **Step 1: 수정** — 코드 동작은 바꾸지 않는다
- [ ] **Step 2: 확인** — 전체 테스트 OK
- [ ] **Step 3: 커밋** — `docs: pension strategy switch and transition steps`
