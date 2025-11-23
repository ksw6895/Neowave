# NEoWave: 프랙탈 NEoWave 파동 엔진 & 웹 대시보드

한국어 사용자를 위한 종합 가이드입니다. 본 프로젝트는 단일 Monowave 시퀀스를 바탕으로 프랙탈 계층을 구축하고, 패턴 시나리오를 생성하여 웹 UI로 시각화합니다. Macro/Base/Micro 같은 병렬 스케일을 없애고, 하나의 트리에서 원하는 뷰 레벨을 선택하는 방식으로 정리되었습니다.

## 핵심 특징
- 단일 Monowave → 패턴 압축 → WaveNode 트리로 이어지는 **프랙탈 파서**.
- View Level: 목표 파동 수(예: 30~60개)에 맞춰 적절한 레벨을 자동 선택.
- Rule X-Ray: 패턴별 검증 결과(하드/소프트 룰)와 메트릭을 노출.
- FastAPI + LightweightCharts 웹 UI: 시나리오 카드, 뷰 노드 배지, Rule X-Ray 툴팁 제공.

## 폴더 구조 요약
- `src/neowave_core`: 엔진 로직 (스윙 감지, 패턴 검사, 시나리오 생성, Rule X-Ray).
- `src/neowave_web`: FastAPI 서비스 및 정적 웹 UI.
- `rules/`: NEoWave 규칙 JSON.
- `docs/`: 사양 및 가이드 문서.
- `tests/`: pytest 기반 단위 테스트.

## 사전 준비
- Python 3.10+ (3.12 권장)
- 선택: Financial Modeling Prep(FMP) API 키 (`FMP_API_KEY`)가 있으면 실데이터 조회 가능.

## 빠른 시작
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 웹 서비스 실행
```bash
uvicorn neowave_web.api:app --reload --port 8000
```
- 기본 페이지: http://localhost:8000
- 제공 엔드포인트
- `GET /api/ohlcv?symbol=BTCUSD&interval=1hour&limit=500`
- `GET /api/monowaves?retrace_price=0.236&retrace_time=0.2&similarity_threshold=0.33`
- `GET /api/scenarios?target_wave_count=40` : 프랙탈 트리에서 최적 뷰 레벨을 포함한 시나리오 목록
- `GET /api/waves/{wave_id}/children` : 드릴다운용 자식 파동
- `GET /api/waves/{wave_id}/rules` : Rule X-Ray (검증 결과/메트릭)
- `POST /api/analyze/custom-range` : `symbol`, `interval`, `start_ts`, `end_ts`로 임의 구간 분석

### CLI로 시나리오 출력
```bash
python -m neowave_core.cli --symbol BTCUSD --interval 1hour --lookback 500
```
주요 옵션: `--price-threshold`, `--similarity-threshold`, `--min-price-retrace-ratio`, `--min-time-ratio`, `--max-pivots`, `--max-scenarios`, `--rules-path`, `--api-key`.

## UI 사용법 요약
- Symbol/Interval 설정 후 `Analyze` 클릭 → 최신 Monowave와 시나리오 생성.
- Target Waves 슬라이더로 뷰 레벨을 조정(추천 30~60개).
- Scenario 카드의 배지를 클릭하면 해당 Wave의 Rule X-Ray 툴팁 확인.

## 환경 변수 (선택)
- `SYMBOL`, `INTERVAL`, `LOOKBACK` : 기본 심볼/주기/캔들 수.
- `PRICE_THRESHOLD_PCT`, `SIMILARITY_THRESHOLD`: 기본 스윙 감지 파라미터.
- `MIN_PRICE_RETRACE_RATIO`, `MIN_TIME_RATIO`: NEoWave식 스윙 확정 임계값(가격/시간 1/3 룰).
- `FMP_API_KEY`: 실데이터 조회용 FMP 키.

## 테스트
```bash
.venv/bin/python -m pytest
```

## 주요 설계 포인트
- Monowave 감지: NEoWave 1/3 규칙(가격·시간)을 적용해 노이즈 스윙을 병합 (`detect_monowaves_from_df`).
- 패턴 평가: PatternEvaluator + RULE_DB 로 패턴별 하드/소프트 룰을 점수화.
- 시나리오: `analyze_market_structure`가 Bottom-Up 압축→Top-Down 검증을 수행하고, `generate_scenarios`가 직렬화.
- 웹: `/`에서 차트 + Monowave 경로 + Scenario 카드 + Rule X-Ray 툴팁 제공.

## 참고 문서
- `docs/newguideline.md`: 트레이더 관점 문제 정의 및 개선 스펙.
- `docs/01_neowave_overview_and_scope.md` 등: 추가 규칙/아키텍처 설명.
