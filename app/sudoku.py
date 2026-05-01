"""Pure Sudoku logic — stateless and side-effect free.

Supports 9×9 grids with arbitrary single-character symbol sets (digits,
letters, Unicode, etc.). Empty cells are represented as ``None``.
Internally, symbols are mapped to integers 1–9 for efficient backtracking.
"""

import random
from typing import Optional


class Sudoku:
    """Stateless utilities for 9×9 Sudoku grids with arbitrary symbol sets.

    All methods are static; the class groups related puzzle operations under a
    common namespace.  Empty cells are represented as ``None``.  Internally,
    symbols are mapped to integers 1–9 for efficient backtracking.
    """

    # ── Solved-grid generation ─────────────────────────────────────────────────

    @staticmethod
    def band_solved(symbols: list[str]) -> list[list[str]]:
        """Generate a valid 9×9 solved grid using the band-shift pattern.

        Guarantees a valid Sudoku for any set of 9 unique symbols without any
        search.  Row *i* is constructed as::

            row[i][j] = symbols[(j + offset_i) % 9]
            offset_i  = (i % 3) * 3 + (i // 3)

        In particular, ``row[4]`` (offset 4) equals::

            [s4, s5, s6, s7, s8, s0, s1, s2, s3]

        This property is exploited by the flag-encoding puzzles.

        Args:
            symbols: Exactly 9 unique symbols used to fill the grid.

        Returns:
            A 9×9 list of lists containing the solved grid.

        Raises:
            ValueError: If *symbols* does not contain exactly 9 unique elements.
        """
        if len(symbols) != 9 or len(set(symbols)) != 9:
            raise ValueError("Exactly 9 unique symbols are required.")
        return [
            [symbols[(j + (i % 3) * 3 + (i // 3)) % 9] for j in range(9)]
            for i in range(9)
        ]

    # ── Index conversion helpers ───────────────────────────────────────────────

    @staticmethod
    def _sym_to_idx(symbols: list[str]) -> dict[str, int]:
        """Return a symbol → 1-based integer mapping.

        Args:
            symbols: Ordered list of 9 unique symbols.

        Returns:
            Dict mapping each symbol to its 1-based index.
        """
        return {s: i + 1 for i, s in enumerate(symbols)}

    @staticmethod
    def _to_idx(grid: list[list], s2i: dict[str, int]) -> list[list[int]]:
        """Convert a symbol grid to an integer grid (0 = empty).

        Args:
            grid: 9×9 grid of symbols or ``None`` for empty cells.
            s2i: Symbol-to-index mapping from :meth:`_sym_to_idx`.

        Returns:
            9×9 grid of integers (1–9) with 0 for empty cells.
        """
        return [[s2i[c] if c is not None else 0 for c in row] for row in grid]

    @staticmethod
    def _from_idx(grid: list[list[int]], symbols: list[str]) -> list[list]:
        """Convert an integer grid back to a symbol grid.

        Args:
            grid: 9×9 grid of integers (1–9, 0 = empty).
            symbols: Ordered list of 9 symbols.

        Returns:
            9×9 grid of symbols with ``None`` for empty cells.
        """
        idx_to_sym = {i + 1: s for i, s in enumerate(symbols)}
        return [[idx_to_sym[v] if v != 0 else None for v in row] for row in grid]

    # ── Backtracking helpers ───────────────────────────────────────────────────

    @staticmethod
    def _box_origin(r: int, c: int) -> tuple[int, int]:
        """Return the top-left corner ``(row, col)`` of the 3×3 box containing ``(r, c)``.

        Args:
            r: Row index (0–8).
            c: Column index (0–8).

        Returns:
            ``(br, bc)`` where ``br`` and ``bc`` are multiples of 3.
        """
        return (r // 3) * 3, (c // 3) * 3

    @staticmethod
    def _valid_placement(g: list[list[int]], r: int, c: int, v: int) -> bool:
        """Return whether placing integer *v* at ``(r, c)`` is legal.

        Checks the row, column, and 3×3 box constraints.

        Args:
            g: 9×9 integer grid (0 = empty).
            r: Target row (0–8).
            c: Target column (0–8).
            v: Integer value to place (1–9).

        Returns:
            ``True`` if *v* does not already appear in the same row, column,
            or 3×3 box.
        """
        if v in g[r]:
            return False
        for i in range(9):
            if g[i][c] == v:
                return False
        br, bc = Sudoku._box_origin(r, c)
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if g[i][j] == v:
                    return False
        return True

    @staticmethod
    def _find_empty(g: list[list[int]]) -> Optional[tuple[int, int]]:
        """Return the position of the first empty cell (value 0).

        Args:
            g: 9×9 integer grid.

        Returns:
            ``(row, col)`` of the first zero found, or ``None`` if the grid is
            fully filled.
        """
        for r in range(9):
            for c in range(9):
                if g[r][c] == 0:
                    return r, c
        return None

    @staticmethod
    def _solve(g: list[list[int]]) -> bool:
        """Fill *g* in-place using backtracking; return whether a solution exists.

        Args:
            g: 9×9 integer grid modified in place.

        Returns:
            ``True`` if the grid was solved successfully.
        """
        pos = Sudoku._find_empty(g)
        if pos is None:
            return True
        r, c = pos
        for v in range(1, 10):
            if Sudoku._valid_placement(g, r, c, v):
                g[r][c] = v
                if Sudoku._solve(g):
                    return True
                g[r][c] = 0
        return False

    @staticmethod
    def _count_solutions(g: list[list[int]], limit: int = 2) -> int:
        """Count solutions up to *limit*, stopping early once the limit is reached.

        Args:
            g: 9×9 integer grid modified in place (restored after each branch).
            limit: Stop counting once this many solutions are found.

        Returns:
            Number of distinct solutions, capped at *limit*.
        """
        pos = Sudoku._find_empty(g)
        if pos is None:
            return 1
        r, c = pos
        count = 0
        for v in range(1, 10):
            if Sudoku._valid_placement(g, r, c, v):
                g[r][c] = v
                count += Sudoku._count_solutions(g, limit)
                g[r][c] = 0
                if count >= limit:
                    return count
        return count

    # ── Public API ─────────────────────────────────────────────────────────────

    @staticmethod
    def generate_puzzle(
        symbols: list[str],
        seed: int = 42,
        max_removals: int = 81,
    ) -> tuple[list[list], list[list]]:
        """Generate a puzzle with a unique solution by removing cells from a solved grid.

        Uses the band-shift pattern to build the solved grid, then performs a
        deterministic random removal: a cell is removed only if the resulting
        grid still has exactly one solution.

        Args:
            symbols: Exactly 9 unique symbols for this puzzle.
            seed: RNG seed controlling the removal order (reproducible puzzles).
            max_removals: Maximum number of cells to attempt removing.

        Returns:
            A ``(puzzle, solution)`` pair, each a 9×9 list of lists.  Empty
            cells in *puzzle* are ``None``; *solution* is fully filled.
        """
        solved = Sudoku.band_solved(symbols)
        s2i = Sudoku._sym_to_idx(symbols)

        sol_idx = Sudoku._to_idx(solved, s2i)
        puzzle_idx = [row[:] for row in sol_idx]

        rng = random.Random(seed)
        cells = [(r, c) for r in range(9) for c in range(9)]
        rng.shuffle(cells)

        removed = 0
        for r, c in cells:
            if removed >= max_removals:
                break
            backup = puzzle_idx[r][c]
            puzzle_idx[r][c] = 0
            if Sudoku._count_solutions([row[:] for row in puzzle_idx]) == 1:
                removed += 1
            else:
                puzzle_idx[r][c] = backup

        return Sudoku._from_idx(puzzle_idx, symbols), Sudoku._from_idx(sol_idx, symbols)

    @staticmethod
    def validate_solution(submitted: list[list], symbols: list[str]) -> bool:
        """Return whether *submitted* is a complete, valid Sudoku solution.

        Checks that every row, column, and 3×3 box contains exactly the 9
        expected symbols.

        Args:
            submitted: 9×9 grid of symbols to validate.
            symbols: The 9 symbols that must each appear exactly once per unit.

        Returns:
            ``True`` if *submitted* is a valid and complete solution.
        """
        sym_set = set(symbols)
        if len(submitted) != 9:
            return False
        for row in submitted:
            if len(row) != 9 or set(row) != sym_set:
                return False
        for c in range(9):
            if {submitted[r][c] for r in range(9)} != sym_set:
                return False
        for br in range(0, 9, 3):
            for bc in range(0, 9, 3):
                box = {submitted[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)}
                if box != sym_set:
                    return False
        return True

    @staticmethod
    def is_consistent_with_puzzle(submitted: list[list], puzzle: list[list]) -> bool:
        """Return whether *submitted* preserves all pre-filled cells from *puzzle*.

        Args:
            submitted: Player-submitted 9×9 grid.
            puzzle: Original puzzle grid (``None`` for empty cells).

        Returns:
            ``True`` if every non-``None`` cell in *puzzle* matches *submitted*.
        """
        for r in range(9):
            for c in range(9):
                if puzzle[r][c] is not None and puzzle[r][c] != submitted[r][c]:
                    return False
        return True
