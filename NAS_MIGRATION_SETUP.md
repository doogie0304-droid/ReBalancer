# ReBalancer NAS 마이그레이션 가이드
## Python 가상환경 설정 및 코드 배포

---

## 📋 목차
1. NAS 환경 준비
2. Python 가상환경 설치
3. ReBalancer 코드 마이그레이션
4. 환경 설정
5. Systemd Service 등록
6. 운영 스크립트
7. 테스트 및 검증

---

## 1️⃣ NAS 환경 준비

### 1.1 SSH 접속

```bash
# 로컬 PC에서
ssh admin@[NAS_IP]

# NAS에 접속되면 아래 명령어 실행
# (앞의 명령어는 admin으로, 이후는 필요시 sudo)
```

### 1.2 폴더 구조 생성

```bash
# SSH 접속 상태에서 실행

# 1. 메인 디렉토리 생성
sudo mkdir -p /volume1/rebalancer/{src,data,venv,config,scripts,docs}
sudo mkdir -p /volume1/rebalancer/data/{logs,backups/{daily,weekly,monthly}}

# 2. 권한 설정
sudo chown -R rebalancer:rebalancer /volume1/rebalancer
sudo chmod 755 /volume1/rebalancer
sudo chmod 700 /volume1/rebalancer/config

# 3. 생성 확인
sudo ls -la /volume1/rebalancer/
```

### 1.3 Python 설치 확인

```bash
# Python 버전 확인
python3 --version
# 출력 예: Python 3.8.x 이상 필요

# pip 확인
pip3 --version
# 출력 예: pip 21.x.x from ...

# 필요시 업그레이드
sudo pip3 install --upgrade pip
```

---

## 2️⃣ Python 가상환경 설치

### 2.1 가상환경 생성

```bash
# 1. 가상환경 생성 위치로 이동
cd /volume1/rebalancer

# 2. 가상환경 생성
python3 -m venv venv

# 3. 가상환경 활성화
source venv/bin/activate

# 4. 프롬프트 변경 확인
# (venv) rebalancer@nas:/volume1/rebalancer$

# 5. pip 업그레이드
pip install --upgrade pip setuptools wheel

echo "Virtual environment created successfully"
```

### 2.2 의존성 설치

```bash
# 가상환경 활성화 상태에서 실행

# 1. requirements.txt 준비 (로컬에서 미리 업데이트)
# 아래 내용을 /volume1/rebalancer/src/requirements.txt에 저장

pip install -r /volume1/rebalancer/src/requirements.txt

# 2. 설치 확인
pip list
# FastAPI, uvicorn, sqlalchemy, pymysql 등이 보여야 함

# 3. 가상환경 비활성화
deactivate
```

**requirements.txt 내용** (최신버전):
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
pymysql==1.1.0
cryptography==41.0.7
beautifulsoup4==4.12.2
requests==2.31.0
python-dotenv==1.0.0
apscheduler==3.10.4
pytz==2023.3.post1
```

---

## 3️⃣ ReBalancer 코드 마이그레이션

### 3.1 코드 전송

**옵션 A: SCP를 이용한 파일 전송** (권장)

```bash
# 로컬 PC에서 실행

# 1. 단일 파일 전송
scp main.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp crawler.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp momentum_engine.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp rebalance_engine.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp scheduler.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp database.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp config.py admin@[NAS_IP]:/volume1/rebalancer/src/
scp requirements.txt admin@[NAS_IP]:/volume1/rebalancer/src/

# 또는 2. 한 번에 폴더 전송
scp -r /path/to/ReBalancer/src/* admin@[NAS_IP]:/volume1/rebalancer/src/
```

**옵션 B: Synology NAS 공유 폴더 이용** (GUI 선호할 때)

1. Synology DSM 웹 인터페이스 로그인
2. 파일 관리자 → `rebalancer` 공유폴더
3. `src` 폴더에 파일 드래그앤드롭 업로드

### 3.2 파일 권한 설정

```bash
# SSH에서 실행

# 1. 소유권 설정
sudo chown rebalancer:rebalancer /volume1/rebalancer/src/*.py
sudo chown rebalancer:rebalancer /volume1/rebalancer/src/requirements.txt

# 2. 파일 권한 설정
chmod 644 /volume1/rebalancer/src/*.py
chmod 644 /volume1/rebalancer/src/requirements.txt

# 3. main.py는 실행 가능하게
chmod 755 /volume1/rebalancer/src/main.py

# 4. 확인
ls -la /volume1/rebalancer/src/
```

### 3.3 마이그레이션 검증

```bash
# SSH에서 실행

# 1. 가상환경 활성화
source /volume1/rebalancer/venv/bin/activate

# 2. 디렉토리 이동
cd /volume1/rebalancer/src

# 3. Python 문법 검사
python3 -m py_compile *.py
# 에러 없으면 정상

# 4. Import 테스트
python3 << 'EOF'
import main
import crawler
import momentum_engine
import rebalance_engine
import scheduler
import database
import config
print("All modules imported successfully!")
EOF

# 5. 가상환경 비활성화
deactivate

echo "Migration validation completed"
```

---

## 4️⃣ 환경 설정

### 4.1 .env 파일 설정

**파일**: `/volume1/rebalancer/config/.env`

```bash
# SSH에서 생성
sudo nano /volume1/rebalancer/config/.env

# 아래 내용 추가:
```

```ini
# ============================================
# ReBalancer NAS Configuration
# ============================================

# Database
DATABASE_URL=mysql+pymysql://rebalancer:SecurePassword123!@#@localhost:3306/rebalance_db

# API
API_TITLE=ReBalancer
API_DESCRIPTION=ETF Momentum-based Auto Rebalancing System
API_VERSION=1.0.0
API_PREFIX=/api/v1
API_HOST=127.0.0.1
API_PORT=8000

# Logging
LOG_LEVEL=INFO
LOG_DIR=/volume1/rebalancer/data/logs
LOG_FILE=rebalancer.log

# Paths
BACKUP_DIR=/volume1/rebalancer/data/backups
PROJECT_ROOT=/volume1/rebalancer

# Timezone
TIMEZONE=Asia/Seoul

# Environment
ENVIRONMENT=production
DEBUG=False

# Crawler
NAVER_CRAWLER_TIMEOUT=10
CRAWL_RETRY_COUNT=3
CRAWL_RETRY_DELAY=5

# Notifications (Optional)
NOTIFICATION_CHANNELS=console
FCM_API_KEY=
TELEGRAM_BOT_TOKEN=
SMTP_SERVER=
```

**권한 설정**:
```bash
sudo chmod 600 /volume1/rebalancer/config/.env
sudo chown rebalancer:rebalancer /volume1/rebalancer/config/.env
```

### 4.2 config.py에서 환경변수 로드

**업데이트**: config.py 첫줄에서 .env 로드

```python
# config.py 최상단
import os
from dotenv import load_dotenv

# NAS 환경변수 로드
PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/volume1/rebalancer")
load_dotenv(os.path.join(PROJECT_ROOT, "config", ".env"))

# 이후 코드는 os.getenv() 사용
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://rebalancer:password@localhost:3306/rebalance_db"
)
```

---

## 5️⃣ Systemd Service 등록

### 5.1 Systemd Service 파일 생성

**파일**: `/etc/systemd/system/rebalancer.service`

```bash
# SSH에서 생성
sudo nano /etc/systemd/system/rebalancer.service

# 아래 내용 추가:
```

```ini
[Unit]
Description=ReBalancer ETF Auto Rebalancing Service
Documentation=file:///volume1/rebalancer/docs/README.md
After=network.target mysql.service
Wants=network-online.target
StartLimitInterval=60
StartLimitBurst=3

[Service]
Type=simple
User=rebalancer
Group=rebalancer
WorkingDirectory=/volume1/rebalancer/src

# Environment variables
EnvironmentFile=/volume1/rebalancer/config/.env
Environment="PATH=/volume1/rebalancer/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Start command
ExecStart=/volume1/rebalancer/venv/bin/python main.py

# Restart policy
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rebalancer

# Resource limits
MemoryLimit=512M
CPUQuota=50%

# Process management
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# Security
PrivateTmp=yes
ProtectHome=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
Alias=rebalancer.service
```

### 5.2 Service 파일 등록 및 테스트

```bash
# 1. Systemd 설정 재로드
sudo systemctl daemon-reload

# 2. 서비스 활성화 (자동 시작)
sudo systemctl enable rebalancer

# 3. 서비스 시작
sudo systemctl start rebalancer

# 4. 서비스 상태 확인
sudo systemctl status rebalancer

# 5. 서비스 로그 확인
sudo journalctl -u rebalancer -n 50 -f

# 6. 서비스 중지 (테스트용)
sudo systemctl stop rebalancer

# 7. 서비스 재시작
sudo systemctl restart rebalancer
```

**정상 로그 예**:
```
Jul 06 15:00:24 nas systemd[1]: Started ReBalancer ETF Auto Rebalancing Service.
Jul 06 15:00:25 rebalancer[1234]: 2026-07-06 15:00:25,123 - __main__ - INFO - ======================================================================
Jul 06 15:00:25 rebalancer[1234]: ReBalancer 1.0.0 Starting
Jul 06 15:00:25 rebalancer[1234]: Server: http://127.0.0.1:8000
Jul 06 15:00:25 rebalancer[1234]: Application startup complete.
```

---

## 6️⃣ 운영 스크립트

### 6.1 시작/중지/재시작 스크립트

**파일**: `/volume1/rebalancer/scripts/start.sh`

```bash
#!/bin/bash
echo "Starting ReBalancer service..."
sudo systemctl start rebalancer
sleep 2
sudo systemctl status rebalancer
```

**파일**: `/volume1/rebalancer/scripts/stop.sh`

```bash
#!/bin/bash
echo "Stopping ReBalancer service..."
sudo systemctl stop rebalancer
sleep 2
echo "Service stopped"
```

**파일**: `/volume1/rebalancer/scripts/restart.sh`

```bash
#!/bin/bash
echo "Restarting ReBalancer service..."
sudo systemctl restart rebalancer
sleep 2
sudo systemctl status rebalancer
```

**파일**: `/volume1/rebalancer/scripts/status.sh`

```bash
#!/bin/bash
echo "=== ReBalancer Service Status ==="
sudo systemctl status rebalancer
echo ""
echo "=== Recent Logs (last 20 lines) ==="
sudo journalctl -u rebalancer -n 20
```

**파일**: `/volume1/rebalancer/scripts/health_check.sh`

```bash
#!/bin/bash

LOG_FILE="/volume1/rebalancer/data/logs/health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 1. 프로세스 확인
if systemctl is-active --quiet rebalancer; then
    PROCESS_STATUS="✓ Running"
else
    PROCESS_STATUS="✗ Stopped"
    systemctl restart rebalancer
    echo "[$TIMESTAMP] Service auto-restarted" >> $LOG_FILE
fi

# 2. API 응답 확인
HEALTH=$(curl -s http://127.0.0.1:8000/health 2>/dev/null)
if echo "$HEALTH" | grep -q "healthy"; then
    API_STATUS="✓ Responding"
else
    API_STATUS="✗ Not responding"
fi

# 3. MariaDB 연결 확인
if mysql -u rebalancer -p'SecurePassword123!@#' -e "SELECT 1;" rebalance_db &>/dev/null; then
    DB_STATUS="✓ Connected"
else
    DB_STATUS="✗ Disconnected"
fi

# 4. 디스크 사용률
DISK_USAGE=$(df /volume1 | awk 'NR==2 {print $5}')
if [ "${DISK_USAGE%\%}" -lt 80 ]; then
    DISK_STATUS="✓ ${DISK_USAGE}"
else
    DISK_STATUS="⚠ ${DISK_USAGE}"
fi

# 5. 메모리 사용률
MEM_USAGE=$(free | awk 'NR==2 {printf("%.0f%%", $3/$2*100)}')
if [ "${MEM_USAGE%\%}" -lt 80 ]; then
    MEM_STATUS="✓ ${MEM_USAGE}"
else
    MEM_STATUS="⚠ ${MEM_USAGE}"
fi

# 결과 출력
echo "[$TIMESTAMP] Health Check Results:"
echo "  Process: $PROCESS_STATUS"
echo "  API: $API_STATUS"
echo "  Database: $DB_STATUS"
echo "  Disk: $DISK_STATUS"
echo "  Memory: $MEM_STATUS"

# 로그에 기록
echo "[$TIMESTAMP] $PROCESS_STATUS | $API_STATUS | $DB_STATUS | $DISK_STATUS | $MEM_STATUS" >> $LOG_FILE
```

**실행 권한 설정**:
```bash
chmod +x /volume1/rebalancer/scripts/*.sh
```

### 6.2 Cron 헬스 체크 등록

```bash
# rebalancer 사용자의 crontab
crontab -u rebalancer -e

# 아래 추가:
# 매 5분마다 헬스 체크
*/5 * * * * /volume1/rebalancer/scripts/health_check.sh
```

---

## 7️⃣ 테스트 및 검증

### 7.1 기본 동작 테스트

```bash
# 1. 서비스 상태 확인
sudo systemctl status rebalancer

# 2. 로그 확인
sudo journalctl -u rebalancer -n 30

# 3. API 응답 확인
curl http://127.0.0.1:8000/health | python3 -m json.tool

# 4. 스케줄 확인
curl http://127.0.0.1:8000/api/v1/scheduler/status | python3 -m json.tool
```

### 7.2 API 엔드포인트 테스트

```bash
# 1. 관리 종목 조회
curl http://127.0.0.1:8000/api/v1/etfs | python3 -m json.tool

# 2. 최신 모멘텀 데이터
curl http://127.0.0.1:8000/api/v1/momentum/latest | python3 -m json.tool

# 3. 최신 리밸런싱 신호
curl http://127.0.0.1:8000/api/v1/rebalance/latest | python3 -m json.tool

# 4. 수동 리밸런싱 체크
curl -X POST http://127.0.0.1:8000/api/v1/jobs/check-rebalance | python3 -m json.tool
```

### 7.3 데이터베이스 검증

```bash
# 1. SSH 접속
ssh admin@[NAS_IP]

# 2. MySQL 접속
mysql -u rebalancer -p rebalance_db

# 3. 테이블 확인
SHOW TABLES;

# 4. 데이터 행 수
SELECT 'etf_prices' as table_name, COUNT(*) as count FROM etf_prices
UNION ALL
SELECT 'momentum_scores', COUNT(*) FROM momentum_scores
UNION ALL
SELECT 'rebalance_signals', COUNT(*) FROM rebalance_signals;

# 5. 최신 데이터 확인
SELECT * FROM rebalance_signals ORDER BY signal_date DESC LIMIT 5;

# 6. 종료
EXIT;
```

### 7.4 부팅 후 자동 시작 테스트

```bash
# 1. NAS 재부팅 (관리자)
sudo reboot

# 2. 재부팅 후 서비스 확인 (약 2분 대기)
sudo systemctl status rebalancer

# 3. 로그 확인
sudo journalctl -u rebalancer -n 20
```

---

## ✅ 마이그레이션 완료 체크리스트

- [ ] 폴더 구조 생성 및 권한 설정
- [ ] Python 3.8+ 설치 확인
- [ ] 가상환경 생성 및 활성화
- [ ] requirements.txt 설치 완료
- [ ] ReBalancer 코드 전송 완료
- [ ] config.py에서 환경변수 로드 확인
- [ ] .env 파일 생성 및 보안 설정
- [ ] Systemd Service 파일 생성 및 등록
- [ ] 서비스 자동 시작 활성화
- [ ] API 엔드포인트 모두 정상 작동
- [ ] 데이터베이스 연결 확인
- [ ] 스케줄러 작업 등록 확인
- [ ] 로그 로테이션 설정
- [ ] 백업 자동화 설정
- [ ] 헬스 체크 Cron 등록
- [ ] 부팅 후 자동 시작 확인

---

## 📊 예상 결과

**마이그레이션 후**:
```
/volume1/rebalancer/
├── src/              ✓ 모든 코드 설치됨
├── venv/             ✓ 의존성 설치됨 (~300MB)
├── data/
│   ├── logs/         ✓ 자동 로그 기록 중
│   └── backups/      ✓ 자동 백업 중
├── config/
│   ├── .env          ✓ 환경변수 설정됨
│   └── .env.example  ✓ 템플릿 제공
├── scripts/          ✓ 모든 운영 스크립트 준비
└── docs/             ✓ 문서 완성
```

**서비스**:
- ✓ Systemd 서비스 자동 시작
- ✓ 크래시 시 자동 재시작
- ✓ 5분마다 헬스 체크
- ✓ 매일 로그 로테이션
- ✓ 자동 DB 백업

---

## 📝 다음 단계

→ **Phase 2: 실제 포트폴리오 데이터 연동** 준비
