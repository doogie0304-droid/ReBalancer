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
