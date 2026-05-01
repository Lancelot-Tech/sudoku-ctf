"""SUDOKU - FastAPI application.

Routes:
    GET  /                            Serve the single-page UI.
    GET  /api/start                   Create a new session.
    GET  /api/puzzle/{id}             Return puzzle metadata and grid.
    GET  /api/puzzle/{id}/demo        Return the solution (gated).
    POST /api/puzzle/{id}/submit      Validate and record a submitted solution.
    POST /api/flag                    Validate the reconstructed flag.
    GET  /api/symbols                 Return available symbol sets.
    GET  /api/session                 Return full session state.
    GET  /api/log                     Poll the event log.
    GET  /api/status                  Return server health information.
"""

import random
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import DEMO_LIMIT, FLAG, MAX_SESSIONS, PUZZLES, SESSION_TTL_SECONDS
from .session import SessionStore
from .sudoku import Sudoku


# ── Request models ──────────────────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    grid: list[list[Optional[str]]]


class FlagRequest(BaseModel):
    flag: str


# ── Symbol sets ────────────────────────────────────────────────────────────────

_SYMBOL_SETS: dict[str, list[list[str]]] = {
    "easy": [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
        ["0", "1", "2", "3", "4", "5", "6", "7", "8"],
        ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
    ],
    "medium": [
        ["α", "β", "γ", "δ", "ε", "ζ", "η", "θ", "ι"],
        ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
        ["J", "K", "L", "M", "N", "O", "P", "Q", "R"],
        ["♠", "♣", "♥", "♦", "★", "☆", "●", "○", "■"],
    ],
    "hard": [
        ["!", "@", "#", "$", "%", "^", "&", "*", "?"],
        ["A", "z", "3", "_", "!", "0", "x", "9", "#"],
        ["π", "Σ", "Δ", "Ω", "λ", "μ", "ψ", "φ", "ξ"],
        ["€", "£", "¥", "©", "®", "™", "§", "¶", "†"],
    ],
}


# ── Application ────────────────────────────────────────────────────────────────

class SudokuCTF:
    """SUDOKU application state and request helpers.

    Encapsulates the FastAPI :attr:`app` instance, the rate :attr:`limiter`,
    and the session :attr:`store`.  Route handlers are module-level functions
    registered via :attr:`app` and :attr:`limiter` after instantiation.
    """

    def __init__(self) -> None:
        self.store = SessionStore(ttl=SESSION_TTL_SECONDS, max_sessions=MAX_SESSIONS)
        self.limiter = Limiter(key_func=get_remote_address)
        self.app = FastAPI(
            title="SUDOKU",
            version="1.0.0",
            lifespan=self._lifespan,
            docs_url="/docs",
            redoc_url=None,
        )
        self.app.state.limiter = self.limiter
        self.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
        self.app.mount("/static", StaticFiles(directory="/app/static"), name="static")

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI):
        import asyncio

        async def _cleanup() -> None:
            while True:
                await asyncio.sleep(300)
                purged = self.store.purge_expired()
                if purged:
                    print(f"[cleanup] removed {purged} expired session(s)")

        task = asyncio.create_task(_cleanup())
        yield
        task.cancel()

    # ── Request helpers ────────────────────────────────────────────────────────

    def require_session(self, token: Optional[str]) -> dict[str, Any]:
        """Validate the ``X-Token`` header and return the live session data.

        Args:
            token: Value of the ``X-Token`` request header.

        Returns:
            The session data dict.

        Raises:
            HTTPException: 401 if the token is absent, invalid, or expired.
        """
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Missing X-Token header. Call GET /api/start first.",
            )
        session = self.store.get(token)
        if session is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token. Call GET /api/start first.",
            )
        return session

    @staticmethod
    def get_puzzle(puzzle_id: int) -> tuple[int, dict]:
        """Validate a puzzle ID and return its 0-based index and metadata.

        Args:
            puzzle_id: 1-based puzzle identifier from the URL path.

        Returns:
            A ``(idx, meta)`` pair where *idx* is the 0-based list index and
            *meta* is the corresponding entry from :data:`~app.config.PUZZLES`.

        Raises:
            HTTPException: 404 if *puzzle_id* is out of the valid range.
        """
        idx = puzzle_id - 1
        if idx < 0 or idx >= len(PUZZLES):
            raise HTTPException(status_code=404, detail=f"Puzzle {puzzle_id} not found.")
        return idx, PUZZLES[idx]


# ── ASGI entry point ───────────────────────────────────────────────────────────

ctf = SudokuCTF()
app = ctf.app
limiter = ctf.limiter


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    with open("/app/templates/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/start")
@limiter.limit("10/minute")
async def start_session(request: Request) -> dict:
    """Create a new isolated session and return its token.

    Raises:
        HTTPException: 503 when the active session cap is reached.
    """
    if ctf.store.count() >= MAX_SESSIONS:
        raise HTTPException(status_code=503, detail="Server at capacity. Try again later.")

    token = secrets.token_hex(16)
    session: dict[str, Any] = {
        "token":        token,
        "solved":       [False] * len(PUZZLES),
        "started_at":   time.time(),
        "completed_at": None,
        "events":       [],
    }
    ctf.store.set(token, session)
    return {
        "token":      token,
        "message":    "Session created. Use X-Token: <token> in your request headers.",
        "puzzles":    len(PUZZLES),
        "expires_in": f"{SESSION_TTL_SECONDS // 60} minutes",
    }


@app.get("/api/puzzle/{puzzle_id}")
@limiter.limit("120/minute")
async def get_puzzle(
    request: Request,
    puzzle_id: int,
    x_token: Optional[str] = Header(default=None),
) -> dict:
    """Return the puzzle grid, symbols, and solve state for the caller's session."""
    session = ctf.require_session(x_token)
    idx, meta = ctf.get_puzzle(puzzle_id)
    return {
        "id":      puzzle_id,
        "level":   meta["level"],
        "symbols": meta["symbols"],
        "hint":    meta["hint"],
        "grid":    meta["puzzle"],
        "solved":  session["solved"][idx],
        "total":   len(PUZZLES),
    }


@app.get("/api/puzzle/{puzzle_id}/demo")
@limiter.limit("15/minute")
async def demo_solution(
    request: Request,
    puzzle_id: int,
    x_token: Optional[str] = Header(default=None),
) -> dict:
    """Return the full solution for a puzzle.

    Free for the first :data:`~app.config.DEMO_LIMIT` puzzles; gated
    behind solving for all others.

    Raises:
        HTTPException: 403 if the puzzle is beyond the free demo limit and
            has not been solved yet.
    """
    session = ctf.require_session(x_token)
    idx, meta = ctf.get_puzzle(puzzle_id)
    if puzzle_id > DEMO_LIMIT and not session["solved"][idx]:
        raise HTTPException(
            status_code=403,
            detail=f"Demo is only available for the first {DEMO_LIMIT} puzzles, "
                   "or after the puzzle has been solved.",
        )
    return {"solution": meta["solution"]}


@app.post("/api/puzzle/{puzzle_id}/submit")
@limiter.limit("60/minute")
async def submit_solution(
    request: Request,
    puzzle_id: int,
    body: SubmitRequest,
    x_token: Optional[str] = Header(default=None),
) -> dict:
    """Validate and record a submitted 9×9 solution grid.

    For the last 3 puzzles (which encode the flag) the submitted grid must
    match the unique canonical solution exactly, not just be a valid Sudoku.

    Raises:
        HTTPException: 400 if the puzzle is already solved.
        HTTPException: 422 if the grid dimensions are wrong or pre-filled
            cells were modified.
    """
    session = ctf.require_session(x_token)
    idx, meta = ctf.get_puzzle(puzzle_id)

    if session["solved"][idx]:
        raise HTTPException(status_code=400, detail="Puzzle already solved.")

    grid = body.grid
    if len(grid) != 9 or any(len(row) != 9 for row in grid):
        raise HTTPException(status_code=422, detail="Grid must be 9×9.")

    if not Sudoku.is_consistent_with_puzzle(grid, meta["puzzle"]):
        raise HTTPException(
            status_code=422,
            detail="Pre-filled cells must not be modified.",
        )

    if not Sudoku.validate_solution(grid, meta["symbols"]):
        return {
            "correct":    False,
            "message":    "Incorrect solution. Check every row, column, and 3×3 box.",
            "solved":     False,
            "all_solved": False,
        }

    if idx >= len(PUZZLES) - 3 and grid != meta["solution"]:
        return {
            "correct":    False,
            "message":    "Incorrect solution. This puzzle has only one valid solution.",
            "solved":     False,
            "all_solved": False,
        }

    session["solved"][idx] = True
    session["events"].append({
        "t":         round(time.time(), 3),
        "type":      "solve",
        "puzzle_id": puzzle_id,
        "level":     meta["level"],
    })
    if all(session["solved"]):
        session["completed_at"] = time.time()

    ctf.store.touch(x_token)
    return {
        "correct":    True,
        "message":    f"Puzzle {puzzle_id} solved!",
        "solved":     True,
        "all_solved": all(session["solved"]),
        "remaining":  [i + 1 for i, s in enumerate(session["solved"]) if not s],
    }


@app.post("/api/flag")
@limiter.limit("10/minute")
async def submit_flag(
    request: Request,
    body: FlagRequest,
    x_token: Optional[str] = Header(default=None),
) -> dict:
    """Validate the flag reconstructed from the last three puzzles' central rows.

    Raises:
        HTTPException: 403 if any puzzle remains unsolved.
    """
    session = ctf.require_session(x_token)
    if not all(session["solved"]):
        remaining = [i + 1 for i, s in enumerate(session["solved"]) if not s]
        raise HTTPException(
            status_code=403,
            detail=f"Solve all puzzles first. Remaining: {remaining}",
        )
    if body.flag != FLAG:
        return {
            "correct": False,
            "message": "Incorrect flag. Re-read the central rows of the last 3 puzzles.",
        }
    session["events"].append({"t": round(time.time(), 3), "type": "flag"})
    elapsed = (session["completed_at"] or time.time()) - session["started_at"]
    return {
        "correct":        True,
        "message":        "Congratulations! You reconstructed the flag.",
        "puzzles_solved": len(PUZZLES),
        "time_seconds":   round(elapsed, 1),
        "time_note":      "measured from session creation (/api/start)",
    }


@app.get("/api/symbols")
async def get_symbols(difficulty: Optional[str] = None) -> dict:
    """Return available symbol sets, optionally filtered by difficulty.

    Args:
        difficulty: One of ``"easy"``, ``"medium"``, ``"hard"``; omit to
            receive all sets.

    Raises:
        HTTPException: 400 if *difficulty* is not a recognised value.
    """
    if difficulty is None:
        return {"difficulties": list(_SYMBOL_SETS.keys()), "sets": _SYMBOL_SETS}
    d = difficulty.lower()
    if d not in _SYMBOL_SETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown difficulty. Choices: {list(_SYMBOL_SETS.keys())}",
        )
    return {"difficulty": d, "symbols": random.choice(_SYMBOL_SETS[d])}


@app.get("/api/session")
async def session_info(x_token: Optional[str] = Header(default=None)) -> dict:
    """Return the full solve state for the caller's session."""
    session = ctf.require_session(x_token)
    return {
        "token":          x_token,
        "solved":         session["solved"],
        "puzzles_solved": sum(session["solved"]),
        "total":          len(PUZZLES),
        "all_solved":     all(session["solved"]),
        "remaining":      [i + 1 for i, s in enumerate(session["solved"]) if not s],
    }


@app.get("/api/log")
async def get_log(
    x_token: Optional[str] = Header(default=None),
    since: Optional[float] = None,
) -> dict:
    """Return events for the caller's session, optionally filtered by timestamp.

    Args:
        since: If provided, only events with ``t > since`` are returned.
    """
    session = ctf.require_session(x_token)
    events = session.get("events", [])
    if since is not None:
        events = [e for e in events if e["t"] > since]
    return {"events": events}


@app.get("/api/status")
async def server_status() -> dict:
    """Return server health and capacity information."""
    return {
        "active_sessions": ctf.store.count(),
        "max_sessions":    MAX_SESSIONS,
        "uptime":          "ok",
    }
