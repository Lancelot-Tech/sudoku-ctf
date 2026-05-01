"""SUDOKU configuration.

Loads pre-generated puzzles from ``puzzles.json`` (produced at Docker build
time by ``generate_puzzles.py``). The flag is injected at runtime via the
``FLAG`` environment variable and is never stored in the JSON file.
"""

import json
import os

FLAG: str = os.environ["FLAG"]    # crash early if missing — intentional

_PUZZLES_PATH = os.path.join(os.path.dirname(__file__), "..", "puzzles.json")

with open(_PUZZLES_PATH, encoding="utf-8") as _f:
    PUZZLES: list[dict] = json.load(_f)["puzzles"]

SESSION_TTL_SECONDS: int = 60 * 60  # session expires after 1 hour of inactivity
MAX_SESSIONS: int = 500
DEMO_LIMIT: int = 2                 # free demo available for the first N puzzles
