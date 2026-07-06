# ReBalancer NAS 배포 설계서
## Synology NAS DS425 하이브리드 환경

작성일: 2026-07-06  
전략: 방안 4 (하이브리드) - MariaDB + Native Python + Systemd Service

---

## 📂 1단계: NAS 환경 구성 설계

### 1.1 추천 폴더 구조

```
/volume1/
├── rebalancer/                           # 메인 프로젝트 폴더
│   ├── src/                             # 소스 코드
│   │   ├── main.py
│   │   ├── crawler.py
│   │   ├── momentum_engine.py
│   │   ├── rebalance_engine.py
│   │   ├── scheduler.py
│   │   ├── database.py
│   │   ├── config.py
│   │   └── requirements.txt
│   │
│   ├── data/                            # 데이터 디렉토리
│   │   ├── logs/                        # 로그 파일 (일별 로테이션)
│   │   │   ├── rebalancer.log
│   │   │   ├── rebalancer.log.2026-07-05
│   │   │   └── rebalancer.log.2026-07-04
│   │   │
│   │   └── backups/                    # DB 백업
│   │       ├── daily/
│   │       ├── weekly/
│   │       └── monthly/
│   │
│   ├── venv/                            # Python 가상환경 (용량 주의)
│   │   └── [3-party packages installed]
│   │
│   ├── config/                          # 설정 파일 (민감정보)
│   │   ├── .env                         # 환경변수 (권한: 600)
│   │   ├── .env.example                 # 템플릿 (권한: 644)
│   │   └── systemd/
│   │       └── rebalancer.service       # Systemd 서비스 파일
│   │
│   ├── scripts/                         # 운영 스크립트
│   │   ├── start.sh                     # 서비스 시작
│   │   ├── stop.sh                      # 서비스 중지
│   │   ├── restart.sh                   # 서비스 재시작
│   │   ├── backup.sh                    # DB 백업 스크립트
│   │   ├── health_check.sh              # 헬스 체크
│   │   └── setup.sh                     # 초기 설치 스크립트
│   │
│   └── docs/                            # 문서
│       ├── README.md
│       ├── NAS_DEPLOYMENT_GUIDE.md      # 이 파일
│       └── TROUBLESHOOTING.md
│
└── nas-shared/                          # Synology 공유 폴더
    └── rebalancer_backups/              # 외부 백업 위치 (선택사항)
```

### 1.2 용량 계획

| 항목 | 예상 크기 | 설명 |
|------|---------|------|
| src/ | ~50 MB | 소스 코드 + 파이썬 라이브러리 |
| venv/ | ~300 MB | Python 가상환경 (setuptools, pip 포함) |
| data/logs/ | ~50 MB/월 | 로그 파일 (월별 로테이션) |
| data/backups/ | ~100 MB | MariaDB 백업 (압축) |
| **총합** | **~500-600 MB** | NAS DS425에서 충분함 |

---

## 🔐 2. 권한 설정

### 2.1 사용자 및 그룹 생성

```bash
# Synology NAS 터미널에서 실행 (sudo 권한 필요)

# 1. 전용 사용자 생성
useradd -m -s /bin/bash rebalancer

# 2. 전용 그룹 생성
groupadd rebalancer

# 3. 사용자를 그룹에 추가
usermod -a -G rebalancer rebalancer
```

### 2.2 폴더 권한 설정

```bash
# ReBalancer 소유권 설정
cd /volume1
chown -R rebalancer:rebalancer rebalancer/

# 폴더별 권한 설정
chmod 755 rebalancer/                          # 읽기+실행
chmod 755 rebalancer/src/
chmod 755 rebalancer/data/
chmod 700 rebalancer/config/                   # 설정폴더: 소유자만
chmod 700 rebalancer/data/backups/
chmod 755 rebalancer/scripts/
chmod 755 rebalancer/docs/

# 파일별 권한 설정
chmod 644 rebalancer/src/*.py                  # 일반 파이썬 파일
chmod 600 rebalancer/config/.env               # .env: 소유자만 읽기
chmod 644 rebalancer/config/.env.example
chmod 755 rebalancer/scripts/*.sh               # 실행 스크립트
chmod 644 rebalancer/docs/*.md
```

### 2.3 MariaDB 접근 권한

```sql
-- MySQL 터미널에서 실행 (root 권한)

-- 1. 전용 사용자 생성
CREATE USER 'rebalancer'@'localhost' IDENTIFIED BY '[강력한_비밀번호]';

-- 2. 데이터베이스 생성
CREATE DATABASE rebalance_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 3. 권한 부여 (필요한 것만)
GRANT SELECT, INSERT, UPDATE, DELETE ON rebalance_db.* TO 'rebalancer'@'localhost';
GRANT CREATE, ALTER, DROP ON rebalance_db.* TO 'rebalancer'@'localhost';

-- 4. 권한 적용
FLUSH PRIVILEGES;
```

---

## 💾 3. 데이터 관리 전략

### 3.1 로그 로테이션 (일별)

**파일 경로**: `/etc/logrotate.d/rebalancer`

```
/volume1/rebalancer/data/logs/rebalancer.log {
    daily                      # 매일 로테이션
    rotate 90                  # 90일 보관
    compress                   # gzip으로 압축
    delaycompress             # 다음날 압축
    notifempty                # 빈 파일은 로테이션 안함
    create 0644 rebalancer rebalancer  # 새 파일 권한
    sharedscripts
    postrotate
        systemctl reload rebalancer > /dev/null 2>&1 || true
    endscript
}
```

**효과**: 매일 자정에 로그 로테이션, 90일분 보관

---

### 3.2 데이터베이스 백업 전략 (3중 백업)

#### Tier 1: 일일 백업 (NAS 내부)
```bash
# /volume1/rebalancer/data/backups/daily/
# 매일 02:00 실행
# 보관: 7일
# 파일명: rebalance_db_YYYY-MM-DD.sql.gz
```

#### Tier 2: 주간 백업 (NAS 내부)
```bash
# /volume1/rebalancer/data/backups/weekly/
# 매주 일요일 03:00 실행
# 보관: 12주 (3개월)
# 파일명: rebalance_db_W##.sql.gz (W는 주차)
```

#### Tier 3: 월간 백업 (외부 저장소)
```bash
# /volume1/nas-shared/rebalancer_backups/
# 매월 1일 04:00 실행
# 보관: 12개월
# 파일명: rebalance_db_YYYY-MM.sql.gz
```

**백업 Cron 스케줄**:
```cron
# 일일 백업 (02:00)
0 2 * * * /volume1/rebalancer/scripts/backup.sh daily

# 주간 백업 (일요일 03:00)
0 3 * * 0 /volume1/rebalancer/scripts/backup.sh weekly

# 월간 백업 (1일 04:00)
0 4 1 * * /volume1/rebalancer/scripts/backup.sh monthly
```

---

## 🔍 4. 모니터링 및 헬스 체크

### 4.1 자동 헬스 체크

**실행 주기**: 매 5분  
**파일**: `/volume1/rebalancer/scripts/health_check.sh`

체크 항목:
- ✓ 프로세스 실행 여부 (systemd)
- ✓ MariaDB 연결 상태
- ✓ API 응답 상태 (/health)
- ✓ 디스크 용량
- ✓ 메모리 사용률

실패 시 동작:
- 1차: 자동 재시작 시도
- 2차 (재시작 실패): Syslog에 ERROR 기록
- 3차 (30분 지속 실패): 선택사항 - 이메일 알림

---

### 4.2 로깅 전략

**Log Level**: INFO (프로덕션)  
**Format**: `[TIMESTAMP] [LEVEL] [MODULE] [MESSAGE]`

```python
# 예시
2026-07-06 14:54:24 - rebalance_engine - INFO - Saved 6 rebalance signals
2026-07-06 14:54:37 - scheduler - ERROR - Job collect_prices failed: Connection timeout
```

**로그 분류**:
- `rebalancer.log` - 메인 로그 (모든 레벨)
- `rebalancer.error` - ERROR만 (트러블슈팅용)
- `rebalancer.audit` - 신호 생성/저장 (감시용)

---

## 📡 5. 네트워크 및 보안

### 5.1 접근 제어

| 항목 | 설정 | 이유 |
|------|------|------|
| FastAPI 바인드 | localhost:8000 | 외부 접근 차단 (NAS 내부만) |
| MariaDB 바인드 | localhost:3306 | 로컬만 허용 |
| SSH 접근 | 키 기반 인증만 | 비밀번호 인증 차단 |
| 방화벽 | 기본 차단 | 필요한 포트만 허용 |

### 5.2 환경변수 관리

**파일**: `/volume1/rebalancer/config/.env` (권한: 600)

```
# Database
DATABASE_URL=mysql+pymysql://rebalancer:[PASSWORD]@localhost:3306/rebalance_db

# API
API_PORT=8000
API_HOST=127.0.0.1

# Logging
LOG_LEVEL=INFO
LOG_DIR=/volume1/rebalancer/data/logs

# Backup
BACKUP_DIR=/volume1/rebalancer/data/backups

# Alerts (선택사항)
ALERT_EMAIL=your-email@example.com
```

---

## 🚀 6. 초기 설정 체크리스트

- [ ] Synology NAS SSH 접근 활성화
- [ ] rebalancer 사용자 및 그룹 생성
- [ ] 폴더 구조 생성 및 권한 설정
- [ ] MariaDB 설치 및 사용자/DB 생성
- [ ] Python 가상환경 설치
- [ ] ReBalancer 코드 마이그레이션
- [ ] 환경변수 설정 (.env 파일)
- [ ] 로그 로테이션 설정
- [ ] 백업 스크립트 설정
- [ ] Systemd Service 등록
- [ ] 헬스 체크 설정
- [ ] 테스트 실행 및 검증

---

## 📊 7. 예상 결과

**설치 후**:
```
/volume1/rebalancer/
├── src/              ✓ 모든 코드 설치됨
├── venv/             ✓ 의존성 설치됨
├── data/
│   ├── logs/         ✓ 자동 로테이션 중
│   └── backups/      ✓ 자동 백업 중
├── config/           ✓ 환경변수 설정됨
├── scripts/          ✓ 운영 스크립트 준비됨
└── docs/             ✓ 문서 완성
```

**자동화**:
- ✓ Systemd: 부팅 시 자동 시작
- ✓ Cron: 백업/로그로테이션 자동 실행
- ✓ Monit: 프로세스 헬스 체크 (5분마다)
- ✓ Scheduler: 모멘텀 & 리밸런싱 작업 자동 실행

---

## 📝 다음 단계

→ **2단계: Synology MariaDB 설치 가이드**로 진행
