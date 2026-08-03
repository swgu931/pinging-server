# Docker 사용법 (ARM / AMD 멀티 아키텍처)

`ping3.py`(측정)와 `plot_from_file.py`(분석/그래프)를 Docker로 실행하기 위한 안내.
베이스 이미지 `python:3.12-slim`이 `linux/amd64`와 `linux/arm64`를 모두 지원하므로,
**AMD64(x86_64)와 ARM64(Apple Silicon, ARM 서버) 양쪽에서** 동일하게 동작한다.

> ICMP 참고: 컨테이너는 기본적으로 root + `NET_RAW` 권한으로 실행되므로 **raw ICMP 소켓이
> 그대로 동작한다**(호스트에서 하던 `ping_group_range` sysctl 설정이 필요 없다). 코드는
> 비특권 datagram 소켓을 먼저 시도하고 안 되면 raw 소켓으로 자동 폴백한다.

---

## 1. 이미지 빌드

### (A) 현재 아키텍처용 (가장 간단)

빌드하는 머신의 아키텍처(ARM이면 ARM, AMD이면 AMD)로 만들어진다.

```bash
docker build -t pinging-server .
```

### (B) 멀티 아키텍처 빌드 (buildx)

한 번에 amd64 + arm64 이미지를 만든다. 레지스트리로 push 하는 방식이 표준이다.

```bash
# buildx 빌더 준비 (최초 1회)
docker buildx create --name multi --use
docker buildx inspect --bootstrap

# 두 아키텍처를 함께 빌드해서 레지스트리에 push
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t <registry>/pinging-server:latest \
  --push .
```

로컬에 한 아키텍처만 로드하려면(`--load`는 단일 플랫폼만 가능):

```bash
docker buildx build --platform linux/arm64 -t pinging-server --load .
```

### 특정 아키텍처 강제 (교차 실행 확인용)

```bash
docker build --platform linux/amd64 -t pinging-server:amd64 .
docker build --platform linux/arm64 -t pinging-server:arm64 .
```

> QEMU 에뮬레이션으로 다른 아키텍처를 빌드/실행하려면 최초 1회:
> `docker run --privileged --rm tonistiigi/binfmt --install all`

---

## 2. 측정 실행 (`ping3.py`)

프롬프트가 있으므로 **대화형(`-it`)**으로 실행한다. 결과 파일을 호스트에 남기려면
`/data`에 볼륨을 마운트한다.

```bash
mkdir -p data
docker run -it --rm \
  --network host \
  -v "$(pwd)/data:/data" \
  pinging-server
```

입력 예:

```
Please input the IP address (or hostname) to ping : 10.232.183.148
Please input timeout to wait for ping response (unit: ms) : 1000
Please input the number of count to ping : 100
Please input interval between pings (unit: ms, 0 = back-to-back, 1000 = like system ping) : 1000
```

→ `data/ping100.csv` 생성 (컬럼: `seq,timestamp,rtt_ms`).

### 비대화형 / 스크립트 실행

입력을 파이프로 주입한다(`-i`만, `-t`는 제외).

```bash
printf '10.232.183.148\n1000\n100\n1000\n' | \
docker run -i --rm --network host -v "$(pwd)/data:/data" pinging-server
```

### 옵션 설명

| 옵션 | 의미 |
|---|---|
| `--network host` | 브리지 NAT를 거치지 않아 RTT 측정이 더 정확 (Linux 전용). macOS/Windows에서는 생략(브리지로 동작). |
| `-v "$(pwd)/data:/data"` | 컨테이너의 작업 디렉터리 `/data`를 호스트 `./data`에 연결 → CSV·PNG 보존. |
| `--cap-add=NET_RAW` | 런타임이 기본 권한을 제거한 경우에만 필요(대부분 불필요). |
| `-e TZ=Asia/Seoul` | CSV의 송신 타임스탬프를 로컬 시간으로. 미설정 시 UTC. |

---

## 3. 분석 / 그래프 (`plot_from_file.py`)

측정으로 만든 CSV를 같은 `/data` 볼륨에서 읽어 그래프를 PNG로 저장한다(헤드리스, `MPLBACKEND=Agg`).

```bash
docker run --rm \
  -v "$(pwd)/data:/data" \
  pinging-server /app/plot_from_file.py ping100.csv
```

→ `data/ping100_timeseries.png`, `data/ping100_dist.png` 생성.
통계 주석 박스, 평균선, 분포 그래프 범례(빨강=실측 histogram+KDE, 파랑=적합 정규분포)가 포함된다.

파일명을 인자로 주지 않으면 프롬프트로 물어보므로 이때는 `-it`를 붙인다:

```bash
docker run -it --rm -v "$(pwd)/data:/data" pinging-server /app/plot_from_file.py
```

---

## 4. 여러 호스트 동시 측정 (`main.py`)

```bash
docker run -it --rm --network host pinging-server /app/main.py
```

---

## 5. 자주 겪는 문제

- **`Operation not permitted` (소켓 생성 실패)**: 런타임이 `NET_RAW`를 제거한 경우.
  `--cap-add=NET_RAW`를 추가한다. 그래도 안 되면 `--privileged`(권장하지 않음)로 확인.
- **CSV/PNG가 호스트에 안 보임**: `-v "$(pwd)/data:/data"` 마운트를 빠뜨렸거나, 파일명에
  경로를 붙여 `/data` 밖에 쓴 경우. 파일명은 경로 없이(`ping100.csv`) 준다.
- **타임스탬프가 UTC로 나옴**: `-e TZ=Asia/Seoul` 지정.
- **`exec format error`**: 실행 호스트와 다른 아키텍처 이미지를 받은 경우. 멀티아키
  이미지를 push 했는지, 또는 위 QEMU binfmt를 설치했는지 확인.
