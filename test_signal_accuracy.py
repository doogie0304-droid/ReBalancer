# -*- coding: utf-8 -*-
"""신호 신뢰도 평가 엔진 테스트"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 프로젝트 디렉토리 추가
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Windows UTF-8 인코딩 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import SessionLocal, init_db, SignalAccuracy, ETFPrice
from signal_accuracy_engine import SignalAccuracyEngine
from config import IRP_PORTFOLIO

def test_signal_accuracy():
    """신호 신뢰도 테스트"""

    print("=" * 60)
    print("SIGNAL ACCURACY ENGINE TEST")
    print("=" * 60)

    # 데이터베이스 초기화
    init_db()
    db = SessionLocal()

    try:
        accuracy_engine = SignalAccuracyEngine(db)

        print("\n[Test 1] 모멘텀 신호 기록")
        print("-" * 60)

        # 테스트용 모멘텀 스코어
        momentum_data = {
            "weighted_score": 25.5,
            "r3": 5.2,
            "r6": 10.3,
            "r12": 20.1,
        }

        ticker = "360750"
        signal_date = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")

        result = accuracy_engine.record_momentum_signal(ticker, momentum_data, signal_date)
        print(f"Signal recorded: {result}")
        print(f"Signal ID: {result['signal_id']}")
        print(f"Direction: {result['direction']}")
        print(f"Confidence: {result['confidence']:.3f}")

        print("\n[Test 2] 리밸런싱 신호 기록")
        print("-" * 60)

        signal_date2 = (datetime.now() - timedelta(days=32)).strftime("%Y-%m-%d")
        result2 = accuracy_engine.record_rebalance_signal("379810", "BUY", signal_date2, 50000)
        print(f"Signal recorded: {result2}")
        print(f"Signal ID: {result2['signal_id']}")

        print("\n[Test 3] 평가 대기 신호 조회")
        print("-" * 60)

        pending = accuracy_engine.get_pending_evaluations()
        print(f"Pending evaluations: {len(pending)}")
        for sig in pending:
            print(f"  - {sig['signal_id']} ({sig['days_elapsed']} days elapsed)")

        print("\n[Test 4] 신호 평가")
        print("-" * 60)

        if pending:
            signal_id = pending[0]["signal_id"]
            print(f"Evaluating signal: {signal_id}")

            # 평가를 위해 30일 뒤 가격 데이터 필요
            print("(실제 평가는 30일 뒤 가격 데이터가 필요합니다)")

        print("\n[Test 5] 정확도 통계")
        print("-" * 60)

        stats = accuracy_engine.get_accuracy_stats(limit_days=90)
        print(f"Total signals: {stats['total_signals']}")
        print(f"Evaluated signals: {stats['evaluated_signals']}")
        print(f"Accuracy rate: {stats['accuracy_rate']}%")
        print(f"Avg accuracy score: {stats['avg_accuracy_score']}")

        print("\n" + "=" * 60)
        print("TEST COMPLETED")
        print("=" * 60)

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_signal_accuracy()
