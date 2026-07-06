# ReBalancer 코드 수정 상세 문서

## 📝 개요
이 문서는 ReBalancer 프로젝트의 구조적, 기능적 결함을 식별하고 수정한 내용을 상세히 설명합니다.

---

## 1️⃣ crawler.py 주요 수정사항

### 1.1 fetch_page() - 명시적 None 반환
**문제:**
```python
def fetch_page(self, ticker: str, page: int = 1) -> str:
    for attempt in range(CRAWL_RETRY_COUNT):
        try:
            # ...
            return response.text
        except Exception as e:
            # ...
    # 반환문 없음 → None 암시적 반환
```

**원인:** 모든 재시도가 실패하면 명시적 반환문이 없어서 `None` 반환

**영향:**
```python
html = self.fetch_page(ticker)  # None 반환 가능
prices = self.parse_price_data(html)  # None을 BeautifulSoup에 전달
# TypeError: expected string or bytes-like object
```

**수정:**
```python
def fetch_page(self, ticker: str, page: int = 1) -> Optional[str]:
    for attempt in range(CRAWL_RETRY_COUNT):
        try:
            response = requests.get(...)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.warning(f"...")
            if attempt < CRAWL_RETRY_COUNT - 1:
                time.sleep(CRAWL_RETRY_DELAY)
    
    # 명시적 None 반환 + 에러 로깅
    logger.error(f"❌ {ticker}: {CRAWL_RETRY_COUNT}회 재시도 후 실패")
    return None
```

### 1.2 parse_price_data() - Null 가드 추가
**문제:**
```python
def parse_price_data(self, html: str):
    soup = BeautifulSoup(html, 'html.parser')  # html이 None이면 크래시
```

**수정:**
```python
def parse_price_data(self, html: Optional[str]) -> List[Tuple[str, float]]:
    # Null 가드
    if not html:
        logger.warning("HTML 입력이 None 또는 빈 문자열입니다")
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    prices = []
    # ...
```

### 1.3 BeautifulSoup 선택자 개선
**문제:**
```python
table = soup.find('table', class_='tbl_data tbl_type1 tbl_quant')
```

**문제점:**
- 공백으로 구분된 클래스명 문자열 매칭은 불안정
- BeautifulSoup의 `class_` 파라미터는 단순 문자열 매칭
- 클래스 순서나 추가 공백이 있으면 작동 안 함

**수정:**
```python
# CSS 선택자 사용 (더 안정적)
table = soup.select_one('table.tbl_data.tbl_type1.tbl_quant')
```

### 1.4 예외 처리 개선
**문제:**
```python
try:
    price = float(price_str)
except:  # bare except - 너무 광범위
    continue
```

**수정:**
```python
try:
    price = float(price_str)
except (ValueError, IndexError) as e:
    logger.debug(f"행 {idx} 파싱 오류 (무시): {e}")
    continue
```

### 1.5 DB 저장 로직 추가 (✨ 새로운 기능)
**문제:** 파싱된 데이터를 메모리에만 보관 (휘발성)

**수정:** `save_prices_to_db()` 메서드 추가
```python
def save_prices_to_db(
    self, 
    db: Session, 
    ticker: str, 
    prices: List[Tuple[str, float]]
) -> int:
    """파싱된 시세를 데이터베이스에 저장"""
    saved_count = 0
    
    for date_str, close_price in prices:
        try:
            price_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # 중복 체크
            existing = db.query(ETFPrice).filter(
                ETFPrice.ticker == ticker,
                ETFPrice.price_date == price_date
            ).first()
            
            if existing:
                existing.close_price = close_price
            else:
                record = ETFPrice(
                    ticker=ticker,
                    price_date=price_date,
                    close_price=close_price
                )
                db.add(record)
            
            saved_count += 1
            
        except ValueError as e:
            logger.warning(f"날짜 파싱 실패 ({date_str}): {e}")
            continue
    
    try:
        db.commit()
        logger.info(f"✅ {ticker}: {saved_count}건 저장 완료")
    except Exception as e:
        db.rollback()
        logger.error(f"DB 커밋 실패: {e}")
        saved_count = 0
    
    return saved_count
```

### 1.6 collect_all_prices() 개선
**문제:**
```python
html = self.fetch_page(ticker)
prices = self.parse_price_data(html)  # html이 None일 수 있음

if not prices:
    stats['skip'] += 1
```

**수정:**
```python
html = self.fetch_page(ticker)
if html is None:
    logger.warning(f"⚠️  {ticker_name}: 페이지 다운로드 실패")
    stats['fail'] += 1
    continue

prices = self.parse_price_data(html)
if not prices:
    logger.warning(f"⚠️  {ticker_name}: 시세 데이터 파싱 실패")
    stats['skip'] += 1
    continue

# DB 저장
saved_count = self.save_prices_to_db(db, ticker, prices)
if saved_count > 0:
    stats['success'] += 1
else:
    stats['fail'] += 1
```

### 1.7 타입 힌팅 추가
```python
from typing import Optional, List, Tuple, Dict

def fetch_page(self, ticker: str, page: int = 1) -> Optional[str]:
    """..."""

def parse_price_data(self, html: Optional[str]) -> List[Tuple[str, float]]:
    """..."""

def save_prices_to_db(
    self, 
    db: Session, 
    ticker: str, 
    prices: List[Tuple[str, float]]
) -> int:
    """..."""

def collect_all_prices(
    self, 
    db: Session, 
    tickers: Optional[Dict[str, Dict]] = None
) -> Dict[str, int]:
    """..."""
```

---

## 2️⃣ config.py 수정사항

### 2.1 티커 코드 정정
**문제:**
```python
"072r0": {"name": "TIGER KRX금현물", "target_weight": 15.0},
```

**문제점:**
- 선행 0 누락 (정확: `0072R0`)
- 소문자 `r` (정확: 대문자 `R`)

**수정:**
```python
"0072R0": {"name": "TIGER KRX금현물", "target_weight": 15.0},
```

**확인:** 김동건 확인함

---

## 3️⃣ scheduler.py 주요 수정사항

### 3.1 실제 Job 구현
**문제:**
```python
def _job_collect_prices(self):
    """종가 수집 작업"""
    logger.info("🔄 종가 수집")  # 로그만 출력
```

**수정:** 실제 크롤러 호출
```python
def _job_collect_prices(self):
    """종가 수집 작업"""
    logger.info("=" * 70)
    logger.info(f"🔄 [종가 수집] 시작 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    db = None
    try:
        db = next(get_db())
        stats = self.crawler.collect_all_prices(db, PENSION_ETFS)
        logger.info(
            f"✅ [종가 수집] 완료 - "
            f"성공: {stats['success']}, 실패: {stats['fail']}, 스킵: {stats['skip']}"
        )
    except Exception as e:
        logger.error(f"❌ [종가 수집] 오류: {type(e).__name__}: {e}", exc_info=True)
    finally:
        if db:
            db.close()
        logger.info("=" * 70)
```

### 3.2 스케줄 3가지 추가
1. **매일 18:00**: 종가 수집
2. **매월 2일 09:00**: 모멘텀 계산
3. **반기(1/1, 7/1) 09:00**: 리밸런싱 체크

```python
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
    
    # Job 2: 매월 2일 09:00 모멘텀 계산
    self.scheduler.add_job(
        self._job_calculate_momentum,
        trigger=CronTrigger(
            day=MOMENTUM_SCHEDULE_MONTH_DAY, 
            hour=MOMENTUM_SCHEDULE_HOUR, 
            minute=0, 
            timezone=tz
        ),
        id='calculate_momentum',
        name='월별 모멘텀 계산',
        replace_existing=True,
        max_instances=1
    )
    
    # Job 3: 반기(1/1, 7/1) 09:00 리밸런싱 체크
    for month, day in REBALANCE_CHECK_DATES:
        job_id = f'check_rebalance_{month}{day}'
        self.scheduler.add_job(
            self._job_check_rebalance,
            trigger=CronTrigger(
                month=month, 
                day=day, 
                hour=REBALANCE_CHECK_HOUR, 
                minute=0, 
                timezone=tz
            ),
            id=job_id,
            name=f'{month}월 {day}일 리밸런싱 체크',
            replace_existing=True,
            max_instances=1
        )
```

### 3.3 스케줄러 제어 메서드 추가
```python
def pause(self):
    """스케줄러 일시 정지"""
    if self.scheduler.running:
        self.scheduler.pause()
        logger.info("⏸️  스케줄러 일시 정지")

def resume(self):
    """스케줄러 재개"""
    if self.scheduler.running:
        self.scheduler.resume()
        logger.info("▶️  스케줄러 재개")

def get_jobs(self):
    """등록된 job 목록 조회"""
    return self.scheduler.get_jobs()

def is_running(self) -> bool:
    """스케줄러 실행 여부"""
    return self.scheduler.running
```

---

## 4️⃣ main.py 주요 수정사항

### 4.1 기본 API 엔드포인트 구현
README에서 명시된 API 중 다음을 구현:

| 메서드 | 경로 | 설명 | 상태 |
|---|---|---|---|
| GET | `/health` | 헬스 체크 | ✅ |
| GET | `/api/v1/etfs` | 관리 종목 목록 | ✅ |
| GET | `/api/v1/etfs/{ticker}` | 특정 종목 시세 | ✅ |
| GET | `/api/v1/momentum/latest` | 최신 모멘텀 | ✅ |
| GET | `/api/v1/rebalance/latest` | 최신 신호 | ✅ |
| GET | `/api/v1/scheduler/status` | 스케줄러 상태 | ✅ |
| POST | `/api/v1/scheduler/pause` | 스케줄러 일시 정지 | ✅ |
| POST | `/api/v1/scheduler/resume` | 스케줄러 재개 | ✅ |
| POST | `/api/v1/jobs/collect-prices` | 즉시 종가 수집 | ✅ |
| POST | `/api/v1/jobs/calculate-momentum` | 즉시 모멘텀 계산 | ⏳ Phase 2 |
| POST | `/api/v1/jobs/check-rebalance` | 즉시 리밸런싱 체크 | ⏳ Phase 2 |

### 4.2 에러 처리 개선
```python
@app.get("/api/v1/etfs/{ticker}")
async def get_etf_prices(
    ticker: str, 
    limit: int = 30,
    db: Session = Depends(get_db)
) -> Dict:
    """특정 종목의 시세 조회"""
    try:
        limit = min(limit, 100)  # 최대 100개로 제한
        
        prices = db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker
        ).order_by(
            ETFPrice.price_date.desc()
        ).limit(limit).all()
        
        if not prices:
            raise HTTPException(
                status_code=404, 
                detail=f"종목 {ticker}의 데이터가 없습니다"
            )
        
        # 데이터 변환
        data = [...]
        
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
```

### 4.3 스케줄러 상태 API
```python
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
```

---

## 📊 수정 요약

### Critical Issues (즉시 수정)
| # | 파일 | 문제 | 수정 |
|---|------|------|------|
| 1 | crawler.py | fetch_page() 암시적 None | ✅ 명시적 반환 + 로깅 |
| 2 | crawler.py | parse_price_data() null 처리 | ✅ Null 가드 추가 |
| 3 | crawler.py | BeautifulSoup 선택자 | ✅ CSS 선택자로 변경 |
| 4 | config.py | 티커 코드 오류 | ✅ 0072R0 수정 |
| 5 | crawler.py | DB 미저장 | ✅ save_prices_to_db() 추가 |

### High Priority Issues
| # | 파일 | 문제 | 상태 |
|---|------|------|------|
| 6 | scheduler.py | Job 미구현 | ✅ 실제 구현 완료 |
| 7 | main.py | API 미구현 | ✅ 기본 API 구현 |

### Code Quality
| # | 파일 | 개선 | 상태 |
|---|------|------|------|
| 8 | crawler.py | 타입 힌팅 | ✅ 추가 |
| 9 | crawler.py | 예외 처리 | ✅ bare except 제거 |
| 10 | crawler.py | Import 최적화 | ✅ 모듈 상단으로 이동 |

---

## 🚀 다음 단계 (Phase 2)

### 1. 계산 엔진 구현
- `MomentumEngine.calculate_momentum_score()` 실제 구현
- `RebalanceEngine.calculate_rebalance_signal()` 실제 구현

### 2. 알림 기능
- FCM 푸시 알림 구현
- Telegram 봇 알림 구현

### 3. 마이그레이션 관리
- Alembic 도입
- 스키마 버전 관리

### 4. 테스트
- Unit test (pytest)
- Integration test
- E2E test

### 5. 모니터링
- 로그 수집 및 분석
- 메트릭 수집 (Prometheus)
- 대시보드 (Grafana)

---

## 💡 QA 관점의 검토 체크리스트

✅ **입력 유효성**
- None/null 입력 처리
- 경계값 처리 (max_instances=1)
- 유효한 날짜 형식

✅ **에러 처리**
- 예외 타입 명시
- 복구 불가능한 에러 로깅
- 사용자 친화적 에러 메시지

✅ **리소스 관리**
- DB 세션 close() 호출
- 트랜잭션 롤백 처리
- 메모리 누수 방지

✅ **로깅**
- 모든 중요 작업 로깅
- 에러 로깅 (exc_info=True)
- 타임스탬프 포함

✅ **보안**
- SQL 인젝션 방지 (ORM 사용)
- CORS 설정 (명확히 하기)
- API 인증 (Phase 2)

---

**작성자:** Claude (AI Assistant)  
**작성일:** 2026-07-05  
**검토자:** 김동건
