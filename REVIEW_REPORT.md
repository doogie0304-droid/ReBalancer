# ReBalancer 프로젝트 코드 검토 보고서

## 🔴 Critical Issues (즉시 수정 필요)

### 1. crawler.py - fetch_page() 암시적 None 반환
**파일:** `crawler.py` 라인 21-37
**문제:** 재시도 모두 실패 시 명시적 `return None` 없음
**영향:** `parse_price_data()`에서 `None` 전달 시 BeautifulSoup 크래시
**상태:** ✅ 수정됨

### 2. crawler.py - parse_price_data() null 가드 부족
**파일:** `crawler.py` 라인 39-41
**문제:** `html`이 `None`일 경우 처리 없음
**영향:** `BeautifulSoup(None, 'html.parser')` → TypeError
**상태:** ✅ 수정됨

### 3. crawler.py - BeautifulSoup selector 부정확
**파일:** `crawler.py` 라인 45
**문제:** `class_='tbl_data tbl_type1 tbl_quant'` 공백 분리는 불안정
**개선:** CSS 선택자 `select_one()` 사용
**상태:** ✅ 수정됨

### 4. config.py - 잘못된 티커 코드
**파일:** `config.py` 라인 48
**문제:** `"072r0"` → 정확히는 `"0072R0"` (선행 0 누락, 소문자 r)
**확인:** 김동건 확인함
**상태:** ✅ 수정됨

### 5. crawler.py - collect_all_prices() DB 미저장
**파일:** `crawler.py` 라인 68-89
**문제:** 파싱된 데이터를 DB에 저장하지 않음
**영향:** 데이터가 메모리에만 존재, 휘발성
**상태:** ✅ 수정됨

---

## 🟡 High Priority Issues

### 6. scheduler.py - _job_collect_prices() 미구현
**파일:** `scheduler.py` 라인 44-45
**문제:** 실제 작업 로직 없음 (로그만 출력)
**해결:** 크롤러 호출 및 에러 처리 로직 추가 필요
**상태:** 구조 개선 필요

### 7. main.py - API 엔드포인트 부재
**파일:** `main.py`
**문제:** README에서 명시된 10개 이상의 엔드포인트 미구현
- `/api/v1/momentum/latest`
- `/api/v1/rebalance/latest`
- `/api/v1/notifications/pending`
- `/api/v1/scheduler/status`
- POST `/api/v1/jobs/*`
**상태:** Phase 2 (미구현 스텁)

### 8. momentum_engine.py, rebalance_engine.py - stub 구현
**파일:** `momentum_engine.py`, `rebalance_engine.py`
**문제:** 실제 계산 로직 없음 (반환만 함)
**상태:** Phase 2 (미구현 스텁)

### 9. database.py - 마이그레이션 전략 부재
**파일:** `database.py` 라인 78-79
**문제:** `Base.metadata.create_all()` 사용 → 스키마 진화 관리 어려움
**권장:** Alembic 마이그레이션 도입
**상태:** Phase 2 개선 사항

---

## 🟠 Medium Priority Issues

### 10. 예외 처리 - bare except 사용
**파일:** `crawler.py` 라인 60
**문제:** `except:` 사용 → 예상치 못한 에러 숨김
**개선:** 특정 예외 타입으로 변경
**상태:** ✅ 수정됨

### 11. 환경 설정 - time.sleep() 반복 import
**파일:** `crawler.py` 라인 36
**문제:** 루프 내에서 매번 `import time`
**개선:** 모듈 상단에서 import
**상태:** ✅ 수정됨

### 12. 로깅 설정 - 중복 정의
**파일:** `main.py` 라인 11-14, `config.py` 라인 87
**문제:** 로깅 포매터가 두 곳에서 정의됨
**개선:** 통합 로거 설정 모듈 생성
**상태:** ✅ 개선됨

### 13. 타입 힌팅 부재
**파일:** 여러 파일
**문제:** 함수 반환 타입 명시 부족 (Optional, Union 등)
**개선:** `from typing import Optional, List` 추가
**상태:** 개선 가능

---

## 📋 수정 완료 항목

| 항목 | 파일 | 라인 | 상태 |
|------|------|------|------|
| fetch_page() 명시적 None 반환 | crawler.py | 21-37 | ✅ 수정 |
| parse_price_data() null 가드 | crawler.py | 39-41 | ✅ 수정 |
| BeautifulSoup 선택자 개선 | crawler.py | 45 | ✅ 수정 |
| 티커 코드 수정 | config.py | 48 | ✅ 수정 |
| DB 저장 로직 추가 | crawler.py | 68-89 | ✅ 수정 |
| bare except 제거 | crawler.py | 60 | ✅ 수정 |
| import 위치 최적화 | crawler.py | 1-10 | ✅ 수정 |
| 타입 힌팅 추가 | crawler.py | 전체 | ✅ 수정 |

---

## 🔄 다음 단계

### Phase 1 (현재 - MVP)
- ✅ 크롤러 안정화 (완료)
- ⏳ 스케줄러 실제 job 구현 필요
- ⏳ 기본 API 엔드포인트 (최소 3개)

### Phase 2
- 모멘텀/리밸런싱 계산 로직
- FCM 푸시 알림
- Alembic 마이그레이션

### Phase 3
- 모바일 앱 (Flutter/PWA)
- 사용자 포트폴리오 입력 API
