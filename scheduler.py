# -*- coding: utf-8 -*-
"""ReBalancer - 자동 스케줄러"""

import calendar
import logging
from typing import List, Optional
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from config import (
    TIMEZONE, CRAWL_SCHEDULE_HOUR,
    MOMENTUM_SCHEDULE_HOUR, PENSION_ETFS, IRP_PORTFOLIO, REBALANCE_CHECK_DATES,
    REBALANCE_CHECK_HOUR, MARKET_HOLIDAYS, HOLIDAY_API_KEY_EXPIRES
)
from database import get_db, MomentumScore
from crawler import NaverETFCrawler
from momentum_engine import MomentumEngine
from rebalance_engine import RebalanceEngine
from notification import TelegramNotificationManager
from webhook_notifier import WebhookNotifier
from performance_report_engine import PerformanceReportEngine
from portfolio_engine import PortfolioEngine
from signal_accuracy_engine import SignalAccuracyEngine
from holiday_checker import check_upcoming_holidays

logger = logging.getLogger(__name__)
tz = timezone(TIMEZONE)


def _is_business_day(d: date) -> bool:
    """주말 또는 MARKET_HOLIDAYS에 해당하면 휴장일"""
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in MARKET_HOLIDAYS


def _first_business_day_of_month(year: int, month: int) -> date:
    """해당 월의 첫 영업일(휴장일이면 다음 영업일로 순연)"""
    d = date(year, month, 1)
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d


def _next_business_day_on_or_after(d: date) -> date:
    """주어진 날짜가 휴장일이면 다음 영업일로 순연"""
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d


def _rebalance_check_dates(year: int) -> List[date]:
    """올해의 리밸런싱 체크 예정일 목록 (REBALANCE_CHECK_DATES 기준, 휴장일이면 순연)"""
    return [
        _next_business_day_on_or_after(date(year, int(month), int(day)))
        for month, day in REBALANCE_CHECK_DATES
    ]


def _signal_with_name(signal: dict) -> dict:
    """리밸런싱 신호에 ETF 이름 추가 (웹훅 payload용, HOLD 포함 전체)"""
    ticker = signal.get('ticker', 'N/A')
    etf_info = IRP_PORTFOLIO.get(ticker) or PENSION_ETFS.get(ticker, {})
    return {**signal, "name": etf_info.get('name', ticker)}

class JobScheduler:
    """작업 스케줄러"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=tz)
        self.crawler = NaverETFCrawler()

    def schedule_jobs(self):
        """스케줄 등록"""
        # Job 1: 매일 18:00 종가 수집
        self.scheduler.add_job(
            self._job_collect_prices,
            trigger=CronTrigger(hour=CRAWL_SCHEDULE_HOUR, minute=0, timezone=tz),
            id='collect_prices',
            name='일일 종가 수집',
            replace_existing=True,
            max_instances=1  # 동시 실행 방지
        )
        logger.info(f"Schedule registered: Daily {CRAWL_SCHEDULE_HOUR}:00 - Price collection")

        # Job 2: 매월 첫 영업일 09:00 모멘텀 계산 (휴장일이면 다음 영업일로 순연, 매일 09:00에 해당 여부 체크)
        self.scheduler.add_job(
            self._job_calculate_momentum,
            trigger=CronTrigger(hour=MOMENTUM_SCHEDULE_HOUR, minute=0, timezone=tz),
            id='calculate_momentum',
            name='월별 모멘텀 계산',
            replace_existing=True,
            max_instances=1
        )
        logger.info(f"Schedule registered: Daily check at {MOMENTUM_SCHEDULE_HOUR}:00 - Momentum calculation on first business day of month")

        # Job 3: 매월 말일 08:00 - 향후 12개월 휴장일 캘린더 자동 점검 (매일 08:00에 말일 여부 체크)
        self.scheduler.add_job(
            self._job_check_holidays,
            trigger=CronTrigger(hour=8, minute=0, timezone=tz),
            id='check_holidays',
            name='휴장일 캘린더 점검',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Schedule registered: Daily check at 8:00 - Holiday calendar check on last day of month")

        # Job 4: 매일 08:00 - 공공데이터포털 API 키 만료 D-30/D-15/D-3 알림
        self.scheduler.add_job(
            self._job_check_api_key_expiry,
            trigger=CronTrigger(hour=8, minute=0, timezone=tz),
            id='check_api_key_expiry',
            name='API 키 만료 점검',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Schedule registered: Daily check at 8:00 - Holiday API key expiry (D-30/D-15/D-3)")

        # Job 5: 반기(1/1, 7/1) 09:00 리밸런싱 체크 (휴장일이면 다음 영업일로 순연, 매일 09:00에 해당 여부 체크)
        self.scheduler.add_job(
            self._job_check_rebalance,
            trigger=CronTrigger(hour=REBALANCE_CHECK_HOUR, minute=0, timezone=tz),
            id='check_rebalance',
            name='반기 리밸런싱 체크',
            replace_existing=True,
            max_instances=1
        )
        logger.info(f"Schedule registered: Daily check at {REBALANCE_CHECK_HOUR}:00 - Rebalance check on scheduled dates (deferred if holiday)")

    def start(self):
        """스케줄러 시작"""
        if not self.scheduler.running:
            self.schedule_jobs()
            self.scheduler.start()
            logger.info("Scheduler started")
        else:
            logger.warning("Scheduler is already running")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def pause(self):
        """스케줄러 일시 정지"""
        if self.scheduler.running:
            self.scheduler.pause()
            logger.info("Scheduler paused")

    def resume(self):
        """스케줄러 재개"""
        if self.scheduler.running:
            self.scheduler.resume()
            logger.info("Scheduler resumed")

    def get_jobs(self):
        """등록된 job 목록 조회"""
        return self.scheduler.get_jobs()

    def is_running(self) -> bool:
        """스케줄러 실행 여부"""
        return self.scheduler.running

    # ==================== Job Implementations ====================

    def _job_collect_prices(self):
        """종가 수집 작업"""
        today = date.today()
        if not _is_business_day(today):
            logger.info(f"[Price Collection] Skipped - {today.isoformat()} is not a business day (weekend/holiday)")
            return

        logger.info("=" * 70)
        logger.info(f"[Price Collection] Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        db = None
        try:
            db = next(get_db())
            all_tickers = {**PENSION_ETFS, **IRP_PORTFOLIO}
            stats = self.crawler.collect_all_prices(db, all_tickers)
            logger.info(
                f"[Price Collection] Completed - "
                f"Success: {stats['success']}, Failed: {stats['fail']}, Skipped: {stats['skip']}"
            )

            # Telegram 알림 - 계좌별 관리종목 시세/등락률 + 보유종목 평가금액 + 계좌합계 전일대비
            if stats['success'] > 0:
                portfolio_engine = PortfolioEngine(db)
                report_engine = PerformanceReportEngine(db)
                accounts = []
                pension_prices = {}

                for account_type, etf_map in (("연금저축", PENSION_ETFS), ("IRP", IRP_PORTFOLIO)):
                    held_map = {
                        h.ticker: h for h in portfolio_engine.get_portfolio_by_account(account_type)
                    }
                    items = []
                    for ticker, info in etf_map.items():
                        if ticker == "CASH":
                            continue
                        price = portfolio_engine.get_latest_price(ticker)
                        if price == 0:
                            continue
                        if account_type == "연금저축":
                            pension_prices[ticker] = price

                        held_row = held_map.get(ticker)
                        if not held_row:
                            continue  # 보유 중인 종목만 알림에 표시

                        prev_price = portfolio_engine.get_previous_close(ticker)
                        change_pct = ((price - prev_price) / prev_price * 100) if prev_price else None

                        perf = portfolio_engine.calculate_holding_performance(
                            ticker, held_row.quantity, held_row.avg_buy_price
                        )
                        current_value = perf['current_value']
                        value_change = (
                            held_row.quantity * (price - prev_price) if prev_price else None
                        )

                        items.append({
                            "ticker": ticker,
                            "name": info['name'],
                            "price": price,
                            "change_pct": change_pct,
                            "held": True,
                            "value_change": value_change,
                            "current_value": current_value,
                        })

                    total_value = portfolio_engine.calculate_portfolio_performance(account_type)['total_value']
                    prev_total_value = report_engine.get_previous_day_value(account_type, today)

                    accounts.append({
                        "label": account_type,
                        "items": items,
                        "total_value": total_value,
                        "prev_total_value": prev_total_value,
                    })

                notifier = TelegramNotificationManager(db)
                notifier.send_price_alert(today.isoformat(), accounts)

                webhook = WebhookNotifier(db)
                webhook.send_webhook("price_update", {
                    "date": today.isoformat(),
                    "prices": pension_prices,
                    "collected_count": stats['success'],
                })

            # 포트폴리오 스냅샷 저장 (종가 수집 직후, 같은 db 세션)
            self._job_snapshot_portfolio(db)

        except Exception as e:
            logger.error(f"[Price Collection] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)

    def _job_snapshot_portfolio(self, db):
        """계좌별 포트폴리오 스냅샷 저장 (매일 종가 수집 직후 호출, 별도 스케줄 등록 안 함)"""
        try:
            report_engine = PerformanceReportEngine(db)
            result = report_engine.save_daily_snapshot()
            logger.info(f"[Portfolio Snapshot] Completed - {result}")
        except Exception as e:
            logger.error(f"[Portfolio Snapshot] Error: {type(e).__name__}: {e}", exc_info=True)

    def _job_check_api_key_expiry(self):
        """공공데이터포털 API 키 만료 D-30/D-15/D-3 알림"""
        try:
            expires = datetime.strptime(HOLIDAY_API_KEY_EXPIRES, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"[API Key Expiry] Invalid HOLIDAY_API_KEY_EXPIRES: {HOLIDAY_API_KEY_EXPIRES}")
            return

        days_left = (expires - date.today()).days
        if days_left not in (30, 15, 3):
            return

        logger.warning(f"[API Key Expiry] D-{days_left} - HOLIDAY_API_KEY expires on {expires}")

        db = None
        try:
            db = next(get_db())
            notifier = TelegramNotificationManager(db)
            message = (
                f"공공데이터포털 특일 정보 API 키가 {days_left}일 후({expires}) 만료됩니다.\n\n"
                "data.go.kr에서 재발급/연장 후 .env의 HOLIDAY_API_KEY와 "
                "config.py의 HOLIDAY_API_KEY_EXPIRES를 갱신해주세요."
            )
            notifier.send_telegram_message("API 키 만료 예정 알림", message, notification_type="api_key_expiry")

            webhook = WebhookNotifier(db)
            webhook.send_webhook("api_key_expiry", {
                "days_left": days_left,
                "expires": expires.isoformat(),
                "key_name": "HOLIDAY_API_KEY",
            })
        except Exception as e:
            logger.error(f"[API Key Expiry] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()

    def _job_check_holidays(self):
        """휴장일 캘린더 점검 작업 (매월 말일에만 실행)"""
        today = date.today()
        last_day_of_month = calendar.monthrange(today.year, today.month)[1]
        if today.day != last_day_of_month:
            return

        logger.info("=" * 70)
        logger.info(f"[Holiday Check] Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        db = None
        try:
            db = next(get_db())
            result = check_upcoming_holidays(months_ahead=12)

            if result["error"]:
                logger.warning(f"[Holiday Check] Skipped - {result['error']}")
            elif result["missing"]:
                logger.warning(f"[Holiday Check] Missing holidays found: {result['missing']}")
                notifier = TelegramNotificationManager(db)
                message = (
                    f"조회 범위: {result['checked_range']}\n\n"
                    f"config.py의 MARKET_HOLIDAYS에 없는 공휴일이 발견됐습니다.\n"
                    + "\n".join(result["missing"])
                    + "\n\nMARKET_HOLIDAYS에 추가해주세요.\n"
                    "(근로자의날, 증권시장 연말휴장 등 KRX 자체 휴장일은 이 점검 대상이 아니므로 별도 확인 필요)"
                )
                notifier.send_telegram_message("휴장일 캘린더 점검 알림", message, notification_type="holiday_check")

                webhook = WebhookNotifier(db)
                webhook.send_webhook("holiday_check", {
                    "checked_range": result["checked_range"],
                    "missing": result["missing"],
                })
            else:
                logger.info(f"[Holiday Check] OK - no missing holidays in {result['checked_range']}")

        except Exception as e:
            logger.error(f"[Holiday Check] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)

    def _job_calculate_momentum(self):
        """모멘텀 계산 작업 (매월 첫 영업일에만 실행)"""
        today = date.today()
        expected_day = _first_business_day_of_month(today.year, today.month)
        if today != expected_day:
            logger.info(
                f"[Momentum Calculation] Skipped - {today} is not this month's first business day "
                f"(expected {expected_day})"
            )
            return

        logger.info("=" * 70)
        logger.info(f"[Momentum Calculation] Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        db = None
        try:
            db = next(get_db())

            # 모멘텀 엔진 생성
            momentum_engine = MomentumEngine(db)
            calc_date = date.today()

            # TOP N 종목 선정 (조건 통과 + 상위 2개)
            top_n_scores = momentum_engine.select_top_n_passed(calc_date, n=2)
            selected_tickers = {score['ticker'] for score in top_n_scores}

            # 모든 종목의 모멘텀 계산 및 저장
            all_scores = []
            from config import PENSION_ETFS
            for ticker in PENSION_ETFS.keys():
                score = momentum_engine.calculate_momentum_score(ticker, calc_date)
                score['is_selected'] = ticker in selected_tickers
                all_scores.append(score)

            saved_count = momentum_engine.save_momentum_scores(all_scores, calc_date)

            logger.info(
                f"[Momentum Calculation] Completed - "
                f"Calculated: {len(all_scores)}, Saved: {saved_count}, Top Selected: {len(top_n_scores)}"
            )

            # SignalAccuracyEngine - 신호 기록
            if top_n_scores:
                accuracy_engine = SignalAccuracyEngine(db)
                for score in top_n_scores:
                    signal_result = accuracy_engine.record_momentum_signal(
                        ticker=score['ticker'],
                        momentum_score=score,
                        signal_date=calc_date.isoformat()
                    )
                    logger.info(f"[Signal Recorded] Momentum: {signal_result['signal_id']} - {signal_result['direction']} (confidence: {signal_result['confidence']:.2f})")

            # Telegram 알림
            if all_scores:
                notifier = TelegramNotificationManager(db)
                selected_tickers = [score['ticker'] for score in top_n_scores]
                notifier.send_momentum_alert(all_scores, selected_tickers, calc_date.isoformat())

                webhook = WebhookNotifier(db)
                webhook.send_webhook("momentum_update", {
                    "calc_date": calc_date.isoformat(),
                    "selected_tickers": selected_tickers,
                    "scores": [
                        {
                            "ticker": s['ticker'],
                            "name": PENSION_ETFS.get(s['ticker'], {}).get('name', s['ticker']),
                            "current_price": s['current_price'],
                            "r3": s['r3'],
                            "r6": s['r6'],
                            "r12": s['r12'],
                            "weighted_score": s['weighted_score'],
                            "passed_condition": s['passed_condition'],
                            "is_selected": s['is_selected'],
                        }
                        for s in all_scores
                    ],
                })

            # 연저펀 Top2 밴드형 재조정 체크 (같은 달 재선정 직후 실행)
            self._check_pension_rebalance(db, calc_date)

        except Exception as e:
            logger.error(f"[Momentum Calculation] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)

    def _check_pension_rebalance(self, db, calc_date):
        """연저펀 Top2 +/-5%p 밴드 재조정 체크 (모멘텀 계산 직후 호출)"""
        try:
            rebalance_engine = RebalanceEngine(db)
            signals = rebalance_engine.calculate_pension_rebalance_signal(calc_date)
            if not signals:
                return

            saved_count = rebalance_engine.save_rebalance_signals(signals)
            needs_rebalance_count = sum(1 for s in signals if s['needs_rebalance'])

            logger.info(
                f"[Pension Rebalance Check] Completed - "
                f"Signals: {len(signals)}, Needs Rebalance: {needs_rebalance_count}, Saved: {saved_count}"
            )

            accuracy_engine = SignalAccuracyEngine(db)
            for signal in signals:
                signal_result = accuracy_engine.record_rebalance_signal(
                    ticker=signal['ticker'],
                    action=signal['action'],
                    signal_date=calc_date.isoformat(),
                    current_price=signal['current_price']
                )
                logger.info(f"[Signal Recorded] Pension Rebalance: {signal_result['signal_id']} - {signal_result['direction']} (confidence: {signal_result['confidence']:.2f})")

            notifier = TelegramNotificationManager(db)
            needs_rebalance = needs_rebalance_count > 0
            rebalance_signals = [s for s in signals if s['needs_rebalance']]
            notifier.send_rebalance_alert(needs_rebalance, calc_date.isoformat(), rebalance_signals, label="연저펀 Top2")

            webhook = WebhookNotifier(db)
            webhook.send_webhook("rebalance_signal", {
                "label": "연저펀 Top2",
                "signal_date": calc_date.isoformat(),
                "needs_rebalance": needs_rebalance,
                "signals": [_signal_with_name(s) for s in signals],
            })

        except Exception as e:
            logger.error(f"[Pension Rebalance Check] Error: {type(e).__name__}: {e}", exc_info=True)

    def _job_check_rebalance(self):
        """리밸런싱 체크 작업 (반기, 휴장일이면 다음 영업일로 순연)"""
        today = date.today()
        expected_dates = _rebalance_check_dates(today.year)
        if today not in expected_dates:
            logger.info(
                f"[Rebalance Check] Skipped - {today} is not a scheduled rebalance date "
                f"(expected {expected_dates})"
            )
            return

        logger.info("=" * 70)
        logger.info(f"[Rebalance Check] Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        db = None
        try:
            db = next(get_db())

            # 리밸런싱 엔진 생성 (기본 1000만원 포트폴리오)
            rebalance_engine = RebalanceEngine(db)
            signal_date = date.today()

            # 리밸런싱 신호 계산
            signals = rebalance_engine.calculate_rebalance_signal(signal_date)

            # 신호 저장
            saved_count = rebalance_engine.save_rebalance_signals(signals)

            # 리밸런싱 필요 여부 체크
            needs_rebalance_count = sum(1 for s in signals if s['needs_rebalance'])

            logger.info(
                f"[Rebalance Check] Completed - "
                f"Signals: {len(signals)}, Needs Rebalance: {needs_rebalance_count}, Saved: {saved_count}"
            )

            # 신호별 상세 로그
            for signal in signals:
                if signal['needs_rebalance']:
                    logger.warning(
                        f"[REBALANCE SIGNAL] {signal['ticker']}: "
                        f"Action={signal['action']}, "
                        f"Current={signal['current_weight']:.1f}%, "
                        f"Target={signal['target_weight']:.1f}%, "
                        f"Diff={signal['weight_diff']:+.1f}%, "
                        f"Amount={signal['rebalance_amount']:,.0f}"
                    )

            # SignalAccuracyEngine - 신호 기록
            accuracy_engine = SignalAccuracyEngine(db)
            for signal in signals:
                signal_result = accuracy_engine.record_rebalance_signal(
                    ticker=signal['ticker'],
                    action=signal['action'],
                    signal_date=signal_date.isoformat(),
                    current_price=signal['current_price']
                )
                logger.info(f"[Signal Recorded] Rebalance: {signal_result['signal_id']} - {signal_result['direction']} (confidence: {signal_result['confidence']:.2f})")

            # Telegram 알림
            notifier = TelegramNotificationManager(db)
            needs_rebalance = needs_rebalance_count > 0
            rebalance_signals = [s for s in signals if s['needs_rebalance']]
            notifier.send_rebalance_alert(needs_rebalance, signal_date.isoformat(), rebalance_signals)

            webhook = WebhookNotifier(db)
            webhook.send_webhook("rebalance_signal", {
                "label": "IRP",
                "signal_date": signal_date.isoformat(),
                "needs_rebalance": needs_rebalance,
                "signals": [_signal_with_name(s) for s in signals],
            })

        except Exception as e:
            logger.error(f"[Rebalance Check] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)


# 전역 스케줄러 인스턴스
_scheduler: Optional[JobScheduler] = None

def get_scheduler() -> JobScheduler:
    """전역 스케줄러 인스턴스 획득"""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler()
    return _scheduler
