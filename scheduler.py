# -*- coding: utf-8 -*-
"""ReBalancer - 자동 스케줄러"""

import logging
from typing import Optional
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from config import (
    TIMEZONE, CRAWL_SCHEDULE_HOUR, MOMENTUM_SCHEDULE_MONTH_DAY,
    MOMENTUM_SCHEDULE_HOUR, PENSION_ETFS, REBALANCE_CHECK_DATES,
    REBALANCE_CHECK_HOUR
)
from database import get_db, ETFPrice, MomentumScore
from crawler import NaverETFCrawler
from momentum_engine import MomentumEngine
from rebalance_engine import RebalanceEngine
from notification import TelegramNotificationManager
from datetime import date

logger = logging.getLogger(__name__)
tz = timezone(TIMEZONE)

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

        # Job 2: 매월 2일 09:00 모멘텀 계산
        self.scheduler.add_job(
            self._job_calculate_momentum,
            trigger=CronTrigger(day=MOMENTUM_SCHEDULE_MONTH_DAY, hour=MOMENTUM_SCHEDULE_HOUR, minute=0, timezone=tz),
            id='calculate_momentum',
            name='월별 모멘텀 계산',
            replace_existing=True,
            max_instances=1
        )
        logger.info(f"Schedule registered: Monthly on day {MOMENTUM_SCHEDULE_MONTH_DAY} {MOMENTUM_SCHEDULE_HOUR}:00 - Momentum calculation")

        # Job 3: 반기(1/1, 7/1) 09:00 리밸런싱 체크
        for month, day in REBALANCE_CHECK_DATES:
            job_id = f'check_rebalance_{month}{day}'
            self.scheduler.add_job(
                self._job_check_rebalance,
                trigger=CronTrigger(month=month, day=day, hour=REBALANCE_CHECK_HOUR, minute=0, timezone=tz),
                id=job_id,
                name=f'{month}월 {day}일 리밸런싱 체크',
                replace_existing=True,
                max_instances=1
            )
            logger.info(f"Schedule registered: {month}/{day} {REBALANCE_CHECK_HOUR}:00 - Rebalance check")

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
        logger.info("=" * 70)
        logger.info(f"[Price Collection] Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        db = None
        try:
            db = next(get_db())
            stats = self.crawler.collect_all_prices(db, PENSION_ETFS)
            logger.info(
                f"[Price Collection] Completed - "
                f"Success: {stats['success']}, Failed: {stats['fail']}, Skipped: {stats['skip']}"
            )

            # 최신 종가 데이터 조회
            latest_prices = {}
            for ticker in PENSION_ETFS.keys():
                latest = db.query(ETFPrice).filter(
                    ETFPrice.ticker == ticker
                ).order_by(ETFPrice.price_date.desc()).first()

                if latest:
                    latest_prices[ticker] = latest.close_price

            # Telegram 알림
            if stats['success'] > 0:
                notifier = TelegramNotificationManager(db)
                etf_data = {
                    "date": date.today().isoformat(),
                    "prices": latest_prices
                }
                notifier.send_price_alert(etf_data)

        except Exception as e:
            logger.error(f"[Price Collection] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)

    def _job_calculate_momentum(self):
        """모멘텀 계산 작업 (월별)"""
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

            # 모든 종목의 모멘텀 계산 및 저장
            all_scores = []
            from config import PENSION_ETFS
            for ticker in PENSION_ETFS.keys():
                score = momentum_engine.calculate_momentum_score(ticker, calc_date)
                all_scores.append(score)

            saved_count = momentum_engine.save_momentum_scores(all_scores, calc_date)

            logger.info(
                f"[Momentum Calculation] Completed - "
                f"Calculated: {len(all_scores)}, Saved: {saved_count}, Top Selected: {len(top_n_scores)}"
            )

            # Telegram 알림
            if top_n_scores:
                notifier = TelegramNotificationManager(db)
                selected_tickers = [score['ticker'] for score in top_n_scores]
                momentum_data = {score['ticker']: score for score in top_n_scores}
                notifier.send_momentum_alert(selected_tickers, calc_date.isoformat(), momentum_data)

        except Exception as e:
            logger.error(f"[Momentum Calculation] Error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("=" * 70)

    def _job_check_rebalance(self):
        """리밸런싱 체크 작업 (반기)"""
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

            # Telegram 알림
            notifier = TelegramNotificationManager(db)
            needs_rebalance = needs_rebalance_count > 0
            rebalance_signals = [s for s in signals if s['needs_rebalance']]
            notifier.send_rebalance_alert(needs_rebalance, signal_date.isoformat(), rebalance_signals)

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
