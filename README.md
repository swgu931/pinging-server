# pinging-server

Python 3 기반 ICMP ping 측정 도구. 목적지의 RTT(왕복시간)를 반복 측정해 통계와 그래프를
만든다. 논문 실험용으로 RTT 측정 정확도에 초점을 둔다.

변경 이력은 [CHANGELOG.md](CHANGELOG.md) 참고.

## 사전 준비 (권한 없이 실행하기)

raw 소켓 대신 **비특권 ICMP datagram 소켓**을 우선 사용하므로 sudo 없이 실행할 수 있다.
단, 한 번만 아래 sysctl로 현재 사용자 gid가 ping 허용 범위에 들어가게 해야 한다.

```bash
# 임시 (재부팅 시 초기화)
sudo sysctl -w net.ipv4.ping_group_range="0 2147483647"

# 영구 적용
echo 'net.ipv4.ping_group_range = 0 2147483647' | sudo tee /etc/sysctl.d/99-ping.conf
sudo sysctl --system
```

설정을 못 하는 환경이면 sudo로도 실행 가능하다. 이때 numpy가 사용자 영역(`~/.local`)에만
있으면 root가 못 보므로 경로를 넘겨준다:

```bash
sudo env PYTHONPATH="$HOME/.local/lib/python3.12/site-packages" python3 ping3.py
```

의존성: `numpy`(측정/통계), 그래프는 추가로 `matplotlib seaborn scipy`.

```bash
pip install --user numpy matplotlib seaborn scipy
```

## 1. 측정: `ping3.py`

```bash
python3 ping3.py
```

아래 4개를 입력받는다:

- `Please input the IP address (or hostname) to ping :` 예) `10.232.183.148`
- `Please input timeout to wait for ping response (unit: ms) :` 예) `1000`
- `Please input the number of count to ping :` 예) `100`
- `Please input interval between pings (unit: ms, ...) :`
  - `0` = 연속(back-to-back)
  - `1000` = 시스템 `ping`과 동일한 1초 간격 (비교 실험 시 권장)

실행이 끝나면 통계(mean/var/std/min/max, 단위 ms)를 출력하고,
**`ping<count>.csv`** 파일을 생성한다.

### 출력 CSV 포맷 (`ping<count>.csv`)

```csv
seq,timestamp,rtt_ms
0,2026-08-03T11:05:10.225887,6.9
1,2026-08-03T11:05:10.225911,1.4
2,2026-08-03T11:05:10.225916,          <- 타임아웃: rtt_ms 공란
3,2026-08-03T11:05:10.225927,6.8
```

- `seq`: sequence 번호(0부터). 순서/누락 추적용.
- `timestamp`: 각 ping 송신 시각(wall-clock, ISO 8601).
- `rtt_ms`: 왕복시간(ms). **타임아웃이면 공란** → pandas에서 `NaN`으로 로드된다.

> RTT는 단조 시계(`time.perf_counter`)로 측정하고, 송신 타임스탬프를 패킷 payload에 심어
> 응답에서 되돌려받은 값으로 계산한다. 소켓 하나를 재사용하고 sequence/id로 응답을 엄격히
> 매칭하므로, 지연·중복 응답이 있어도 측정값이 오염되지 않는다.

## 2. 분석/그래프: `plot_from_file.py`

```bash
# 파일명을 인자로
python3 plot_from_file.py ping100.csv

# 또는 프롬프트로 입력
python3 plot_from_file.py
  Please input the filename to plot (e.g. ping100.csv) : ping100.csv
```

동작:

- CSV의 `rtt_ms`를 읽고 타임아웃(공란)은 제외한 뒤 통계를 출력한다.
- 그래프 2개를 **PNG로 저장**한다(150 dpi, 헤드리스 환경에서도 사용 가능):
  - `<name>_timeseries.png` — 시간축 대비 RTT + 평균선 + 통계 박스
  - `<name>_dist.png` — RTT 히스토그램/KDE + 적합 정규분포 + 통계 박스 + 범례
- 그래프 내부에 `n/mean/std/var/min/max` 주석 박스가 표시된다.

`<name>_dist.png`의 색 의미:

- **빨강** — 실측 RTT의 분포 (histogram + KDE, 경험적 밀도)
- **파랑** — 표본 평균·표준편차로 적합한 정규분포(이상적 모델). 빨강과 겹치는 정도로
  RTT가 정규분포를 따르는지 눈으로 확인한다.
- **회색 점선** — 평균

GUI 창으로 바로 보고 싶으면 GUI 백엔드가 필요하다:

```bash
sudo apt install python3-tk
```

## 참고: 여러 호스트 동시 측정 (`main.py`)

```bash
python3 main.py
```

`pingpkg/ping_func.py`의 `multi_ping_query()`(select 기반)를 사용해 여러 호스트를 한 번에
핑한다. 단일 목적지 실험에는 `ping3.py`를 사용한다.
