# Change Note — Python 3 포팅 & 논문용 RTT 측정 정밀화

- **날짜**: 2026-08-03
- **범위**: 기존 Python 2 기반 ping 코드를 Python 3.12에서 동작하게 포팅하고, sudo 없이
  실행 가능하게 만들고, RTT 측정을 논문 실험 수준으로 정밀화. 출력은 CSV로 변경.
- **관련 파일**: `ping3.py`, `pingpkg/ping_func.py`, `main.py`

## Python 3 호환 (Python 3.12 기준)
- `ping3.py`, `pingpkg/ping_func.py`
  - `checksum()`: `bytes` 인덱싱이 이미 `int`를 주므로 `ord()` 제거, 정수 나눗셈(`//`) 사용.
  - `create_packet()`: payload를 `str` → `bytes`로 변경 (`bytes + str` `TypeError` 수정).
  - `asyncore` 의존 제거 (Python 3.12에서 모듈 삭제됨).
    - `pingpkg/ping_func.py`: `asyncore.dispatcher` 기반 `PingQuery` 제거 →
      `multi_ping_query()`를 `select` 기반 동시 구현으로 재작성.
    - `ping3.py`: `asyncore`를 지연 import 하고 없으면 안전하게 대체.
- `main.py`
  - import 경로 수정: `ping_func` → `pingpkg.ping_func`.
  - `.iteritems()` → `.items()` (Python 2 → 3).

## 권한 없이 실행 (no sudo)
- `new_icmp_socket()` 추가: 우선 **비특권 datagram 소켓**(`SOCK_DGRAM` + `IPPROTO_ICMP`)을
  시도하고, 안 되면 **raw 소켓**(`SOCK_RAW`, root 필요)으로 폴백.
- 커널이 datagram/raw 응답을 다르게 전달하므로 `receive_ping()`이 두 경우를 각각 처리
  (raw는 IP 헤더 20바이트 포함 + id 매칭, datagram은 오프셋 0 + 커널 demux).
- 사전 조건: `sudo sysctl -w net.ipv4.ping_group_range="0 2147483647"` (사용자 gid 포함).

## RTT 측정 정밀화 (핵심)
기존에는 시스템 `ping` 대비 값이 계통적으로 너무 작게 나오는 문제가 있었음. 원인은 느슨한
응답 매칭 + ping마다 소켓 open/close로 인한 포트·ICMP id 재사용. 아래로 수정:
- **소켓 1개 재사용**: `verbose_ping()`이 소켓을 한 번만 열고 `count`번 재사용.
- **payload에 송신 타임스탬프 삽입**: `time.perf_counter()`(단조 고해상도) 값을 payload
  앞 8바이트에 넣고, 응답이 되돌려준 그 값으로 `RTT = 수신시각 − 송신시각` 계산.
  → 어떤 응답에 매칭되든 RTT 값이 오염되지 않음(잘못 매칭돼도 값이 작아질 수 없음).
- **엄격한 응답 검증**: echo reply(type=0) + sequence 번호 일치(raw는 id까지) 일 때만 인정,
  지연·중복·타 트래픽 응답은 폐기.
- `time.time()` → `time.perf_counter()` (NTP 보정 점프 영향 제거).

## 입력 프롬프트 및 동작 개선 (`ping3.py`)
- **IP 주소 입력 프롬프트 추가** (하드코딩된 목적지 제거).
- **interval 입력 프롬프트 추가** (ms 단위, `0`=연속, `1000`=시스템 `ping`과 동일 간격).
  간격은 RTT 분포에 영향을 주는 교란변수이므로 실험 시 고정·명시 권장.
- **timeout 단위 버그 수정**: 프롬프트는 ms인데 내부적으로 초로 쓰던 문제 → `/1000.0` 변환.
- 모든 ping이 타임아웃일 때 통계 계산이 죽던 문제 방어 (빈 배열 가드).

## 출력 포맷: CSV
- 결과 파일이 `ping<count>` → **`ping<count>.csv`** 로 변경.
- 컬럼: `seq,timestamp,rtt_ms`
  - `seq`: sequence 번호
  - `timestamp`: 각 ping 송신 시각(wall-clock, ISO 8601, 마이크로초)
  - `rtt_ms`: 왕복시간(ms), **타임아웃이면 공란** (pandas에서 `NaN`으로 로드 → 손실 구간 보존)

## 검증
- 전체 소스 `py_compile` 통과.
- 패킷 레이아웃/타임스탬프 왕복/엄격 매칭을 소켓 없이 시뮬레이션한 단위 테스트 통과
  (datagram seq 매칭, raw id+seq 매칭, 타임아웃 → None).
- 실측 비교: 동일 interval(1000ms)에서 시스템 `ping`과 평균이 일치함을 확인.
