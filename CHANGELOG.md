# Change Notes

## 2026-08-03

Python 3 포팅 및 논문 실험용 RTT 측정 정밀화 작업.

### Python 3 호환 (Python 3.12 기준)
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

### 권한 없이 실행 (no sudo)
- `new_icmp_socket()` 추가: 우선 **비특권 datagram 소켓**(`SOCK_DGRAM` + `IPPROTO_ICMP`)을
  시도하고, 안 되면 **raw 소켓**(`SOCK_RAW`, root 필요)으로 폴백.
- 커널이 datagram/raw 응답을 다르게 전달하므로 `receive_ping()`이 두 경우를 각각 처리
  (raw는 IP 헤더 20바이트 포함 + id 매칭, datagram은 오프셋 0 + 커널 demux).
- 사전 조건: `sudo sysctl -w net.ipv4.ping_group_range="0 2147483647"` (사용자 gid 포함).

### RTT 측정 정밀화 (핵심)
기존에는 시스템 `ping` 대비 값이 계통적으로 너무 작게 나오는 문제가 있었음. 원인은 느슨한
응답 매칭 + ping마다 소켓 open/close로 인한 포트·ICMP id 재사용. 아래로 수정:
- **소켓 1개 재사용**: `verbose_ping()`이 소켓을 한 번만 열고 `count`번 재사용.
- **payload에 송신 타임스탬프 삽입**: `time.perf_counter()`(단조 고해상도) 값을 payload
  앞 8바이트에 넣고, 응답이 되돌려준 그 값으로 `RTT = 수신시각 − 송신시각` 계산.
  → 어떤 응답에 매칭되든 RTT 값이 오염되지 않음(잘못 매칭돼도 값이 작아질 수 없음).
- **엄격한 응답 검증**: echo reply(type=0) + sequence 번호 일치(raw는 id까지) 일 때만 인정,
  지연·중복·타 트래픽 응답은 폐기.
- `time.time()` → `time.perf_counter()` (NTP 보정 점프 영향 제거).

### 입력 프롬프트 및 동작 개선 (`ping3.py`)
- **IP 주소 입력 프롬프트 추가** (하드코딩된 목적지 제거).
- **interval 입력 프롬프트 추가** (ms 단위, `0`=연속, `1000`=시스템 `ping`과 동일 간격).
  간격은 RTT 분포에 영향을 주는 교란변수이므로 실험 시 고정·명시 권장.
- **timeout 단위 버그 수정**: 프롬프트는 ms인데 내부적으로 초로 쓰던 문제 → `/1000.0` 변환.
- 모든 ping이 타임아웃일 때 통계 계산이 죽던 문제 방어 (빈 배열 가드).

### 출력 포맷: CSV
- 결과 파일이 `ping<count>` → **`ping<count>.csv`** 로 변경.
- 컬럼: `seq,timestamp,rtt_ms`
  - `seq`: sequence 번호
  - `timestamp`: 각 ping 송신 시각(wall-clock, ISO 8601, 마이크로초)
  - `rtt_ms`: 왕복시간(ms), **타임아웃이면 공란** (pandas에서 `NaN`으로 로드 → 손실 구간 보존)

### 분석/플롯 (`plot_from_file.py`)
- 새 CSV(`rtt_ms`) 읽기, 타임아웃 행 자동 제외. 예전 "한 줄에 숫자 하나" 포맷도 자동 폴백.
- **파일명 입력**: 인자(`python3 plot_from_file.py ping100.csv`) 또는 프롬프트로 지정.
- 무거운 import(matplotlib/scipy/seaborn)를 함수 내부로 지연 → numpy만 있어도 로딩/통계 가능.
- seaborn `distplot`(0.14에서 제거) → `histplot(stat='density', kde=True)`.
- 플롯을 **PNG로 저장**(`<name>_timeseries.png`, `<name>_dist.png`, 150 dpi). 헤드리스에서도 사용 가능.
- 그래프 내부에 **통계 주석 박스**(n/mean/std/var/min/max)와 **평균 기준선** 추가.
- 분포 그래프에 **범례** 추가:
  - 빨강 = 실측 RTT (histogram + KDE, 경험적 밀도)
  - 파랑 = 표본 μ·σ로 적합한 정규분포(이상적 모델)
  - 회색 점선 = 평균
