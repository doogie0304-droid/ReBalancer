# -*- coding: utf-8 -*-
"""ReBalancer - FastAPI 통합"""

import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from sqlalchemy.orm import Session

from config import API_TITLE, API_DESCRIPTION, API_VERSION, LOG_LEVEL, PENSION_ETFS, IRP_PORTFOLIO
from database import init_db, get_db, ETFPrice, MomentumScore, RebalanceSignal, UserPortfolio
from scheduler import get_scheduler
from crawler import NaverETFCrawler
from momentum_engine import MomentumEngine
from rebalance_engine import RebalanceEngine
from portfolio_engine import PortfolioEngine
from datetime import date

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
scheduler = get_scheduler()
scheduler.start()

# ==================== Health & Status ====================

@app.get("/health")
async def health_check() -> Dict:
    """헬스 체크"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": API_VERSION,
        "scheduler_running": scheduler.is_running()
    }

# ==================== ETF Management ====================

@app.get("/api/v1/etfs")
async def get_managed_etfs(db: Session = Depends(get_db)) -> Dict:
    """관리 종목 목록"""
    try:
        # 가장 최신 날짜의 각 종목 시세 조회
        etfs = db.query(
            ETFPrice.ticker,
            ETFPrice.close_price,
            ETFPrice.price_date
        ).distinct(ETFPrice.ticker).order_by(
            ETFPrice.ticker, ETFPrice.price_date.desc()
        ).all()
        
        result = []
        for ticker, close_price, price_date in etfs:
            result.append({
                "ticker": ticker,
                "close_price": float(close_price),
                "price_date": price_date.isoformat() if price_date else None
            })
        
        return {
            "status": "ok",
            "count": len(result),
            "data": result
        }
    except Exception as e:
        logger.error(f"관리 종목 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="종목 조회 실패")

@app.get("/api/v1/etfs/{ticker}")
async def get_etf_prices(
    ticker: str, 
    limit: int = 30,
    db: Session = Depends(get_db)
) -> Dict:
    """특정 종목의 시세 조회
    
    Args:
        ticker: ETF 티커 코드
        limit: 조회 개수 (최대 100)
    """
    try:
        limit = min(limit, 100)  # 최대 100개로 제한
        
        prices = db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker
        ).order_by(
            ETFPrice.price_date.desc()
        ).limit(limit).all()
        
        if not prices:
            raise HTTPException(status_code=404, detail=f"종목 {ticker}의 데이터가 없습니다")
        
        data = [
            {
                "date": p.price_date.isoformat(),
                "close_price": float(p.close_price)
            }
            for p in reversed(prices)  # 오름차순으로 반환
        ]
        
        return {
            "status": "ok",
            "ticker": ticker,
            "count": len(data),
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시세 조회 오류 ({ticker}): {e}")
        raise HTTPException(status_code=500, detail="시세 조회 실패")

# ==================== Momentum ====================

@app.get("/api/v1/momentum/latest")
async def get_latest_momentum(db: Session = Depends(get_db)) -> Dict:
    """최신 모멘텀 데이터 조회"""
    try:
        # 가장 최신 calc_date 조회
        latest_scores = db.query(MomentumScore).order_by(
            MomentumScore.calc_date.desc()
        ).limit(20).all()  # TOP 20
        
        if not latest_scores:
            return {
                "status": "ok",
                "message": "모멘텀 데이터가 없습니다",
                "data": []
            }
        
        data = [
            {
                "ticker": score.ticker,
                "calc_date": score.calc_date.isoformat() if score.calc_date else None,
                "weighted_score": float(score.weighted_score),
                "r3": float(score.r3),
                "r6": float(score.r6),
                "r12": float(score.r12),
                "passed_condition": score.passed_condition,
                "rank": score.rank_in_month,
                "selected": score.is_selected
            }
            for score in latest_scores
        ]
        
        return {
            "status": "ok",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        logger.error(f"모멘텀 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="모멘텀 데이터 조회 실패")

# ==================== Rebalance ====================

@app.get("/api/v1/rebalance/latest")
async def get_latest_rebalance_signal(db: Session = Depends(get_db)) -> Dict:
    """최신 리밸런싱 신호 조회"""
    try:
        # 가장 최신 signal_date 조회
        latest_signals = db.query(RebalanceSignal).order_by(
            RebalanceSignal.signal_date.desc()
        ).limit(20).all()
        
        if not latest_signals:
            return {
                "status": "ok",
                "message": "리밸런싱 신호가 없습니다",
                "data": []
            }
        
        data = [
            {
                "ticker": signal.ticker,
                "signal_date": signal.signal_date.isoformat() if signal.signal_date else None,
                "target_weight": float(signal.target_weight),
                "current_weight": float(signal.current_weight) if signal.current_weight else 0.0,
                "weight_diff": float(signal.weight_diff) if signal.weight_diff else 0.0,
                "action": signal.action,
                "needs_rebalance": signal.needs_rebalance
            }
            for signal in latest_signals
        ]
        
        return {
            "status": "ok",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        logger.error(f"리밸런싱 신호 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="리밸런싱 신호 조회 실패")

# ==================== Portfolio Management ====================

@app.post("/api/v1/portfolio/add")
async def add_portfolio_holding(
    ticker: str,
    quantity: float,
    avg_buy_price: float,
    account_type: str = "IRP",
    db: Session = Depends(get_db)
) -> Dict:
    """포트폴리오 종목 추가"""
    try:
        portfolio_engine = PortfolioEngine(db)
        result = portfolio_engine.add_portfolio_holding(ticker, quantity, avg_buy_price, account_type)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "status": "ok",
            "message": "Portfolio holding added",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio add error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add portfolio holding")

@app.get("/api/v1/portfolio")
async def get_portfolio(
    account_type: str = None,
    db: Session = Depends(get_db)
) -> Dict:
    """포트폴리오 조회"""
    try:
        portfolio_engine = PortfolioEngine(db)

        if account_type:
            holdings = portfolio_engine.get_portfolio_by_account(account_type)
        else:
            holdings = db.query(UserPortfolio).filter(UserPortfolio.is_active == True).all()

        data = [
            {
                "ticker": h.ticker,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
                "account_type": h.account_type,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "updated_at": h.updated_at.isoformat() if h.updated_at else None
            }
            for h in holdings
        ]

        return {
            "status": "ok",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        logger.error(f"Portfolio query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve portfolio")

@app.get("/api/v1/portfolio/{ticker}")
async def get_portfolio_holding(
    ticker: str,
    account_type: str = "IRP",
    db: Session = Depends(get_db)
) -> Dict:
    """특정 종목 포트폴리오 조회"""
    try:
        portfolio_engine = PortfolioEngine(db)
        result = portfolio_engine.get_portfolio_by_ticker(ticker, account_type)

        if not result:
            raise HTTPException(status_code=404, detail=f"Portfolio holding not found: {ticker}")

        return {
            "status": "ok",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio query error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve portfolio holding")

@app.put("/api/v1/portfolio/{ticker}")
async def update_portfolio_holding(
    ticker: str,
    quantity: float,
    avg_buy_price: float,
    account_type: str = "IRP",
    db: Session = Depends(get_db)
) -> Dict:
    """포트폴리오 종목 수정"""
    try:
        portfolio_engine = PortfolioEngine(db)
        result = portfolio_engine.update_portfolio_holding(ticker, quantity, avg_buy_price, account_type)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return {
            "status": "ok",
            "message": "Portfolio holding updated",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update portfolio holding")

@app.delete("/api/v1/portfolio/{ticker}")
async def delete_portfolio_holding(
    ticker: str,
    account_type: str = "IRP",
    db: Session = Depends(get_db)
) -> Dict:
    """포트폴리오 종목 삭제"""
    try:
        portfolio_engine = PortfolioEngine(db)
        success = portfolio_engine.delete_portfolio_holding(ticker, account_type)

        if not success:
            raise HTTPException(status_code=404, detail=f"Portfolio holding not found: {ticker}")

        return {
            "status": "ok",
            "message": "Portfolio holding deleted"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio delete error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete portfolio holding")

@app.get("/api/v1/portfolio/performance/summary")
async def get_portfolio_performance(
    account_type: str = None,
    db: Session = Depends(get_db)
) -> Dict:
    """포트폴리오 수익률 계산"""
    try:
        portfolio_engine = PortfolioEngine(db)
        performance = portfolio_engine.calculate_portfolio_performance(account_type)

        return {
            "status": "ok",
            "data": performance
        }
    except Exception as e:
        logger.error(f"Portfolio performance calculation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate portfolio performance")

# ==================== Scheduler Control ====================

@app.get("/api/v1/scheduler/status")
async def get_scheduler_status() -> Dict:
    """스케줄러 상태 조회"""
    try:
        jobs = scheduler.get_jobs()
        
        job_list = [
            {
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
            }
            for job in jobs
        ]
        
        return {
            "status": "ok",
            "scheduler_running": scheduler.is_running(),
            "job_count": len(jobs),
            "jobs": job_list
        }
    except Exception as e:
        logger.error(f"스케줄러 상태 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="스케줄러 상태 조회 실패")

@app.post("/api/v1/scheduler/pause")
async def pause_scheduler() -> Dict:
    """스케줄러 일시 정지"""
    try:
        scheduler.pause()
        return {
            "status": "ok",
            "message": "스케줄러가 일시 정지되었습니다",
            "scheduler_running": scheduler.is_running()
        }
    except Exception as e:
        logger.error(f"스케줄러 일시 정지 오류: {e}")
        raise HTTPException(status_code=500, detail="스케줄러 일시 정지 실패")

@app.post("/api/v1/scheduler/resume")
async def resume_scheduler() -> Dict:
    """스케줄러 재개"""
    try:
        scheduler.resume()
        return {
            "status": "ok",
            "message": "스케줄러가 재개되었습니다",
            "scheduler_running": scheduler.is_running()
        }
    except Exception as e:
        logger.error(f"스케줄러 재개 오류: {e}")
        raise HTTPException(status_code=500, detail="스케줄러 재개 실패")

# ==================== Manual Jobs ====================

@app.post("/api/v1/jobs/collect-prices")
async def trigger_collect_prices() -> Dict:
    """즉시 종가 수집 실행"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        logger.info("⚡ 수동 종가 수집 시작")
        crawler = NaverETFCrawler()
        all_tickers = {**PENSION_ETFS, **IRP_PORTFOLIO}
        stats = crawler.collect_all_prices(db, all_tickers)

        return {
            "status": "ok",
            "message": "종가 수집 완료",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"수동 종가 수집 오류: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.post("/api/v1/jobs/calculate-momentum")
async def trigger_calculate_momentum(db: Session = Depends(get_db)) -> Dict:
    """즉시 모멘텀 계산 실행"""
    try:
        logger.info("⚡ 수동 모멘텀 계산 시작")

        # MomentumEngine 생성
        momentum_engine = MomentumEngine(db)
        calc_date = date.today()

        # 모든 종목의 모멘텀 계산
        all_scores = []
        for ticker in PENSION_ETFS.keys():
            score = momentum_engine.calculate_momentum_score(ticker, calc_date)
            all_scores.append(score)

        # 스코어 저장
        saved_count = momentum_engine.save_momentum_scores(all_scores, calc_date)

        # TOP N 선정
        top_n_scores = momentum_engine.select_top_n_passed(calc_date, n=2)

        return {
            "status": "ok",
            "message": "모멘텀 계산 완료",
            "calculated_count": len(all_scores),
            "saved_count": saved_count,
            "top_selected": len(top_n_scores),
            "calculation_date": calc_date.isoformat()
        }
    except Exception as e:
        logger.error(f"수동 모멘텀 계산 오류: {e}")
        raise HTTPException(status_code=500, detail=f"모멘텀 계산 실패: {str(e)}")

@app.post("/api/v1/jobs/check-rebalance")
async def trigger_check_rebalance(db: Session = Depends(get_db)) -> Dict:
    """즉시 리밸런싱 체크 실행"""
    try:
        logger.info("⚡ 수동 리밸런싱 체크 시작")

        # RebalanceEngine 생성
        rebalance_engine = RebalanceEngine(db)
        signal_date = date.today()

        # 리밸런싱 신호 계산
        signals = rebalance_engine.calculate_rebalance_signal(signal_date)

        # 신호 저장
        saved_count = rebalance_engine.save_rebalance_signals(signals)

        # 리밸런싱 필요 여부 체크
        needs_rebalance_count = sum(1 for s in signals if s['needs_rebalance'])

        # 신호 상세 정보
        signal_details = [
            {
                "ticker": s['ticker'],
                "action": s['action'],
                "current_weight": round(s['current_weight'], 2),
                "target_weight": s['target_weight'],
                "weight_diff": round(s['weight_diff'], 2),
                "needs_rebalance": s['needs_rebalance'],
                "rebalance_amount": round(s['rebalance_amount'], 0)
            }
            for s in signals
        ]

        return {
            "status": "ok",
            "message": "리밸런싱 체크 완료",
            "signal_date": signal_date.isoformat(),
            "total_signals": len(signals),
            "needs_rebalance_count": needs_rebalance_count,
            "saved_count": saved_count,
            "signals": signal_details
        }
    except Exception as e:
        logger.error(f"수동 리밸런싱 체크 오류: {e}")
        raise HTTPException(status_code=500, detail=f"리밸런싱 체크 실패: {str(e)}")

# ==================== Shutdown ====================

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료"""
    scheduler.stop()
    logger.info("Server shutdown")

# ==================== Main ====================

if __name__ == "__main__":
    import uvicorn
    logger.info("=" * 70)
    logger.info(f"{API_TITLE} {API_VERSION} Starting")
    logger.info(f"Server: http://127.0.0.1:8000")
    logger.info(f"API Docs: http://127.0.0.1:8000/docs")
    logger.info("=" * 70)

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level=LOG_LEVEL.lower())
