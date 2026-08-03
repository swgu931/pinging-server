# Change Notes

변경 상세는 `docs/changes/<날짜>-<주제>.md` 독립 파일에 있고, 여기서는 날짜별로 링크한다.

## 2026-08-03

- [Python 3 포팅 & 논문용 RTT 측정 정밀화](docs/changes/2026-08-03-python3-rtt-measurement.md)
  — Python 3.12 호환, sudo 없이 실행(datagram→raw), payload 타임스탬프 기반 정밀 RTT,
  IP/interval 프롬프트, CSV 출력.
- [분석/플롯 (`plot_from_file.py`)](docs/changes/2026-08-03-analysis-plots.md)
  — CSV 읽기, 파일명 입력, PNG 저장, 통계 주석 박스·범례.
- [상시 지연 모니터링 & Docker 구성](docs/changes/2026-08-03-cloud-robotics-monitoring.md)
  — 클라우드 로보틱스용 Prometheus 프로브(`monitor.py`, ICMP+TCP, p95/p99·jitter·loss),
  ARM/AMD 멀티아키 Docker/Compose.
