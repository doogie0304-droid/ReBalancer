# -*- coding: utf-8 -*-
"""
연저펀 Top2 페어(고정) 대상 밴드형 재조정(+/-10%p) vs 방치(Buy&Hold) 백테스트

전제 및 한계:
- 실데이터가 1년(약 260거래일)뿐이라 모멘텀 Top2가 실제로 "바뀌는" 시나리오는
  검증할 수 없음. 사용자가 물어본 질문("Top2 종목은 그대로인데 비중만 벌어지는 경우")에
  정확히 대응하는 단순화: 현재 실제 선정된 Top2 페어를 고정한 채, 그 페어의 1년 가격
  히스토리 전체에 대해 두 전략을 비교.
- 매매비용/세금/슬리피지는 0으로 가정 (ETF 매매비용이 낮은 편이라 결과 방향성엔
  큰 영향 없을 것으로 가정하지만, 절대 수치엔 낙관적 편향이 있을 수 있음).
- 1년치 단일 경로(single historical path)이므로 CAGR/MDD/Sharpe는 통계적으로
  유의미한 추정치가 아니라 "이 1년 동안 이랬다"는 참고치.
"""
import math
from datetime import date

from database import get_db, ETFPrice
from momentum_engine import MomentumEngine
from config import PENSION_ETFS

BAND_PCT = 10.0  # +/- 10%p
INITIAL_CAPITAL = 10_000_000.0


def get_price_series(db, ticker):
    rows = (
        db.query(ETFPrice)
        .filter(ETFPrice.ticker == ticker)
        .order_by(ETFPrice.price_date.asc())
        .all()
    )
    return {r.price_date: r.close_price for r in rows}


def align_series(series_a, series_b):
    common_dates = sorted(set(series_a.keys()) & set(series_b.keys()))
    return common_dates, [series_a[d] for d in common_dates], [series_b[d] for d in common_dates]


def simulate_buy_and_hold(prices_a, prices_b, initial_capital):
    shares_a = (initial_capital / 2) / prices_a[0]
    shares_b = (initial_capital / 2) / prices_b[0]
    values = []
    for pa, pb in zip(prices_a, prices_b):
        values.append(shares_a * pa + shares_b * pb)
    return values


def simulate_band_rebalance(prices_a, prices_b, initial_capital, band_pct):
    shares_a = (initial_capital / 2) / prices_a[0]
    shares_b = (initial_capital / 2) / prices_b[0]
    values = []
    rebalance_count = 0
    for pa, pb in zip(prices_a, prices_b):
        value_a = shares_a * pa
        value_b = shares_b * pb
        total = value_a + value_b
        weight_a_pct = (value_a / total * 100) if total > 0 else 50.0

        if abs(weight_a_pct - 50.0) > band_pct:
            shares_a = (total / 2) / pa
            shares_b = (total / 2) / pb
            rebalance_count += 1
            value_a = shares_a * pa
            value_b = shares_b * pb
            total = value_a + value_b

        values.append(total)
    return values, rebalance_count


def compute_metrics(values, trading_days_per_year=252):
    n = len(values)
    total_return = values[-1] / values[0] - 1
    years = (n - 1) / trading_days_per_year
    cagr = (values[-1] / values[0]) ** (1 / years) - 1 if years > 0 else total_return

    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (v - peak) / peak
        max_dd = min(max_dd, dd)

    daily_returns = [values[i] / values[i - 1] - 1 for i in range(1, n)]
    mean_r = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std_r = math.sqrt(variance)
    sharpe = (mean_r / std_r) * math.sqrt(trading_days_per_year) if std_r > 0 else 0.0

    return {
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "mdd_pct": max_dd * 100,
        "sharpe": sharpe,
    }


def main():
    db = next(get_db())

    # 1) 실제 최신 momentum 계산으로 현재 Top2 확인 (최신 가격일 기준)
    engine = MomentumEngine(db)
    latest_price_date = (
        db.query(ETFPrice.price_date)
        .order_by(ETFPrice.price_date.desc())
        .first()[0]
    )
    scores = []
    for ticker in PENSION_ETFS.keys():
        s = engine.calculate_momentum_score(ticker, latest_price_date)
        scores.append(s)
    scores.sort(key=lambda s: s["weighted_score"], reverse=True)
    top2 = scores[:2]
    ticker_a, ticker_b = top2[0]["ticker"], top2[1]["ticker"]
    name_a = PENSION_ETFS[ticker_a]["name"]
    name_b = PENSION_ETFS[ticker_b]["name"]

    print(f"기준일: {latest_price_date}")
    print(f"현재 Top2: {ticker_a}({name_a}, score={top2[0]['weighted_score']:.2f}), "
          f"{ticker_b}({name_b}, score={top2[1]['weighted_score']:.2f})")
    print()

    # 2) 두 종목의 전체 가격 히스토리 정렬
    series_a = get_price_series(db, ticker_a)
    series_b = get_price_series(db, ticker_b)
    dates, prices_a, prices_b = align_series(series_a, series_b)
    print(f"백테스트 기간: {dates[0]} ~ {dates[-1]} ({len(dates)}거래일)")
    print()

    # 3) 두 전략 시뮬레이션
    bh_values = simulate_buy_and_hold(prices_a, prices_b, INITIAL_CAPITAL)
    bh_metrics = compute_metrics(bh_values)

    # 마지막 비중(방치 시 얼마나 벌어졌는지 확인용)
    final_value_a_bh = (INITIAL_CAPITAL / 2 / prices_a[0]) * prices_a[-1]
    final_value_b_bh = (INITIAL_CAPITAL / 2 / prices_b[0]) * prices_b[-1]
    final_weight_a_bh = final_value_a_bh / (final_value_a_bh + final_value_b_bh) * 100

    print(f"방치(Buy&Hold) 최종 비중: {ticker_a}={final_weight_a_bh:.1f}% / {ticker_b}={100 - final_weight_a_bh:.1f}%"
          f" (시작 50.0%/50.0%, 최대 이탈폭 참고용)")
    print()

    header = f"{'밴드폭':<10}{'CAGR':>10}{'MDD':>10}{'Sharpe':>10}{'재조정횟수':>12}"
    print("=" * 70)
    print(f"{'전략':<10}{'CAGR':>10}{'MDD':>10}{'Sharpe':>10}{'재조정횟수':>12}")
    print("-" * 70)
    print(f"{'방치':<10}{bh_metrics['cagr_pct']:>9.2f}%{bh_metrics['mdd_pct']:>9.2f}%{bh_metrics['sharpe']:>10.2f}{'-':>12}")

    for band in (10.0, 5.0, 2.0, 1.0):
        band_values, rebalance_count = simulate_band_rebalance(prices_a, prices_b, INITIAL_CAPITAL, band)
        band_metrics = compute_metrics(band_values)
        label = f"밴드{band:g}%p"
        print(f"{label:<10}{band_metrics['cagr_pct']:>9.2f}%{band_metrics['mdd_pct']:>9.2f}%"
              f"{band_metrics['sharpe']:>10.2f}{rebalance_count:>12d}")
    print("=" * 70)

    db.close()


if __name__ == "__main__":
    main()
