from neowave_core.patterns.complex_corrections import is_double_three, is_triple_three
from neowave_core.patterns.flat import is_flat
from neowave_core.patterns.impulse import is_impulse
from neowave_core.patterns.terminal_impulse import is_terminal_impulse
from neowave_core.patterns.triangle import is_triangle
from neowave_core.patterns.zigzag import is_zigzag

__all__ = [
    "is_impulse",
    "is_terminal_impulse",
    "is_zigzag",
    "is_flat",
    "is_triangle",
    "is_double_three",
    "is_triple_three",
]
