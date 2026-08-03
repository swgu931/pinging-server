# Change Note — 분석/플롯 (`plot_from_file.py`)

- **날짜**: 2026-08-03
- **범위**: 측정 결과 분석·시각화 스크립트를 새 CSV 포맷에 맞추고, 헤드리스 환경에서
  PNG로 저장하며, 그래프에 통계 주석과 범례를 추가.
- **관련 파일**: `plot_from_file.py`

## 변경 내용
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

## 사용법
```bash
# 파일명을 인자로
python3 plot_from_file.py ping100.csv

# 또는 프롬프트로 입력
python3 plot_from_file.py
  Please input the filename to plot (e.g. ping100.csv) : ping100.csv
```
→ `ping100_timeseries.png`, `ping100_dist.png` 생성.

## 검증
- `py_compile` 통과.
- 새 CSV(타임아웃 행 포함)와 레거시 포맷 모두에서 `load_rtts()`가 올바른 RTT만 로드,
  통계 계산 정상(타임아웃 제외) 확인. (플롯 렌더링은 matplotlib/seaborn 설치 환경에서 수행.)
