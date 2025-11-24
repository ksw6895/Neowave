from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from neowave_core.models import Monowave, PatternValidation, Scenario, WaveNode
from neowave_core.pattern_evaluator import PatternEvaluator
from neowave_core.rules_db import RULE_DB, load_rule_db
from neowave_core.swings import auto_select_timeframe, detect_monowaves_from_df
from neowave_core.wave_engine import (
    PatternMatch,
    find_all_local_patterns,
    wrap_monowaves,
    _new_scenario_id,
    build_wavenode_from_match
)

logger = logging.getLogger(__name__)


@dataclass
class MacroScanner:
    """
    Top-Down scanner that identifies 'Macro' structures first.
    It uses strict NEoWave rules to validate high-level hypotheses
    and projects future wave targets.
    """

    rule_db: dict[str, Any]
    evaluator: PatternEvaluator = field(init=False)

    def __post_init__(self):
        self.evaluator = PatternEvaluator(self.rule_db)

    def scan(self, df: pd.DataFrame, target_wave_count: int = 12) -> list[Scenario]:
        """
        Scan the dataframe for Macro scenarios.
        
        Args:
            df: OHLCV DataFrame.
            target_wave_count: Number of swings to target for the macro view (default 12 for clear major moves).
            
        Returns:
            List of Scenarios with hypotheses and projections.
        """
        # 1. Macro Swing Detection
        # We use a small target_wave_count to force the algorithm to pick a higher timeframe
        # or larger threshold, effectively filtering for "Major Swings".
        try:
            # We wrap the single dataframe in a dict as auto_select_timeframe expects candidates.
            # However, since we might not have multiple timeframes pre-fetched, we can simulate
            # "dynamic thresholding" by just running detection on the provided DF but
            # logically we might want to resample if we had that capability.
            # For now, we rely on the user providing a sufficient window, or we could
            # implement a loop that increases threshold until count is low.
            
            # Simplified approach for this phase: Use the provided DF but filter aggressively?
            # Actually, auto_select_timeframe is designed to pick from candidates.
            # If we only have one DF, we just use it.
            # But to be "Macro", we should perhaps smooth it or use a larger retrace?
            # Let's use a larger retrace threshold for "Macro" scanning if not using multiple TFs.
            
            # Heuristic: Try to find a retrace threshold that gives us ~target_wave_count swings.
            monowaves = self._detect_macro_swings_adaptive(df, target_wave_count)
            
        except ValueError as e:
            logger.warning(f"Macro scan failed to detect swings: {e}")
            return []

        if not monowaves:
            return []

        # Convert to WaveNodes (Level 1 to indicate Macro)
        nodes = wrap_monowaves(monowaves)
        for node in nodes:
            node.level = 1  # Mark as Macro

        # 2. Hypothesis Generation
        # We look for patterns in the macro swings.
        matches = find_all_local_patterns(nodes, self.evaluator)
        
        scenarios = []
        
        # If we found complete patterns, create scenarios for them
        for match in matches:
            # Create a scenario for this match
            # We collapse the matched nodes into a single parent node
            parent_node = build_wavenode_from_match(match)
            
            # The scenario root is this single parent node (plus any surrounding nodes if we wanted context)
            # For now, let's just focus on the identified pattern as the "Macro View"
            
            # We might want to include the 'rest' of the chart if the pattern is only a part of it.
            # But for a "Hypothesis", isolating the pattern is useful.
            
            # Let's construct a scenario where this pattern is the focus.
            # We need to reconstruct the full list of nodes with this one collapsed.
            collapsed_roots = self._collapse_match_in_sequence(nodes, match)
            
            sc = Scenario(
                id=_new_scenario_id(),
                root_nodes=collapsed_roots,
                global_score=match.score, # Start with pattern score
                status="active",
                invalidation_reasons=[]
            )
            scenarios.append(sc)

        # 3. Projection for Incomplete Patterns (The "Sophisticated" Part)
        # If we have a partial pattern (e.g. 3 swings that look like 1-2-3 of Impulse),
        # we should propose it even if it's not "complete" in the standard sense.
        # find_all_local_patterns currently looks for *complete* patterns (5 for impulse, 3 for zigzag).
        # We need a way to detect *partial* patterns.
        
        partial_scenarios = self._scan_partial_patterns(nodes)
        scenarios.extend(partial_scenarios)

        # Sort by score
        scenarios.sort(key=lambda s: s.global_score)
        
        return scenarios

    def _detect_macro_swings_adaptive(self, df: pd.DataFrame, target_count: int) -> list[Monowave]:
        """
        Detect swings using a percentage-based ZigZag algorithm.
        This ignores moves smaller than 'sensitivity' percent of the price.
        We adjust sensitivity to get close to target_count.
        """
        # Sensitivities to try: 1%, 3%, 5%, 10%, 15%, 20%
        sensitivities = [0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
        
        best_swings = []
        best_diff = float('inf')
        
        # Pre-convert to records for speed
        records = df.to_dict('records')
        if not records:
            return []
            
        for sensitivity in sensitivities:
            swings = self._detect_percentage_zigzag(records, sensitivity)
            count = len(swings)
            diff = abs(count - target_count)
            
            if diff < best_diff:
                best_diff = diff
                best_swings = swings
            
            # If we have fewer swings than target, higher sensitivity will only reduce it more (or same)
            # So we can stop if we are already below target? 
            # Higher sensitivity = fewer waves.
            # If count < target, we want MORE waves -> Lower sensitivity.
            # We are iterating Low -> High.
            # So if count < target, we have gone too far (or started too high).
            # Actually, 0.01 (1%) -> Many waves. 0.20 (20%) -> Few waves.
            # So count will decrease.
            # Once count < target, we check if this one is better than previous.
            # If count drops way below target, we stop.
            if count < target_count:
                break
                
        return best_swings

    def _detect_percentage_zigzag(self, bars: list[dict[str, Any]], threshold_pct: float) -> list[Monowave]:
        """
        ZigZag based on absolute percentage change.
        """
        if not bars:
            return []
            
        swings: list[Monowave] = []
        pivot_idx = 0
        pivot_price = bars[0]['close']
        current_dir = None # 'up' or 'down'
        extreme_idx = 0
        extreme_price = pivot_price
        
        # Find first move > threshold
        start_i = 0
        for i in range(1, len(bars)):
            price = bars[i]['close']
            pct_change = abs(price - pivot_price) / pivot_price
            
            if pct_change >= threshold_pct:
                if price > pivot_price:
                    current_dir = 'up'
                    extreme_price = price
                    extreme_idx = i
                else:
                    current_dir = 'down'
                    extreme_price = price
                    extreme_idx = i
                start_i = i + 1
                break
        
        if current_dir is None:
            return [] # No moves > threshold
            
        # Main loop
        for i in range(start_i, len(bars)):
            price = bars[i]['close']
            
            if current_dir == 'up':
                if price > extreme_price:
                    extreme_price = price
                    extreme_idx = i
                else:
                    # Check for reversal
                    retrace_pct = (extreme_price - price) / extreme_price
                    if retrace_pct >= threshold_pct:
                        # Confirmed swing up to extreme
                        wave_id = len(swings)
                        swings.append(Monowave.from_bars(bars, pivot_idx, extreme_idx, wave_id))
                        
                        # New pivot is the extreme (high)
                        pivot_idx = extreme_idx
                        pivot_price = extreme_price
                        
                        # New direction is down
                        current_dir = 'down'
                        extreme_price = price
                        extreme_idx = i
            else: # down
                if price < extreme_price:
                    extreme_price = price
                    extreme_idx = i
                else:
                    # Check for reversal
                    retrace_pct = (price - extreme_price) / extreme_price
                    if retrace_pct >= threshold_pct:
                        # Confirmed swing down to extreme
                        wave_id = len(swings)
                        swings.append(Monowave.from_bars(bars, pivot_idx, extreme_idx, wave_id))
                        
                        # New pivot is the extreme (low)
                        pivot_idx = extreme_idx
                        pivot_price = extreme_price
                        
                        # New direction is up
                        current_dir = 'up'
                        extreme_price = price
                        extreme_idx = i
                        
        # Final leg
        if pivot_idx != len(bars) - 1:
            # Add the last leg from pivot to end (or extreme?)
            # Usually to the last extreme or the last bar?
            # ZigZag usually connects to the last bar if it extends the trend, 
            # or if the current incomplete leg is significant.
            # Let's just connect to the last bar for continuity.
            wave_id = len(swings)
            swings.append(Monowave.from_bars(bars, pivot_idx, len(bars)-1, wave_id))
            
        return swings

    def _collapse_match_in_sequence(self, nodes: list[WaveNode], match: PatternMatch) -> list[WaveNode]:
        """
        Returns a new list of nodes where the matched segment is replaced by a single parent node.
        """
        new_nodes = []
        i = 0
        while i < len(nodes):
            if nodes[i].start_idx == match.start_index:
                # This is the start of the match
                parent = build_wavenode_from_match(match)
                new_nodes.append(parent)
                # Skip to end of match
                # match.end_index is the end_idx of the last node in match
                # We need to find which node in 'nodes' corresponds to that.
                # The nodes list is sequential.
                # match.wave_nodes contains the nodes.
                count = len(match.wave_nodes)
                i += count
            else:
                new_nodes.append(nodes[i])
                i += 1
        return new_nodes

    def _scan_partial_patterns(self, nodes: list[WaveNode]) -> list[Scenario]:
        """
        Identify potential incomplete patterns (e.g. Impulse 1-2-3) and project them.
        """
        scenarios = []
        n = len(nodes)
        
        # Check for Impulse 1-2-3 (needs 3 nodes)
        # Conditions: 
        # 1. Alternating
        # 2. Wave 2 retrace < 100% (Hard rule)
        # 3. Wave 3 not shortest? (Can't know for sure yet, but if 3 < 1, 5 must be shorter than 3? No)
        #    If 3 is much shorter than 1, it's unlikely to be an impulse unless 5 extends.
        #    But standard rule: 3 is not shortest.
        #    If 3 > 1, good candidate.
        
        for i in range(n - 2):
            window = nodes[i : i + 3]
            # Check basic alternating
            if window[0].direction == window[1].direction:
                continue
            
            # Try to fit as 1-2-3
            # We use a temporary evaluator or manual check?
            # Let's use manual check for speed and flexibility for "Partial"
            
            w1, w2, w3 = window
            
            # Calculate metrics
            w1_len = w1.abs_price_change
            w2_len = w2.abs_price_change
            w3_len = w3.abs_price_change
            
            if w1_len == 0: continue
            
            w2_ratio = w2_len / w1_len
            
            # Rule: Wave 2 < 100% of Wave 1
            if w2_ratio >= 1.0:
                continue # Invalid Impulse start
            
            # Rule: Wave 3 usually > Wave 2
            if w3_len <= w2_len:
                # Weak wave 3, unlikely impulse start (unless diagonal)
                pass 
            
            # If it looks like 1-2-3, project 4 and 5
            # Create a "Projected Impulse" scenario
            
            # We need to create phantom nodes for 4 and 5
            projected_nodes = self._project_impulse_4_5(w1, w2, w3)
            
            # Combine real + phantom
            full_pattern_nodes = list(window) + projected_nodes
            
            # Create a parent node for this projected impulse
            # We mark it as "Projected" in subtype or label
            parent = WaveNode(
                id=-1, # Placeholder
                level=w1.level + 1,
                degree_label="Macro",
                start_idx=w1.start_idx,
                end_idx=projected_nodes[-1].end_idx, # Projected end
                start_time=w1.start_time,
                end_time=projected_nodes[-1].end_time,
                start_price=w1.start_price,
                end_price=projected_nodes[-1].end_price,
                high_price=max(n.high_price for n in full_pattern_nodes),
                low_price=min(n.low_price for n in full_pattern_nodes),
                direction=w1.direction, # Impulse direction same as Wave 1
                children=full_pattern_nodes,
                pattern_type="Impulse",
                pattern_subtype="Projected",
                score=0.5, # Lower score for projection
                label="Projected Impulse"
            )
            
            # Reconstruct root list
            # Preceding nodes + Parent + Following nodes (none, since we consumed up to i+3, 
            # but wait, if there are more nodes after i+3, they conflict with projection?
            # If we are at the END of the data, projection makes sense.
            # If we are in the middle, projection is only valid if subsequent price action fits.
            # For "Forecast", we usually care about the *latest* waves.
            
            if i + 3 == n:
                # We are at the edge. Projection is valid.
                roots = nodes[:i] + [parent]
                sc = Scenario(
                    id=_new_scenario_id(),
                    root_nodes=roots,
                    global_score=0.5,
                    status="active",
                    invalidation_reasons=["Projected scenario"]
                )
                scenarios.append(sc)
                
        return scenarios

    def _project_impulse_4_5(self, w1: WaveNode, w2: WaveNode, w3: WaveNode) -> list[WaveNode]:
        """
        Generate phantom Wave 4 and Wave 5 nodes based on 1-2-3.
        """
        # Simple Fibonacci projection
        # Wave 4: Typically 38.2% retrace of Wave 3
        # Wave 5: Typically equal to Wave 1 (or 0.618 of Wave 1+3)
        
        w3_end_price = w3.end_price
        w3_len = w3.abs_price_change
        direction = w3.direction # 'up' or 'down'
        
        # Wave 4 Target
        retrace_4 = 0.382 * w3_len
        if direction == 'up':
            w4_end_price = w3_end_price - retrace_4
            w4_dir = 'down'
        else:
            w4_end_price = w3_end_price + retrace_4
            w4_dir = 'up'
            
        # Wave 5 Target
        # Equality with Wave 1
        w1_len = w1.abs_price_change
        w5_len = w1_len
        
        if direction == 'up':
            w5_end_price = w4_end_price + w5_len
            w5_dir = 'up'
        else:
            w5_end_price = w4_end_price - w5_len
            w5_dir = 'down'
            
        # Create Phantom Nodes
        # Time projection: Wave 4 time = Wave 2 time? Wave 5 time = Wave 1 time?
        # Just add some dummy duration or estimate based on averages
        avg_duration = (w1.duration + w2.duration + w3.duration) / 3
        
        # Timestamps are tricky without a calendar, just add seconds if datetime
        # or we assume equal spacing for visualization
        last_time = w3.end_time
        w4_time = last_time + pd.Timedelta(seconds=avg_duration)
        w5_time = w4_time + pd.Timedelta(seconds=avg_duration)
        
        w4 = WaveNode(
            id=-2,
            level=w1.level,
            degree_label="Projected",
            start_idx=w3.end_idx,
            end_idx=w3.end_idx + 10, # Dummy
            start_time=last_time,
            end_time=w4_time,
            start_price=w3.end_price,
            end_price=w4_end_price,
            high_price=max(w3.end_price, w4_end_price),
            low_price=min(w3.end_price, w4_end_price),
            direction=w4_dir,
            children=[],
            pattern_type="Monowave",
            label="4?"
        )
        
        w5 = WaveNode(
            id=-3,
            level=w1.level,
            degree_label="Projected",
            start_idx=w4.end_idx,
            end_idx=w4.end_idx + 10,
            start_time=w4_time,
            end_time=w5_time,
            start_price=w4.end_price,
            end_price=w5_end_price,
            high_price=max(w4.end_price, w5_end_price),
            low_price=min(w4.end_price, w5_end_price),
            direction=w5_dir,
            children=[],
            pattern_type="Monowave",
            label="5?"
        )
        
        return [w4, w5]
