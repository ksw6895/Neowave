## 0. 개요 – 현재 엔진의 구조적 한계

### 0.1 확인된 핵심 문제

1. **“데이터의 첫 캔들 = 파동의 시작점” 가정**

   * `swings.detect_swings`는 **시계열의 0번 인덱스부터** 단방향으로 스윙을 생성합니다.
   * `parser.parse_wave_tree → build_wave_leaves → _merge_pass`는 **스윙 리스트의 0번 요소부터** 순차적으로 패턴 매칭을 수행합니다.
   * 결과적으로,

     * 0번째 캔들이 이미 진행 중인 하락/상승 파동의 **중간**이어도
     * 엔진은 그 지점을 **무조건 1파 / A파 후보**로 가정하고 임펄스·조정 패턴을 억지로 맞추려 합니다.
   * 이로 인해:

     * 좌측 차트 초반부에 **이상한 파동 라벨이 몰리는 현상**
     * “이미 끝난 이전 파동의 꼬리”를 강제로 새로운 파동의 1파로 해석하는 오류가 상시 발생합니다.

2. **Macro / Base / Micro 스케일의 완전한 분리**

   * `api.get_scenarios`는 `detect_swings_multi_scale`로 복수 스케일의 스윙을 계산하지만,
   * `generate_scenarios` 호출 시에는 **단일 `scale_id`의 스윙 리스트만** 사용합니다.
   * 즉,

     * Base 스케일에서 3파로 라벨링된 구간이
     * Micro 스케일에서 실제로 **5개의 모노웨이브(impulse subdivision)를 갖는지** 전혀 검증되지 않습니다.
   * NEoWave의 **“동일 차수 파동 간 비례성(rule of similarity & balance)”**, **“하위 파동의 구조적 검증”** 개념이 코드에 반영되어 있지 않습니다. 

3. **NEoWave 정량 규칙 미반영**

   * 첨부 문서에 정리된

     * **1/3 비례 규칙(가격·시간 33% 이상이면 동일 차수)**
     * Zigzag / Flat / Triangle / Complex correction의 **정량 임계값 (61.8%, 38.2%, 161.8% 등)**
     * **Impulse의 확장 규칙, 2–4 라인·채널·touch-point 규칙, Complexity cap(Triple Three 한계)**
       가 엔진의 어떤 계층에서도 **사용되지 않습니다.** 

---

## 1. NEoWave 엔진 개선 사양서 v0.3+ (보강본)

**목표 세 축**

1. **맹목적 시작점 제거** – Smart Anchoring & Swing Normalization
2. **계층적 통합 분석** – Macro/Base/Micro 간 구조적 일관성 확보
3. **인터랙티브 분석 & 정사각형(Time–Price) 검증 강화** – 사용자 가설 반영 + NEoWave 정량 규칙 내재화

---

## 2. 엔진 코어 개선 – Smart Anchoring & Swing Normalization

### 2.1 Monowave 정규화 (NEoWave 스윙 기준 반영)

**요구사항**

1. **스윙 분해 기준을 NEoWave 규칙에 맞게 재정의**

   * 첨부 문서에서 제안하는 방식:

     * **역추세 움직임이 직전 스윙의 최소 23–38% 이상**일 때 새로운 모노웨이브로 간주. 
     * 또는 **가격·시간 중 최소 하나가 33% 이상(1/3 rule)**이면 동일 차수의 새로운 파동으로 인정.
   * 구현 방향:

     * `detect_swings`에서 **고정 % threshold** 대신

       * `price_retrace_ratio ≥ 0.23 ~ 0.33`
       * 또는 `time_ratio ≥ 0.33`
         를 만족할 때만 새로운 스윙으로 확정.
     * 너무 작은 스윙은 이후 단계 `merge_small_swings`에서 **자동 병합**.

2. **“적정 모노웨이브 개수” 유도**

   * NEoWave는 신뢰도 있는 파동 카운팅을 위해 **바 차트에 30–60개 수준의 monowave**가 보이는 타임 프레임·축비를 권고합니다. 
   * 엔진 레벨에서:

     * 분석 구간 안에 모노웨이브가 15개 미만이면 → **스윙 threshold를 완화** (더 많이 쪼갬)
     * 80개 이상이면 → threshold를 강화하여 **노이즈 스윙을 병합**

> 요약: `detect_swings`는 “NEoWave식 모노웨이브 시퀀스”를 생성하도록 재설계하고, 이를 후속 Smart Anchoring·패턴 인식의 공통 입력으로 사용합니다.

---

### 2.2 Anchor 후보 자동 탐색 – `identify_major_pivots`

**목적**
“데이터의 첫 캔들 = 파동 0번”이라는 가정을 버리고,
**“시장이 실제로 중요하게 인식한 Pivot(고점·저점)”**을 기준으로 파동 시작점을 탐색합니다.

**알고리즘 스펙 (의사 코드 수준)**

```python
def identify_major_pivots(swings, max_pivots=5):
    """
    Input : 동일 차수로 정규화된 Swing 리스트
    Output: Anchor로 사용할 pivot 인덱스 리스트 (중요도 순 정렬)
    """
    for each swing i:
        price_score  = abs(sw[i].delta_price) / avg_abs_delta
        time_score   = sw[i].duration       / avg_duration
        volume_score = sw[i].volume_sum     / avg_volume  # 선택적
        # NEoWave Thermodynamic Balance: 가격·시간·거래량이 모두 큰 구간을 우선시
        energy_score = price_score * max(time_score, 1.0)
        # 지나치게 얇은 스윙(시간/가격 비율 극단)을 패널티
        shape_penalty = f_aspect_ratio(sw[i])
        pivot_score = w_price*price_score + w_time*time_score \
                      + w_vol*volume_score + w_energy*energy_score \
                      - w_shape*shape_penalty
    상위 max_pivots개 인덱스를 중요도 순으로 반환
```

**핵심 포인트**

* **가격·시간·에너지(=가격×시간 또는 가격×거래량)**가 모두 의미 있는 스윙을 우선 앵커로 선정 → NEoWave의 “Thermodynamic Balance” 개념 반영. 
* 극단적으로 **길쭉한 바늘형/납작한 스윙**은 정사각형 비율 규칙에서 불리한 점수 부여(아래 §4 참조).

---

### 2.3 Multi-Anchor 시나리오 생성 & 점수화

**AS-IS**

* `generate_scenarios(swings)`
  → `swings[0]`에서 시작해 한 번의 `parse_wave_tree`만 수행
  → “왼쪽 끝에서부터 강제 카운팅”만 존재

**TO-BE**

1. **Anchor 세트 정의**

   * 입력:

     * `major_pivots = identify_major_pivots(swings, K)`
     * (옵션) **사용자 선택 구간의 시작/저점**도 Anchor 후보에 추가 (뒤의 custom-range와 연계).
   * Anchor 후보 예:

     * 전체 구간의 주요 저점 3개 + 주요 고점 2개 = 최대 5개

2. **Anchor별 시나리오 생성**

   ```python
   for anchor_idx in major_pivots:
       local_swings = swings[anchor_idx : ]
       scenario = parse_wave_tree(local_swings)
       score    = score_scenario_with_neowave_rules(scenario)
       scenarios.append((anchor_idx, scenario, score))
   ```

3. **NEoWave 규칙 기반 스코어링 – `score_scenario_with_neowave_rules`**

   * **Hard rule (위반 시 즉시 invalid)**

     * Impulse

       * 2파 ≥ 100% 1파, 3파가 1·3·5 중 최단, 1.618배 확장 부재 등. 
     * Zigzag / Flat / Triangle / Combo

       * Flat의 B < 61.8% A, Zigzag의 B > 61.8% A, Triangle의 C > A 등.
     * Complexity cap

       * W–X–Y–X–Z 이상 구조(4번째 X-wave) 등장 시 해당 시나리오 폐기. 

   * **Soft rule (위반 시 감점)**

     * **Rule of Similarity & Balance**

       * 동일 차수 인접 파동의 가격·시간 비가 **0.33 미만**이면 패널티. 
     * Impulse의 비확장 파동 간 Equality(1·5 파 동등성), 2·4파 Alternation(깊이/형태·시간의 상반성). 
     * Time–Price Equality

       * 큰 충격파 이후 조정이 가격 또는 시간 면에서 **0.33 미만으로 너무 짧으면** 감점.

   * **복잡도 패널티**

     * 동일 데이터를 설명하는 두 시나리오가 있을 때

       * 더 많은 패턴 조합(Triple Three 등)을 쓰는 시나리오에는 복잡도 패널티 부여.
       * NEoWave의 “가능한 한 **가장 단순한 패턴**을 우선 채택” 논리 구현. 

4. **최종 채택 전략**

   * **기본 출력**: Hard rule 위반이 0개이면서,

     * 전체 score가 최대인 시나리오 1개
   * **대안 시나리오**:

     * 상위 N개(예: 2~3개)를 “alternative”로 함께 반환
     * 각 시나리오마다 “주요 무효화 조건(invalidation condition)”을 같이 제공
       (예: “가격이 X를 돌파하면 이 카운트는 폐기”)

> 결과적으로, 엔진은 “데이터 시작점에 억지로 맞춘 유일한 시나리오”가 아니라,
> **“여러 유효 Anchor 중에서 NEoWave 규칙을 가장 잘 만족하는 시나리오”**를 제시하게 됩니다.

---

## 3. 계층 통합 분석 – Macro/Base/Micro 연결

### 3.1 구조 개념

* **Macro/Base/Micro 스케일을 “동일 이론, 다른 해상도”**로 보고,
* 상위 파동이 하위 파동의 구조로 **검증/감점/무효화**되도록 설계합니다.

### 3.2 Bottom-Up Verification (하향식 + 상향식 혼합 검증)

1. **Base 파동을 정의한 뒤 Micro 재검증**

   * 예시: Base 스케일에서

     * 특정 구간이 **Impulse 3파**로 라벨링되었다면,

   * 그 구간에 대해 Micro 스윙을 불러와:

     * `is_valid_impulse(micro_swings_subseq)`를 실제 NEoWave 규칙으로 검사

       * 5개 모노웨이브,
       * 3파 확장 여부,
       * 2·4파 가격·시간·구조 alternation,
       * 2–4 Trendline & post-impulse 2–4 라인 브레이크 등. 

   * **만약**

     * Micro 내부가 3-wave(zigzag 형태)만 보인다면

       * Base 3파에 **강한 감점 또는 invalid** 처리.

2. **패턴별 cross-scale 규칙 예시**

   * Base: Zigzag A파
     → Micro: A파는 반드시 **5파 구조(Impulse 또는 Leading diagonal)**여야 함.
   * Base: Flat B파
     → Micro: B파 내부는 3-3 구조이며, retracement 비율(61.8–138.2%)과 시간 규칙을 만족해야 함. 
   * Base: Triangle (Contracting)
     → Macro 스윙에서 수렴형이지만, 각 A–E leg 내부 Micro에서 **모두 조정파(3-3 구조)**가 나와야 함.

3. **Rule of Similarity & Balance – 스케일 간 일관성**

   * NEoWave: 동일 차수 파동은 인접 파동 대비 **가격/시간 33% 이상**이어야 합니다. 
   * 엔진 구현:

     * Macro/Base/Micro 각각에 대해 이 규칙을 적용하고,
     * 상위 차수 파동의 길이·시간이 하위 차수 평균의 **정수배 수준(대략 3~5배)**에 위치하도록 점수화.
     * 지나치게 “스케일 불연속(예: Base 한 파동이 Micro 파동 2~3개에 불과)”이면 감점.

### 3.3 데이터 구조 확장 – `WaveNode.sub_scale_analysis`

`src/neowave_core/models.py`:

```python
class WaveNode(BaseModel):
    id: int
    label: str              # 1,2,3,4,5 또는 A,B,C 등
    pattern_type: str       # Impulse, Zigzag, Flat, Triangle, Combo...
    children: list["WaveNode"]  # 동일 스케일 내 subdivision
    # 추가 필드
    sub_scale_analysis: dict | None = None
    """
    예시:
    {
      "scale": "micro",
      "swings": [...],           # 해당 구간 micro swings 요약
      "pattern": {...},          # micro에서 찾은 패턴 구조(JSON)
      "score": float,            # micro 레벨 NEoWave 규칙 적합도
      "violations": [...],       # 위반된 규칙 리스트
    }
    """
```

* Base 레벨 3파 Node를 클릭하면

  * `sub_scale_analysis.pattern`의 구조를 시각화하여
  * Micro 레벨의 실제 1·2·3·4·5 파동 (혹은 조정 구조)을 오버레이할 수 있게 합니다.

---

### 3.4 UI Drill-down 설계

Frontend (`app.js` + LightweightCharts):

1. 파동 박스(예: Base 3파)를 클릭 시:

   * 해당 WaveNode ID로 `/api/wave/{id}/detail` 호출
   * 응답으로 Micro 패턴 구조를 수신
   * 동일 차트 상에 **반투명 레이어**로 Micro 파동 카운트 overlay

2. 툴팁에 표시:

   * “이 Base 3파 내부 Micro 구조: Impulse(확장 3파), score 0.92 / 1.0, Rule violation 0개”
   * 또는 “Micro 구조: Zigzag(3파), Base Impulse 가설과 불일치 → scenario penalty -0.3”

---

## 4. 인터랙티브 분석 – Custom Range & Anchor Override

### 4.1 Frontend 인터랙션

1. 새로운 도구:

   * 차트 상단: `[영역 분석]` 토글 버튼
   * 활성화 시: 마우스 드래그로 **임의 구간 선택(시간 범위)**

2. 동작:

   * 선택 구간의 `startTime`, `endTime`(Unix timestamp 혹은 ISO) 추출
   * 현재 심볼/타임프레임과 함께 `POST /api/analyze/custom-range`로 전송

### 4.2 Backend API – `/api/analyze/custom-range`

**스펙**

* Endpoint: `POST /api/analyze/custom-range`
* Input(JSON):

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "start_ts": 1700000000,
  "end_ts":   1700500000,
  "max_pivots": 5,       // optional
  "max_scenarios": 3     // optional
}
```

* Logic:

  1. 전체 데이터셋에서 해당 구간만 **슬라이스**
  2. 슬라이스된 구간에서 다시 `detect_swings → merge_small_swings`
  3. `identify_major_pivots`로 Anchor 후보 생성하되,

     * **필수 Anchor**로 “선택 구간 내 첫 번째 local 저점(or 고점)”을 하나 포함 (사용자 직관 반영)
  4. 위에서 정의한 **Multi-Anchor + NEoWave Rule Scoring** 파이프라인 실행
  5. 상위 N개 시나리오와 각 시나리오의

     * score
     * invalidation 조건
     * 주요 패턴 설명을 JSON으로 반환

**이점**

* 사용자가 “여기가 1파 시작처럼 보인다”는 영역을 직접 표시하면,

  * 엔진은 **그 가설을 Anchor 후보로 강제 포함**시켜
  * NEoWave 규칙 하에서 가장 일관된 카운트를 찾아 줍니다.
* 시스템은 여전히 다른 Anchor 시나리오도 함께 계산해

  * “사용자 가설 vs 시스템 최적 시나리오”를 비교 가능하게 합니다.

---

## 5. 정사각형(Time–Price Balance) & 에너지 검증 강화

### 5.1 Box Ratio – 파동 정사각형성 평가

각 WaveNode 혹은 Swing에 대해, 다음과 같은 **Bounding Box**를 정의합니다.

* 높이: `price_range = |high - low|`
* 너비: `time_range  = end_time - start_time`
* 비율: `aspect_ratio = price_range / (k * time_range)`

  * `k`는 종목·타임프레임별 스케일 상수 (예: 로그 스케일 고려)

**규칙**

* **정상적인 파동**: `aspect_ratio`가 **일정 범위(예: 0.5 ~ 2.0)** 내에 위치
* 지나치게 납작(0.2 이하) 또는 바늘형(5 이상)은

  * **의미 있는 파동이라기보다 노이즈/이상 구조**로 간주
  * 스윙 병합 대상 또는 패턴 스코어 감점

이는 NEoWave의

* “가격뿐 아니라 시간도 균형을 이뤄야 한다(Time–Price Equality)”
* “큰 에너지를 소모한 파동에는 그에 상응하는 시간·가격 조정이 필요하다(Thermodynamic Balance)”
  를 기계적으로 반영하는 모듈입니다. 

### 5.2 패턴별 Time–Price / Energy 체크

1. **Impulse**

   * 5파 전체의 “에너지(가격×시간×평균 거래량)”와 이후 조정의 에너지를 비교
   * 조정 에너지가 이전 추세 에너지의 **일정 비율(예: ≥ 0.33)**에 못 미치면

     * “조정 미완료 가능성” 플래그 또는 시나리오 감점

2. **Zigzag / Flat**

   * A–B–C의 **시간 관계**:

     * `T_B ≈ T_A`면 `T_C ≈ T_A + T_B` 기대,
     * `T_B >> T_A`면 `T_C ≈ (T_A + T_B)/2` 기대 등. 
   * 이 관계에서 크게 벗어나면:

     * 해당 패턴 가설의 점수를 낮추고
     * Combo(복합 조정) 가능성에 가중치를 부여

3. **Triangle, Diametric, Symmetrical**

   * Triangle: A→E로 갈수록 **시간·가격·거래량이 수축**, touch-point 2개 제한. 
   * Diametric(7파): 7 leg의 시간 길이가 **서로 10–25% 이내**, 중간 D를 기준으로 대칭적 확장/수축. 
   * Symmetrical(9파): 9 leg의 시간·가격이 **대부분 10% 이내로 균질**해야 함. 
   * 엔진은 이 균질성 지표를 통해

     * “이상하게 균일한 7·9파 구조”를 단순 combo가 아닌 **Diametric/Symmetrical** 후보로 인식

---

## 6. 코드 레벨 구체 수정 지시

### 6.1 `src/neowave_core/swings.py`

1. `detect_swings` 개선

   * 인자 추가:

     * `min_price_retrace_ratio: float` (기본 0.23~0.33)
     * `min_time_ratio: float` (기본 0.33)
   * 로직:

     * 역추세 움직임이 위 임계값을 만족할 때만 스윙 종료·신규 스윙 생성.
   * 후처리:

     * 인접 스윙들에 대해 Rule of Similarity 적용

       * 가격·시간 비 둘 다 0.33 미만인 스윙은 이웃과 병합.

2. `identify_major_pivots(swings, max_pivots=5)` 신규 함수

   * 상술한 Pivot Scoring 로직 구현
   * 반환: Anchor 후보 스윙 인덱스 리스트 (중요도 순 정렬)

---

### 6.2 `src/neowave_core/scenarios.py`

1. **시나리오 생성 인터페이스 변경**

   ```python
   def generate_scenarios(
       swings,
       max_pivots: int = 5,
       max_scenarios: int = 3,
       anchor_indices: list[int] | None = None
   ) -> list[WaveScenario]:
   ```

   * `anchor_indices`가 주어지면 (예: custom-range)

     * 이를 우선 Anchor로 사용,
     * 부족하면 `identify_major_pivots` 결과로 보충

2. **Anchor별 파싱 & 스코어링**

   ```python
   def _generate_from_anchor(swings, anchor_idx):
       sub_swings = swings[anchor_idx:]
       tree = parse_wave_tree(sub_swings)
       score, violations = score_scenario_with_neowave_rules(tree)
       return WaveScenario(anchor_idx=anchor_idx, tree=tree, score=score, violations=violations)
   ```

3. **NEoWave Rule Engine 연동**

   * `rules.py` 또는 `rule_engine.py` 모듈 신설:

     * 첨부 문서 Output 3(JSON) 기반으로

       * 패턴별 price/time/volume/invalidation 규칙을 상수 테이블화. 
   * `score_scenario_with_neowave_rules`는 이 룰 테이블을 참조하여

     * Hard rule 위반 여부
     * Soft rule 위반 개수
     * 복잡도(사용된 패턴 수·조합 깊이)를 종합한 스코어 계산

4. **Multi-scale 검증 훅**

   * `generate_scenarios_multi_scale` 또는 유사 함수에서

     * Base 파동이 완성된 후 Micro 스윙을 받아
     * 각 WaveNode에 `sub_scale_analysis` 채우는 **후처리 패스** 추가

---

### 6.3 `src/neowave_core/models.py`

* `WaveNode`에 다음 필드 추가 (앞서 제시한 형태):

```python
sub_scale_analysis: dict | None = None
box_ratio: float | None = None         # 정사각형성 지표
energy_metric: float | None = None     # price * time * volume 기반 에너지
```

* `WaveScenario` (있다면) 구조에:

  * `score: float`
  * `violations: list[str]`
  * `invalidation_levels: dict[str, float]` (예: {"price_above": 42000.0})

---

### 6.4 `src/neowave_web/api.py`

1. **신규 엔드포인트 – `/api/analyze/custom-range`**

   * Input / Output은 §4.2에 정의한 JSON 스펙 준수
   * 내부에서:

     * `fetch_raw_candles(symbol, interval, start_ts, end_ts)`
     * `detect_swings` → `generate_scenarios` 호출
     * 상위 N개 시나리오를 요약하여 반환

       * 기본적으로:

         * Anchor 위치(시간·가격)
         * Top-level pattern (Impulse, Zigzag, Flat, Triangle, Combo, etc.)
         * score, 주요 invalidation 레벨(가격·시간)

2. **기존 `/api/scenarios` (혹은 유사 엔드포인트) 수정**

   * 파라미터로 `max_pivots`, `max_scenarios`, `scale_mode` 등을 받을 수 있도록 확장
   * 응답에 `alternative_scenarios` 필드를 추가해

     * 1차·2차·3차 시나리오를 동시에 내려줄 수 있도록 설계

---

## 7. Devil’s Advocate – 예상 리스크와 설계 상 Trade-off

각하, 이 구조는 이론적으로는 타당하지만, 실제 구현·운영 관점에서 다음과 같은 리스크가 존재합니다. 이에 대한 대안까지 함께 제시드립니다.

1. **Anchor 폭증 & 계산량 증가**

   * 문제:

     * Anchor 후보를 많이 잡을수록 시나리오 수가 기하급수적으로 증가.
   * 대응:

     * `max_pivots`, `max_scenarios`를 **하드 리밋**으로 두고,
     * Score 상위 Anchor만 채택 (예: 상위 3개 Pivot만 사용).
     * 실시간 트레이딩 모듈에는 “최근 N 캔들만 분석” 옵션을 두어 시간 제한.

2. **NEoWave 규칙의 과도한 엄격성 → 시나리오 전멸 위험**

   * NEoWave 규칙은 정량화되어 있어 **“0.618”을 강하게 요구**하지만,
   * 실제 시장에서는 약간의 오버슈트/언더슈트가 빈번.
   * 대응:

     * Hard rule은 꼭 필요한 최소한(예: 2파 ≥ 100% 1파)만 적용,
     * 대부분의 수치는 **±2~5% 허용 오차**를 둔 Soft rule로 두고 점수화.
     * Crypto와 같이 변동성 큰 자산에는

       * B파 0.618 대신 0.65까지 허용 등, 자산별 프로파일링.

3. **Multi-scale 검증의 과도한 제약**

   * Micro 파동이 항상 교과서적 5파/3파 구조를 보이는 것은 아니므로,
   * cross-scale 검증을 너무 엄격하게 두면 **유효한 큰 구조도 계속 invalid**될 수 있습니다.
   * 대응:

     * Micro 레벨 불일치는 **감점 요소**로만 사용하고,
     * Base 구조가 NEoWave 핵심 룰(확장·비례·복잡도 제한)을 잘 만족하면
       → Micro 불일치가 일부 있어도 시나리오를 허용.
     * Base–Micro 간 co-consistency score를 따로 두어, UI에서 “신뢰도 메타 정보”로 보여주는 방향.

4. **정사각형(Time–Price) 기준의 오판 위험**

   * 어떤 추세는 본질적으로 매우 빠르거나(짧은 시간, 큰 가격 변화),
     반대로 매우 지루할 수 있습니다.
   * 단순 Box Ratio 기준만으로 노이즈/유효 파동을 구분하면,
   * **트렌드 초입 또는 막판 blow-off를 노이즈로 오인**할 위험 존재.
   * 대응:

     * Box Ratio는

       * “스윙 병합”의 기준보다는
       * **에너지·비례성 스코어 보조 지표**로 활용.
     * 특히, 거래량·변동성 정보와 결합해

       * “짧지만 거래량·변동성이 폭발한 파동”은 노이즈가 아니라
         중요한 확장 파동 후보로 인정.

---

## 8. 정리

위 사양서 v0.3+는

1. **시작점 선택 로직**을

   * “0번 캔들 맹목적 시작”에서
   * **NEoWave식 Pivot Scoring + Multi-Anchor 탐색**으로 전환하고,

2. **스케일 간 일관성**을

   * Macro/Base/Micro 독립 분석에서
   * **하위 파동 구조로 상위 시나리오를 검증·감점·무효화**하는 구조로 확장하며,

3. **정량 규칙과 사용자 인터랙션**을

   * 첨부 NEoWave 정량 규칙(1/3 비례, 피보나치 retracement, Triangle/Complexity cap, Time–Price Equality 등)을
   * **룰 엔진 + 시나리오 스코어링 + custom-range 인터페이스**로 실제 코드 레벨에 녹여 넣는 방향입니다. 

각하께서 이 문서를 코드 에이전트에 그대로 전달하시면,
현재 `neowave_core / neowave_web`이 “패턴 모양만 비슷한 장난감” 수준에서 벗어나,
**실제 NEoWave 논리에 가까운 정량 분석 엔진**으로 진화할 수 있을 것입니다.
