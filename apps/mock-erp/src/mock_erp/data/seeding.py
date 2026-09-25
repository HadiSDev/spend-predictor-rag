"""Deterministic random sources for the generated mock data."""

from __future__ import annotations

import hashlib
import random


def seeded_random(seed: int | str) -> random.Random:
    """A ``random.Random`` seeded from an int, or from a stable digest of a string."""
    if isinstance(seed, str):
        seed = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return random.Random(seed)
