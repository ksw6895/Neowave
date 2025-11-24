import unittest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from neowave_core.macro_scanner import MacroScanner
from neowave_core.rules_db import RULE_DB

class TestMacroScanner(unittest.TestCase):
    def setUp(self):
        self.scanner = MacroScanner(rule_db=RULE_DB)
        
    def create_mock_df(self, prices):
        """Create a simple OHLCV dataframe from a list of close prices."""
        dates = [datetime(2023, 1, 1) + timedelta(hours=i) for i in range(len(prices))]
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': prices,
            'low': prices,
            'close': prices,
            'volume': [1000.0] * len(prices)
        })
        return df

    def test_detect_macro_swings_adaptive(self):
        # Create a noisy uptrend: Big moves up, small moves down, with micro noise
        # 100 -> 200 (with 150 dip) -> 180 -> 300
        # We want to catch 100->200->180->300 as the macro moves
        
        prices = [100, 110, 105, 120, 115, 150, 140, 200, # Swing 1 Up to 200
                  190, 195, 180, # Swing 2 Down to 180
                  220, 210, 300] # Swing 3 Up to 300
        
        df = self.create_mock_df(prices)
        
        # Target 3 swings
        swings = self.scanner._detect_macro_swings_adaptive(df, target_count=3)
        
        self.assertTrue(len(swings) >= 3, f"Expected at least 3 swings, got {len(swings)}")
        # Check directions
        self.assertEqual(swings[0].direction, 'up')
        self.assertEqual(swings[1].direction, 'down')
        self.assertEqual(swings[2].direction, 'up')
        
        # Check magnitudes
        self.assertEqual(swings[0].end_price, 200)
        self.assertEqual(swings[1].end_price, 180)
        self.assertEqual(swings[2].end_price, 300)

    def test_scan_impulse_hypothesis(self):
        # Create a clear 5-wave impulse
        # 1: 100 -> 200 (+100)
        # 2: 200 -> 150 (-50, 50% retrace)
        # 3: 150 -> 350 (+200, 2.0x ext)
        # 4: 350 -> 275 (-75, 37.5% retrace)
        # 5: 275 -> 400 (+125)
        
        # We need enough points to trigger monowave detection
        path = [100, 200, 150, 350, 275, 400]
        expanded_path = []
        for i in range(len(path)-1):
            expanded_path.extend(np.linspace(path[i], path[i+1], 10))
            
        df = self.create_mock_df(expanded_path)
        
        scenarios = self.scanner.scan(df, target_wave_count=5)
        
        # Should find at least one Impulse scenario
        impulse_scenarios = [s for s in scenarios if s.root_nodes[0].pattern_type == 'Impulse']
        self.assertTrue(len(impulse_scenarios) > 0, "Failed to identify Impulse")
        
        best = impulse_scenarios[0]
        self.assertEqual(best.root_nodes[0].pattern_subtype, 'TrendingImpulse')

    def test_scan_projection(self):
        # Create 1-2-3 partial impulse
        # 1: 100 -> 200
        # 2: 200 -> 150
        # 3: 150 -> 350
        
        path = [100, 200, 150, 350]
        expanded_path = []
        for i in range(len(path)-1):
            expanded_path.extend(np.linspace(path[i], path[i+1], 10))
            
        df = self.create_mock_df(expanded_path)
        
        scenarios = self.scanner.scan(df, target_wave_count=3)
        
        # Look for Projected Impulse
        projected = [s for s in scenarios if s.root_nodes[-1].pattern_subtype == 'Projected']
        self.assertTrue(len(projected) > 0, "Failed to project impulse")
        
        sc = projected[0]
        # Check phantom nodes
        # Root nodes should contain: [Wave1, Wave2, Wave3, Wave4?, Wave5?] collapsed into one parent?
        # In my implementation, I collapsed them into one parent "Projected Impulse"
        
        parent = sc.root_nodes[-1]
        self.assertEqual(parent.pattern_type, 'Impulse')
        self.assertEqual(parent.pattern_subtype, 'Projected')
        
        # Check children
        children = parent.children
        self.assertEqual(len(children), 5) # 1,2,3 + 4,5
        self.assertEqual(children[3].label, "4?")
        self.assertEqual(children[4].label, "5?")
        
        # Verify projection targets
        # Wave 3 len = 200. Wave 4 retrace 38.2% = 76.4. Target = 350 - 76.4 = 273.6
        self.assertAlmostEqual(children[3].end_price, 273.6, delta=1.0)

if __name__ == '__main__':
    unittest.main()
