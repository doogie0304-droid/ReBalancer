# -*- coding: utf-8 -*-
"""ReBalancer - 데이터베이스 ORM 모델"""

import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from datetime import datetime

Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class ETFPrice(Base):
    """일별 ETF 시세"""
    __tablename__ = "etf_prices"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), index=True, nullable=False)
    price_date = Column(Date, index=True, nullable=False)
    close_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class MomentumScore(Base):
    """모멘텀 스코어"""
    __tablename__ = "momentum_scores"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), index=True, nullable=False)
    calc_date = Column(Date, index=True, nullable=False)
    r3 = Column(Float)
    r6 = Column(Float)
    r12 = Column(Float)
    weighted_score = Column(Float)
    ma10 = Column(Float)
    passed_condition = Column(Boolean)
    rank_in_month = Column(Integer)
    is_selected = Column(Boolean)
    created_at = Column(DateTime, default=datetime.now)

class RebalanceSignal(Base):
    """IRP 리밸런싱 신호"""
    __tablename__ = "rebalance_signals"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), index=True, nullable=False)
    signal_date = Column(Date, index=True, nullable=False)
    target_weight = Column(Float)
    current_weight = Column(Float)
    weight_diff = Column(Float)
    current_price = Column(Float)
    total_assets = Column(Float)
    target_amount = Column(Float)
    current_amount = Column(Float)
    rebalance_amount = Column(Float)
    rebalance_quantity = Column(Float)
    action = Column(String(10))
    needs_rebalance = Column(Boolean)
    created_at = Column(DateTime, default=datetime.now)

class NotificationHistory(Base):
    """알림 발송 이력"""
    __tablename__ = "notification_history"

    id = Column(Integer, primary_key=True, index=True)
    notification_type = Column(String(50), index=True)
    title = Column(String(200))
    message = Column(Text)
    channel = Column(String(20))
    status = Column(String(20))
    sent_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

class CrawlHistory(Base):
    """크롤링 로그"""
    __tablename__ = "crawl_history"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(50))
    crawl_date = Column(Date, index=True)
    status = Column(String(20))
    collected_count = Column(Integer)
    error_count = Column(Integer)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

class UserPortfolio(Base):
    """사용자 보유 포트폴리오"""
    __tablename__ = "user_portfolio"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), index=True, nullable=False)
    quantity = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)
    account_type = Column(String(20), default="IRP")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class SignalAccuracy(Base):
    """신호 신뢰도 평가"""
    __tablename__ = "signal_accuracy"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(String(50), index=True, nullable=False)
    signal_type = Column(String(20), nullable=False)  # 'momentum', 'rebalance'
    signal_date = Column(Date, index=True, nullable=False)
    ticker = Column(String(20), index=True)
    signal_direction = Column(String(10))  # 'BUY', 'SELL', 'HOLD'
    signal_confidence = Column(Float)  # 0.0 ~ 1.0, 신호 발송 시 점수
    price_at_signal = Column(Float)  # 신호 발송 시 가격
    evaluation_date = Column(Date, index=True)  # 평가 실시 날짜 (signal_date + 30일)
    price_at_evaluation = Column(Float)  # 평가 시점 가격
    actual_return_pct = Column(Float)  # 실제 수익률 %
    signal_correct = Column(Boolean)  # 신호 방향이 맞았는지 여부
    accuracy_score = Column(Float)  # 0.0 ~ 1.0, 최종 정확도 점수
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

def init_db():
    """데이터베이스 초기화"""
    Base.metadata.create_all(bind=engine)
    logger = logging.getLogger(__name__)
    logger.info("DB tables created successfully")

def get_db():
    """데이터베이스 세션"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
