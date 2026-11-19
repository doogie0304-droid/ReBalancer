from database import SessionLocal, MomentumScore, SignalAccuracy

db = SessionLocal()
try:
    m = db.query(MomentumScore).delete()
    s = db.query(SignalAccuracy).delete()
    db.commit()
    print(f"Deleted {m} momentum_scores rows, {s} signal_accuracy rows")
finally:
    db.close()
