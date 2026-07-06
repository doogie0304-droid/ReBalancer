# Synology MariaDB 설치 및 설정 가이드
## ReBalancer용 MariaDB 완전 설정

---

## 📋 목차
1. MariaDB 설치
2. 초기 설정
3. 사용자 및 데이터베이스 생성
4. 백업 설정
5. 성능 최적화
6. 테스트 및 검증

---

## 1️⃣ MariaDB 설치

### 1.1 Synology 패키지 센터에서 설치

**경로**: DSM → 패키지 센터 → 데이터베이스 → MariaDB 설치

```
설치 옵션:
- 버전: 최신 LTS (10.6 이상)
- 설치 위치: /volume1 (권장)
- 포트: 3306 (기본값)
```

**설치 후 확인**:
```bash
# SSH로 NAS 접속
ssh admin@[NAS_IP]

# MariaDB 버전 확인
mysql --version
# 출력 예: mysql  Ver 15.1 Distrib 10.6.x-MariaDB, for Linux (x86_64)

# 서비스 상태 확인
sudo systemctl status mysql
# 출력: ● mysql.service - MariaDB database server
#       Loaded: loaded (/etc/systemd/system/mysql.service; enabled; vendor preset: enabled)
#       Active: active (running)
```

---

### 1.2 자동 시작 설정

**DSM Web 인터페이스**:
1. 제어판 → 작업 스케줄러
2. 새로운 작업 생성
3. 이벤트 기반: 부팅 시
4. 실행: `/usr/local/mariadb/bin/mysqld_safe &`

또는 **터미널에서**:
```bash
sudo systemctl enable mysql
sudo systemctl start mysql
```

---

## 2️⃣ 초기 설정

### 2.1 root 비밀번호 설정

```bash
# SSH 접속 후 실행
mysql -u root

# MySQL 명령어
ALTER USER 'root'@'localhost' IDENTIFIED BY '[NEW_PASSWORD]';
FLUSH PRIVILEGES;
EXIT;
```

### 2.2 보안 강화 스크립트 (mysql_secure_installation)

```bash
# 대화형 보안 설정
sudo mysql_secure_installation

# 질문과 답변
Enter current password for root: [root 비밀번호 입력]

Switch to unix_socket authentication? n
Change the root password? n
Remove anonymous users? y
Disable root login remotely? y
Remove test database? y
Reload privilege tables? y
```

---

## 3️⃣ ReBalancer용 사용자 및 데이터베이스 생성

### 3.1 전용 사용자 생성

```bash
# SSH 접속 후
mysql -u root -p

# MySQL 프롬프트에서:
```

```sql
-- 1. 데이터베이스 생성
CREATE DATABASE rebalance_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- 2. 전용 사용자 생성
CREATE USER 'rebalancer'@'localhost' 
IDENTIFIED BY 'SecurePassword123!@#';

-- 3. 권한 부여 (필요한 것만)
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP 
ON rebalance_db.* 
TO 'rebalancer'@'localhost';

-- 4. 권한 적용
FLUSH PRIVILEGES;

-- 5. 생성 확인
SHOW GRANTS FOR 'rebalancer'@'localhost';

-- 6. 종료
EXIT;
```

### 3.2 연결 테스트

```bash
# rebalancer 사용자로 접속 테스트
mysql -u rebalancer -p rebalance_db

# 프롬프트에서 비밀번호 입력

# 접속 성공 확인
SELECT VERSION();
SHOW TABLES;  # 처음엔 비어있음 (정상)
EXIT;
```

---

## 4️⃣ 데이터베이스 최적화

### 4.1 MariaDB 설정 파일 수정

**파일 경로**: `/etc/mysql/my.cnf` 또는 `/volume1/.mysql/my.cnf`

```bash
sudo nano /etc/mysql/my.cnf

# 아래 내용 추가 (또는 기존값 수정)
```

```ini
[mysqld]
# === 메모리 설정 (DS425는 2GB) ===
max_connections = 100
max_allowed_packet = 256M
thread_stack = 192K
thread_cache_size = 8

# === 성능 최적화 ===
innodb_buffer_pool_size = 512M        # 전체 메모리의 50%
innodb_log_file_size = 100M
innodb_flush_log_at_trx_commit = 2    # 성능 vs 안정성 균형

# === 문자 인코딩 ===
character_set_server = utf8mb4
collation_server = utf8mb4_unicode_ci
character_set_client = utf8mb4

# === 로깅 ===
log_error = /volume1/rebalancer/data/logs/mysql_error.log
slow_query_log = 1
slow_query_log_file = /volume1/rebalancer/data/logs/mysql_slow.log
long_query_time = 2

# === 백업 설정 ===
binlog_format = mixed
log_bin = /volume1/rebalancer/data/logs/mysql_bin
expire_logs_days = 7
```

**설정 적용**:
```bash
sudo systemctl restart mysql

# 설정 확인
mysql -u rebalancer -p rebalance_db
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
EXIT;
```

---

## 5️⃣ 백업 자동화

### 5.1 백업 스크립트 작성

**파일**: `/volume1/rebalancer/scripts/backup.sh`

```bash
#!/bin/bash

BACKUP_DIR="/volume1/rebalancer/data/backups"
LOG_FILE="/volume1/rebalancer/data/logs/backup.log"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")

# === 일일 백업 (보관 7일) ===
if [ "$1" = "daily" ]; then
    mkdir -p $BACKUP_DIR/daily
    
    mysqldump -u rebalancer -p'SecurePassword123!@#' \
        --single-transaction \
        --quick \
        --lock-tables=false \
        rebalance_db | gzip > $BACKUP_DIR/daily/rebalance_db_$(date +%Y-%m-%d).sql.gz
    
    # 7일 이상 된 파일 삭제
    find $BACKUP_DIR/daily -name "*.sql.gz" -mtime +7 -delete
    
    echo "[$TIMESTAMP] Daily backup completed" >> $LOG_FILE

# === 주간 백업 (보관 12주) ===
elif [ "$1" = "weekly" ]; then
    mkdir -p $BACKUP_DIR/weekly
    
    WEEK=$(date +%W)
    YEAR=$(date +%Y)
    
    mysqldump -u rebalancer -p'SecurePassword123!@#' \
        --single-transaction \
        --quick \
        --lock-tables=false \
        rebalance_db | gzip > $BACKUP_DIR/weekly/rebalance_db_${YEAR}_W${WEEK}.sql.gz
    
    # 12주 이상 된 파일 삭제
    find $BACKUP_DIR/weekly -name "*.sql.gz" -mtime +84 -delete
    
    echo "[$TIMESTAMP] Weekly backup completed" >> $LOG_FILE

# === 월간 백업 (보관 12개월) ===
elif [ "$1" = "monthly" ]; then
    mkdir -p $BACKUP_DIR/monthly
    
    mysqldump -u rebalancer -p'SecurePassword123!@#' \
        --single-transaction \
        --quick \
        --lock-tables=false \
        rebalance_db | gzip > $BACKUP_DIR/monthly/rebalance_db_$(date +%Y-%m).sql.gz
    
    # 12개월 이상 된 파일 삭제
    find $BACKUP_DIR/monthly -name "*.sql.gz" -mtime +365 -delete
    
    echo "[$TIMESTAMP] Monthly backup completed" >> $LOG_FILE

else
    echo "Usage: $0 {daily|weekly|monthly}"
    exit 1
fi
```

**실행 권한 설정**:
```bash
chmod +x /volume1/rebalancer/scripts/backup.sh

# 수동 테스트
/volume1/rebalancer/scripts/backup.sh daily
ls -lh /volume1/rebalancer/data/backups/daily/
```

### 5.2 Cron 작업 등록

**SSH에서**:
```bash
# rebalancer 사용자의 crontab 편집
crontab -u rebalancer -e

# 아래 내용 추가:
# 일일 백업 (02:00)
0 2 * * * /volume1/rebalancer/scripts/backup.sh daily

# 주간 백업 (일요일 03:00)
0 3 * * 0 /volume1/rebalancer/scripts/backup.sh weekly

# 월간 백업 (1일 04:00)
0 4 1 * * /volume1/rebalancer/scripts/backup.sh monthly
```

**확인**:
```bash
crontab -u rebalancer -l
# 등록된 작업 목록이 출력됨
```

---

## 6️⃣ 성능 모니터링

### 6.1 데이터베이스 상태 확인

```bash
mysql -u rebalancer -p rebalance_db

# 데이터베이스 크기 조회
SELECT table_schema, 
       ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
FROM information_schema.tables
WHERE table_schema = 'rebalance_db'
GROUP BY table_schema;

# 테이블별 상세 정보
SELECT table_name,
       table_rows,
       ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.tables
WHERE table_schema = 'rebalance_db'
ORDER BY (data_length + index_length) DESC;

# 연결 상태
SHOW PROCESSLIST;

# 느린 쿼리 확인
SHOW VARIABLES LIKE 'slow_query%';

EXIT;
```

### 6.2 로그 확인

```bash
# MySQL 에러 로그
tail -100 /volume1/rebalancer/data/logs/mysql_error.log

# 느린 쿼리 로그
tail -50 /volume1/rebalancer/data/logs/mysql_slow.log

# 백업 로그
tail -20 /volume1/rebalancer/data/logs/backup.log
```

---

## 7️⃣ 재해복구 절차

### 7.1 백업에서 복구

```bash
# 최신 백업 파일 확인
ls -lht /volume1/rebalancer/data/backups/daily/ | head -1

# 복구 실행 (예: 2026-07-05 백업에서 복구)
mysql -u rebalancer -p rebalance_db < \
    <(gunzip -c /volume1/rebalancer/data/backups/daily/rebalance_db_2026-07-05.sql.gz)

# 복구 확인
mysql -u rebalancer -p rebalance_db
SELECT COUNT(*) FROM etf_prices;  # 레코드 수 확인
EXIT;
```

---

## ✅ 설치 완료 체크리스트

- [ ] MariaDB 설치 완료
- [ ] root 비밀번호 설정
- [ ] 보안 설정 완료 (mysql_secure_installation)
- [ ] rebalancer 사용자 및 rebalance_db 생성
- [ ] 권한 설정 완료
- [ ] 연결 테스트 성공
- [ ] my.cnf 최적화 설정 완료
- [ ] 백업 스크립트 작성 및 테스트
- [ ] Cron 작업 등록 완료
- [ ] 로그 디렉토리 생성 완료

---

## 📊 예상 성능

```
데이터 크기: ~5-10 MB (1년 운영 기준)
쿼리 속도: < 100ms (평균)
백업 시간: < 5초
메모리 사용: ~150-200 MB (정상)
```

---

## 🆘 문제 해결

### MariaDB가 시작되지 않음
```bash
# 로그 확인
sudo journalctl -u mysql -n 50

# 강제 재시작
sudo systemctl restart mysql
sudo systemctl status mysql
```

### 비밀번호를 잊음
```bash
# MySQL 백업 모드로 시작
sudo systemctl stop mysql
sudo mysqld_safe --skip-grant-tables &

# 비밀번호 리셋
mysql -u root
FLUSH PRIVILEGES;
ALTER USER 'rebalancer'@'localhost' IDENTIFIED BY 'NewPassword123!@#';
EXIT;

# 정상 재시작
sudo systemctl restart mysql
```

### 디스크 용량 부족
```bash
# 오래된 백업 삭제
find /volume1/rebalancer/data/backups -name "*.sql.gz" -mtime +180 -delete

# 로그 파일 정리
find /volume1/rebalancer/data/logs -name "*.log.*" -mtime +90 -delete
```

---

## 📝 다음 단계

→ **3단계: Python 가상환경 + ReBalancer 마이그레이션**으로 진행
