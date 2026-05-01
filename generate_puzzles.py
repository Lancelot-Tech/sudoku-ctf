#!/usr/bin/env python3
"""Pre-generate 300 Sudoku puzzles and save them to ``puzzles.json``.

Puzzle layout:
    - Puzzles 1–297: Regular puzzles (EASY / MEDIUM / HARD), varied symbol sets.
    - Puzzles 298–300: Flag-encoding puzzles — ``row[4]`` of each solution
      concatenates to form the full flag.

Regular puzzles are generated in parallel with :mod:`multiprocessing`.
Flag puzzles are generated sequentially with deterministic seeds.

The flag is read from the ``FLAG`` environment variable (via ``.env``).
"""

import json
import os
import random
import string
import sys
import time
from multiprocessing import Pool, cpu_count

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from app.sudoku import Sudoku  # noqa: E402

FLAG = os.environ["FLAG"]
N_REGULAR = 297
N_TOTAL = 300


# ── Multiprocessing worker (must be at module level for pickling) ──────────────

def _gen_one(args: tuple) -> tuple:
    """Generate one puzzle and return its data alongside diagnostics.

    This function is the multiprocessing worker target.  It must be defined
    at module level so that ``multiprocessing`` can pickle it.

    Args:
        args: ``(puzzle_id, symbols, seed, max_removals, level, hint)``

    Returns:
        ``(puzzle_id, data_dict, given_count, elapsed_seconds)``
    """
    pid, symbols, seed, max_removals, level, hint = args
    t0 = time.time()
    puzzle, solution = Sudoku.generate_puzzle(symbols, seed=seed, max_removals=max_removals)
    given = sum(1 for row in puzzle for cell in row if cell is not None)
    return pid, {
        "id":       pid,
        "level":    level,
        "hint":     hint,
        "symbols":  symbols,
        "puzzle":   puzzle,
        "solution": solution,
    }, given, time.time() - t0


# ── Generator class ────────────────────────────────────────────────────────────

class SudokuPuzzleGenerator:
    """Orchestrates generation of all 300 Sudoku puzzles.

    Call :meth:`run` to generate puzzles and write ``puzzles.json``.
    """

    @staticmethod
    def build_symbol_pool(n: int) -> list[list[str]]:
        """Generate *n* distinct 9-symbol sets covering a wide range of characters.

        Starts with a set of curated fixed symbol sets, then extends with
        sliding windows over ASCII alphabets and random samples until *n*
        distinct sets are available.

        Args:
            n: Number of distinct symbol sets to produce.

        Returns:
            List of *n* symbol lists, each containing 9 unique characters.

        Raises:
            RuntimeError: If *n* distinct sets cannot be generated.
        """
        rng = random.Random(2025)
        seen: set[tuple] = set()
        pool: list[list[str]] = []

        def try_add(s: list[str]) -> bool:
            key = tuple(s)
            if key in seen or len(s) != 9 or len(set(s)) != 9:
                return False
            seen.add(key)
            pool.append(list(s))
            return True

        for s in [
            list("123456789"),
            list("ABCDEFGHI"),
            list("abcdefghi"),
            list("αβγδεζηθι"),
            list("JKLMNOPQR"),
            list("jklmnopqr"),
            list("STUVWXYZ0"),
            ["!", "@", "#", "$", "%", "^", "&", "*", "?"],
            ["♠", "♣", "♥", "♦", "★", "☆", "●", "○", "■"],
            ["π", "Σ", "Δ", "Ω", "λ", "μ", "ψ", "φ", "ξ"],
            ["€", "£", "¥", "©", "®", "™", "§", "¶", "†"],
        ]:
            try_add(s)

        for alpha in [string.ascii_uppercase, string.ascii_lowercase]:
            for i in range(len(alpha) - 8):
                try_add(list(alpha[i: i + 9]))

        greek = "αβγδεζηθικλμνξοπρστ"
        for i in range(len(greek) - 8):
            try_add(list(greek[i: i + 9]))

        char_pools = [
            list(string.ascii_uppercase),
            list(string.ascii_lowercase),
            list(string.ascii_uppercase + string.digits),
            list(string.ascii_lowercase + string.digits),
            list(string.ascii_uppercase + string.ascii_lowercase),
            list(string.ascii_lowercase + "!@#$%^&*?"),
            list(string.ascii_uppercase + "!@#$%^&*?"),
        ]
        attempts = 0
        while len(pool) < n and attempts < n * 50:
            attempts += 1
            try_add(rng.sample(rng.choice(char_pools), 9))

        if len(pool) < n:
            raise RuntimeError(
                f"Could not generate {n} distinct symbol sets (got {len(pool)})."
            )
        return pool[:n]

    @staticmethod
    def difficulty(idx: int) -> tuple[str, int]:
        """Return ``(level, max_removals)`` for the 0-based regular puzzle index.

        Args:
            idx: 0-based index among the 297 regular puzzles.

        Returns:
            A ``(level_string, max_removals)`` pair.
        """
        if idx < 99:
            return "EASY",   30 + (idx % 7)   # 30–36 clues remaining
        if idx < 198:
            return "MEDIUM", 40 + (idx % 9)   # 40–48 clues remaining
        return     "HARD",   50 + (idx % 9)   # 50–58 clues remaining

    @staticmethod
    def hint(symbols: list[str], level: str) -> str:
        """Generate a flavour hint string based on the symbol set and level.

        Args:
            symbols: The 9 symbols used in this puzzle.
            level: Difficulty string (``"EASY"``, ``"MEDIUM"``, or ``"HARD"``).

        Returns:
            A short hint string for display in the UI.
        """
        if all(c.isdigit() for c in symbols):
            return f"[{level}] Numeric Sudoku. Pure logic."
        if all(c.isupper() and c.isascii() for c in symbols):
            return f"[{level}] Uppercase letters. Same rules, different encoding."
        if all(c.islower() and c.isascii() for c in symbols):
            return f"[{level}] Lowercase letters. Automate your solver."
        if all(ord(c) > 127 for c in symbols):
            return f"[{level}] Unicode symbols. Handle UTF-8 carefully."
        return f"[{level}] Mixed symbols. Algorithm beats intuition here."

    @staticmethod
    def build_regular_args(sym_sets: list[list[str]]) -> list[tuple]:
        """Build the argument list for all 297 regular puzzle workers.

        Args:
            sym_sets: Pre-generated symbol sets, one per regular puzzle.

        Returns:
            List of ``(pid, symbols, seed, removals, level, hint)`` tuples.
        """
        args: list[tuple] = []
        gen = SudokuPuzzleGenerator
        for i in range(N_REGULAR):
            pid = i + 1
            level, removals = gen.difficulty(i)
            args.append((pid, sym_sets[i], pid * 31 + 7, removals, level, gen.hint(sym_sets[i], level)))
        return args

    @staticmethod
    def _flag_defs() -> list[tuple]:
        """Derive the 3 flag-encoding puzzle definitions from :data:`FLAG`.

        Uses the band-shift property ``row[4] = [s4,s5,s6,s7,s8,s0,s1,s2,s3]``.
        For each 9-character flag segment the symbol list is derived as
        ``seg[5:] + seg[:5]`` so that ``row[4]`` spells that segment exactly.

        Returns:
            List of ``(pid, symbols, seed, removals, level, hint)`` tuples.

        Raises:
            ValueError: If any flag segment does not contain exactly 9 unique characters.
        """
        hints = [
            "Heterogeneous symbols. The truth is in the middle…",
            "More mixed characters. The middle row never lies.",
            "Final puzzle. Align the central rows of the last 3.",
        ]
        defs = []
        for i in range(3):
            pid = 298 + i
            seg = FLAG[i * 9: (i + 1) * 9]
            if len(seg) != 9 or len(set(seg)) != 9:
                raise ValueError(
                    f"Flag segment {i} ({seg!r}) must contain exactly 9 unique characters."
                )
            defs.append((pid, list(seg[5:] + seg[:5]), 9001 + i, 81, "HARD", hints[i]))
        return defs

    @staticmethod
    def generate_flag_puzzles() -> dict[int, dict]:
        """Generate the 3 flag-encoding puzzles sequentially.

        Verifies that ``row[4]`` of each solution matches the expected flag
        segment before accepting the result.

        Returns:
            Dict mapping puzzle ID (298–300) to its data dict.

        Raises:
            AssertionError: If a generated puzzle's central row does not match
                the expected flag segment.
        """
        results: dict[int, dict] = {}
        print("Generating 3 flag puzzles…")
        for pid, symbols, seed, removals, level, hint in SudokuPuzzleGenerator._flag_defs():
            t0 = time.time()
            print(f"  Puzzle {pid} (seed={seed})…", end="", flush=True)
            puzzle, solution = Sudoku.generate_puzzle(symbols, seed=seed, max_removals=removals)

            offset = pid - 298
            expected = FLAG[offset * 9: (offset + 1) * 9]
            middle = "".join(solution[4])
            assert middle == expected, (
                f"Puzzle {pid}: row[4]={middle!r} ≠ expected={expected!r}"
            )

            given = sum(1 for row in puzzle for cell in row if cell is not None)
            print(f"  {given}/81 given  ({time.time() - t0:.1f}s)")
            results[pid] = {
                "id": pid, "level": level, "hint": hint,
                "symbols": symbols, "puzzle": puzzle, "solution": solution,
            }
        return results

    @staticmethod
    def run() -> None:
        """Generate all 300 puzzles and write ``puzzles.json``.

        Regular puzzles are generated in parallel; flag puzzles are generated
        sequentially to allow deterministic assertion checking.
        """
        print(f"Generating {N_TOTAL} SUDOKU puzzles…\n")

        print("Building symbol sets…", flush=True)
        sym_sets = SudokuPuzzleGenerator.build_symbol_pool(N_REGULAR)
        print(f"  {len(sym_sets)} sets ready.\n")

        regular_args = SudokuPuzzleGenerator.build_regular_args(sym_sets)
        ncpu = max(1, cpu_count() - 1)
        print(f"Generating {N_REGULAR} regular puzzles ({ncpu} workers)…\n")

        t_start = time.time()
        results: dict[int, dict] = {}

        with Pool(ncpu) as pool:
            for pid, data, given, dt in pool.imap_unordered(_gen_one, regular_args, chunksize=4):
                results[pid] = data
                done = len(results)
                pct = done / N_REGULAR * 100
                bar = "█" * (done * 30 // N_REGULAR)
                print(
                    f"\r  [{bar:<30}] {pct:5.1f}%  puzzle {pid:3d} "
                    f"({data['level']:6s})  {given:2d}/81 given  {dt:.1f}s",
                    end="", flush=True,
                )

        print(f"\n\n  ✓ {N_REGULAR} regular puzzles in {time.time() - t_start:.1f}s\n")

        results.update(SudokuPuzzleGenerator.generate_flag_puzzles())

        puzzles = [results[i] for i in range(1, N_TOTAL + 1)]
        out_path = os.path.join(os.path.dirname(__file__), "puzzles.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"puzzles": puzzles}, f, ensure_ascii=False, indent=2)

        reconstructed = "".join("".join(puzzles[i]["solution"][4]) for i in [-3, -2, -1])
        assert reconstructed == FLAG, f"Flag mismatch: {reconstructed!r} ≠ {FLAG!r}"

        print(f"\n{'─' * 50}")
        print(f"Saved   : {out_path}")
        print(f"Total   : {len(puzzles)} puzzles")
        print(f"FLAG    : {FLAG}")
        print("Central rows (puzzles 298–300):")
        for p in puzzles[-3:]:
            print(f"  Puzzle {p['id']} row[4]: {''.join(p['solution'][4])}")
        print(f"  Concatenated: {reconstructed}")
        print("  ✓ Flag verified.")


if __name__ == "__main__":
    SudokuPuzzleGenerator.run()
