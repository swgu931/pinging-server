# Change Note — 상시 지연 모니터링 & ARM/AMD Docker 구성

- **날짜**: 2026-08-03
- **범위**: 클라우드 로보틱스(로봇↔엣지↔클라우드) 링크의 지연을 **실제 구동과 동시에**
  상시 측정하기 위한 Prometheus 프로브 서버(`monitor.py`)와 ARM/AMD 멀티아키 Docker 구성.
- **관련 파일**: `monitor.py`, `Dockerfile`, `docker-compose.yml`, `prometheus.yml`,
  `.dockerignore`, `requirements.txt`, `docker_readme.md`

## 배경 / 동기

기존 `ping3.py`는 ICMP 왕복(RTT)의 **정밀 분포를 오프라인으로 측정**(논문 실험)하는 데
적합하다. 하지만 클라우드 로보틱스 운영에서는 다음이 추가로 필요하다.

- ICMP는 클라우드 방화벽/보안그룹/LB에서 차단·throttle 되기 쉬움 → **실제 서비스 포트(TCP)**
  도달성 측정 필요.
- 제어/QoS에는 평균보다 **꼬리 지연(p95/p99)과 jitter, 손실률**이 중요.
- 파일(CSV)이 아니라 **상시 수집 + 대시보드**(Prometheus/Grafana)로 관측 필요.
- 로봇 스택과 **동시에** 컨테이너로 띄울 수 있어야 하고, ARM(엣지/로봇)·AMD(클라우드)를
  모두 지원해야 함.

## 추가된 것

### `monitor.py` — 상시 프로브 서버
- **프로브 2종**
  - `icmp:HOST` — ICMP echo RTT (`ping3.do_one` 재사용, datagram→raw 폴백).
  - `tcp:HOST:PORT` — TCP connect(핸드셰이크) RTT. ICMP가 막힌 환경에서 실제 서비스
    도달성을 반영.
- **지표(롤링 윈도 계산)**: p50/p95/p99, min/max/mean/stddev, IPDV jitter
  (연속 RTT 차의 평균절대값), 손실률.
- **Prometheus `/metrics` 노출**
  - 히스토그램 `probe_rtt_seconds`(→ `histogram_quantile` 집계용)
  - 게이지 `probe_rtt_p50/p95/p99_seconds`, `probe_rtt_{min,max,mean,stddev}_seconds`,
    `probe_jitter_seconds`, `probe_loss_ratio`, `probe_success`
  - 카운터 `probe_total`, `probe_failures_total`
- **동시 프로브**: 타깃별 스레드, 프로브 예외가 나도 스레드 유지.
- **설정(env/CLI)**: `PROBE_TARGETS`, `PROBE_INTERVAL`, `PROBE_TIMEOUT`, `PROBE_WINDOW`,
  `METRICS_PORT`.
- **의존성**: `prometheus_client` 추가.

### Docker (ARM/AMD 멀티 아키텍처)
- `Dockerfile`: `python:3.12-slim`(amd64+arm64), `monitor.py` 포함, `EXPOSE 9145`,
  `PYTHONUNBUFFERED=1`(도커 로그 즉시 출력), `MPLBACKEND=Agg`(헤드리스 플롯).
- `docker-compose.yml`: `probe`(monitor) 서비스 + `monitoring` 프로필의 Prometheus/Grafana.
- `prometheus.yml`: `probe:9145` 스크레이프.
- `.dockerignore`, `requirements.txt`.
- 컨테이너는 기본 root+`NET_RAW`라 raw ICMP가 바로 동작 → 호스트 `ping_group_range` sysctl
  불필요.

## 사용법 (요약)

```bash
# 프로브만 (경량, :9145/metrics)
docker compose up -d --build

# 프로브 + Prometheus(:9090) + Grafana(:3000, admin/admin)
docker compose --profile monitoring up -d --build

curl -s localhost:9145/metrics | grep '^probe_'
```

`docker-compose.yml`의 `PROBE_TARGETS`를 실제 로봇↔엣지↔클라우드 대상으로 바꾸고, 기존
로봇 스택 옆에 `probe` 서비스를 붙여 운영 중 상시 수집한다. 자세한 빌드/실행/PromQL/
트러블슈팅은 `docker_readme.md` 참고.

## 검증

- `monitor.py` 컴파일 + 스모크 테스트: 도달 타깃 success=1/loss=0/분위수 계산,
  닫힌 포트 success=0/loss=1.0, `/metrics` 정상 응답.
- `docker compose config` 유효, `docker build --check` 무경고.
- (전체 이미지 빌드는 레지스트리/apt 네트워크가 열린 환경에서 수행.)

## 한계 / 후속 (권장)

- 이 변경은 **네트워크·전송 계층 상시 관제**까지다. **LLM 추론시간 분해**와 **구간별
  end-to-end** 지연은 애플리케이션 계측(OpenTelemetry: 실제 메시지에 타임스탬프+trace)이
  필요하다.
- 실시간 제어 편도 지연은 TWAMP/OWAMP + PTP 시계 동기를 별도로 고려.
- Grafana 대시보드(p99/jitter/loss 패널) 프로비저닝은 추후 추가 가능.
