# -*- coding: utf-8 -*-
"""ReBalancer - 포트폴리오 성과 계산 엔진"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
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

    def calculate_holding_performance(self, ticker: str, quantity: float, avg_buy_price: float) -> dict:
        """개별 종목 수익률 계산"""
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

        holdings_data = []
        total_cost = 0
        total_value = 0

        for holding in holdings:
            performance = self.calculate_holding_performance(
                holding.ticker,
                holding.quantity,
                holding.avg_buy_price
            )

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
            logger.warning(f"Portfolio holding already exists: {ticker} in {account_type}")
            return {"error": "Already exists"}

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
