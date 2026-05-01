import { state, DEMO_LIMIT } from './state.js';
import { api }               from './api.js';
import { $, sleep, log, renderGrid, renderMeta, flashGrid } from './ui.js';

// ── Progression ───────────────────────────────────────────────────────────────

let _pollTimer     = null;
let _lastEventTime = 0;
let _flagShown     = false;

function updateProgress(solvedArr, total) {
  const count   = solvedArr.filter(Boolean).length;
  const fill    = $('progress-fill');
  const sSolved = $('s-solved');
  const sTotal  = $('s-total');
  if (fill)    fill.style.width    = (total ? (count / total * 100) : 0) + '%';
  if (sSolved) sSolved.textContent = count;
  if (sTotal)  sTotal.textContent  = total;
}

async function advanceToPuzzle(puzzleId) {
  try {
    const p = await api('GET', `/api/puzzle/${puzzleId}`);
    p.givenMask    = p.grid.map(row => row.map(c => c !== null));
    p.solved       = true;
    state.curPuzzle    = p;
    state.selectedCell = null;

    // fetch solution if not already cached (covers external-script solves)
    if (!state.solutions[puzzleId]) {
      try {
        const demo = await api('GET', `/api/puzzle/${puzzleId}/demo`);
        state.solutions[puzzleId] = demo.solution;
      } catch (_) {}
    }

    state.editedGrid = state.solutions[puzzleId]
      ? state.solutions[puzzleId].map(row => row.slice())
      : p.grid.map(row => row.slice());

    renderMeta(p, handleSymbolClick);
    refreshGrid();
    updateClearBtn();
    updateManualSubmitBtn();

    const badge = $('puz-solved');
    if (badge) badge.style.display = 'inline';
  } catch (_) {}
}

async function handleNewEvents(events) {
  const solveEvents = events.filter(e => e.type === 'solve');
  const flagEvent   = events.find(e => e.type === 'flag');

  // Log dans le terminal
  for (const evt of events) {
    if (evt.type === 'solve') {
      const ts = new Date(evt.t * 1000).toLocaleTimeString();
      log(`<span class="t-dim">[${ts}]</span> <span class="t-prompt">$</span> <span class="t-cmd">POST /api/puzzle/${evt.puzzle_id}/submit</span> <span class="t-ok">→ ✓ ${evt.level}</span>`);
    } else if (evt.type === 'flag') {
      const ts = new Date(evt.t * 1000).toLocaleTimeString();
      log(`<span class="t-dim">[${ts}]</span> <span class="t-prompt">$</span> <span class="t-cmd">POST /api/flag</span> <span class="t-ok">→ ✓ FLAG</span>`);
    }
  }

  if (solveEvents.length > 0) {
    const latest = solveEvents[solveEvents.length - 1];
    await advanceToPuzzle(latest.puzzle_id);
  }

  // flag solved by an external script — fetch solutions and show it
  if (flagEvent && !_flagShown) {
    _flagShown = true;
    const missing = [state.nPuzzles - 2, state.nPuzzles - 1, state.nPuzzles]
      .filter(id => !state.solutions[id]);
    for (const id of missing) {
      try {
        const demo = await api('GET', `/api/puzzle/${id}/demo`);
        state.solutions[id] = demo.solution;
      } catch (_) {}
    }
    await sleep(400);
    await showFlag();
  }
}

function startPolling() {
  stopPolling();
  _lastEventTime = 0;
  _flagShown     = false;
  _pollTimer = setInterval(async () => {
    if (!state.token) return;
    try {
      const [session, logData] = await Promise.all([
        api('GET', '/api/session'),
        api('GET', `/api/log?since=${_lastEventTime}`),
      ]);
      updateProgress(session.solved, session.total);
      if (logData.events.length > 0) {
        await handleNewEvents(logData.events);
        _lastEventTime = logData.events[logData.events.length - 1].t;
      }
    } catch (_) {}
  }, 2000);
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

// ── Symbol picker ─────────────────────────────────────────────────────────────

let _picker = null;

function closeSymbolPicker() {
  if (_picker) { _picker.remove(); _picker = null; }
}

function showSymbolPicker(r, c, rect) {
  closeSymbolPicker();
  if (!state.curPuzzle || state.curPuzzle.solved || state.running) return;

  const symbols = state.curPuzzle.symbols;
  const picker  = document.createElement('div');
  picker.className        = 'sym-picker';
  picker.style.visibility = 'hidden';

  symbols.forEach(sym => {
    const btn       = document.createElement('button');
    btn.className   = 'sym-picker-btn';
    btn.textContent = sym;
    btn.addEventListener('mousedown', e => {
      e.preventDefault(); e.stopPropagation();
      handleSymbolClick(sym);
      closeSymbolPicker();
    });
    picker.appendChild(btn);
  });

  const erase            = document.createElement('button');
  erase.className        = 'sym-picker-btn erase';
  erase.textContent      = '✕ EFFACER';
  erase.style.gridColumn = '1 / -1';
  erase.addEventListener('mousedown', e => {
    e.preventDefault(); e.stopPropagation();
    clearSelectedCell();
    closeSymbolPicker();
  });
  picker.appendChild(erase);

  document.body.appendChild(picker);
  _picker = picker;

  // capture rect before refreshGrid — position after insertion so the picker dimensions are known
  const pw   = picker.offsetWidth;
  const ph   = picker.offsetHeight;
  let left   = rect.right + 8;
  let top    = rect.top;
  if (left + pw > window.innerWidth  - 8) left = rect.left - pw - 8;
  if (top  + ph > window.innerHeight - 8) top  = window.innerHeight - ph - 8;
  if (top < 8) top = 8;
  picker.style.left       = left + 'px';
  picker.style.top        = top  + 'px';
  picker.style.visibility = 'visible';

  // deferred so the current click that opened the picker is not immediately captured
  const onOutside = e => {
    if (!picker.contains(e.target)) {
      closeSymbolPicker();
      state.selectedCell = null;
      refreshGrid();
      document.removeEventListener('mousedown', onOutside, true);
    }
  };
  setTimeout(() => document.addEventListener('mousedown', onOutside, true), 0);
}

// ── Editable grid helpers ─────────────────────────────────────────────────────

function refreshGrid() {
  if (!state.curPuzzle) return;
  const { grid, givenMask } = state.curPuzzle;
  renderGrid(grid, givenMask, state.editedGrid, handleCellClick);
}

function updateClearBtn() {
  const p   = state.curPuzzle;
  const btn = $('btn-clear');
  if (!btn || !p) return;
  const hasEdits = state.editedGrid?.some((row, r) =>
    row.some((val, c) => val !== null && !p.givenMask[r][c])
  );
  btn.disabled = !hasEdits || p.solved || state.running;
}

function updateManualSubmitBtn() {
  const btn = $('btn-submit-manual');
  if (!btn) return;
  const p          = state.curPuzzle;
  const allFilled  = state.editedGrid?.every(row => row.every(c => c !== null));
  btn.disabled = !p || p.solved || state.running || !allFilled;
}

function handleCellClick(r, c, cellEl) {
  if (state.running || !state.curPuzzle || state.curPuzzle.solved) return;
  const same = state.selectedCell?.r === r && state.selectedCell?.c === c;
  if (same) {
    state.selectedCell = null;
    closeSymbolPicker();
    refreshGrid();
    return;
  }
  // capture rect before refreshGrid — cellEl is detached after re-render
  const rect = cellEl.getBoundingClientRect();
  state.selectedCell = { r, c };
  refreshGrid();
  showSymbolPicker(r, c, rect);
}

function handleSymbolClick(sym) {
  if (!state.selectedCell || state.running || !state.curPuzzle || state.curPuzzle.solved) return;
  const { r, c } = state.selectedCell;
  state.editedGrid[r][c] = sym;
  updateManualSubmitBtn();
  updateClearBtn();
  refreshGrid();
}

function clearSelectedCell() {
  if (!state.selectedCell || !state.curPuzzle) return;
  const { r, c } = state.selectedCell;
  if (state.curPuzzle.givenMask[r][c]) return;
  state.editedGrid[r][c] = null;
  updateManualSubmitBtn();
  refreshGrid();
}

function initEditGrid(p) {
  state.editedGrid   = p.grid.map(row => row.slice());
  state.selectedCell = null;
  const btn = $('btn-clear');
  if (btn) btn.disabled = true;
}

export function clearGrid() {
  const p = state.curPuzzle;
  if (!p || p.solved || state.running) return;
  state.editedGrid   = p.grid.map(row => row.slice());
  state.selectedCell = null;
  closeSymbolPicker();
  updateManualSubmitBtn();
  refreshGrid();
  $('btn-clear').disabled = true;
}

// ── Manual submission ─────────────────────────────────────────────────────────

export async function manualSubmit() {
  if (state.running || !state.curPuzzle || state.curPuzzle.solved) return;
  const p = state.curPuzzle;

  state.running = true;
  $('btn-submit-manual').disabled = true;
  $('btn-solve').disabled  = true;
  state.selectedCell = null;
  refreshGrid();

  log(`<span class="t-prompt">$</span> <span class="t-cmd">POST /api/puzzle/${p.id}/submit</span>`);
  log(`<span class="t-dim">  {"grid": [[…9×9…]]}</span>`);

  let result;
  try {
    result = await api('POST', `/api/puzzle/${p.id}/submit`, { grid: state.editedGrid });
  } catch (e) {
    log(`<span class="t-err">  ${e.message}</span>`);
    state.running = false;
    updateManualSubmitBtn();
    return;
  }

  if (!result.correct) {
    log(`<span class="t-err">  ✗ ${result.message}</span>`);
    state.running = false;
    updateManualSubmitBtn();
    return;
  }

  state.solutions[p.id] = state.editedGrid.map(row => row.slice());
  flashGrid();
  log(`<span class="t-ok">→ 200 OK  {"correct": true}</span>`);
  log(`<span class="t-sep">  ══════════════════════════════</span>`);
  log(`<span class="t-ok">  ✓ PUZZLE #${p.id} RÉSOLU !</span>`);
  if (p.id > state.nPuzzles - 3) {
    log(`<span class="t-dim">  row[4] → <span class="t-info">${state.editedGrid[4].join('')}</span></span>`);
  }
  log(`<span class="t-sep">  ══════════════════════════════</span>`);

  p.solved = true;
  state.running = false;

  if (result.all_solved) {
    await sleep(500);
    await showFlag();
  } else {
    $('btn-next').disabled = false;
    if (state.demoUsed < DEMO_LIMIT) $('btn-solve').disabled = false;
    log(`<span class="t-info">  → Puzzle suivant disponible</span>`);
  }
}

// ── Demo auto-solve ────────────────────────────────────────────────────────────

export async function demoSolve() {
  if (state.running || !state.token || !state.curPuzzle || state.curPuzzle.solved) return;
  if (state.demoUsed >= DEMO_LIMIT) {
    log(`<span class="t-err">Demo limitée à ${DEMO_LIMIT} puzzle(s). Écris ton propre solver !</span>`);
    $('btn-solve').disabled = true;
    return;
  }

  state.running = true;
  state.selectedCell = null;
  closeSymbolPicker();
  $('btn-solve').disabled         = true;
  $('btn-next').disabled          = true;
  $('btn-submit-manual').disabled = true;
  const p = state.curPuzzle;

  log(`<span class="t-sep">─── Puzzle #${p.id}/${state.nPuzzles} (${p.level}) ───────────</span>`);
  log(`<span class="t-ok">→ symboles : [${p.symbols.join(', ')}]</span>`);
  const given = p.grid.flat().filter(c => c !== null).length;
  log(`<span class="t-dim">  ${given}/81 cases données</span>`);
  await sleep(180);

  log(`<span class="t-prompt">$</span> <span class="t-cmd">GET /api/puzzle/${p.id}/demo</span>`);
  await sleep(120);
  let demoData;
  try {
    demoData = await api('GET', `/api/puzzle/${p.id}/demo`);
  } catch (e) {
    log(`<span class="t-err">  ${e.message}</span>`);
    state.running = false;
    $('btn-solve').disabled = false;
    return;
  }

  const solution = demoData.solution;
  state.solutions[p.id] = solution;
  state.demoUsed++;

  log(`<span class="t-ok">  ✓ Solution reçue du serveur</span>`);
  const rem = DEMO_LIMIT - state.demoUsed;
  $('btn-solve').textContent = rem > 0
    ? `▶ DEMO AUTO-SOLVE (${rem} restant${rem > 1 ? 's' : ''})`
    : `▶ DEMO AUTO-SOLVE (épuisée)`;
  await sleep(140);

  // Animation remplissage cellule par cellule
  const emptyCells = [];
  for (let r = 0; r < 9; r++)
    for (let c = 0; c < 9; c++)
      if (!p.givenMask[r][c]) emptyCells.push([r, c]);

  const display = p.grid.map(row => row.slice());
  const delay   = Math.max(8, Math.floor(350 / emptyCells.length));
  for (const [r, c] of emptyCells) {
    display[r][c] = solution[r][c];
    renderGrid(p.grid, p.givenMask, display);
    await sleep(delay);
  }
  state.editedGrid = solution.map(row => row.slice());
  await sleep(180);

  log(`<span class="t-prompt">$</span> <span class="t-cmd">POST /api/puzzle/${p.id}/submit</span>`);
  log(`<span class="t-dim">  {"grid": [[…9×9…]]}</span>`);
  await sleep(260);

  let result;
  try {
    result = await api('POST', `/api/puzzle/${p.id}/submit`, { grid: solution });
  } catch (e) {
    log(`<span class="t-err">  ${e.message}</span>`);
    state.running = false;
    $('btn-solve').disabled = false;
    return;
  }

  if (!result.correct) {
    log(`<span class="t-err">  ✗ ${result.message}</span>`);
    state.running = false;
    $('btn-solve').disabled = false;
    return;
  }

  flashGrid();
  log(`<span class="t-ok">→ 200 OK  {"correct": true}</span>`);
  log(`<span class="t-sep">  ══════════════════════════════</span>`);
  log(`<span class="t-ok">  ✓ PUZZLE #${p.id} RÉSOLU !</span>`);
  if (p.id > state.nPuzzles - 3) {
    log(`<span class="t-dim">  row[4] → <span class="t-info">${solution[4].join('')}</span></span>`);
  }
  log(`<span class="t-sep">  ══════════════════════════════</span>`);

  p.solved = true;
  state.running = false;

  if (result.all_solved) {
    await sleep(500);
    await showFlag();
  } else {
    $('btn-next').disabled = false;
    if (state.demoUsed < DEMO_LIMIT) $('btn-solve').disabled = false;
    else log(`<span class="t-err">  Demo épuisée — à toi d'écrire le solver !</span>`);
    log(`<span class="t-info">  → Puzzle suivant disponible</span>`);
  }
}

// ── Next puzzle ───────────────────────────────────────────────────────────────

export async function nextPuzzle() {
  if (!state.curPuzzle || !state.curPuzzle.solved || state.curPuzzle.id >= state.nPuzzles) return;
  const nextId = state.curPuzzle.id + 1;
  $('btn-next').disabled          = true;
  $('btn-solve').disabled         = true;
  $('btn-submit-manual').disabled = true;
  try {
    log(`<span class="t-prompt">$</span> <span class="t-cmd">GET /api/puzzle/${nextId}</span>`);
    const p       = await api('GET', `/api/puzzle/${nextId}`);
    p.givenMask   = p.grid.map(row => row.map(c => c !== null));
    state.curPuzzle = p;
    initEditGrid(p);
    renderMeta(p, handleSymbolClick);
    refreshGrid();
    const badge = $('puz-solved');
    if (badge) badge.style.display = 'none';
    try { const s = await api('GET', '/api/session'); updateProgress(s.solved, s.total); } catch (_) {}
    log(`<span class="t-dim">─── Puzzle #${nextId} chargé ──────────────</span>`);
    if (state.demoUsed < DEMO_LIMIT) $('btn-solve').disabled = false;
  } catch (e) {
    log(`<span class="t-err">Erreur chargement : ${e.message}</span>`);
  }
}

// ── Flag reconstruction ───────────────────────────────────────────────────────

export async function showFlag() {
  log(`<span class="t-sep">─────────────────────────────────</span>`);
  log(`<span class="t-info">  Reconstruction du flag…</span>`);

  const flagIds = [state.nPuzzles - 2, state.nPuzzles - 1, state.nPuzzles];
  const rows    = flagIds.map(id => {
    const sol = state.solutions[id];
    return sol ? sol[4].join('') : '?'.repeat(9);
  });

  for (let i = 0; i < rows.length; i++) {
    log(`<span class="t-dim">  Puzzle ${flagIds[i]} row[4] → <span class="t-info">${rows[i]}</span></span>`);
    await sleep(200);
  }

  const reconstructed = rows.join('');
  log(`<span class="t-ok">  Concatenation → ${reconstructed}</span>`);
  await sleep(300);

  log(`<span class="t-prompt">$</span> <span class="t-cmd">POST /api/flag</span>`);
  log(`<span class="t-dim">  {"flag": "${reconstructed}"}</span>`);
  await sleep(320);

  let res;
  try {
    res = await api('POST', '/api/flag', { flag: reconstructed });
  } catch (e) {
    log(`<span class="t-err">Erreur : ${e.message}</span>`);
    return;
  }

  if (!res.correct) {
    log(`<span class="t-err">  ✗ ${res.message}</span>`);
    return;
  }

  log(`<span class="t-ok">→ 200 OK  {"correct": true}</span>`);
  log(`<span class="t-sep">══════════════════════════════════</span>`);
  log(`<span class="t-ok">  FÉLICITATIONS ! Tous résolus.</span>`);
  log(`<span class="t-flag">  ${reconstructed}</span>`);
  log(`<span class="t-dim">  ${res.puzzles_solved} puzzles | ${res.time_seconds}s</span>`);
  log(`<span class="t-sep">══════════════════════════════════</span>`);
  await sleep(400);

  const overlay     = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">CHALLENGE COMPLETE</div>
      <div class="modal-sub">Tous les puzzles 9×9 résolus via l'API.</div>
      <div class="modal-flag">${reconstructed}</div>
      <div class="modal-rows">
        <div><span class="hl">Puzzle ${flagIds[0]} row[4] :</span> ${rows[0]}</div>
        <div><span class="hl">Puzzle ${flagIds[1]} row[4] :</span> ${rows[1]}</div>
        <div><span class="hl">Puzzle ${flagIds[2]} row[4] :</span> ${rows[2]}</div>
        <div style="margin-top:8px;color:#4fc3f7">→ ${reconstructed}</div>
      </div>
      <div class="modal-note">${res.puzzles_solved} puzzles · ${res.time_seconds}s</div>
      <br>
      <button class="btn success" onclick="this.closest('.modal-overlay').remove()">FERMER</button>
    </div>`;
  document.body.appendChild(overlay);
}

// ── Reset ──────────────────────────────────────────────────────────────────────

export async function resetAll() {
  if (state.resetting) return;
  state.resetting = true;
  closeSymbolPicker();
  stopPolling();
  Object.assign(state, {
    solutions: {}, demoUsed: 0, running: false,
    token: null, curPuzzle: null, nPuzzles: 0,
    selectedCell: null, editedGrid: null,
  });
  $('btn-solve').disabled         = true;
  $('btn-next').disabled          = true;
  $('btn-submit-manual').disabled = true;
  document.querySelectorAll('.modal-overlay').forEach(m => m.remove());
  await init();
  state.resetting = false;
}

// ── Init ───────────────────────────────────────────────────────────────────────

export async function init() {
  $('term').innerHTML     = '';
  $('grid').innerHTML     = '';
  $('syms-row').innerHTML = '';
  $('s-solved').textContent = '0';
  $('s-total').textContent  = '—';
  $('progress-fill').style.width = '0%';
  $('puz-hint').textContent = 'Chargement…';
  const badge = $('puz-solved');
  if (badge) badge.style.display = 'none';

  log(`<span class="t-info">Connexion au serveur SUDOKU-CTF…</span>`);

  try {
    log(`<span class="t-prompt">$</span> <span class="t-cmd">GET /api/start</span>`);
    const session   = await api('GET', '/api/start');
    state.token     = session.token;
    state.nPuzzles  = session.puzzles;
    updateProgress(new Array(state.nPuzzles).fill(false), state.nPuzzles);
    startPolling();
    log(`<span class="t-ok">→ Token : ${state.token}</span>`)
    log(`<span class="t-sep">─────────────────────────────────</span>`)
    log(`<span class="t-info">  Réutilise ce token dans ton script :</span>`)
    log(`<span class="t-ok">  python solver.py --token ${state.token}</span>`)
    log(`<span class="t-dim">  (expire dans ${session.expires_in} — ne rappelle pas /api/start)</span>`);

    log(`<span class="t-prompt">$</span> <span class="t-cmd">GET /api/puzzle/1</span>`);
    const p       = await api('GET', '/api/puzzle/1');
    p.givenMask   = p.grid.map(row => row.map(c => c !== null));
    state.curPuzzle = p;
    initEditGrid(p);
    renderMeta(p, handleSymbolClick);
    refreshGrid();

    const given = p.grid.flat().filter(c => c !== null).length;
    log(`<span class="t-ok">→ Puzzle 1 chargé — ${given}/81 cases données</span>`);
    log(`<span class="t-dim">─────────────────────────────────</span>`);
    log(`<span class="t-info">Workflow attendu :</span>`);
    log(`<span class="t-dim">1. GET  /api/start          → token</span>`);
    log(`<span class="t-dim">2. GET  /api/puzzle/{id}    → grille + symboles</span>`);
    log(`<span class="t-dim">3. Résoudre localement</span>`);
    log(`<span class="t-dim">4. POST /api/puzzle/{id}/submit</span>`);
    log(`<span class="t-dim">   {"grid": [[sym|null, …], …]}</span>`);
    log(`<span class="t-dim">5. Répéter pour les ${state.nPuzzles} puzzles</span>`);
    log(`<span class="t-dim">6. POST /api/flag</span>`);
    log(`<span class="t-dim">   {"flag": "???"}</span>`);
    log(`<span class="t-dim">─────────────────────────────────</span>`);
    log(`<span class="t-info">Indice : aligne les lignes centrales</span>`);
    log(`<span class="t-dim">  des 3 derniers puzzles.</span>`);
    log(`<span class="t-dim">─────────────────────────────────</span>`);

    $('btn-solve').disabled = false;
    $('btn-solve').textContent = `▶ DEMO AUTO-SOLVE (${DEMO_LIMIT} puzzles)`;
  } catch (e) {
    log(`<span class="t-err">Erreur : ${e.message}</span>`);
  }
}

// ── Keyboard: fill / erase selected cell ─────────────────────────────────────
window.addEventListener('keydown', e => {
  if (state.running || !state.curPuzzle || state.curPuzzle.solved) return;
  if (e.key === 'Escape')                            { state.selectedCell = null; refreshGrid(); return; }
  if (e.key === 'Backspace' || e.key === 'Delete')   { clearSelectedCell(); return; }
  if (!state.selectedCell) return;
  const sym = state.curPuzzle.symbols.find(s => s === e.key);
  if (sym) handleSymbolClick(sym);
});

// ── Global exposure for inline onclick handlers ───────────────────────────────
window.demoSolve    = demoSolve;
window.nextPuzzle   = nextPuzzle;
window.resetAll     = resetAll;
window.manualSubmit = manualSubmit;
window.clearGrid    = clearGrid;

// ── Boot + resize ──────────────────────────────────────────────────────────────
init();
window.addEventListener('resize', () => {
  if (state.curPuzzle) refreshGrid();
});
