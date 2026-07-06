# ReBalancer - ETF 모멘텀 기반 자동 리밸런싱 시스템

## 개요

연금저축펀드와 IRP의 모멘텀을 자동으로 계산하고 리밸런싱 신호를 제공합니다.

## 주요 기능

### 1. 모멘텀 계산
- 3개월(20%), 6개월(30%), 12개월(50%) 가중 평균
- 월별 자동 계산 (매월 2일 09:00)
- TOP 2 종목 자동 선정

### 2. IRP 리밸런싱
- 고정비중 포트폴리오 관리
- ±5%p 밴드 이탈 감지
- 반기(1/1, 7/1)마다 체크

### 3. 자동 스케줄링
- 매일 18:00: 종가 수집
- 매월 2일 09:00: 모멘텀 계산
- 반기 09:00: 리밸런싱 체크

## 빠른 시작

### 1. 가상환경 설정
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 설정
```bash
mysql -u root -p

CREATE DATABASE rebalance_db CHARACTER SET utf8mb4;
CREATE USER 'rebalance_user'@'localhost' IDENTIFIED BY 'rebalance_pass';
GRANT ALL PRIVILEGES ON rebalance_db.* TO 'rebalance_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 4. 환경 설정
```bash
cp .env.example .env
# 필요시 수정
```

### 5. 서버 시작
```bash
python main.py
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 헬스 체크 |
| GET | `/api/v1/etfs` | 관리 종목 |
| GET | `/api/v1/momentum/latest` | 최신 모멘텀 |
| GET | `/api/v1/rebalance/latest` | 최신 신호 |
| GET | `/api/v1/notifications/pending` | 미발송 알림 |
| GET | `/api/v1/scheduler/status` | 스케줄러 상태 |
| POST | `/api/v1/jobs/collect-prices` | 즉시 종가 수집 |
| POST | `/api/v1/jobs/calculate-momentum` | 즉시 모멘텀 계산 |
| POST | `/api/v1/jobs/check-rebalance` | 즉시 리밸런싱 체크 |
| POST | `/api/v1/scheduler/pause` | 스케줄러 일시 정지 |
| POST | `/api/v1/scheduler/resume` | 스케줄러 재개 |

## API 문서

서버 실행 후 http://localhost:8000/docs 접속

## 문제 해결

### 데이터베이스 연결 오류
```bash
mysql -u rebalance_user -p rebalance_db
SHOW TABLES;
```

### 크롤링 실패
- 네이버 금융 페이지 CSS 선택자 변경 확인
- `crawler.py`의 `NAVER_CRAWLER_SELECTORS` 업데이트

### 스케줄 미실행
- `/api/v1/scheduler/status` API로 확인
- 로그 파일 확인: `logs/rebalancer.log`

## Phase 2 계획

- 사용자 포트폴리오 입력 API
- FCM 푸시 알림
- 모바일 앱 (Flutter/PWA)
- CAGR/MDD 대시보드

---

**버전:** 1.0.0
