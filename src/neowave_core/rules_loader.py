from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_rules(path: str | Path = "rules/neowave_rules.json") -> dict[str, Any]:
    """Load NEoWave rule definitions from JSON."""
    rules_path = Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"Rules file not found: {rules_path}")
    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
