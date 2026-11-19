# -*- coding: utf-8 -*-
"""ReBalancer - 포트폴리오 성과 계산 엔진"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from database import UserPortfolio, ETFPrice
from config import IRP_PORTFOLIO, PENSION_ETFS

logger = logging.getLogger(__name__)

class PortfolioEngine:
    """포트폴리오 수익률 계산 엔진"""

    def __init__(self, db: Session):
        self.db = db

    def get_latest_price(self, ticker: str) -> float:
        """특정 종목의 최신 가격 조회"""
        latest = self.db.query(ETFPrice)\
            .filter(ETFPrice.ticker == ticker)\
            .order_by(ETFPrice.price_date.desc())\
            .first()
        return latest.close_price if latest else 0.0

    def get_previous_close(self, ticker: str) -> Optional[float]:
        """최신 가격 이전(전일 거래일)의 종가. 데이터가 1개뿐이면 None."""
        rows = self.db.query(ETFPrice).filter(ETFPrice.ticker == ticker)\
            .order_by(ETFPrice.price_date.desc()).limit(2).all()
        return rows[1].close_price if len(rows) == 2 else None

    def calculate_holding_performance(self, ticker: str, quantity: float, avg_buy_price: float) -> dict:
        """개별 종목 수익률 계산 (현금은 quantity=금액, avg_buy_price=1)"""
        # 현금 특별 처리
        if ticker == "CASH":
            cash_amount = quantity  # quantity = 현금액
            return {
                "ticker": ticker,
                "quantity": cash_amount,
                "avg_buy_price": 1,
                "current_price": 1,
                "cost_value": cash_amount,
                "current_value": cash_amount,
                "unrealized_return": 0,
                "unrealized_return_pct": 0,
            }

        current_price = self.get_latest_price(ticker)

        if current_price == 0 or avg_buy_price == 0:
            return {
                "ticker": ticker,
                "quantity": quantity,
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "cost_value": avg_buy_price * quantity,
                "current_value": current_price * quantity,
                "unrealized_return": 0,
                "unrealized_return_pct": 0,
            }

        cost_value = avg_buy_price * quantity
        current_value = current_price * quantity
        unrealized_return = current_value - cost_value
        unrealized_return_pct = (unrealized_return / cost_value * 100) if cost_value != 0 else 0

        return {
            "ticker": ticker,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
            "current_price": current_price,
            "cost_value": cost_value,
            "current_value": current_value,
            "unrealized_return": unrealized_return,
            "unrealized_return_pct": unrealized_return_pct,
        }

    def get_portfolio_by_account(self, account_type: str) -> list:
        """계좌 유형별 포트폴리오 조회"""
        portfolio = self.db.query(UserPortfolio)\
            .filter(
                UserPortfolio.account_type == account_type,
                UserPortfolio.is_active == True
            )\
            .all()
        return portfolio

    def calculate_portfolio_performance(self, account_type: str = None) -> dict:
        """포트폴리오 전체 수익률 계산"""

        # 활성 포트폴리오 조회
        if account_type:
            holdings = self.get_portfolio_by_account(account_type)
        else:
            holdings = self.db.query(UserPortfolio)\
                .filter(UserPortfolio.is_active == True)\
                .all()

        if not holdings:
            logger.warning(f"No active portfolio found for {account_type or 'any account'}")
            return {
                "account_type": account_type,
                "total_cost": 0,
                "total_value": 0,
                "total_return": 0,
                "total_return_pct": 0,
                "holdings": [],
            }

        # 연금저축용 Top2 선택 정보 조회
        selected_tickers = set()
        if account_type == "연금저축" or not account_type:
            from database import MomentumScore
            latest = self.db.query(MomentumScore).order_by(MomentumScore.calc_date.desc()).first()
            if latest:
                calc_date = latest.calc_date
                selected = self.db.query(MomentumScore).filter(
                    MomentumScore.calc_date == calc_date,
                    MomentumScore.is_selected == True
                ).all()
                selected_tickers = {s.ticker for s in selected}

        holdings_data = []
        total_cost = 0
        total_value = 0

        for holding in holdings:
            performance = self.calculate_holding_performance(
                holding.ticker,
                holding.quantity,
                holding.avg_buy_price
            )

            performance["account_type"] = holding.account_type
            performance["is_selected"] = holding.ticker in selected_tickers

            # ETF 정보 추가
            etf_info = IRP_PORTFOLIO.get(holding.ticker) or PENSION_ETFS.get(holding.ticker)
            if etf_info:
                performance["name"] = etf_info.get("name", "Unknown")

            holdings_data.append(performance)
            total_cost += performance["cost_value"]
            total_value += performance["current_value"]

        total_return = total_value - total_cost
        total_return_pct = (total_return / total_cost * 100) if total_cost != 0 else 0

        return {
            "account_type": account_type,
            "total_cost": total_cost,
            "total_value": total_value,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "holdings": holdings_data,
            "calculated_at": datetime.now().isoformat(),
        }

    def add_portfolio_holding(self, ticker: str, quantity: float, avg_buy_price: float,
                            account_type: str = "IRP") -> dict:
        """포트폴리오 종목 추가"""

        existing = self.db.query(UserPortfolio)\
            .filter(
                UserPortfolio.ticker == ticker,
                UserPortfolio.account_type == account_type
            )\
            .first()

        if existing:
            if existing.is_active:
                logger.warning(f"Portfolio holding already exists: {ticker} in {account_type}")
                return {"error": "Already exists"}

            # 이전에 삭제(비활성화)된 종목 재활성화
            existing.quantity = quantity
            existing.avg_buy_price = avg_buy_price
            existing.is_active = True
            existing.updated_at = datetime.now()
            self.db.commit()
            self.db.refresh(existing)
            logger.info(f"Portfolio holding reactivated: {ticker} x{quantity} @ {avg_buy_price} ({account_type})")
            return self.calculate_holding_performance(ticker, quantity, avg_buy_price)

        holding = UserPortfolio(
            ticker=ticker,
            quantity=quantity,
            avg_buy_price=avg_buy_price,
            account_type=account_type,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.db.add(holding)
        self.db.commit()
        self.db.refresh(holding)

        logger.info(f"Portfolio holding added: {ticker} x{quantity} @ {avg_buy_price} ({account_type})")
        return self.calculate_holding_performance(ticker, quantity, avg_buy_price)

    def update_portfolio_holding(self, ticker: str, quantity: float, avg_buy_price: float,
                               account_type: str = "IRP") -> dict:
        """포트폴리오 종목 수정"""

        holding = self.db.query(UserPortfolio)\
            .filter(
                UserPortfolio.ticker == ticker,
                UserPortfolio.account_type == account_type
            )\
            .first()

        if not holding:
            logger.error(f"Portfolio holding not found: {ticker} in {account_type}")
            return {"error": "Not found"}

        holding.quantity = quantity
        holding.avg_buy_price = avg_buy_price
        holding.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(holding)

        logger.info(f"Portfolio holding updated: {ticker} x{quantity} @ {avg_buy_price} ({account_type})")
        return self.calculate_holding_performance(ticker, quantity, avg_buy_price)

    def delete_portfolio_holding(self, ticker: str, account_type: str = "IRP") -> bool:
        """포트폴리오 종목 삭제 (비활성화)"""

        holding = self.db.query(UserPortfolio)\
            .filter(
                UserPortfolio.ticker == ticker,
                UserPortfolio.account_type == account_type
            )\
            .first()

        if not holding:
            logger.error(f"Portfolio holding not found: {ticker} in {account_type}")
            return False

        holding.is_active = False
        holding.updated_at = datetime.now()

        self.db.commit()
        logger.info(f"Portfolio holding deleted: {ticker} in {account_type}")
        return True

    def get_portfolio_by_ticker(self, ticker: str, account_type: str = "IRP") -> dict:
        """특정 종목 포트폴리오 조회"""

        holding = self.db.query(UserPortfolio)\
            .filter(
                UserPortfolio.ticker == ticker,
                UserPortfolio.account_type == account_type,
                UserPortfolio.is_active == True
            )\
            .first()

        if not holding:
            return None

        return self.calculate_holding_performance(
            holding.ticker,
            holding.quantity,
            holding.avg_buy_price
        )
