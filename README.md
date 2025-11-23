# NEoWave: 트레이더급 NEoWave 분석 엔진 & 웹 대시보드

한국어 사용자를 위한 종합 가이드입니다. 본 프로젝트는 NEoWave 규칙 기반으로 스윙을 감지하고, 패턴 시나리오를 생성해 웹 UI로 시각화합니다. Wave Box/Tree, 다중 스케일 스윙, Rule X-Ray를 포함하여 실제 트레이딩 의사결정에 바로 참고할 수 있는 수준을 목표로 합니다.

## 핵심 특징
- Wave Box: 시나리오가 인식한 시간/가격 범위를 박스 형태로 표현.
- Wave Tree: 상위 패턴과 하위 레그(1~5, A~E 등)를 계층 구조로 직렬화.
- Rule X-Ray: 규칙 단위의 pass/fail, 기대값, 패널티를 노출하여 점수의 근거 제공.
- 다중 스윙 스케일: macro/base/micro 스케일을 병렬로 계산해 민감도 완화.
- FastAPI + LightweightCharts 웹 UI: 실시간 시나리오 카드, invalidation 라인, Wave Box 오버레이, 규칙 근거 모달 제공.

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
  - `GET /api/swings?scale_id=base|macro|micro&price_threshold=<opt>&similarity_threshold=<opt>`
  - `GET /api/scenarios?scale_id=...&max_scenarios=8&price_threshold=<opt>&similarity_threshold=<opt>`
- Scenario 응답 주요 필드: `wave_box`, `wave_tree`, `wave_labels`, `rule_evidence`, `scale_id`, `invalidation_levels`, `details.active_path`, `details.scale_context`.

### CLI로 시나리오 출력
```bash
python -m neowave_core.cli --symbol BTCUSD --interval 1hour --lookback 500
```
주요 옵션: `--price-threshold`, `--similarity-threshold`, `--max-scenarios`, `--rules-path`, `--api-key`.

## UI 사용법 요약
- Timeframe 버튼: 차트 캔들 주기 변경.
- Scale (Base/Macro/Micro): 스윙 감지 스케일 변경.
- 카드 클릭: 해당 시나리오 Wave Box, 라벨, invalidation 표시.
- Rule X-Ray ▶: 규칙별 값/기대치/패널티/통과 여부 모달.

## 환경 변수 (선택)
- `SYMBOL`, `INTERVAL`, `LOOKBACK` : 기본 심볼/주기/캔들 수.
- `PRICE_THRESHOLD_PCT`, `SIMILARITY_THRESHOLD`: 기본 스윙 감지 파라미터.
- `FMP_API_KEY`: 실데이터 조회용 FMP 키.

## 테스트
```bash
.venv/bin/python -m pytest
```

## 주요 설계 포인트
- 스윙 감지: `detect_swings` + `detect_swings_multi_scale`로 macro/base/micro 세트 생성.
- 패턴 검사: 각 패턴 모듈이 `RuleCheck` 리스트를 생성하여 Rule X-Ray 제공.
- 시나리오: `generate_scenarios`가 Wave Box/Tree, 라벨, rule evidence를 포함한 응답 생성.
- 웹: `/`에서 차트 + Wave Box 오버레이 + Scenario 카드 + Rule X-Ray 모달 제공.

## 참고 문서
- `docs/newguideline.md`: 트레이더 관점 문제 정의 및 개선 스펙.
- `docs/01_neowave_overview_and_scope.md` 등: 추가 규칙/아키텍처 설명.
