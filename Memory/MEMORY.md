# ReBalancer 프로젝트 Memory

**마지막 업데이트**: 2026-07-06 (17:20 KST)  
**현재 상태**: Phase 1 MVP 완료 ✅ | NAS 배포 완료 ✅ (Unix 소켓 + 보안 비밀번호 관리)

---

## 🎯 프로젝트 개요

**프로젝트명**: ReBalancer - ETF 모멘텀 기반 자동 리밸런싱 시스템  
**최종 목표**: 연금저축펀드와 IRP의 자동 모니터링 및 리밸런싱 신호 제공  
**기술 스택**: FastAPI + Uvicorn, MySQL, APScheduler, BeautifulSoup4

---

## ✅ Phase 1 MVP 완료 (100%)

### 구현 완료 항목
1. **크롤러** (crawler.py) - 네이버 금융 종가 수집 ✅
2. **MomentumEngine** (momentum_engine.py) - 모멘텀 점수 계산 ✅
3. **RebalanceEngine** (rebalance_engine.py) - 리밸런싱 신호 생성 ✅
4. **API 엔드포인트** - 모든 주요 기능 API 완성 ✅
5. **Scheduler** - APScheduler 자동화 ✅
6. **통합 테스트** - 모든 모듈 정상 작동 ✅

### 서비스 자동화 흐름
```
매일 18:00    → 종가 수집 (크롤러)
매월 2일 09:00 → 모멘텀 계산 (TOP 2 선정)
반기 09:00    → 포트폴리오 리밸런싱 체크
↓
알림 발송 & API 조회
```

### 관리 중인 8개 종목
**연금저축**: 379800, 360750, 402970, 449170  
**IRP**: 379810, 0072R0, 453850, 214980

---

## 🚀 NAS 배포 진행 현황

### STEP 1: NAS 환경 구성 ✅ 완료
- NAS 접속: 192.168.0.46 (doogie_admin, SSH 포트 22)
- 폴더 구조 생성: `/volume1/rebalancer/`
  - src/, data/, venv/, config/, scripts/, docs/
- 권한 설정 완료 (config: 700, 나머지: 755)

### STEP 2: MariaDB 설치 ✅ 완료
- Synology 패키지에서 설치 완료
- 데이터베이스: `rebalance_db` ✅
- 사용자: `rebalancer` / 비밀번호: `RebalancerPass123!` ✅
- 권한: rebalance_db.* 모든 권한 부여 ✅

### STEP 3: Python 환경 & 코드 배포 ✅ 완료

**완료된 작업** (2026-07-06):
1. ✅ Python 가상환경 생성 (`python3 -m venv venv`)
2. ✅ pip, setuptools, wheel 업그레이드
3. ✅ 필수 패키지 설치 완료:
   - FastAPI, Uvicorn, SQLAlchemy, PyMySQL
   - BeautifulSoup4, Requests, APScheduler
4. ✅ GitHub에 ReBalancer 코드 업로드 (https://github.com/doogie0304-droid/ReBalancer)
5. ✅ NAS에서 `git clone` 성공
6. ✅ 모든 의존성 재설치 완료
7. ✅ .env 파일 생성:
   ```
   DB_HOST=localhost
   DB_USER=rebalancer
   DB_PASSWORD=RebalancerPass123!
   DB_NAME=rebalance_db
   LOG_LEVEL=INFO
   ```
8. ✅ Systemd Service 파일 생성 (`/etc/systemd/system/rebalancer.service`)
9. ✅ 서비스 활성화 및 시작 시도

**문제 해결 과정** (2026-07-06):

1. ❌ **MariaDB TCP 연결 실패** (초기)
   - Unix 소켓 설정으로 해결

2. ✅ **Unix 소켓 지원 추가** (완료)
   - config.py 수정: .env.local 우선 로드
   - DATABASE_URL을 환경변수에서 동적으로 생성
   - Unix 소켓 경로 지원: `/run/mysqld/mysqld10.sock`

3. ✅ **보안 비밀번호 관리** (완료)
   - `.env.local` 파일로 민감한 정보 분리
   - `.gitignore`에 `.env`, `.env.local`, `.secrets/` 추가
   - 파일 권한: 600 (소유자만 읽기)

4. ✅ **NAS 배포 완료** (2026-07-06 17:20)
   - GitHub에서 최신 코드 pull
   - .env.local에 NAS 비밀번호 설정
   - ReBalancer 서비스 정상 실행 확인
   - Systemd에서 자동 시작 설정

**최종 연결 정보**:
- 데이터베이스: Unix 소켓 (`/run/mysqld/mysqld10.sock`)
- 사용자: rebalancer
- API 포트: 8000
- 자동 실행: enabled

---

## 📊 핵심 설정값

### 모멘텀 계산 가중치 (config.py)
```python
MOMENTUM_WEIGHTS = {
    "R3": 0.20,   # 3개월
    "R6": 0.30,   # 6개월
    "R12": 0.50,  # 12개월
}
MOMENTUM_POSITIVE_THRESHOLD = 0.0
MOMENTUM_TOP_N = 2
```

### 리밸런싱 설정
```python
REBALANCE_BAND_PCT = 5.0
REBALANCE_CHECK_DATES = [("01", "01"), ("07", "01")]
REBALANCE_CHECK_HOUR = 9
```

### IRP 포트폴리오 목표 배분
```python
360750: 25.0%  (TIGER 미국S&P500)
379810: 15.0%  (KODEX 미국나스닥100)
402970: 15.0%  (ACE 미국배당다우존스)
0072R0: 15.0%  (TIGER KRX금현물)
453850: 15.0%  (ACE 미국30년국채액티브)
214980: 15.0%  (KODEX 단기채권PLUS)
```

---

## 💾 데이터베이스 테이블

| 테이블 | 용도 | 현재 레코드 |
|--------|------|----------|
| etf_prices | 일일 ETF 시세 | 80개 (8종목×10일) |
| momentum_scores | 월별 모멘텀 스코어 | 4개 (4종목×1계산일) |
| rebalance_signals | 리밸런싱 신호 | 6개 (IRP 6종목×1신호일) |

---

## 🔗 주요 파일

| 파일 | 설명 | 상태 |
|------|------|------|
| main.py | FastAPI 메인 & API 엔드포인트 | ✅ |
| crawler.py | 네이버 금융 크롤러 | ✅ |
| momentum_engine.py | 모멘텀 계산 엔진 | ✅ |
| rebalance_engine.py | 리밸런싱 엔진 | ✅ |
| scheduler.py | APScheduler 통합 | ✅ |
| database.py | SQLAlchemy ORM | ✅ |
| config.py | 설정 & 상수 | ✅ |
| notification.py | 알림 시스템 | ⏳ |
| requirements.txt | Python 의존성 | ✅ |

---

## 🔐 보안 비밀번호 관리

### **비밀번호 저장 위치**
- **파일**: `.secrets/db_credentials.txt`
- **접근**: Windows 로컬에서만 (git 제외)
- **권한**: 파일 권한 600 (소유자만 읽기)

### **관리 정책**
1. **절대 공유 금지**
   - git에 커밋하지 않음 (.gitignore에 등록)
   - 이메일/슬랙/문서에 기재하지 않음
   - USB/클라우드에 백업하지 않음

2. **변경 시 절차**
   - `.secrets/db_credentials.txt` 수정
   - `.env.local` (NAS) 동시 업데이트
   - 서비스 재시작

3. **긴급 초기화** (비밀번호 노출 시)
   ```bash
   # NAS에서
   mysql -u root -p
   ALTER USER 'rebalancer'@'localhost' IDENTIFIED BY '[새_비밀번호]';
   FLUSH PRIVILEGES;
   
   # 로컬 .secrets/db_credentials.txt 업데이트
   # NAS .env.local 업데이트
   # 서비스 재시작
   ```

### **현재 비밀번호 정보**
- **저장 위치**: `.secrets/db_credentials.txt`
- **사용처**: 
  - Windows 개발: `.env.local`
  - NAS 운영: `/volume1/rebalancer/.env.local`
- **마지막 변경**: 2026-07-06 (Unix 소켓 설정 시)

---

## 🔐 NAS SSH 접속 방법

### 현재 방식: 수동 실행 (방법 2)
**진행 일자**: 2026-07-06  
**접속 방식**: PowerShell 터미널 수동 입력

```powershell
# 1. NAS에 SSH 접속
ssh doogie_admin@192.168.0.46

# 비밀번호 입력 → STEP 3 명령어 실행
```

**상태**: 🔄 진행 중 (STEP 3 수동 실행)

### 추후 계획: SSH 키 설정 (방법 1)
**목표**: 비밀번호 없이 자동 접속  
**예상 시기**: STEP 3 완료 후 (2026-07-07 이후)

**SSH 키 설정 절차**:
1. Windows에서 SSH 공개키 생성
   ```powershell
   ssh-keygen -t rsa -b 4096 -f $env:USERPROFILE\.ssh\id_rsa -N ""
   ```

2. NAS에 공개키 등록
   ```powershell
   ssh-copy-id -i $env:USERPROFILE\.ssh\id_rsa.pub doogie_admin@192.168.0.46
   ```

3. 이후 비밀번호 없이 접속 가능
   ```powershell
   ssh doogie_admin@192.168.0.46
   ```

**설정 후 이점**:
- ✅ STEP 3 이후 자동화 작업에서 비밀번호 입력 불필요
- ✅ SCP 명령어도 자동으로 실행 가능
- ✅ 크론 작업 또는 스케줄된 배포에 활용 가능

---

## 📝 관리 노트

### Phase 1 MVP - 완전 완료 ✅
- ✅ Windows 로컬 환경에서 MVP 완성 (2026-07-06)
- ✅ 모든 핵심 기능 테스트 완료
- ✅ GitHub에 코드 업로드 완료
- ✅ NAS에서 24/7 자동 운영 준비 완료

**운영 환경**:
- 개발: Windows 로컬 (http://localhost:8000/docs)
- 운영: NAS (http://192.168.0.46:8000/docs)

### NAS 배포 진행 상황
**완료율**: 100% ✅

**완료된 것**:
- ✅ NAS 폴더 구조 및 권한 설정
- ✅ MariaDB 설치 및 사용자 생성
- ✅ Python 가상환경 및 모든 의존성
- ✅ GitHub 저장소 생성 및 NAS clone
- ✅ Systemd Service 파일 생성 및 자동 실행
- ✅ Unix 소켓을 통한 MariaDB 연결
- ✅ 보안 비밀번호 관리 시스템 구축
- ✅ ReBalancer 서비스 정상 실행

**배포 완료 시간**: 2026-07-06 17:20 KST

**NAS 접속 정보**:
- IP: 192.168.0.46
- API 포트: 8000
- Swagger UI: http://192.168.0.46:8000/docs
- MariaDB: Unix 소켓 (`/run/mysqld/mysqld10.sock`)

### 향후 계획
- **Phase 2**: 실제 포트폴리오 데이터 연동 (통장 잔액 기반)
- **Phase 3**: 자동 매매 신호 발송
- **Phase 4**: 모바일 앱 개발

---
