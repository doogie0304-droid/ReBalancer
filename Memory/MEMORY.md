# ReBalancer 프로젝트 Memory

**마지막 업데이트**: 2026-07-06  
**현재 상태**: Phase 1 MVP 완료 → NAS 배포 진행 중 (66% 진행)

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

### STEP 3: Python 환경 & 코드 배포 🔄 진행 중

**다음 실행 순서** (NAS 터미널에서):

1. Python 가상환경 생성
   ```bash
   cd /volume1/rebalancer
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip setuptools wheel
   ```

2. requirements.txt 설치
   ```bash
   pip install -r /volume1/rebalancer/src/requirements.txt
   ```

3. ReBalancer 코드 전송 (Windows PC에서)
   ```bash
   scp -r C:\My_Obsidian\Projects\ReBalancer\src/* doogie_admin@192.168.0.46:/volume1/rebalancer/src/
   ```

4. .env 파일 설정
   ```bash
   nano /volume1/rebalancer/config/.env
   ```
   필수 값:
   - DB_HOST=localhost
   - DB_USER=rebalancer
   - DB_PASSWORD=RebalancerPass123!
   - DB_NAME=rebalance_db

5. Systemd Service 파일 생성
   ```bash
   sudo nano /etc/systemd/system/rebalancer.service
   ```

6. 서비스 시작 및 테스트
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable rebalancer
   sudo systemctl start rebalancer
   sudo systemctl status rebalancer
   ```

### 배포 후 검증
- [ ] Systemd 서비스 정상 실행
- [ ] `/api/v1/health` 응답 확인
- [ ] 스케줄러 작업 등록 확인
- [ ] DB 연결 확인
- [ ] 크롤러 자동 실행 확인

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

### 개발 완료 사항
- Windows 로컬 환경에서 MVP 완성 (2026-07-06)
- 모든 핵심 기능 테스트 완료
- API 문서: http://localhost:8000/docs

### 현재 진행 중
- NAS 배포 STEP 3 (Python 환경 구성 대기)
- 예상 완료: 2026-07-07

### 향후 계획
- Phase 2: 실제 포트폴리오 데이터 연동 (통장 잔액 기반)
- Phase 3: 자동 매매 신호 발송
- Phase 4: 모바일 앱 개발

---
