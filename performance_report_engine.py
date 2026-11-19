# -*- coding: utf-8 -*-
"""ReBalancer - 시계열 성과 리포트 엔진

수익률 계산은 Simple(Original) Dietz 근사 방식이다. 입금 시점별 일수 가중을 하는
Modified Dietz나 XIRR이 아니며, 개인용 봇 성격상 정밀도보다 단순함을 우선한 근사치임을
명시한다 (입금이 월 1회 이하 빈도라 근사 오차가 크지 않다고 판단).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from database import PortfolioSnapshot, CashFlow
from portfolio_engine import PortfolioEngine

logger = logging.getLogger(__name__)

ACCOUNT_TYPES = ["연금저축", "IRP"]


class PerformanceReportEngine:
    """계좌별 시계열 성과 스냅샷/리포트 엔진"""

    def __init__(self, db: Session):
        self.db = db

    def save_daily_snapshot(self, snapshot_date: date = None) -> dict:
        """계좌별 오늘(또는 지정일) 스냅샷 저장. 같은 날짜에 이미 있으면 갱신(upsert)."""
        snapshot_date = snapshot_date or date.today()
        portfolio_engine = PortfolioEngine(self.db)
        saved = []

        for account_type in ACCOUNT_TYPES:
            performance = portfolio_engine.calculate_portfolio_performance(account_type)

            existing = self.db.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.snapshot_date == snapshot_date,
                PortfolioSnapshot.account_type == account_type
            ).first()

            if existing:
                existing.total_value = performance["total_value"]
                existing.total_cost = performance["total_cost"]
            else:
                self.db.add(PortfolioSnapshot(
                    snapshot_date=snapshot_date,
                    account_type=account_type,
                    total_value=performance["total_value"],
                    total_cost=performance["total_cost"],
                    created_at=datetime.now(),
                ))
            saved.append(account_type)

        self.db.commit()
        logger.info(f"[Portfolio Snapshot] Saved for {snapshot_date}: {saved}")
        return {"saved": saved, "date": snapshot_date.isoformat()}

    def record_cash_flow(self, flow_date: date, account_type: str, amount: float, memo: str = "") -> dict:
        """입출금 이력 신규 기록"""
        flow = CashFlow(
            flow_date=flow_date,
            account_type=account_type,
            amount=amount,
            memo=memo,
            created_at=datetime.now(),
        )
        self.db.add(flow)
        self.db.commit()
        self.db.refresh(flow)
        logger.info(f"[Cash Flow] Recorded: {account_type} {amount:+,.0f} on {flow_date} ({memo})")
        return {
            "id": flow.id,
            "flow_date": flow.flow_date.isoformat(),
            "account_type": flow.account_type,
            "amount": flow.amount,
            "memo": flow.memo,
        }

    def get_cash_flow(self, flow_id: int) -> Optional[dict]:
        """단건 입출금 이력 조회 (수정 폼 프리필용)"""
        flow = self.db.query(CashFlow).filter(CashFlow.id == flow_id).first()
        if not flow:
            return None
        return {
            "id": flow.id,
            "flow_date": flow.flow_date.isoformat(),
            "account_type": flow.account_type,
            "amount": flow.amount,
            "memo": flow.memo,
        }

    def update_cash_flow(self, flow_id: int, flow_date: date, account_type: str, amount: float, memo: str = "") -> Optional[dict]:
        """입출금 이력 수정"""
        flow = self.db.query(CashFlow).filter(CashFlow.id == flow_id).first()
        if not flow:
            return None
        flow.flow_date = flow_date
        flow.account_type = account_type
        flow.amount = amount
        flow.memo = memo
        self.db.commit()
        logger.info(f"[Cash Flow] Updated id={flow_id}: {account_type} {amount:+,.0f} on {flow_date} ({memo})")
        return {
            "id": flow.id,
            "flow_date": flow.flow_date.isoformat(),
            "account_type": flow.account_type,
            "amount": flow.amount,
            "memo": flow.memo,
        }

    def delete_cash_flow(self, flow_id: int) -> bool:
        """입출금 이력 삭제"""
        flow = self.db.query(CashFlow).filter(CashFlow.id == flow_id).first()
        if not flow:
            return False
        self.db.delete(flow)
        self.db.commit()
        logger.info(f"[Cash Flow] Deleted id={flow_id}")
        return True

    def get_cash_flows(self, account_type: str = None, limit: int = 50) -> list:
        """최근 입출금 이력 조회 (최신순)"""
        query = self.db.query(CashFlow)
        if account_type:
            query = query.filter(CashFlow.account_type == account_type)
        flows = query.order_by(CashFlow.flow_date.desc(), CashFlow.id.desc()).limit(limit).all()
        return [
            {
                "id": f.id,
                "flow_date": f.flow_date.isoformat(),
                "account_type": f.account_type,
                "amount": f.amount,
                "memo": f.memo,
            }
            for f in flows
        ]

    def _get_snapshot_value(self, account_type: str, on_or_before: date) -> Optional[float]:
        """on_or_before 이전(포함) 최신 스냅샷. 없으면 그 이후 최초 스냅샷으로 대체(소급 데이터 없음)."""
        snapshot = self.db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_type == account_type,
            PortfolioSnapshot.snapshot_date <= on_or_before
        ).order_by(PortfolioSnapshot.snapshot_date.desc()).first()

        if not snapshot:
            snapshot = self.db.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.account_type == account_type,
                PortfolioSnapshot.snapshot_date > on_or_before
            ).order_by(PortfolioSnapshot.snapshot_date.asc()).first()

        return snapshot.total_value if snapshot else None

    def get_previous_day_value(self, account_type: str, before_date: date) -> Optional[float]:
        """before_date 전날 이전(포함) 가장 최근 스냅샷의 total_value. 없으면 None."""
        return self._get_snapshot_value(account_type, before_date - timedelta(days=1))

    def calculate_period_return(self, account_type: str, start_date: date, end_date: date) -> dict:
        """Simple Dietz 근사 수익률 계산"""
        start_value = self._get_snapshot_value(account_type, start_date)
        end_value = self._get_snapshot_value(account_type, end_date)

        net_deposits = self.db.query(CashFlow).filter(
            CashFlow.account_type == account_type,
            CashFlow.flow_date > start_date,
            CashFlow.flow_date <= end_date,
        ).all()
        net_deposits_sum = sum(f.amount for f in net_deposits)

        result = {
            "account_type": account_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "start_value": start_value,
            "end_value": end_value,
            "net_deposits": net_deposits_sum,
            "investment_gain": None,
            "investment_return_pct": None,
            "deposit_growth_pct": None,
            "total_growth_pct": None,
        }

        if start_value is None or end_value is None:
            return result

        investment_gain = (end_value - start_value) - net_deposits_sum
        result["investment_gain"] = investment_gain

        denominator = start_value + net_deposits_sum
        result["investment_return_pct"] = (investment_gain / denominator * 100) if denominator != 0 else None

        if start_value != 0:
            result["deposit_growth_pct"] = net_deposits_sum / start_value * 100
            result["total_growth_pct"] = (end_value - start_value) / start_value * 100

        return result

    def get_monthly_report(self, account_type: str, year: int, month: int) -> dict:
        """월간 리포트 (당월이면 오늘까지로 클램프)"""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year, 12, 31)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        today = date.today()
        if end_date > today:
            end_date = today

        return self.calculate_period_return(account_type, start_date, end_date)

    def get_yearly_report(self, account_type: str, year: int) -> dict:
        """연간 리포트 + 월별 breakdown"""
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        today = date.today()
        if end_date > today:
            end_date = today

        yearly = self.calculate_period_return(account_type, start_date, end_date)

        monthly_breakdown = []
        for month in range(1, 13):
            if date(year, month, 1) > today:
                break
            monthly_breakdown.append(self.get_monthly_report(account_type, year, month))

        yearly["monthly_breakdown"] = monthly_breakdown
        return yearly

    def get_ohlc_series(self, account_type: str, period: str) -> list:
        """일별 스냅샷을 주간/월간/연간 단위로 묶어 OHLC(시가/고가/저가/종가) 캔들 데이터로 변환.

        period: 'weekly' | 'monthly' | 'yearly'. 하루 1회 스냅샷이므로 시가=그 기간 첫 스냅샷,
        종가=마지막 스냅샷, 고가/저가=기간 내 최대/최소값이다(일간 스냅샷 기반 근사치이며 장중
        변동은 반영하지 않는다)."""
        snapshots = self.db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_type == account_type
        ).order_by(PortfolioSnapshot.snapshot_date.asc()).all()

        if not snapshots:
            return []

        def bucket_key(d: date):
            if period == "weekly":
                iso_year, iso_week, _ = d.isocalendar()
                return f"{iso_year}-W{iso_week:02d}"
            elif period == "yearly":
                return f"{d.year:04d}"
            return f"{d.year:04d}-{d.month:02d}"

        buckets: dict = {}
        order = []
        for s in snapshots:
            key = bucket_key(s.snapshot_date)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(s)

        result = []
        for key in order:
            rows = sorted(buckets[key], key=lambda r: r.snapshot_date)
            values = [r.total_value for r in rows]
            first_date = rows[0].snapshot_date
            result.append({
                "label": key,
                "date": first_date.isoformat(),
                "o": values[0],
                "h": max(values),
                "l": min(values),
                "c": values[-1],
            })

        return result

    # -- 종합 점검 리포트 (입금 중립화 성장지수 기반) --------------------------------

    def _resolve_account_types(self, account_type: str) -> list:
        if account_type == "전체":
            return list(ACCOUNT_TYPES)
        return [account_type]

    def _get_daily_series(self, account_types: list) -> list:
        """계좌(들)의 날짜별 total_value 합계 시계열 (전체 요청 시 두 계좌 합산)."""
        snapshots = self.db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_type.in_(account_types)
        ).order_by(PortfolioSnapshot.snapshot_date.asc()).all()

        totals: dict = {}
        order = []
        for s in snapshots:
            if s.snapshot_date not in totals:
                totals[s.snapshot_date] = 0.0
                order.append(s.snapshot_date)
            totals[s.snapshot_date] += s.total_value

        order.sort()
        return [(d, totals[d]) for d in order]

    def _get_cashflow_between(self, account_types: list, start_date_exclusive: date, end_date_inclusive: date) -> float:
        flows = self.db.query(CashFlow).filter(
            CashFlow.account_type.in_(account_types),
            CashFlow.flow_date > start_date_exclusive,
            CashFlow.flow_date <= end_date_inclusive,
        ).all()
        return sum(f.amount for f in flows)

    def get_daily_growth_index(self, account_type: str) -> list:
        """입금 중립화 성장지수(시작=100). 인접 스냅샷 쌍마다 Simple Dietz 방식으로 일별
        수익률을 구해 체이닝한다 — 입금으로 인한 자산 증가를 수익처럼 잡지 않기 위함."""
        account_types = self._resolve_account_types(account_type)
        series = self._get_daily_series(account_types)
        if not series:
            return []

        index = 100.0
        result = [{"date": series[0][0].isoformat(), "index": index}]
        prev_date, prev_value = series[0]

        for d, v in series[1:]:
            cf = self._get_cashflow_between(account_types, prev_date, d)
            denom = prev_value + cf
            r = (v - prev_value - cf) / denom if denom != 0 else 0.0
            index *= (1 + r)
            result.append({"date": d.isoformat(), "index": index})
            prev_date, prev_value = d, v

        return result

    def get_cumulative_return_vs_deposits(self, account_type: str) -> Optional[float]:
        """전체 기간 누적 순입금 대비 현재 총자산 수익률. 누적 순입금이 0이면 None."""
        account_types = self._resolve_account_types(account_type)
        series = self._get_daily_series(account_types)
        if not series:
            return None

        latest_value = series[-1][1]
        total_net_deposits = self.db.query(CashFlow).filter(
            CashFlow.account_type.in_(account_types)
        ).all()
        total_net_deposits_sum = sum(f.amount for f in total_net_deposits)

        if total_net_deposits_sum == 0:
            return None
        return (latest_value - total_net_deposits_sum) / total_net_deposits_sum * 100

    def get_xirr(self, account_type: str) -> Optional[float]:
        """전체 입금 이력(record_cash_flow) + 최신 평가금액 기준 자금가중수익률(XIRR, %).

        스냅샷이 최근에야 쌓이기 시작한 계좌(예: 2018년부터 운용된 IRP)도 입금 시점만
        알면 계산 가능하다는 점이 get_cagr(성장지수 기준, 스냅샷 기간에만 의존)과 다르다.
        입금 기록이 없거나 부호가 한쪽으로만 쏠려 해가 존재하지 않으면 None.
        """
        account_types = self._resolve_account_types(account_type)
        flows = self.db.query(CashFlow).filter(
            CashFlow.account_type.in_(account_types)
        ).order_by(CashFlow.flow_date.asc()).all()
        if not flows:
            return None

        series = self._get_daily_series(account_types)
        if not series:
            return None
        latest_date, latest_value = series[-1]

        cashflows = [(f.flow_date, -f.amount) for f in flows]
        cashflows.append((latest_date, latest_value))
        t0 = cashflows[0][0]

        def npv(rate: float) -> float:
            total = 0.0
            for d, amt in cashflows:
                days = (d - t0).days
                total += amt / ((1 + rate) ** (days / 365.0))
            return total

        low, high = -0.99, 10.0
        f_low, f_high = npv(low), npv(high)
        if f_low == 0:
            return low * 100
        if f_high == 0:
            return high * 100
        if f_low * f_high > 0:
            return None

        mid = 0.0
        for _ in range(200):
            mid = (low + high) / 2
            f_mid = npv(mid)
            if abs(f_mid) < 1e-6:
                break
            if f_low * f_mid < 0:
                high = mid
            else:
                low = mid
                f_low = f_mid
        return mid * 100

    def get_cagr(self, account_type: str) -> Optional[float]:
        """입금 중립화 성장지수 기준 CAGR(%). 스냅샷이 1개뿐이면 None."""
        index_series = self.get_daily_growth_index(account_type)
        if len(index_series) < 2:
            return None

        first_date = date.fromisoformat(index_series[0]["date"])
        last_date = date.fromisoformat(index_series[-1]["date"])
        days = (last_date - first_date).days
        if days <= 0:
            return None

        end_index = index_series[-1]["index"]
        return ((end_index / 100.0) ** (365.25 / days) - 1) * 100

    def get_mdd(self, account_type: str) -> Optional[float]:
        """입금 중립화 성장지수 기준 최대낙폭(%, 음수 또는 0)."""
        index_series = self.get_daily_growth_index(account_type)
        if not index_series:
            return None

        peak = index_series[0]["index"]
        max_drawdown = 0.0
        for pt in index_series:
            peak = max(peak, pt["index"])
            drawdown = (pt["index"] - peak) / peak * 100
            max_drawdown = min(max_drawdown, drawdown)

        return max_drawdown

    def get_annual_returns(self, account_type: str) -> list:
        """성장지수를 연도별로 리샘플해 그 해 수익률(%)과 그 해 raw 스냅샷 평균값(가중치용)을 반환."""
        account_types = self._resolve_account_types(account_type)
        index_series = self.get_daily_growth_index(account_type)
        if not index_series:
            return []

        by_year: dict = {}
        for pt in index_series:
            y = date.fromisoformat(pt["date"]).year
            by_year.setdefault(y, []).append(pt["index"])

        raw_series = self._get_daily_series(account_types)
        raw_by_year: dict = {}
        for d, v in raw_series:
            raw_by_year.setdefault(d.year, []).append(v)

        result = []
        for year in sorted(by_year):
            values = by_year[year]
            start_index, end_index = values[0], values[-1]
            return_pct = (end_index / start_index - 1) * 100 if start_index else None
            avg_capital = sum(raw_by_year[year]) / len(raw_by_year[year])
            result.append({"year": year, "return_pct": return_pct, "avg_capital": avg_capital})

        return result

    def get_annual_return_simple_weighted(self, account_type: str) -> dict:
        """연평균 수익률: 단순(산술) 평균 vs 자산규모 가중 평균."""
        annual_returns = [r for r in self.get_annual_returns(account_type) if r["return_pct"] is not None]
        if not annual_returns:
            return {"simple": None, "weighted": None}

        simple = sum(r["return_pct"] for r in annual_returns) / len(annual_returns)

        total_capital = sum(r["avg_capital"] for r in annual_returns)
        if total_capital == 0:
            weighted = None
        else:
            weighted = sum(r["return_pct"] * r["avg_capital"] for r in annual_returns) / total_capital

        return {"simple": simple, "weighted": weighted}
