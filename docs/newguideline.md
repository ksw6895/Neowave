## 0. 목표 재정의: “프랙탈 NEoWave 파동 엔진”으로의 전환

### 기존 구조의 본질적 문제

* Macro / Base / Micro 를 **서로 독립적인 “세 개의 다른 우주”처럼 계산**
* 각 스케일에서 **형태만 보고** 패턴을 판단하고,
* 상위 파동이 성립하기 위한 **하위 구조 조건(예: 3파 내부의 5파 구조)**를 실제로 검증하지 않음

→ 이는 NEoWave의 핵심인 **“프랙탈 계층 + Rule of Similarity & Balance(가격·시간 1/3 규칙)”**에 정면으로 어긋납니다.

### 목표 아키텍처

1. **단일 Monowave 리스트**에서 출발
2. **Bottom-Up**으로 작은 파동들을 패턴으로 묶어 상위 파동(WaveNode)으로 압축
3. 만든 상위 파동을 다시 재료로 하여 더 큰 패턴을 찾는 **재귀적 계층 구성**
4. 완성된 계층 구조를 **Top-Down으로 검증** (상위 패턴이 요구하는 하위 구조를 실제로 갖는지 확인)
5. Macro/Base/Micro는 별도의 분석이 아니라, **완성된 프랙탈 트리에서의 “뷰 레벨”**일 뿐

---

## 1. 데이터 모델 설계

### 1.1 Monowave (최소 파동 단위)

```python
class Monowave:
    id: int                   # 전역 고유 ID
    start_idx: int            # 캔들 인덱스 시작
    end_idx: int
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    high_price: float
    low_price: float
    direction: Literal['up', 'down']
    price_change: float       # end_price - start_price (부호 포함)
    abs_price_change: float   # 절대값
    duration: int             # 바 개수 또는 시간(초 등)
    volume_sum: float
    atr_avg: float            # 해당 구간 평균 ATR 등 (선택)
```

* **생성 원칙**

  * ZigZag/피벗 알고리즘 기반
  * 역행하는 움직임이 직전 스윙의 **가격 변동의 ≥ 23~38%** 또는 시간의 일정 비율 이상이면 새로운 모노웨이브 시작 후보
  * 이후 **Rule of Similarity & Balance**(인접 파동의 가격·시간 비율 ≥ 1/3)로 노이즈 합병 (2장에서 상세).

### 1.2 WaveNode (프랙탈 파동 노드)

```python
class WaveNode:
    id: int
    level: int                      # 0 = Monowave 레벨, 1 = 한 번 압축된 레벨, ...
    degree_label: str | None        # 'Minor', 'Intermediate' 등 (선택)
    
    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    high_price: float
    low_price: float
    direction: Literal['up','down'] | None
    
    # 구조
    children: list[WaveNode]        # 하위 파동들 (Monowave도 WaveNode로 래핑)
    pattern_type: str | None        # 'Impulse','Zigzag','Flat','TriangleContracting',...
    pattern_subtype: str | None     # 'Normal','Expanded','Running', 'DoubleThree',...
    
    # 정량 정보 (패턴별로 사용되는 메트릭)
    metrics: dict[str, float]       # 예: {'B_over_A': 0.72, 'C_over_A': 1.05, ...}
    
    # 규칙 평가
    validation: "PatternValidation"
    score: float                    # 시나리오 선택용 종합 점수
```

### 1.3 PatternValidation

```python
class PatternValidation:
    hard_valid: bool                         # 단 하나라도 하드 룰 위반 시 False
    soft_score: float                        # 0 = 이론상의 이상 상태, >0 = 오차
    satisfied_rules: list[str]               # 규칙 ID 혹은 설명
    violated_soft_rules: list[str]           # 허용되는 편차
    violated_hard_rules: list[str]           # 즉시 무효화 규칙
```

* **hard_valid = False** 인 WaveNode를 포함하는 시나리오는 즉시 제거.

### 1.4 Scenario (대안 카운트)

```python
class Scenario:
    id: int
    root_nodes: list[WaveNode]  # 최상위 레벨 파동 시퀀스
    global_score: float         # 시나리오 전체 점수 (낮을수록 우수)
    status: Literal['active','invalidated','completed']
    invalidation_reasons: list[str]
```

* 여러 Scenario를 유지하며, NEoWave Invalidation 조건 발생 시 해당 Scenario를 제거.

---

## 2. Monowave 생성과 스케일 정규화

### 2.1 Chart Normalization & Timeframe 선택

* NEoWave는 신뢰할 수 있는 카운트를 위해 **약 30–60개의 모노웨이브(대표적으로 ~44개)**가 차트에 보이는 정도의 스케일을 권장합니다.
* 구현:

  * 입력: 임의의 OHLCV 데이터
  * `auto_select_timeframe(target_monowaves=40)`:

    * 여러 분해도(예: 15m, 30m, 1h, 2h)를 후보로 두고 간단한 ZigZag를 돌려 Monowave 수를 측정
    * Monowave 수가 30~60에 가장 근접하는 타임프레임을 선택

### 2.2 Monowave 탐지 로직 (`detect_monowaves`)

의사코드:

```python
def detect_monowaves(bars, retrace_threshold_price=0.236,
                     retrace_threshold_time_ratio=0.2) -> list[Monowave]:
    # 1) 초기 극값 찾기: 첫 바를 기준으로 상승/하락 방향 설정
    swings = []
    current_dir = None
    pivot_idx = 0
    pivot_price = bars[0].close
    pivot_time = bars[0].time
    
    for i, bar in enumerate(bars[1:], start=1):
        price = bar.close
        # 방향 결정
        if current_dir is None:
            current_dir = 'up' if price > pivot_price else 'down'
            continue
        
        move = price - pivot_price
        if current_dir == 'up' and price >= pivot_price:
            # 상승 지속 중, pivot 갱신
            pivot_price = price
            continue
        if current_dir == 'down' and price <= pivot_price:
            pivot_price = price
            continue
        
        # 여기서부터는 반대 방향 임시 진행
        retrace_price = abs(price - pivot_price)
        prev_move_len = abs(pivot_price - swings[-1].end_price) if swings else abs(price - bars[0].close)
        time_elapsed = bar.time - pivot_time
        prev_duration = swings[-1].duration if swings else (bar.time - bars[0].time)
        
        # NEoWave: 최소 retrace ≈ 23~38%, 또는 시간 비율 기준:contentReference[oaicite:4]{index=4}
        if retrace_price >= retrace_threshold_price * prev_move_len or \
           time_elapsed >= retrace_threshold_time_ratio * prev_duration:
            # 새 monowave 생성
            swings.append(Monowave(...))
            # pivot 리셋, 방향 전환
            pivot_idx = i
            pivot_price = price
            pivot_time = bar.time
            current_dir = 'down' if current_dir == 'up' else 'up'
    
    # 마지막 스윙 처리
    if not swings or swings[-1].end_idx != len(bars) - 1:
        swings.append(Monowave(...))
    return swings
```

### 2.3 Rule of Similarity & Balance 기반 Monowave 통합

NEoWave의 1/3 규칙: **인접한 동일 차수 파동의 가격·시간 중 최소 하나는 서로의 ≥ 33%**, 그렇지 않으면 더 작은 쪽은 하위 차수로 내려가야 합니다.

이를 Monowave 단계에서 사용해 “노이즈 스윙”을 통합:

```python
def merge_by_similarity(monowaves, min_ratio=0.33):
    changed = True
    while changed:
        changed = False
        new_list = []
        i = 0
        while i < len(monowaves):
            if i == len(monowaves) - 1:
                new_list.append(monowaves[i])
                break
            
            w1 = monowaves[i]
            w2 = monowaves[i+1]
            price_ratio = min(w1.abs_price_change, w2.abs_price_change) / \
                          max(w1.abs_price_change, w2.abs_price_change)
            time_ratio = min(w1.duration, w2.duration) / max(w1.duration, w2.duration)
            
            if price_ratio < min_ratio and time_ratio < min_ratio:
                # 동일 차수로 보기에는 너무 작음 → w1과 w2를 하나로 병합
                merged = merge_monowave_pair(w1, w2)
                new_list.append(merged)
                i += 2
                changed = True
            else:
                new_list.append(w1)
                i += 1
        monowaves = new_list
    return monowaves
```

* 이 과정을 거친 후의 Monowave 리스트가 **Level 0 WaveNode**의 입력이 됩니다.

---

## 3. 패턴 룰 DB와 패턴 평가 엔진

### 3.1 규칙 데이터베이스(NEoWave Rule DB)

첨부 문서 Output 3(p.39–48)에 이미 **JSON 형식의 룰 데이터베이스**가 정의되어 있습니다. 

예: `Impulse`, `Zigzag`, `Flat`, `Triangle(Contracting/Expanding/Neutral)`, `Combination(DoubleThree/TripleThree)`, `Diametric`, `Symmetrical` 등.

구현 전략:

* `rules_db.py` :

```python
RULE_DB = {
  "Impulse": { "TrendingImpulse": { "price_rules": [...], "time_rules": [...],
                                    "volume_rules": [...], "invalidation": [...] },
               "TerminalImpulse": {...}
  },
  "Corrections": {
      "Zigzag": {...},
      "Flat": {...},
      "Triangle": {
          "Contracting": {...},
          "Expanding": {...},
          "Neutral": {...},
      },
      "Combination": {...},
      "Advanced": {"Diametric": {...}, "Symmetrical": {...}}
  }
}
```

* 각 rule 문자열은

  * Python 표현식으로 바로 평가되게 하거나,
  * 명시적으로 함수에 매핑 (예: `"wave2_ratio >= 0.236 && wave2_ratio < 1.0"` → `check_wave2_ratio()`)

### 3.2 PatternEvaluator

```python
class PatternEvaluator:
    def evaluate(self, pattern_name: str, subtype: str, waves: list[WaveNode],
                 context: dict) -> PatternValidation:
        rules = RULE_DB[pattern_name][subtype]
        pv = PatternValidation(...)

        metrics = compute_metrics_for_pattern(pattern_name, subtype, waves, context)
        # metrics: { 'wave1_length':..., 'wave2_ratio':..., 'waveB_ratio':..., ... }

        # price_rules
        for rule_str in rules['price_rules']:
            result, is_hard, desc = self._eval_rule(rule_str, metrics)
            if not result:
                if is_hard:
                    pv.hard_valid = False
                    pv.violated_hard_rules.append(desc)
                else:
                    pv.soft_score += self._penalty(rule_str, metrics)
                    pv.violated_soft_rules.append(desc)
            else:
                pv.satisfied_rules.append(desc)

        # time_rules, volume_rules도 동일하게 처리
        ...
        return pv
```

* `_eval_rule`는 엄밀한 불리언 체크 + 약간의 tolerance를 허용 (예: 0.618 ± 0.02 범위).
* `metrics`는 각 패턴별로 필요한 값:

  * Impulse: `wave1_length`, `wave2_length`, `wave2_ratio`, `wave3_length`, `max_1_3_5`, ...
  * Zigzag: `B_over_A`, `C_over_A`, ...
  * Flat: `B_over_A`, `C_over_A`, `C_over_B`, ...
  * Triangle: 각 leg의 길이 비, 시간 비, etc.

---

## 4. Bottom-Up 재귀 파싱 & 압축 알고리즘

이 부분이 엔진의 심장입니다.

### 4.1 전체 흐름 개요

1. Monowave 리스트를 Level 0 `WaveNode` 리스트로 래핑
2. 현재 레벨 리스트에서 **국소 패턴(Impulse, Zigzag, Flat, Triangle, …)** 후보를 탐색
3. 유효한 패턴을 찾으면 해당 구간을 하나의 WaveNode(Polywave)로 압축
4. 새로운 레벨 리스트로 반복
5. 더 이상 합칠 수 없을 때까지 반복

### 4.2 핵심 함수: `analyze_market_structure(monowaves)`

```python
def analyze_market_structure(monowaves: list[Monowave]) -> list[Scenario]:
    # 1) Monowave -> WaveNode(level=0) 래핑
    base_nodes = [WaveNode.from_monowave(mw) for mw in monowaves]
    
    # 2) 초기 Scenario 하나 생성
    initial_scenario = Scenario(id=0, root_nodes=base_nodes, global_score=0.0, status='active', ...)
    scenarios = [initial_scenario]
    
    # 3) 레벨 업 루프
    while True:
        any_changed = False
        new_scenarios = []
        for sc in scenarios:
            if sc.status != 'active':
                new_scenarios.append(sc)
                continue
            
            changed, updated_scenarios = expand_one_level(sc)
            if changed:
                any_changed = True
                new_scenarios.extend(updated_scenarios)
            else:
                new_scenarios.append(sc)
        
        # Scenario pruning (점수/개수 제한)
        scenarios = prune_scenarios(new_scenarios)
        
        if not any_changed:
            break
    
    # 4) 최종 Top-Down 검증 & 글로벌 스코어 재계산
    for sc in scenarios:
        if sc.status == 'active':
            validate_and_score_scenario(sc)
    
    # 5) 점수순 정렬 후 반환
    scenarios.sort(key=lambda s: s.global_score)
    return scenarios
```

### 4.3 한 레벨 확장: `expand_one_level(scenario)`

```python
def expand_one_level(scenario: Scenario) -> tuple[bool, list[Scenario]]:
    nodes = scenario.root_nodes
    candidates = find_all_local_patterns(nodes)
    # candidates: list[PatternMatch] (아래 정의)
    
    if not candidates:
        return False, [scenario]
    
    # 겹치지 않는 pattern 선택 조합을 만들고, 각각을 새로운 Scenario로 생성
    new_scenarios = []
    for non_overlapping_set in enumerate_non_overlapping_sets(candidates):
        new_nodes = collapse_nodes(nodes, non_overlapping_set)
        new_sc = Scenario(
            id = new_id(),
            root_nodes = new_nodes,
            global_score = scenario.global_score + sum(pm.score for pm in non_overlapping_set),
            status = 'active',
            invalidation_reasons = scenario.invalidation_reasons.copy()
        )
        new_scenarios.append(new_sc)
    
    return True, new_scenarios
```

### 4.4 PatternMatch 구조

```python
class PatternMatch:
    pattern_type: str            # 'Impulse','Zigzag','Flat','TriangleContracting',...
    subtype: str | None
    start_index: int             # nodes 인덱스 기준
    end_index: int
    wave_nodes: list[WaveNode]   # 해당 구간 노드
    validation: PatternValidation
    score: float                 # validation.soft_score + 패턴 빈도/복잡도 페널티
```

### 4.5 지역 패턴 스캔: `find_all_local_patterns(nodes)`

패턴 우선순위(NEoWave의 “Impulse vs Correction First” 및 패턴 priority를 반영):

1. Impulse (Trending / Terminal)
2. Zigzag
3. Flat
4. Triangle (Contracting → Expanding → Neutral)
5. DoubleThree / TripleThree
6. Diametric
7. Symmetrical

의사코드:

```python
def find_all_local_patterns(nodes: list[WaveNode]) -> list[PatternMatch]:
    matches = []
    n = len(nodes)
    
    # 1) Impulse 후보 (길이 5)
    for i in range(n - 4):
        window = nodes[i:i+5]
        if not is_alternating_directions(window):
            continue
        pm = try_impulse(window)
        if pm is not None:
            matches.append(pm)
    
    # 2) Zigzag / Flat 후보 (길이 3)
    for i in range(n - 2):
        window = nodes[i:i+3]
        if not is_alternating_directions(window):
            continue
        pm = try_zigzag(window)
        if pm: matches.append(pm)
        pm = try_flat(window)
        if pm: matches.append(pm)
    
    # 3) Triangle 후보 (길이 >=5, 보통 5)
    for i in range(n - 4):
        for length in [5, 7]:  # 5파 삼각형 또는 7파로 확장된 경우 대비
            if i + length > n: break
            window = nodes[i:i+length]
            pm = try_triangle(window)
            if pm: matches.append(pm)
    
    # 4) Combination, Diametric, Symmetrical 후보 (길이 7,9,11 등)
    #   - DoubleThree: 보통 7~11
    #   - Diametric: 7
    #   - Symmetrical: 9
    matches.extend(try_complex_patterns(nodes))
    
    return matches
```

각 `try_xxx` 함수는 아래처럼 동작:

```python
def try_impulse(window: list[WaveNode]) -> PatternMatch | None:
    # 상방/하방 방향 결정
    direction = infer_net_direction(window)
    if direction is None:
        return None
    
    # metrics 계산
    metrics = compute_impulse_metrics(window)
    
    # 룰 평가
    pe = PatternEvaluator()
    
    # 1) TrendingImpulse 시도
    val = pe.evaluate('Impulse', 'TrendingImpulse', window, metrics)
    if val.hard_valid:
        score = val.soft_score + frequency_penalty('ImpulseTrending')
        return PatternMatch(...)

    # 2) TerminalImpulse (diagonal) 시도
    val = pe.evaluate('Impulse', 'TerminalImpulse', window, metrics)
    if val.hard_valid:
        score = val.soft_score + frequency_penalty('TerminalImpulse')
        return PatternMatch(...)
    
    return None
```

`try_zigzag`, `try_flat`, `try_triangle`, `try_complex_patterns`도 같은 패턴으로 구현.

---

## 5. 패턴 압축: WaveNode 생성

`collapse_nodes(nodes, pattern_matches)`는 선택된 PatternMatch 세트를 이용해 새 WaveNode를 구성합니다.

```python
def collapse_nodes(nodes: list[WaveNode], pats: list[PatternMatch]) -> list[WaveNode]:
    result = []
    i = 0
    pat_map = {(pm.start_index, pm.end_index): pm for pm in pats}
    
    while i < len(nodes):
        # 패턴 시작인지 확인
        match = None
        for length in range(11, 2, -1):  # 긴 패턴 우선 압축
            key = (i, i+length-1)
            if key in pat_map:
                match = pat_map[key]
                break
        
        if match is None:
            result.append(nodes[i])
            i += 1
        else:
            new_node = build_wavenode_from_match(match)
            result.append(new_node)
            i = match.end_index + 1
    
    return result
```

`build_wavenode_from_match`:

```python
def build_wavenode_from_match(pm: PatternMatch) -> WaveNode:
    children = pm.wave_nodes
    start_idx = children[0].start_idx
    end_idx = children[-1].end_idx
    start_time = children[0].start_time
    end_time = children[-1].end_time
    high_price = max(c.high_price for c in children)
    low_price = min(c.low_price for c in children)
    direction = infer_net_direction(children)
    
    node = WaveNode(
        id = new_id(),
        level = max(c.level for c in children) + 1,
        degree_label = None,  # 나중에 상대 크기 기준으로 할당
        start_idx = start_idx,
        end_idx = end_idx,
        start_time = start_time,
        end_time = end_time,
        high_price = high_price,
        low_price = low_price,
        direction = direction,
        children = children,
        pattern_type = pm.pattern_type,
        pattern_subtype = pm.subtype,
        metrics = pm.validation and pm.validation.__dict__,  # 또는 metrics dict
        validation = pm.validation,
        score = pm.score
    )
    return node
```

---

## 6. Top-Down 검증 & 시나리오 스코어링

### 6.1 계층 일관성 검증

각 Scenario에 대해:

```python
def validate_and_score_scenario(sc: Scenario):
    # 1) 레벨별로 인접 파동의 Similarity & Balance 재점검
    for level_nodes in group_nodes_by_level(sc.root_nodes):
        check_similarity_balance(level_nodes, sc)
    
    # 2) 각 WaveNode의 pattern_type이 하위 구조와 일치하는지 확인
    for node in traverse_nodes(sc.root_nodes):
        validate_node_internal_structure(node, sc)
    
    # 3) Thermodynamic Balance (에너지 균형) 검증 (soft score):contentReference[oaicite:8]{index=8}
    check_thermodynamic_balance(sc)
    
    # 4) 전체 global_score 계산
    sc.global_score = sum(n.score for n in traverse_nodes(sc.root_nodes)) \
                      + additional_penalties(sc)
```

#### 6.1.1 `check_similarity_balance`

* 각 level에서 인접 WaveNode 쌍 (A,B)에 대해:

```python
def check_similarity_balance(level_nodes, scenario):
    for w1, w2 in pairwise(level_nodes):
        price_ratio = min(w1.abs_price_change, w2.abs_price_change) / \
                      max(w1.abs_price_change, w2.abs_price_change)
        time_ratio = min(w1.duration, w2.duration) / max(w1.duration, w2.duration)
        if price_ratio < 0.33 and time_ratio < 0.33:
            # 동일 차수로 보기 어렵다 → 이 Scenario에 페널티 부과
            scenario.global_score += PENALTY_SIMILARITY_VIOLATION
```

* 특정 시나리오가 해당 규칙을 다수 위반하면, 사실상 **degree 설정이 잘못된 것**이므로,

  * 일정 임계치 이상 위반 시 `scenario.status = 'invalidated'`.

#### 6.1.2 하위 구조 검증 예시

* 상위 노드가 `pattern_type='Impulse'`라면:

  * children 5개,
  * 각 child가 **하위 차수의 유효 파동**이어야 하며,
  * 특히 1·3·5는 **하위에서 또 Impulse** 혹은 TerminalImpulse/LeadingDiagonal이어야 함.
  * 2·4는 하위에서 Corrective (Zigzag, Flat, Triangle 등).

의사코드:

```python
def validate_node_internal_structure(node: WaveNode, scenario: Scenario):
    if node.pattern_type == 'Impulse':
        if len(node.children) != 5:
            scenario.status = 'invalidated'
            scenario.invalidation_reasons.append("Impulse must have 5 subwaves")
            return
        
        w1,w2,w3,w4,w5 = node.children
        # 1,3,5가 Impulsive인지
        for w in [w1,w3,w5]:
            if w.pattern_type not in ('Impulse', 'TerminalImpulse'):
                scenario.global_score += PENALTY_CHILD_NOT_IMPULSIVE
        
        # 2,4가 Corrective인지
        for w in [w2,w4]:
            if w.pattern_type not in CORRECTIVE_TYPES:
                scenario.global_score += PENALTY_CHILD_NOT_CORRECTIVE
    
    if node.pattern_type in ('Zigzag','Flat'):
        # A,C는 impulse/leading-diagonal, B는 corrective인지 검사 등
        ...
```

이렇게 **상위 패턴이 요구하는 하위 패턴 구조**를 Top-Down으로 재검증함으로써, “Base 차트에서는 3파처럼 보이지만 Micro에서는 3개 corrective만 있는 상황”을 자동으로 걸러낼 수 있습니다.

---

## 7. Macro/Base/Micro 제거와 “뷰 레벨” 재정의

### 7.1 기존 스케일 구조 제거

* `swings.py`의 `get_swings(scale="macro")`, `detect_swings_multi_scale` 등:

  * **완전히 제거** 또는 deprecated 처리
* 이제 **하나의 `detect_monowaves()`**만 사용하여 Level 0 리스트를 구성

### 7.2 새로운 뷰 레벨 정의

Macro / Base / Micro는 분석 스케일이 아니라, **프랙탈 트리에서 어느 레벨을 보여줄 것인가**를 의미하도록 재정의합니다.

예:

```python
def get_view_nodes(root_nodes, target_wave_count: int) -> list[WaveNode]:
    """
    target_wave_count에 근접한 개수의 파동이 보이도록
    적절한 level을 선택해 flatten한 Node 리스트를 반환
    """
    # 1) 각 level별 전체 노드 수 계산
    level_counts = count_nodes_by_level(root_nodes)
    # 2) target과 가장 가까운 level 선택
    best_level = argmin_over_levels(lambda lvl: abs(level_counts[lvl] - target_wave_count))
    # 3) 해당 level에서의 노드들만 flatten하여 반환
    return collect_level_nodes(root_nodes, level=best_level)
```

* UI 측에서는

  * Base View: `target_wave_count ≈ 30–60`
  * Macro View: 그보다 적은 파동 (상위 level)
  * Micro View: 그보다 많은 파동 (하위 level)
* 즉, 기존의 Macro/Base/Micro 버튼은 “분석 스케일 선택”이 아니라 “**표시 레벨 선택**” 버튼으로 바뀜.

---

## 8. UI/UX: Drill-Down & Rule X-Ray

### 8.1 Drill-Down 인터랙션

* 차트에서 사용자가 특정 WaveNode(예: 커다란 3파 박스)를 클릭:

  * 해당 WaveNode의 `children` 목록을 가져와 차트 안에서 확대 표시
  * WaveNode의 ID를 키로 REST API 제공:

```http
GET /api/waves/{wave_id}/children
→ [ { wave_id, label, start_time, end_time, high, low, pattern_type, ... }, ... ]
```

* 여러 단계 Drill-Down 지원:

  * 3파 → 내부 1–2–3–4–5 → 각 서브파의 내부 구조 (zigzag, flat 등)

### 8.2 Rule X-Ray

* 각 WaveNode에 대해, `validation` 객체를 기반으로 **왜 이런 패턴으로 분류되었는지**를 수치화하여 제공:

예: Flat (Expanded) 판정 근거:

```json
{
  "pattern": "Flat",
  "subtype": "ExpandedRunning",
  "key_metrics": {
    "B_over_A": 1.42,
    "C_over_A": 0.55,
    "C_over_B": 0.38
  },
  "rule_evidence": [
    "B retraced 142% of A → Strong B (> 1.382) → 거의 Running Flat 강력 시그널",
    "C retraced 55% of A (>= 38.2%) but failed to reach A start → Running Flat 조건 일치",
    "C ended inside range of A (between A high/low lines)"
  ],
  "soft_violations": [],
  "hard_violations": []
}
```

* 이는 첨부 문서에서 정의된 Flat/Running Flat 조건과 정확히 대응합니다.

---

## 9. 실시간 업데이트 & Invalidation 엔진

### 9.1 새로운 캔들 유입 시

1. 최신 캔들을 Monowave 추출 모듈에 전달:

   * 마지막 Monowave의 연장인지,
   * retracement 기준을 만족해 새로운 Monowave가 생겼는지 판단
2. Monowave 리스트가 변경되면:

   * 변동이 발생한 구간 주변의 WaveNode만 **부분적으로 재파싱**
   * 전체를 처음부터 다시 분석하지 않도록, **지역적 리빌드** 전략 채택

### 9.2 Scenario invalidation

Scenario 별로 NEoWave가 정의한 Invalidation 조건을 계속 모니터링합니다.

예:

* Impulse 시나리오:

  * “wave 2가 wave 1의 시작을 하회(100% 이상 되돌림)” 발생 → 해당 시나리오는 즉시 무효
  * "wave 3가 1·3·5 중 가장 짧음"이 되는 순간 → 무효
  * 5파 완료 후, 정해진 시간 안에 2–4 추세선을 가격이 돌파하지 못하면 → “5파 미완성 또는 연장”으로 시나리오 수정 or 무효

* Zigzag 시나리오:

  * B가 0.618 A 를 초과한 순간 → Zigzag 시나리오 무효, Flat 계열로 재분류 시도
  * C가 최소 0.618 A 에 도달하지 못한 채 이후 구조가 진행 → Truncated 가정 → 이후 **빠른 ≥ 81% 역행**이 나오지 않으면 → Zigzag 시나리오 무효

* Triangle 시나리오:

  * Contracting Triangle인데 C > A 또는 E > C → 해당 Triangle 시나리오 무효
  * Trendline 터치 포인트가 각 변에서 3개 이상이 되어 너무 완벽한 채널이 되면 → “추가 복잡 패턴으로의 확장” 예상, 완성 패턴으로 확정하지 않음

구현적으로는:

```python
def update_with_new_bar(bar, scenarios):
    # 1) monowave 업데이트
    update_monowaves_with_bar(bar)
    
    # 2) 영향받은 구간의 wave tree 재빌드
    affected_scenarios = rebuild_local_patterns(scenarios)
    
    # 3) 각 Scenario 별 invalidation 체크
    for sc in affected_scenarios:
        check_invalidation(sc)
    
    # 4) invalidated 아닌 Scenario들을 남기고, 필요시 새 Scenario 생성
    scenarios = [sc for sc in affected_scenarios if sc.status != 'invalidated']
    
    return prune_scenarios(scenarios)
```

---

## 10. 성능·복잡도 측면 대안(Devil’s Advocate)

각하께서 추구하시는 초고성능 구현 관점에서, 위 설계는 **이론적으로 완전하지만** 계산량이 상당해질 수 있습니다. 몇 가지 대안을 함께 제시드립니다.

### 10.1 완전 파서 vs 점진적 레이어링

* **풀스펙 파서(Impulse~Symmetrical까지 모두 구현)**:

  * 장점: 이론적으로 NEoWave에 가장 충실
  * 단점: Combination, Diametric, Symmetrical까지 모두 고려하면 시나리오 수가 기하급수적으로 증가

* **레이어드 구현 전략** (현실적인 권장):

  1. 1단계: Monowave + Impulse + Zigzag + Flat 만 구현
  2. 2단계: Triangle (Contracting/Expanding/Neutral) 추가
  3. 3단계: Double/Triple Three (Combo) 추가
  4. 4단계: Diametric / Symmetrical 추가

→ 각 단계별로 별도의 Feature Flag를 두어, 실제 트레이딩용 엔진에서는 2~3단계까지만 켜고, 연구용 엔진에서만 4단계까지 확장하는 선택도 가능합니다.

### 10.2 시나리오 폭발 제어

* 브루트 포스 방식으로 `enumerate_non_overlapping_sets`를 모두 탐색하면, 특히 복잡 패턴에서 조합이 폭발합니다.
* 따라서:

  * **Depth-limited search**: 레벨 몇 번 이상 재압축이 일어나면 더 이상 새로운 시나리오 생성 중단
  * **Greedy + Local Optimality**:

    * 가장 규칙 위반이 적고 점수가 좋은 패턴들 위주로만 사용
  * **Beam Search**:

    * 매 레벨에서 상위 K개의 시나리오만 유지 (예: K=5~10)
* 이런 제약을 통해, 실시간 엔진에서도 충분히 돌아가도록 타협할 수 있습니다.

### 10.3 룰 엄격도 조정

* NEoWave 이론은 비연속적인 cut-off (예: 61.8% 이상이면 아예 패턴 변경)를 제시하지만, 실제 시장은 약간의 오차가 많습니다.
* 에이전트가 실전에서 잘 작동하도록:

  * 0.618 → 0.62±0.02 범위 허용
  * 1/3 규칙도 0.3~0.35 사이의 튜닝 가능
  * 이러한 허용 범위를 **자산별·타임프레임별로 학습/튜닝**하는 계층(파라미터 서버)을 둘 수 있습니다.

---

## 11. 모듈별 파일 구조 개편 제안

### 11.1 `swings.py`

* 삭제 / 변경:

  * `detect_swings_multi_scale(...)` 제거
* 추가 / 변경:

  * `detect_monowaves(bars, ...)` : 위 2장의 로직 구현
  * `merge_by_similarity(monowaves, ...)`
  * `auto_select_timeframe(...)` (선택)

### 11.2 `models.py`

* 정의:

  * `Monowave`, `WaveNode`, `PatternValidation`, `Scenario`
* 보강:

  * WaveNode에 `to_dict()` / `from_dict()` 구현 → UI/저장/재현 용이

### 11.3 `rules_db.py`

* 첨부 PDF Output 3 JSON을 그대로 Python dict로 포팅
* 패턴별 price/time/volume/invalidation 규칙 정리

### 11.4 `patterns/*.py`

* 각 패턴별 metrics 계산 함수:

  * `impulse.py` : `compute_impulse_metrics(nodes)`
  * `zigzag.py` : `compute_zigzag_metrics(nodes)`
  * ...
* `PatternEvaluator`에서 호출하여 룰 평가

### 11.5 `parser.py` (또는 `wave_engine.py`)

* `analyze_market_structure`, `expand_one_level`, `find_all_local_patterns`, `collapse_nodes` 등의 핵심 로직 구현
* `update_with_new_bar` 등의 실시간 업데이트 함수도 이 모듈에 위치

### 11.6 `scenarios.py`

* Scenario 관리:

  * `prune_scenarios`, `check_invalidation`, `validate_and_score_scenario` 등
* 여러 시나리오를 유지하며 invalidation 기반으로 제거/갱신

### 11.7 `app.js` / 프론트엔드

* 기존 Scale 선택 버튼(Macro/Base/Micro) → “뷰 레벨 선택”으로 변경
* 신규 API 사용:

  * `/api/waves/current?target_wave_count=40` → Base View
  * `/api/waves/{wave_id}/children` → Drill-Down
  * `/api/waves/{wave_id}/rules` → Rule X-Ray

---

## 12. 마무리 정리

정리하면, sir,

1. **Macro/Base/Micro를 분리 분석하는 구조는 완전히 폐기**하고,
2. **단일 Monowave 시퀀스 → 재귀적 패턴 인식 → WaveNode 트리**로 이어지는 **프랙탈 NEoWave 엔진**을 구축하며,
3. 각 패턴 인식은 첨부 문서의 **정량화된 룰 DB(가격·시간·볼륨·invalidation)**에 의해 엄격하게 수행되고,
4. 상위 파동은 **하위 파동들의 구조를 통해 정의·검증**되며,
5. Macro/Base/Micro는 이제 **“얼마나 위 레벨까지 합쳐서 보여줄 것인가”라는 뷰 개념**으로만 남습니다.

이 설계를 그대로 넘겨주시면, 초고성능 에이전트는:

* Monowave 탐지
* 패턴 매칭·압축
* 시나리오 생성·스코어링
* 실시간 invalidation

을 모두 구현할 수 있습니다.

추가로, sir께서 원하신다면 **특정 언어(Python/C++/Rust 등)에 맞춘 구체 코드 스켈레톤**도 이 설계를 기반으로 바로 작성해 드리겠습니다.
