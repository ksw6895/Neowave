# NEoWave Engine Upgrade Guideline: From Theory to Trading Utility

## 1. Current Status & Problem Definition

### The "Blind Compliance" Trap
The current implementation (`wave_engine.py`) faithfully follows NEoWave rules (Similarity, Balance, Pattern definitions) using a **Bottom-Up** approach:
1.  Detects smallest Monowaves.
2.  Tries to merge them into small patterns (Micro-impulses, Micro-zigzags).
3.  Recursively builds larger structures.

**Why this fails for trading:**
*   **Noise Sensitivity**: Small monowaves are often noisy. If the bottom-up parser misinterprets one small noise spike, the entire higher-degree count can fail or become distorted.
*   **Missing the "Big Picture"**: Traders trade the *Macro* and *Base* trends. The current engine might find a technically valid "Triple Three" in a 5-minute chart but miss the obvious "Wave 3" on the 4-hour chart because of a minor sub-wave violation.
*   **Lack of Predictive Value**: It tells you "what happened" (labeling history) but struggles to propose "what will happen" (Scenario Generation) because it's too busy fitting past data into strict boxes.

## 2. The Core Shift: Hybrid Top-Down Architecture

To make the program useful, we must invert the primary flow. **Find the Wave, then Count the Sub-waves.**

### 2.1. Top-Down Hypothesis Generation (The "Trader's Eye")
Instead of starting with Monowaves, start with **Major Swings** (Macro Degree).

*   **Algorithm**:
    1.  Use a ZigZag algorithm with a much larger deviation (e.g., 5-10% or ATR-based dynamic threshold) to identify "Major Pivots".
    2.  Treat these Major Swings as the *candidate* waves (e.g., "This large up-swing is potentially Wave 3 or Wave C").
    3.  **Generate Hypotheses**: Based on the sequence of Major Swings, generate high-level scenarios.
        *   *Scenario A*: Bullish Impulse (We are in Wave 3).
        *   *Scenario B*: Large Zigzag (We are in Wave C).

### 2.2. Recursive Verification (The "Analyst's Check")
Once a Hypothesis is formed (e.g., "This is Wave 3"), **drill down** to verify it.

*   **Verification Logic**:
    *   "If this is Wave 3, it MUST subdivide into 5 smaller waves."
    *   Fetch the lower-timeframe data (or smaller swings) *specifically for that segment*.
    *   Run the `PatternEvaluator` on that specific segment to see if a valid 5-wave count exists.
    *   **Soft Validation**: If the sub-waves are messy but the Macro structure is perfect (Price/Time ratio, Volume), penalize the score but *do not discard* the scenario. This mimics a human trader saying "The sub-count is ugly, but the daily trend is clearly impulsive."

## 3. Practical Trading Features

### 3.1. Scenario Scoring & Ranking
Not all valid counts are equal. Rank them by **Trading Probability**, not just "Rule Compliance".
*   **Trend Alignment**: Scenarios aligned with the higher-degree trend get a score boost.
*   **Setup Quality**: A "Wave 4 nearing completion" is a high-value setup. A "Middle of Wave 3" is less actionable (chasing).
*   **Clarity**: Scenarios with clear, distinct swings are preferred over "complex correction" soup.

### 3.2. "Incomplete" Pattern Recognition
The current engine looks for *completed* patterns. A trading engine must recognize *forming* patterns.
*   **Projected Path**: If we have waves 1, 2, and 3, the engine should project the likely path of Wave 4 and 5.
*   **Invalidation Levels (Stop Loss)**: For every scenario, calculate the exact price level that kills it.
    *   *Example*: "If this is Wave 2, it cannot go below Start of Wave 1 (Price X)." -> **Stop Loss = Price X - buffer**.

### 3.3. Dynamic "View Levels"
Discard the rigid "Macro/Base/Micro" buttons.
*   **Smart Zoom**: When the user looks at the chart, automatically select the Wave Degree that fits the screen.
*   **Drill-Down UI**: Click on a wave to "open" it and see its sub-waves.

## 4. Implementation Roadmap

### Phase 1: The Macro Scanner (New Component)
*   Create `MacroScanner` class.
*   Implement `detect_major_swings(df, sensitivity='low')`.
*   Implement `generate_macro_hypotheses(major_swings)` -> List[ScenarioStub].
    *   *Goal*: Identify potential Impulses and Zigzags on the Daily/4H timeframe without looking at sub-waves yet.

### Phase 2: The Verification Bridge
*   Connect `MacroScanner` to the existing `wave_engine.py`.
*   Modify `analyze_market_structure` to accept a `target_segment` and `expected_pattern`.
    *   *New Function*: `verify_pattern(segment_data, expected_type='Impulse') -> ValidationResult`.
*   This allows the Top-Down engine to "ask" the Bottom-Up engine: "Does this chunk look like an Impulse?"

### Phase 3: Scenario Management & UI
*   Update `Scenario` model to include:
    *   `probability`: Estimated % chance.
    *   `next_move_prediction`: "Up to 50k".
    *   `invalidation_price`: "Below 42k".
*   Build the API to serve these "Actionable Scenarios" to the frontend.

## 5. Summary of Changes

| Feature | Current (`wave_engine.py`) | Proposed Upgrade |
| :--- | :--- | :--- |
| **Direction** | Bottom-Up (Small to Large) | **Top-Down (Large to Small)** |
| **Focus** | Strict Rule Compliance | **Trading Utility & Probability** |
| **Handling Noise** | Fails / Creates Complex Counts | **Filters / Soft Penalties** |
| **Output** | Labeled Chart | **Trade Setups & Invalidation Levels** |
| **Verification** | Implicit (by merging) | **Explicit (Drill-down check)** |

This approach respects the existing `neowave_core` logic (using it as a verification tool) but wraps it in a new "Trader" layer that prioritizes usability and robustness.
