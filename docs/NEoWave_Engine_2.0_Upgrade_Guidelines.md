
# 📘 NEoWave Engine 2.0 Upgrade Guidelines

**주제:** 계층적 파동 분석(Hierarchical Wave Analysis) 및 동적 시나리오 프로젝션(Dynamic Projection) 구현

-----

## 1\. 개요 (Executive Summary)

### 1.1. 목표

기존의 단순 패턴 매칭(Sliding Window 방식) 엔진을 **NEoWave 이론의 핵심인 '프랙탈 구조(Fractal Structure)'를 완벽히 반영한 계층적 분석 엔진**으로 재설계한다.
사용자는 파편화된 파동 조각이 아니라, \*\*"현재 시장이 거대한 사이클(Cycle) 내에서 어디에 위치해 있는가?"\*\*에 대한 구조적인 답변과, \*\*"다음 파동은 어떻게 진행될 것인가?"\*\*에 대한 시나리오를 제공받아야 한다.

### 1.2. 핵심 변경 사항

1.  **분석 방식:** 부분적 패턴 탐색 → **전체론적(Holistic) 바텀업 파싱 (Monowave → Polywave → Multi-wave)**
2.  **자료 구조:** 단순 리스트(`List[Swing]`) → **트리 구조(`WaveTree` / `WaveNode`)**
3.  **결과물:** 단순 패턴 이름 나열 → **계층적 시나리오 객체 (상위/하위 파동 포함) 및 미래 경로 예측**

-----

## 2\. 상세 요구사항 (Core Requirements)

### 2.1. 계층적 구조화 (Hierarchical Structuring)

  * **요구사항:** 모든 파동은 하위 파동(Sub-waves)을 포함해야 하며, 상위 파동(Super-wave)의 일부여야 한다.
  * **근거 문서:** `docs/01_neowave_overview_and_scope.md` (Fractal Wave Hierarchy)
  * **구현 명세:**
      * `Wave` 객체는 `sub_waves: List[Wave]` 속성을 가진다.
      * 가장 기초 단위인 **Monowave**는 `sub_waves`가 없는 Leaf Node이다.
      * **Polywave**(예: Impulse)는 5개의 하위 Wave Node를 가진다.
      * 분석은 가장 작은 단위에서 시작하여, 규칙에 맞는 파동들을 묶어(Group/Collapse) 상위 파동을 만드는 **재귀적(Recursive) 과정**이어야 한다.

### 2.2. 앵커링 및 추세 연계 (Anchoring & Trend Projection)

  * **요구사항:** 분석은 임의의 시점이 아닌, \*\*시장의 주요 변곡점(Major Pivot)\*\*에서 시작되어야 하며, 끊김 없이 현재 캔들(Last Candle)까지 이어져야 한다.
  * **구현 명세:**
      * 데이터 로드 시 전체 기간 내 **Global Min/Max** 또는 **Significant Pivot**을 식별하여 `Wave 0`의 시작점으로 고정한다.
      * 분석된 파동이 현재 시점에서 '진행 중(In Progress)'인지 '완료(Completed)'되었는지를 판별하는 로직을 포함한다.
      * `scenarios.py`는 분석된 현재 파동의 다음 예상 경로(Next Move)를 `neowave_rules.json`의 \*\*'Post-pattern logic'\*\*을 기반으로 생성해야 한다.

### 2.3. 복합성 및 등급 관리 (Complexity & Degree Management)

  * **요구사항:** 무분별한 파동 병합을 방지하고, NEoWave의 '등급(Degree)' 개념을 엄격히 적용한다.
  * **근거 문서:** `docs/05_neowave_validation_and_limitations.md` (Rule of Similarity & Balance)
  * **구현 명세:**
      * 인접한 파동을 상위 파동으로 묶을 때, **가격/시간 비율이 33% 이상**이어야 한다는 `Rule of Similarity`를 강제한다.
      * 복합 조정(Complex Correction)은 최대 **Triple Three**까지만 허용하며, 그 이상은 상위 등급 파동으로 재해석하거나 'Undefined'로 처리한다 (Complexity Cap).

-----

## 3\. 아키텍처 재설계 (Architecture Redesign)

### 3.1. 데이터 모델 변경 (`src/neowave_core/models.py` 신설 권장)

기존 `Swing` 클래스를 확장하여 계층 구조를 지원하는 `WaveNode`를 설계하십시오.

```python
@dataclass
class WaveNode:
    """NEoWave의 계층적 파동을 표현하는 기본 단위"""
    label: str              # 파동 라벨 (e.g., "1", "A", "3")
    pattern_type: str       # 패턴 종류 (e.g., "Impulse", "Zigzag", "Monowave")
    degree: str             # 파동 등급 (Optional: "Minor", "Intermediate" etc.)
    
    start_idx: int          # 데이터 프레임 인덱스
    end_idx: int
    
    sub_waves: List['WaveNode'] = field(default_factory=list) # 하위 파동 리스트
    
    # 검증 점수 및 세부 정보
    score: float = 0.0
    is_complete: bool = True # 현재 진행 중인 파동인지 여부
    rules_passed: List[str] = ...
    invalidation_point: float = ... 
```

### 3.2. 핵심 알고리즘 로직 (`src/neowave_core/engine.py` 또는 `parser.py`)

**Bottom-Up Parsing Algorithm (반복적 압축 방식)**

1.  **Level 0 (Monowave Extraction):**
      * `detect_swings()`를 통해 Raw Data를 가장 작은 단위의 `Monowave` 리스트로 변환.
2.  **Level 1 (Atomic Pattern Search):**
      * Monowave 리스트를 순회하며 `is_impulse`, `is_zigzag` 등의 패턴 함수를 적용.
      * 패턴이 확인되면 해당 구간의 Monowave들을 하나의 `WaveNode`(예: Zigzag)로 그룹화(Collapse).
3.  **Level N (Recursive Merging):**
      * 그룹화된 WaveNode들을 새로운 입력 리스트로 하여 다시 패턴 검사를 수행.
      * 이때 `Rule of Similarity`를 체크하여 등급이 맞는 파동끼리만 결합.
      * 더 이상 병합할 수 없을 때까지 반복.
4.  **Scenario Generation:**
      * 남은 최상위 WaveNode들이 구성하는 가능한 시나리오들을 점수화하여 리스트업.

-----

## 4\. 구현 로드맵 (Implementation Roadmap)

코딩 에이전트는 다음 순서로 작업을 진행해야 합니다.

### Phase 1: 모델링 및 기초 공사

1.  `src/neowave_core/swings.py`: `Swing` 클래스를 `WaveNode`로 업그레이드하거나 래퍼 클래스 작성.
2.  `src/neowave_core/rules_loader.py`: 상위 파동 결합을 위한 규칙(Complexity Cap, Similarity Rule)을 명시적으로 로드하도록 수정.

### Phase 2: 파싱 엔진 구현

1.  `src/neowave_core/parser.py` (신규): 위에서 설계한 **Bottom-Up Parsing** 로직 구현.
      * 재귀적(Recursive) 또는 스택(Stack) 기반의 파동 병합 로직 작성.
      * `docs/05...md`의 "Degree Separation" 로직 필수 적용.

### Phase 3: 시나리오 및 프로젝션 고도화

1.  `src/neowave_core/scenarios.py`: 파싱된 트리 구조를 순회하며 텍스트 요약 및 `Invalidation Level` 계산 로직 전면 수정.
      * 단순 파동 나열이 아닌, \*\*"현재 [Impulse]의 [3파] 중 [v파] 진행 중"\*\*과 같은 계층적 서술 생성.
2.  `Projection Logic`: 현재 파동이 완료되지 않았다면(`is_complete=False`), `neowave_rules.json`의 타겟 규칙(Fibonacci Ratio 등)을 사용하여 예상 도달 가격(Target Price) 계산.

### Phase 4: API 및 웹 시각화 대응

1.  `src/neowave_web/api.py`: 계층적 JSON 응답을 반환하도록 수정.
2.  `src/neowave_web/static/app.js`: 차트 위에 사용자가 시나리오를 클릭하면, 해당 시나리오의 \*\*파동 트리(1-2-3-4-5)\*\*가 시각적으로 오버레이 되도록 렌더링 로직 개선.

-----

## 5\. 품질 보증 (QA Guidelines)

  * **검증 데이터:** 과거 BTCUSD의 명확한 임펄스 구간(예: 2020년 말\~2021년 초)을 대상으로 테스트했을 때, 프로그램이 이를 하나의 거대한 'Impulse' 객체로 묶어내야 함.
  * **실패 처리:** 파동 카운팅이 불가능한 구간(Rule Violation)에서는 억지로 패턴을 끼워 맞추지 말고 'Unknown/Complex Correction'으로 분류하고 하위 파동만 보여줄 것. ("Underspecified or Unknown Patterns")

-----

**이 가이드라인을 바탕으로 작업을 시작하십시오.**