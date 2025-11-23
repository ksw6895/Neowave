

# NEoWave Web – Trader-Grade Usability & Hierarchical Wave Mapping Spec (v0.2)

## 0. 목적 및 범위

이 문서는 현재 코드베이스(`neowave_core`, `neowave_web`)와 동봉된 문서를 기반으로,

* **실제 트레이더가 느낄 치명적인 사용성 문제 3가지**를 명시하고,
* 이를 해결하기 위한 **엔진/스윙 감지/시나리오 스코어링/API/Web UI 전면 개선 방향**을 정의한다.

목표는 이 도구를 “재미있는 장난감”이 아니라 **실제 매매 의사결정에 참고할 수 있는 NEoWave 분석 도구** 수준으로 끌어올리는 것이다.

---

## 1. 트레이더 관점에서의 치명적 사용성 문제 3가지

### 1.1 “숲을 보지 못하고 나무만 보여줌” – 계층적 맥락 부재

현재 `generate_scenarios`는 **슬라이딩 윈도우 방식**으로, 최근 스윙 N개(3·5·7·11개)를 잘라 그 조각이 임펄스인지 지그재그인지만 판별한다.

* **실제 사용자가 느끼는 문제:**

  * “이 5파 상승 임펄스가,

    * 거대한 하락장의 **반등 C파**인지,
    * 아니면 대세 상승장의 **3파 시작**인지
    * 화면 상에서 구분이 안 된다.”
* **구조적 한계:**

  * NEoWave의 핵심은 프랙탈 구조와 Degree(파동 등급)이다.
  * 지금 구조는 “여기 5개 스윙이 임펄스처럼 보인다” 수준의 **로컬 패턴 탐지**에 머물러 있고,
  * “현재 전체 사이클에서 우리가 어디쯤 와 있는지”에 대한 **Top-down Wave Map**이 없다.
  * 결과적으로 사용자는 여러 시나리오 조각을 보고 **머릿속에서 다시 수동으로 큰 그림을 그려야** 하며, 자동화 도구의 장점이 반감된다.

### 1.2 “스윙 감지 세팅에 따라 결과가 널뛰기” – 입력 변수 의존성

`swings.py`에서 스윙 감지는 주로 `price_threshold_pct`(기본 1%)와 `similarity_threshold`(0.33)에 의존한다.

* **실제 사용자가 느끼는 문제:**

  * 1.0%로 스윙을 찍으면 임펄스가 나오는데,
  * 1.2%로 바꾸면 스윙 하나가 사라지며 지그재그로 인식되는 등,
  * **파라미터를 조금만 바꿔도 시나리오 결과가 완전히 바뀐다.**
* **구조적 한계:**

  * NEoWave 규칙(비율·채널링·복잡도 등)보다 앞 단계인 **Monowave(스윙) 정의**가 지나치게 단일 파라미터에 민감하다.
  * 변동성이 커지거나 작아질 때, 사용자가 매번 눈으로 보고 “오늘은 1.5%로 잡아야겠다” 식으로 수동 튜닝을 하면,

    * 분석의 **재현성/객관성**이 떨어지고,
    * 시스템에 대한 신뢰도가 떨어진다.
  * **시장 상황(변동성)에 따라 동적으로 스윙 스케일을 조절하거나**,
    **복수의 스윙 스케일을 동시에 분석해서 더 일관된 패턴을 찾는 로직**이 없다.

### 1.3 “점수만 있고 ‘왜?’가 없다” – 설명 가능성 부족

현재 UI는 시나리오에 대해 `Score: 0.85` 정도의 숫자만 보여준다. 내부에서는 penalty와 rule 점검을 하고 있지만, 사용자에게는 드러나지 않는다.

* **실제 사용자가 느끼는 문제:**

  * “왜 85점인가?
    3파가 연장되어서 점수가 높은 건지,
    2파 조정 깊이가 이상적이라 그런 건지,
    탈락한 시나리오는 어떤 규칙 하나 때문에 탈락했는지 알 수 없다.”
* **구조적 한계:**

  * 트레이딩은 돈이 걸린 영역이므로, **Black-box 알고리즘**은 신뢰받기 어렵다.
  * 현재는 `penalty` -> `score`로 이어지는 수치만 있고,

    * “3파 길이가 1파의 1.618배 조건에서 0.1% 부족 → 작은 패널티 부여”
    * “4파가 1파 가격을 침범 → 임펄스 조건 위반”
      같은 **규칙 단위의 설명(Which rule, pass/fail, by how much)이 전혀 노출되지 않는다.**
  * 사용자는 이 프로그램이 내놓는 시나리오를 **참고는 할 수 있지만, 전적으로 믿고 포지션을 잡기 어려운 상태**다.

---

## 2. 디자인 목표 – “장난감”에서 “실전 도구”로

위 3가지 문제를 해결하기 위해, 다음 세 축을 중심으로 리팩토링한다.

1. **Top-Down 계층 분석**

   * 슬라이딩 윈도우 조각에 머무르지 않고,
   * **상위 파동(부모)–현재 파동–하위 파동(자식)**을 구조적으로 표현하는 Wave Map을 제공한다.
2. **적응형/다중 스케일 스윙 감지**

   * 단일 `price_threshold_pct`에 대한 민감도를 줄이고,
   * 변동성 기반 동적 임계값 또는 다중 스윙 스케일을 동시에 운용한다.
3. **설명 가능한 점수 & 규칙 X-Ray**

   * 각 시나리오의 점수가 어떤 규칙들에 의해 결정되었는지,
   * 어떤 규칙은 통과했고, 어떤 규칙은 아슬아슬했는지,
   * **머신/인간 모두가 읽을 수 있는 형태의 규칙 근거를 제공**한다.

이제 각 축을 구현하기 위한 구체적인 변경 사항을 정의한다.

---

## 3. 현재 시스템 요약 (Baseline)

### 3.1 엔진(`neowave_core`)

* `swings.detect_swings`:

  * `price_threshold_pct`, `similarity_threshold` 등으로 monowave(스윙)를 추출.
* `patterns/*.py`:

  * `impulse`, `terminal_impulse`, `triangle`, `zigzag`, `flat`, `double_three`, `triple_three` 등
  * 각 패턴별로 규칙 점검 및 penalty/score 계산 로직 존재.
* `scenarios.generate_scenarios`:

  * 스윙 시퀀스에 대해 3/5/7/11개의 슬라이싱 윈도우를 돌며 각 패턴을 시험.
  * 통과하는 시나리오에 대해

    * `pattern_type`, `score`, `weighted_score`, `swing_indices`, `textual_summary`,
      `invalidation_levels`, `details`, `in_progress` 등을 dict로 생성.
  * `weighted_score` 기준으로 정렬 후 상위 `max_scenarios` 반환.

### 3.2 API(`neowave_web/api.py`, `schemas.py`)

* `GET /api/ohlcv` → 캔들 데이터.
* `GET /api/swings` → 스윙 목록.
* `GET /api/scenarios` → `ScenarioOut` 리스트.
* `ScenarioOut`:

  * `pattern_type`, `score`, `swing_indices`, `textual_summary`,
    `invalidation_levels`, `details`, `in_progress` 정도만 포함.

### 3.3 Web UI(`static/index.html`, `static/app.js`)

* LightweightCharts로 캔들 차트 렌더링.
* 스윙 끝점에 `S1, S2, ...` 마커 표시.
* 오른쪽 패널에 시나리오 카드 목록 표시.
* 카드 클릭 시:

  * 해당 `swing_indices` 구간 스윙들만 다시 라벨링.
  * Invalidation 레벨을 수평선으로 표시.
  * 단순 projection 라인만 추가.
* **Wave Box, 계층 트리, 규칙 X-Ray UI는 없음.**

---

## 4. 엔진 개선 – WaveBox & WaveTree & Rule X-Ray

### 4.1 WaveBox: “어디부터 어디까지를 하나의 파동으로 봤는가?”

#### 4.1.1 데이터 구조

```python
# src/neowave_core/wave_box.py

from dataclasses import dataclass
from datetime import datetime

@dataclass(slots=True)
class WaveBox:
    swing_start: int   # inclusive
    swing_end: int     # inclusive

    time_start: datetime
    time_end: datetime

    price_low: float
    price_high: float
```

#### 4.1.2 생성 헬퍼

```python
from typing import Sequence

def compute_wave_box(swings: Sequence["Swing"], start_idx: int, end_idx: int) -> WaveBox:
    window = swings[start_idx : end_idx + 1]
    time_start = window[0].start_time
    time_end = window[-1].end_time
    price_low = min(s.low for s in window)
    price_high = max(s.high for s in window)
    return WaveBox(
        swing_start=start_idx,
        swing_end=end_idx,
        time_start=time_start,
        time_end=time_end,
        price_low=price_low,
        price_high=price_high,
    )
```

> 이 구조는: “이 시나리오가 차트 상에서 **어느 시간/가격 박스를 하나의 파동으로 인식했는지**”를 일관되게 표현하는 최소 단위이다.

### 4.2 WaveTree: 계층적 파동 트리

#### 4.2.1 데이터 구조

```python
# src/neowave_core/wave_tree.py

from dataclasses import dataclass, field

@dataclass(slots=True)
class WaveNode:
    id: str              # "primary", "1", "2", "A", "W" 등
    label: str           # 화면에 표시할 라벨
    pattern_type: str    # "impulse", "zigzag", ...
    direction: str | None  # "up", "down", None
    degree: int          # 0: 스윙 레벨, 1: 그 위, ... (NEoWave Degree와 매핑 가능)

    swing_start: int
    swing_end: int

    children: list["WaveNode"] = field(default_factory=list)
```

#### 4.2.2 1차 구현 범위 (필수)

각 시나리오에 대해 최소한 다음을 보장한다.

* 루트 WaveNode (degree 1):

  * `label = pattern_type` (예: "IMPULSE", "ZIGZAG")
  * `swing_start/end = 시나리오 swing_indices`
  * direction: 전체 창에서 상승/하락 판단.
* 1단계 자식 WaveNode들 (degree 0):

  * Impulse/Terminal: 5개 노드 → label "1"~"5"
  * Zigzag/Flat: 3개 노드 → "A","B","C"
  * Triangle: 5개 노드 → "A"~"E"
  * Double three(7 swing): 7개 노드, 단순 3-1-3 구조로 "W","X","Y"를 매핑
  * Triple three(11 swing): 11개 노드, "W","X","Y","X","Z" 패턴에 따라 매핑

즉, 초기 단계에서는 **“스윙 N개 = 최상위 Sub-wave N개”**로 단순 매핑하되, 구조 자체는 계층형으로 구현한다(후속 단계에서 하위 Degree 파동을 재귀적으로 추가 가능하도록).

#### 4.2.3 2차 구현 범위 (선택: 진짜 Top-Down/Bottom-Up 계층 구축)

* `build_wave_tree(swings, swing_indices, pattern_type, details)` 내에서:

  * 시나리오 window 내부 스윙에 대해,
  * NEoWave 규칙을 사용하여:

    * 더 작은 Impulse, Zigzag, Triangle 등을 재귀적으로 탐색하고,
    * 작은 패턴부터 상위로 차례로 압축(compress)하여 Degree를 올려가는 구조를 구축.
* 제약:

  * 탐색 영역은 **해당 시나리오 window로 한정**.
  * Degree 최대 깊이를 설정(예: 0–3).
  * 패턴 후보가 많을 경우 score 기반으로 상위 몇 개 구조만 유지.

> 이 단계는 구현 난이도가 높으므로, 코드 에이전트에게 **1차 구현(Flat Tree) → 2차(진짜 계층 트리)**로 나누어 작업하도록 명시하는 것이 좋다.

### 4.3 Rule X-Ray: 규칙 단위 근거 구조화

#### 4.3.1 RuleCheck 구조

엔진 내부에서 규칙 평가 결과를 다음과 같이 구조화한다.

```python
from dataclasses import dataclass

@dataclass(slots=True)
class RuleCheck:
    key: str              # "wave2_retrace", "wave3_extension", ...
    description: str      # 인간용 설명 (옵션)
    value: float | bool | str
    expected: str         # "0.24–1.0", ">= 1.618", "must be True" 등
    passed: bool
    penalty: float        # 이 규칙으로 인한 패널티 (0이면 통과)
```

각 패턴 모듈(예: `triangle.py`, `impulse.py`)에서,

* 규칙 평가 시 `RuleCheck` 객체를 생성하고,
* 시나리오 `details["rule_checks"]` 리스트로 모은다.

#### 4.3.2 Scenario dict 확장

`generate_scenarios` 내부의 `add_scenario(...)` 로직을 다음과 같이 확장한다.

```python
from .wave_box import compute_wave_box
from .wave_tree import WaveNode, build_wave_tree

def infer_wave_labels(pattern_type: str, swing_indices: tuple[int, int]) -> list[str]:
    # window 길이와 pattern_type prefix를 토대로
    # ["1","2","3","4","5"] / ["A","B","C"] / ["A"~"E"] / ["W","X","Y", ...] 등 리턴
    ...

def build_rule_evidence(pattern_type: str, details: dict) -> list[dict]:
    # details["rule_checks"]에 RuleCheck 리스트가 있다고 가정하고,
    # 이를 JSON-직렬화 가능한 dict array로 변환
    # (엔진 내부 상세 표현은 자유)
    ...

def add_scenario(...):
    ...
    start_idx, end_idx = swing_indices
    box = compute_wave_box(swings, start_idx, end_idx)
    wave_labels = infer_wave_labels(pattern_type, swing_indices)
    wave_tree = build_wave_tree(swings, swing_indices, pattern_type, details)

    scenarios.append(
        {
            "pattern_type": pattern_type,
            "score": score,
            "weighted_score": weighted_score,
            "swing_indices": swing_indices,
            "textual_summary": summary,
            "invalidation_levels": invalidation,
            "details": details or {},
            "in_progress": in_progress,
            # 신규 필드
            "wave_box": serialize_wave_box(box),
            "wave_labels": wave_labels,
            "wave_tree": serialize_wave_tree(wave_tree),
            "rule_evidence": build_rule_evidence(pattern_type, details),
        }
    )
```

---

## 5. 스윙 감지 개선 – Multi-Scale & Adaptive Swings

이 섹션은 **문제 1.2(스윙 민감도)**를 직접 겨냥한다.

### 5.1 다중 스윙 스케일 구조

#### 5.1.1 Config 예시

```python
# src/neowave_core/config.py

SWING_SCALES = [
    {"id": "macro", "price_threshold_pct": 2.5, "similarity_threshold": 0.4},
    {"id": "base",  "price_threshold_pct": 1.0, "similarity_threshold": 0.33},  # 기존 기본값
    {"id": "micro", "price_threshold_pct": 0.5, "similarity_threshold": 0.3},
]
```

#### 5.1.2 SwingSet 구조

```python
from dataclasses import dataclass
from typing import Sequence

@dataclass(slots=True)
class SwingSet:
    scale_id: str               # "macro", "base", "micro"
    swings: Sequence["Swing"]
```

`detect_swings_multi_scale(ohlcv)`:

* 위 `SWING_SCALES`에 정의된 각 스케일에 대해 `detect_swings`를 실행.
* `dict[scale_id, SwingSet]` 혹은 `list[SwingSet]` 형태로 반환.

### 5.2 시나리오 분석 시 스케일 전략

#### 5.2.1 기본 전략

* **Base 스케일**을 메인 분석 스케일로 사용 (`scale_id="base"`).
* 시나리오 생성 시:

  * Base 스케일에서 슬라이딩 윈도우로 시나리오 후보 생성.
  * 동일 구간(시간, swing index)을 macro/micro에서도 확인하여 **컨텍스트 보정**:

예시:

* Base 스케일: 5-swing impulse 후보.
* Macro 스케일: 같은 기간에 “단일 큰 스윙” 또는 “단순 조정”으로 인식.
* Micro 스케일: 내부에 여러 작은 임펄스/조정이 포함되어 있음.

이 정보를 이용하여:

* Macro 스케일이 강한 하락 임펄스 내 조정 구간으로 보이면,

  * 현재 임펄스가 **상위 Degree에서 C파가 될 가능성**이 높다고 판단.
* Micro 스케일이 너무 복잡하고 noisy하면,

  * 해당 시나리오의 신뢰도를 약간 낮추는 penalty 추가.

#### 5.2.2 API 연계 (선택)

* `/api/swings`에 `scale_id` 파라미터 추가:

  * 기본: `scale_id=base`
  * 추가 옵션: `macro`, `micro`
* `/api/scenarios` 요청 시:

  * `scale_id`로 메인 분석 스케일 지정.
  * 응답의 각 시나리오에:

    * `scale_id` 필드 추가.
    * 옵션으로 `parent_scale_id`/`child_scale_summary` 포함 (상위/하위 스케일에서의 간단한 텍스트 요약).

---

## 6. API 스키마 확장

### 6.1 신규 Pydantic 모델

```python
# src/neowave_web/schemas.py

from pydantic import BaseModel
from datetime import datetime
from typing import Any

class WaveBoxOut(BaseModel):
    swing_start: int
    swing_end: int
    time_start: datetime
    time_end: datetime
    price_low: float
    price_high: float


class WaveNodeOut(BaseModel):
    id: str
    label: str
    pattern_type: str
    direction: str | None = None
    degree: int | None = None
    swing_start: int
    swing_end: int
    children: list["WaveNodeOut"] = []


class RuleEvidenceItem(BaseModel):
    key: str
    value: float | bool | str
    expected: str | None = None
    passed: bool | None = None
    penalty: float | None = None


class ScenarioOut(BaseModel):
    pattern_type: str
    score: float
    swing_indices: tuple[int, int]
    textual_summary: str
    invalidation_levels: dict[str, float] | None = None
    details: dict[str, Any] | None = None
    in_progress: bool | None = None

    # 신규 필드
    scale_id: str | None = None
    wave_box: WaveBoxOut | None = None
    wave_labels: list[str] | None = None
    wave_tree: WaveNodeOut | None = None
    rule_evidence: list[RuleEvidenceItem] | None = None
```

> 순환 참조를 위해 모듈 끝에서 `WaveNodeOut.model_rebuild()` 호출 필요.

### 6.2 엔드포인트 변경 요약

* `GET /api/swings`

  * Query: `scale_id`(optional, default="base").
* `GET /api/scenarios`

  * Query: `scale_id`(optional).
  * Response: `ScenarioOut[]` (위 신규 필드 포함).

---

## 7. Web UI 개선 – Wave Box, Context, Rule X-Ray

### 7.1 Wave Box 오버레이 레이어

`index.html`의 차트 영역에 wave box를 위한 겹치는 레이어 추가:

```html
<main class="panel chart-container">
  <div class="chart-overlay">
    <div class="chart-title" id="chart-symbol">BTC/USD</div>
  </div>
  <div id="tv-chart"></div>
  <div id="wave-overlay-layer" class="wave-overlay-layer"></div>
</main>
```

CSS 예시:

```css
.wave-overlay-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.wave-box {
  position: absolute;
  border: 1px solid rgba(0, 242, 255, 0.5);
  background: rgba(0, 242, 255, 0.08);
  box-shadow: 0 0 12px rgba(0, 242, 255, 0.2);
  border-radius: 6px;
}

.wave-box-label {
  position: absolute;
  top: 2px;
  left: 4px;
  font-size: 10px;
  font-family: "JetBrains Mono", monospace;
  color: #00f2ff;
}
```

### 7.2 app.js – Wave Box 그리기

```js
const waveOverlayEl = document.getElementById("wave-overlay-layer");
let activeWaveBoxes = [];

function clearWaveBoxes() {
  if (!waveOverlayEl) return;
  waveOverlayEl.innerHTML = "";
  activeWaveBoxes = [];
}

function drawWaveBoxForScenario(scenario) {
  if (!chart || !waveOverlayEl || !scenario.wave_box) return;

  const box = scenario.wave_box;
  const timeScale = chart.timeScale();
  const priceScale = chart.priceScale("right");

  const t1 = Math.floor(new Date(box.time_start).getTime() / 1000);
  const t2 = Math.floor(new Date(box.time_end).getTime() / 1000);
  const x1 = timeScale.timeToCoordinate(t1);
  const x2 = timeScale.timeToCoordinate(t2);
  const y1 = priceScale.priceToCoordinate(box.price_high);
  const y2 = priceScale.priceToCoordinate(box.price_low);

  if (x1 == null || x2 == null || y1 == null || y2 == null) return;

  const left = Math.min(x1, x2);
  const width = Math.abs(x2 - x1);
  const top = Math.min(y1, y2);
  const height = Math.abs(y2 - y1);

  const div = document.createElement("div");
  div.className = "wave-box";
  div.style.left = `${left}px`;
  div.style.top = `${top}px`;
  div.style.width = `${width}px`;
  div.style.height = `${height}px`;

  const label = document.createElement("div");
  label.className = "wave-box-label";
  label.textContent = scenario.pattern_type.replace(/_/g, " ").toUpperCase();

  div.appendChild(label);
  waveOverlayEl.appendChild(div);
  activeWaveBoxes.push(div);
}
```

### 7.3 Scenario 강조 로직 확장

기존 `highlightScenario`를 수정:

```js
function highlightScenario(scenario) {
  clearPriceLines();
  clearWaveBoxes();
  drawProjection(scenario);

  if (!scenario || !Array.isArray(state.swings)) {
    renderBaseSwingMarkers();
    return;
  }

  // Wave Box
  if (scenario.wave_box) {
    drawWaveBoxForScenario(scenario);
  }

  const [startIdx, endIdx] = scenario.swing_indices || [0, -1];
  const subset = state.swings.slice(startIdx, endIdx + 1);
  if (!subset.length) {
    renderBaseSwingMarkers();
    return;
  }

  const labelsFromScenario = Array.isArray(scenario.wave_labels)
    ? scenario.wave_labels
    : scenarioWaveLabels(subset.length);

  const markers = subset.map((swing, idx) => ({
    time: swing.end_ts,
    position: swing.direction === "up" ? "belowBar" : "aboveBar",
    color: swing.direction === "up" ? "#00f2ff" : "#ff0055",
    shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
    text: `${labelsFromScenario[idx] || ""} ${Number(swing.end_price).toFixed(2)}`,
  }));

  candleSeries.setMarkers(markers);
  drawInvalidations(scenario.invalidation_levels);
}
```

### 7.4 Rule X-Ray UI

Scenario 카드 아래에 “Rule X-Ray” 토글 추가:

```js
function renderScenariosList(scenarios) {
  const container = document.getElementById("scenarios");
  container.innerHTML = "";

  scenarios.forEach((sc, idx) => {
    const card = document.createElement("div");
    card.className = "scenario-card";

    const hasEvidence = Array.isArray(sc.rule_evidence) && sc.rule_evidence.length > 0;

    card.innerHTML = `
      <div class="sc-header">
        <span class="sc-type">${sc.pattern_type.replace(/_/g, " ").toUpperCase()}</span>
        <span class="sc-score">${(sc.score * 100).toFixed(0)}%</span>
      </div>
      <div class="sc-summary">${sc.textual_summary}</div>
      <div class="sc-meta">
        Swings ${sc.swing_indices?.[0]} – ${sc.swing_indices?.[1]}
        ${sc.scale_id ? ` | scale: ${sc.scale_id}` : ""}
      </div>
      ${hasEvidence ? `<div class="sc-evidence-toggle" data-idx="${idx}">Rule X-Ray ▶</div>` : ""}
    `;

    card.addEventListener("click", () => {
      state.activeScenarioIndex = idx;
      highlightScenario(sc);
    });

    if (hasEvidence) {
      const toggle = card.querySelector(".sc-evidence-toggle");
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        openEvidenceModal(sc.rule_evidence);
      });
    }

    container.appendChild(card);
  });
}

function openEvidenceModal(evidence) {
  // 간단한 모달 또는 사이드 패널에
  // key / value / expected / passed / penalty를 테이블로 렌더링
}
```

이렇게 하면 사용자는:

* 점수 숫자만 보지 않고,
* 각 규칙이 어떻게 평가되었는지,
* 어떤 규칙이 약간 위반되었는지까지 확인 가능하다.

---

## 8. 테스트 및 검증 계획

1. **엔진 단위 테스트**

   * `compute_wave_box`가 스윙 window의 min/max 가격과 시간 범위를 정확히 반영하는지 검증.
   * 각 패턴에 대해:

     * synthetic 스윙 시퀀스를 만들어,
     * `wave_labels`, `wave_tree`, `rule_evidence` 구조가 예측과 일치하는지 확인.

2. **다중 스윙 스케일 테스트**

   * 동일 ohlcv 데이터에 대해 `macro`, `base`, `micro` 세 스케일 결과를 비교.
   * extreme case(고변동/저변동)에서 단일 스케일보다 더 일관된 시나리오가 나오는지 검토.

3. **API 테스트**

   * `/api/scenarios` 응답에 신규 필드들이 포함되는지, optional 필드로 backward compatible한지 확인.
   * `scale_id` 쿼리 파라미터가 정상 동작하는지 검증.

4. **UI 수동 테스트**

   * BTCUSD H1에서 2–3개의 대표적 구간(상승 임펄스, 복잡한 조정, 삼각수렴)을 골라:

     * Wave Box 위치,
     * Wave labels(1–5, A–C, A–E),
     * Rule X-Ray 내용을 육안으로 점검.

---

## 9. 정리 – 문제 3가지와 개선안 매핑

1. **계층 맥락 부재 (“숲을 못 본다”)**

   * 해결 방향:

     * `WaveBox` + `WaveTree`를 도입하여,
     * 각 시나리오를 시간·가격 박스로 묶고,
     * 그 안의 sub-wave 구조를 계층적으로 표현.
   * 후속 단계:

     * 다중 스윙 스케일 + 계층 트리로 상위 Degree와 연결하면
       “지금 파동이 전체 사이클에서 어느 위치인지”에 더 가까운 그림을 얻을 수 있음.

2. **스윙 감지 민감도 문제**

   * 해결 방향:

     * `SWING_SCALES`(macro/base/micro 등) 기반 다중 스윙 세트 도입.
     * 상황에 따라 가장 일관된 스케일을 선택하거나, 복수 스케일 정보를 함께 사용.
   * 추가 옵션:

     * ATR 기반 동적 threshold(Volatility adaptive swings) 도입.

3. **점수의 불투명성**

   * 해결 방향:

     * `RuleCheck` → `rule_evidence` 구조화.
     * UI의 Rule X-Ray 패널에 규칙별 pass/fail, value vs expected, penalty를 노출.
   * 효과:

     * 사용자는 “왜 이게 85점인지”, “어떤 규칙이 아슬아슬했는지”를 확인하고
       자신의 트레이딩 철학에 맞춰 해석/필터링 가능.

---

여기까지가 sir께서 말씀하신 내용과 현재 코드/문서를 기준으로 재구성한 **풀 스펙 1차본**입니다.
이 상태로 코드 에이전트에게 넘기면, 우선 **WaveBox + WaveTree + Rule X-Ray + 다중 스윙 스케일** 네 축을 중심으로 구체적인 구현 작업을 진행할 수 있을 것입니다.
