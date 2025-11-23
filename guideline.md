````markdown
# NEoWave Elliott Wave Scenario Program – Coding Agent Guide

> This document is a high-level implementation guideline for a coding agent.
> You will implement a **NEoWave/Elliott Wave–based scenario suggestion program** in Python,
> using FMP API OHLCV data and a pre-defined set of NEoWave rules.

---

## 1. Project Overview

### 1.1. Purpose

Implement a **deterministic, rule-based program** (no LLM at runtime) that:

1. Loads OHLCV data (initially BTCUSD, 1-hour candles) from the FMP API.
2. Converts raw price data into **swings (mono-waves)**.
3. Applies **NEoWave rules** (price, time, and basic volume constraints) to:
   - Detect candidate Elliott/NEoWave patterns (Phase 1: Impulse, Zigzag, Flat).
   - Score the plausibility of each pattern.
4. Generates **human-readable scenario suggestions** such as:
   - “This structure is likely a 5-wave impulse up; a corrective ABC down move is probable.”
   - “We are in wave 3 of an impulse; waves 4 and 5 are likely yet to come.”
5. Outputs:
   - A summary of top scenarios.
   - For each scenario: invalidation levels and expectations for the next wave.

You should **not** “invent” new trading logic on your own.  
Your job is to translate the existing NEoWave rule specifications into clean, testable Python code.

---

## 2. Reference Documents

All conceptual and rule-level details are defined in the following project documents:

- `docs/01_neowave_overview_and_scope.md`  
  – Conceptual summary of NEoWave and the scope of this project.

- `docs/02_neowave_pattern_rules_table.md`  
  – Pattern-by-pattern rule tables (Impulse, Zigzag, Flat, etc.):  
    price ratios, time ratios, volume tendencies, invalidation conditions.

- `rules/neowave_rules.json`  
  – Machine-readable NEoWave rule database for patterns
    (this is the **single source of truth** for rule parameters).

- `docs/04_neowave_python_architecture.md`  
  – Proposed Python module structure, class design, and function signatures.

- `docs/05_neowave_validation_and_limitations.md`  
  – Known ambiguities, limitations, and validation strategy.

Original theoretical basis (for context, not for you to parse directly):

- `NEoWave 이론 정량화 원본 PDF`  
  – `/mnt/data/NEoWave 이론 정량화.pdf`

When in doubt, **follow the JSON rules first**, then refer back to the markdown docs if needed.

---

## 3. Scope for Phase 1 (Initial Implementation)

Phase 1 focuses on a **minimal viable, but structurally correct** NEoWave engine:

1. **Market & timeframe (fixed for now)**
   - Symbol: `BTCUSD` (spot or closest equivalent provided by FMP)
   - Timeframe: 1-hour (H1) candles

2. **Patterns to support (detection & scoring)**
   - 5-wave **Impulse**
   - 3-wave **Zigzag** correction
   - 3-wave **Flat** correction

3. **Core components**
   - Data loading from FMP
   - Swing (mono-wave) detection and normalization
   - Pattern validation functions based on `neowave_rules.json`
   - Scenario generation and ranking
   - CLI interface for running the analysis

4. **Non-goals in Phase 1** (you may create stubs but do not fully implement yet):
   - Triangles (contracting/expanding/neutral)
   - Complex corrections (Double/Triple Three, etc.)
   - Diametric, Symmetrical patterns
   - Multi-timeframe integration
   - Live/streaming data

All code should be written so that **later phases can extend it cleanly**, without rewriting the core.

---

## 4. Technical Requirements

### 4.1. Language & Environment

- **Language**: Python 3.10+ (assume 3.11 if a specific version is needed).
- Recommended libraries:
  - `pandas` (for time series / OHLCV operations)
  - `numpy`
  - Standard library modules (`typing`, `dataclasses`, `enum`, `logging`, `json`, etc.)

No heavy ML/AI libraries are required or desired at runtime.

### 4.2. Coding Style

- Use **type hints** extensively (`from __future__ import annotations` if needed).
- Use clear **docstrings** (Google or NumPy style is fine, but be consistent).
- Prefer small, composable functions over monolithic logic.
- Avoid hard-coded magic numbers; read pattern parameters from `neowave_rules.json`.
- Add comments where rules may be ambiguous or where future tuning is expected.

### 4.3. Configuration

- API key:
  - Read FMP API key from environment:
    - `FMP_API_KEY`
- Basic configuration (e.g. symbol, timeframe, lookback length) can be:
  - Provided via command-line arguments, or
  - Defined in a simple `config.py` / `.env` file (but keep it minimal).

---

## 5. Recommended Repository Structure

You may assume or create the following high-level layout:

```text
/
├─ README.md
├─ docs/
│  ├─ 01_neowave_overview_and_scope.md
│  ├─ 02_neowave_pattern_rules_table.md
│  ├─ 04_neowave_python_architecture.md
│  └─ 05_neowave_validation_and_limitations.md
├─ rules/
│  └─ neowave_rules.json
├─ src/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ data_loader.py
│  ├─ swings.py
│  ├─ patterns/
│  │  ├─ __init__.py
│  │  ├─ impulse.py
│  │  ├─ zigzag.py
│  │  └─ flat.py
│  ├─ scenarios.py
│  └─ cli.py
└─ tests/
   ├─ test_swings.py
   ├─ test_impulse.py
   ├─ test_zigzag.py
   ├─ test_flat.py
   └─ test_scenarios.py
````

You may adjust file names slightly if needed, but keep the overall modular separation.

---

## 6. Detailed Implementation Tasks

### 6.1. Data Loader (`src/data_loader.py`)

**Goal:** Provide a simple interface to fetch OHLCV data from FMP and return as a `pandas.DataFrame`.

Requirements:

* Implement a function such as:

  ```python
  def fetch_ohlcv(
      symbol: str,
      interval: str = "1hour",
      limit: int = 1000
  ) -> pd.DataFrame:
      """
      Fetch OHLCV data (Open, High, Low, Close, Volume) for the given symbol and interval
      from the FMP API and return it as a DataFrame indexed by timestamp.
      """
  ```

* DataFrame columns (at minimum):

  * `timestamp` (as index or column, UTC)
  * `open`, `high`, `low`, `close`
  * `volume`

* Handle HTTP/API errors robustly:

  * Raise clear exceptions (e.g., `RuntimeError` with a meaningful message).
  * Do **not** silently continue on errors.

* The function should be deterministic and side-effect-free (beyond API calls).

### 6.2. Swing Detection (`src/swings.py`)

**Goal:** Convert OHLCV candles into a sequence of **swings (mono-waves)** that approximate NEoWave’s concept of price movement.

Requirements:

* Define a `Swing` data structure, for example:

  ```python
  from dataclasses import dataclass
  from enum import Enum
  from datetime import datetime

  class Direction(Enum):
      UP = "up"
      DOWN = "down"

  @dataclass
  class Swing:
      start_time: datetime
      end_time: datetime
      start_price: float
      end_price: float
      direction: Direction
      high: float
      low: float
      duration: float  # in seconds or hours
  ```

* Implement a function such as:

  ```python
  def detect_swings(
      df: pd.DataFrame,
      price_threshold_pct: float
  ) -> list[Swing]:
      """
      Detect swings from OHLCV data using a simple threshold-based algorithm.
      A new swing is created when price reverses by at least `price_threshold_pct`
      from the previous extreme.
      """
  ```

* Implement **normalization/merging** according to NEoWave’s “Rule of Similarity”:

  * Adjacent swings that are too small (e.g., < ~33% of neighbors) may be merged.
  * The exact threshold and behavior should be taken from the markdown docs
    and/or `neowave_rules.json` where specified.

* Aim for the number of swings in view to be manageable (e.g., **30–60 swings** on the chart),
  as suggested in the NEoWave guidelines.

### 6.3. Pattern Rules Layer (`rules/neowave_rules.json`)

**Goal:** Treat `neowave_rules.json` as the **canonical** source for numeric parameters.

* Define a small helper in Python to load and access rules, e.g.:

  ```python
  import json
  from pathlib import Path
  from typing import Any

  def load_rules(path: str | Path = "rules/neowave_rules.json") -> dict[str, Any]:
      with open(path, "r", encoding="utf-8") as f:
          return json.load(f)
  ```

* Each pattern module (`impulse.py`, `zigzag.py`, `flat.py`) should:

  * Load or receive the relevant subset of rules via function arguments.
  * Avoid duplicating numeric constants inside code.

### 6.4. Pattern Detection Modules (`src/patterns/*.py`)

**Goal:** For each pattern type, implement a deterministic check function that:

1. Accepts a list of **swings** (fixed length, e.g., 3 or 5).
2. Evaluates NEoWave constraints (price/time, basic volume if available).
3. Returns a **scored result** (e.g., valid/invalid + score or error count).

#### 6.4.1. Impulse (`patterns/impulse.py`)

* Implement a function like:

  ```python
  from typing import Sequence
  from .common_types import PatternCheckResult  # You may define this in a shared module

  def is_impulse(
      swings: Sequence[Swing],
      rules: dict
  ) -> PatternCheckResult:
      """
      Check if the given 5 swings form a valid NEoWave impulse pattern.
      Uses price and time rules from `rules`.
      """
  ```

* Use NEoWave rule tables to encode:

  * 5-wave structure (1, 2, 3, 4, 5).
  * Relative lengths (e.g., wave 3 not the shortest, corrective nature of 2 and 4).
  * Overlap rules (e.g., wave 4 not entering the price territory of wave 1, unless
    specific exceptions like terminal impulses later).
  * Time proportionality constraints, as defined in rules.

* `PatternCheckResult` can contain:

  * `is_valid: bool`
  * `score: float` (e.g., 0–1 or a penalty-based score)
  * `violations: list[str]` (optional, human-readable descriptions)

#### 6.4.2. Zigzag (`patterns/zigzag.py`)

* Implement a function like:

  ```python
  def is_zigzag(
      swings: Sequence[Swing],
      rules: dict
  ) -> PatternCheckResult:
      """
      Check if the given 3 swings (A, B, C) form a Zigzag.
      """
  ```

* Use NEoWave rules to check:

  * A and C are impulsive in direction of trend.
  * B is corrective and does not retrace “too much” (rule-defined).
  * Typical retracement and extension relationships between A and C.

#### 6.4.3. Flat (`patterns/flat.py`)

* Implement a function like:

  ```python
  def is_flat(
      swings: Sequence[Swing],
      rules: dict
  ) -> PatternCheckResult:
      """
      Check if the given 3 swings (A, B, C) form a Flat correction.
      """
  ```

* Check:

  * B retraces a large portion of A (often near or beyond 100% in some variants).
  * C is a move opposite to B, with constraints on extensions and overlaps.
  * Use the appropriate NEoWave flat variants as per the rules JSON.

> **Important:** In Phase 1, do **not** attempt to fully classify sub-types (e.g., expanded vs running flat) unless already well-defined in the rules JSON.
> It is acceptable to have a single “Flat” classification with a score reflecting how typical it is.

### 6.5. Scenario Generation (`src/scenarios.py`)

**Goal:** From a sequence of swings, generate and rank possible NEoWave scenarios.

Requirements:

* Given a list of swings (e.g., from the last N candles):

  1. Enumerate candidate segments of size:

     * 5 swings (for impulse tests).
     * 3 swings (for zigzag/flat tests).

  2. For each segment:

     * Run the relevant pattern checks.
     * Collect pattern type + score + location (indices / time window).

  3. Aggregate into scenarios such as:

     * “The last 5 swings form an upward impulse; the market is likely in wave 5 completed.”
     * “The last 3 swings are best explained as a zigzag correction.”

* Implement a central function such as:

  ```python
  from typing import Sequence

  def generate_scenarios(
      swings: Sequence[Swing],
      rules: dict,
      max_scenarios: int = 5
  ) -> list[dict]:
      """
      Analyze recent swings and return a list of top scenario dictionaries.
      Each scenario includes:
        - pattern_type (e.g., 'impulse_up', 'zigzag_down', 'flat_sideways')
        - score
        - swing_indices or time range
        - textual_summary
        - invalidation_levels (price and/or time)
      """
  ```

* `textual_summary` should be a concise, deterministic string built from
  pattern information (no LLM at runtime).

* `invalidation_levels`:

  * Use NEoWave rules to determine price levels that would invalidate
    the pattern (e.g., “if price closes above X, this scenario is invalid”).

### 6.6. CLI Entry Point (`src/cli.py`)

**Goal:** Provide a simple command-line interface to run the analysis.

* A command such as:

  ```bash
  python -m src.cli --symbol BTCUSD --interval 1hour --lookback 500
  ```

* Expected behavior:

  1. Fetch OHLCV data via `data_loader.fetch_ohlcv`.
  2. Compute swings using `swings.detect_swings`.
  3. Load rules from `neowave_rules.json`.
  4. Generate scenarios using `scenarios.generate_scenarios`.
  5. Print a **ranked list of scenarios** in a human-readable format, for example:

     ```text
     Scenario 1 (score: 0.92)
       Pattern: impulse_up
       Time range: 2025-01-01 12:00 – 2025-01-03 08:00
       Summary: Upward 5-wave impulse may be complete; corrective ABC down move likely.
       Invalidation: Close below 39,800 or above 42,500.

     Scenario 2 (score: 0.78)
       Pattern: zigzag_down
       ...
     ```

* Return proper exit codes on failure (e.g., `1` on fatal errors).

---

## 7. Testing & Validation

### 7.1. Unit Tests

* For each module (`swings`, `impulse`, `zigzag`, `flat`, `scenarios`),
  create tests in the `tests/` directory.

* Where possible, construct **synthetic price series** where the expected pattern is known
  (e.g., a textbook 5-wave impulse up) and verify:

  * `is_impulse` returns `is_valid=True` with high score.
  * Invalid structures return `is_valid=False` or low score.

* Keep tests simple but explicit; they are crucial for later refactoring.

### 7.2. Logging & Debug

* Integrate `logging` for key steps:

  * Number of swings detected.
  * Pattern check results (optionally in debug mode).
  * Selected top scenarios.

* Allow log level control via environment or CLI flag (e.g., `--debug`).

---

## 8. Handling Ambiguities and Limitations

When rules are ambiguous or conflict:

1. **Do not guess silently.**
2. Implement the most conservative, straightforward interpretation.
3. Add a `TODO` comment in the code referencing:

   * The relevant section in `docs/05_neowave_validation_and_limitations.md`.
   * A brief explanation of your assumption.

Example:

```python
# TODO: Ambiguity in time ratio for wave 4 vs wave 2 (see docs/05_neowave_validation_and_limitations.md).
# For now, we enforce only the minimum duration constraint from rules['impulse']['wave4']['min_duration_ratio'].
```

This makes future tuning and discussions significantly easier.

---

## 9. Future Extensions (Phase 2+)

You may prepare **stubs** (but not full logic) for:

* Additional patterns modules:

  * `triangle.py`
  * `complex.py` (Double/Triple Three)
  * `diametric.py`, `symmetrical.py`

* Multi-timeframe analysis:

  * Combine signals from, e.g., 15m / 1h / 4h.

* Scenario persistence and visualization:

  * Optional later: export scenarios to JSON for a front-end visualization.

Stubs should be clearly marked and not interfere with Phase 1 functionality.

---

## 10. Summary of Your Role

As the coding agent, your priorities are:

1. **Faithfulness to NEoWave rules**
   – Use `neowave_rules.json` and the docs as the objective reference.

2. **Clean, modular Python implementation**
   – Make it easy to extend, debug, and test.

3. **Deterministic scenario suggestions**
   – No randomness; same inputs should always yield the same outputs.

4. **Clear documentation and tests**
   – So that a human researcher can inspect and refine the system later.

If any requirement in this guide conflicts with the rule documents, prefer the **rules JSON + markdown docs**
and leave a `TODO` note explaining the conflict.

```
```
