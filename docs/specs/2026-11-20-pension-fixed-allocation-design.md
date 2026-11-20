# 연저펀 고정 배분 전환 설계

작성일 2026-11-20. 사용자 승인: 2026-11-20 대화.

## 목적

연금저축(연저펀) 계좌를 월간 모멘텀 Top2 전략에서 IRP와 같은 고정 배분 전략으로 바꾼다.
두 계좌가 같은 종목, 같은 목표 비중, 같은 점검 주기와 밴드로 운영된다.

근거: PensionBacktest 비교(2006-01~2026-10, 비용 차감 후)에서 고정 배분이 변동성 9.7% / MDD -15.1% / 샤프 0.82,
모멘텀 전략이 15.2% / -28.0% / 0.59였다. 사용자는 은퇴 자금으로서 안정성을 우선한다.

## 확정된 결정

| 항목 | 결정 |
|---|---|
| 연저펀 종목·비중 | IRP와 완전히 동일 (`IRP_PORTFOLIO` 표 그대로) |
| 미국 30년 국채 | 환헤지형 453850 유지 |
| 전환 | 한 번에 (배포 후 수동 점검 1회) |
| 월간 모멘텀 계산·알림 | 끔 (코드는 남기고 설정으로 다시 켤 수 있게) |

## 하지 않는 것

- 모멘텀 엔진, 수정주가 기능, 모멘텀 상세 화면 삭제 (남겨 둔다)
- IRP의 점검 주기(1월·7월 첫 영업일)와 밴드(5%p) 변경
- 밴드를 벗어난 종목만 조정하는 현행 방식 변경 (백테스트는 전체 재조정이었지만 운영은 현행 유지)
- 자동 매매 (수량 안내만 한다)
- DB 스키마 변경

## 검토한 방법

1. **고정 배분 계산을 계좌 공통 함수로 (채택)**: 계좌와 목표 비중표를 인자로 받는 함수 하나를 두 계좌가 쓴다. 두 계좌가 같은 규칙이라는 것이 코드로 보장된다.
2. 연저펀용 고정 배분 함수를 따로 추가: 같은 로직이 두 벌이 된다.
3. 모멘텀 선정 결과를 고정값으로 덮어쓰기: 쓰지 않는 계산이 매달 돌고 구조가 헷갈린다.

## 설계

### 설정 (`config.py`)

- `PENSION_STRATEGY = "fixed"` (`"momentum"`으로 바꾸면 이전 동작)
- `PENSION_PORTFOLIO = IRP_PORTFOLIO` (같은 객체. 표는 하나만 둔다)
- `fixed_allocation_accounts()` → `PENSION_STRATEGY`가 `"fixed"`면 `{"연금저축": PENSION_PORTFOLIO, "IRP": IRP_PORTFOLIO}`, 아니면 `{"IRP": IRP_PORTFOLIO}`
- `PENSION_ETFS`는 모멘텀 유니버스로 그대로 둔다. 시세 수집 대상에도 계속 포함된다(모멘텀을 다시 켤 때 이력이 끊기지 않게).

### 재조정 계산 (`rebalance_engine.py`)

- `calculate_fixed_rebalance_signal(signal_date, account_type, portfolio, band_pct=REBALANCE_BAND_PCT)` 신설
  - 대상 종목 = 목표표의 종목 ∪ 그 계좌에서 보유 중인 종목. 목표표에 없는 보유 종목은 목표 0%.
  - 판정은 현행 IRP와 같다: 비중 차이 > 밴드면 SELL, < -밴드면 BUY, 그 외 HOLD. 수량은 목표 금액과의 차이 ÷ 종가.
  - 신호 dict의 키는 현행과 같다(`account_type` 포함).
- `calculate_rebalance_signal(signal_date)`는 IRP에 대해 위 함수를 부르는 얇은 래퍼로 남긴다.
- `calculate_pension_rebalance_signal`(모멘텀 Top2용)은 그대로 둔다.

IRP 동작 변화 한 가지: 목표표에 없는 종목을 IRP에서 보유 중이면 이제 전량 매도 신호가 나온다(이전에는 무시).

### 스케줄 (`scheduler.py`)

- `_job_calculate_momentum`: `PENSION_STRATEGY != "momentum"`이면 로그만 남기고 끝낸다.
- `_job_check_rebalance`: `fixed_allocation_accounts()`의 계좌를 차례로 점검한다. 묵은 시세 가드는 전체 대상 종목 합집합에 대해 한 번. 계좌별로 신호 저장, 정확도 기록, 텔레그램 알림(라벨 = 계좌 이름), 웹훅(`label` = 계좌 이름)을 보낸다. 한 계좌의 실패가 다른 계좌 점검을 막지 않는다.
- 일일 시세 알림: 연금저축의 종목표를 `"fixed"`일 때 `PENSION_PORTFOLIO`로 쓴다.

### 수동 실행 (`main.py`)

- `POST /api/v1/jobs/check-pension-rebalance?notify=false`
  - `"fixed"`면 고정 배분 계산, `"momentum"`이면 기존 Top2 계산.
  - 응답의 각 신호에 `name`, `current_price`, `rebalance_quantity`를 추가한다.
  - `notify=true`면 텔레그램 재조정 알림을 보낸다(전환 때 사용).
- `POST /api/v1/jobs/check-rebalance`(IRP)는 그대로.

### 화면 (`portfolio_engine.py`, `momentum_view_server.py`)

- 포트폴리오 화면의 연금저축 목표 비중을 `"fixed"`일 때 `PENSION_PORTFOLIO`에서 가져온다.
- `is_selected`(Top2 표시)는 `"momentum"`일 때만 채운다.

## 전환 절차

1. NAS 배포, 서비스 재시작(사용자).
2. `check-pension-rebalance?notify=true` 수동 실행 → 6종목의 매수·매도 수량이 텔레그램으로 온다.
   현재 보유(나스닥100, 배당다우존스 각 약 50%)는 목표(15%)에서 5%p 넘게 벗어나 있고, 새 종목 4개는 0%라 모두 신호가 난다.
3. 사용자가 직접 매매하고 포트폴리오 화면에 보유 수량을 입력한다.
4. 이후 정기 점검은 1월·7월 첫 영업일. 다음은 2027-01-04.

## 되돌리기

`PENSION_STRATEGY = "momentum"`으로 바꾸고 재시작하면 이전 동작으로 돌아간다.

## 테스트

`test_fixed_allocation.py`(unittest, sqlite 메모리 DB, 네트워크 불필요):
목표표 밖 보유 종목의 전량 매도, 밴드 안 HOLD, 전환 시나리오(2종목 50:50 → 6종목), 계좌 분리(다른 계좌 보유는 섞이지 않음),
보유가 없을 때 0으로 나누지 않음, IRP 래퍼의 기존 결과 유지, 전략 스위치에 따른 대상 계좌.
