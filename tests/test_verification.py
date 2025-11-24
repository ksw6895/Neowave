import unittest
from datetime import datetime, timedelta
from neowave_core.models import Monowave, WaveNode
from neowave_core.wave_engine import verify_pattern
from neowave_core.rules_db import RULE_DB

class TestVerificationBridge(unittest.TestCase):
    def create_monowave(self, start_idx, end_idx, start_price, end_price, start_time, end_time):
        return Monowave(
            id=start_idx,
            start_idx=start_idx,
            end_idx=end_idx,
            start_time=start_time,
            end_time=end_time,
            start_price=start_price,
            end_price=end_price,
            high_price=max(start_price, end_price),
            low_price=min(start_price, end_price),
            direction='up' if end_price >= start_price else 'down',
            price_change=end_price - start_price,
            abs_price_change=abs(end_price - start_price),
            duration=(end_time - start_time).total_seconds(),
            volume_sum=1000
        )

    def test_verify_impulse_structure(self):
        # Create a Micro structure that forms an Impulse
        # 1: 100 -> 110
        # 2: 110 -> 105
        # 3: 105 -> 125
        # 4: 125 -> 115
        # 5: 115 -> 130
        
        base_time = datetime(2023, 1, 1)
        times = [base_time + timedelta(hours=i) for i in range(6)]
        
        micro_waves = [
            self.create_monowave(0, 1, 100, 110, times[0], times[1]),
            self.create_monowave(1, 2, 110, 105, times[1], times[2]),
            self.create_monowave(2, 3, 105, 125, times[2], times[3]),
            self.create_monowave(3, 4, 125, 115, times[3], times[4]),
            self.create_monowave(4, 5, 115, 130, times[4], times[5]),
        ]
        
        # Macro Node representing the whole move
        macro_node = WaveNode(
            id=999,
            level=1,
            degree_label="Macro",
            start_idx=0,
            end_idx=5,
            start_time=times[0],
            end_time=times[5],
            start_price=100,
            end_price=130,
            high_price=130,
            low_price=100,
            direction='up',
            pattern_type='Impulse',
            children=[]
        )
        
        validation = verify_pattern(macro_node, micro_waves, rule_db=RULE_DB)
        
        self.assertTrue(validation.hard_valid, f"Expected valid impulse, got invalid. Reasons: {validation.violated_hard_rules}")
        self.assertIn("Micro structure confirms Impulse", validation.satisfied_rules)

    def test_verify_fail_mismatch(self):
        # Create a Micro structure that is a Zigzag (3 waves)
        # A: 100 -> 110
        # B: 110 -> 102
        # C: 102 -> 115
        
        base_time = datetime(2023, 1, 1)
        times = [base_time + timedelta(hours=i) for i in range(4)]
        
        micro_waves = [
            self.create_monowave(0, 1, 100, 110, times[0], times[1]),
            self.create_monowave(1, 2, 110, 102, times[1], times[2]),
            self.create_monowave(2, 3, 102, 115, times[2], times[3]),
        ]
        
        # Macro Node claiming it's an Impulse (needs 5)
        macro_node = WaveNode(
            id=999,
            level=1,
            degree_label="Macro",
            start_idx=0,
            end_idx=3,
            start_time=times[0],
            end_time=times[3],
            start_price=100,
            end_price=115,
            high_price=115,
            low_price=100,
            direction='up',
            pattern_type='Impulse', # Expects 5 waves
            children=[]
        )
        
        validation = verify_pattern(macro_node, micro_waves, rule_db=RULE_DB)
        
        self.assertFalse(validation.hard_valid, "Expected validation failure for Impulse on Zigzag data")
        # It might return "Expected Impulse, found Zigzag" OR "found 3 fragments" depending on if it collapsed
        # Since 3 waves form a Zigzag, analyze_market_structure should collapse them into 1 Zigzag node.
        # So we expect "Expected Impulse, found Zigzag"
        
        # Note: analyze_market_structure might return a Zigzag node.
        # Let's check the violated rules content
        self.assertTrue(any("found Zigzag" in r or "found Flat" in r or "found 3 fragments" in r for r in validation.violated_hard_rules), 
                        f"Unexpected violation message: {validation.violated_hard_rules}")

if __name__ == '__main__':
    unittest.main()
