import { state } from './state.js';

export const $     = id => document.getElementById(id);
export const sleep = ms => new Promise(r => setTimeout(r, ms));

export function log(html) {
  const d  = $('term');
  const el = document.createElement('div');
  el.className = 'tl';
  el.innerHTML = html;
  d.appendChild(el);
  d.scrollTop = d.scrollHeight;
}

export function flashGrid() {
  document.querySelectorAll('.cell').forEach(c => {
    if (c.textContent) c.classList.add('flash-ok');
  });
  setTimeout(() => {
    document.querySelectorAll('.cell').forEach(c => c.classList.remove('flash-ok'));
  }, 600);
}

export function cellPx() {
  const area = $('puzzle-area');
  if (!area) return 42;
  const r     = area.getBoundingClientRect();
  const avail = Math.min(r.width * 0.88, r.height * 0.62);
  return Math.max(28, Math.floor(avail / 9));
}

// onCellClick(r, c) — if provided, enables interactive cell editing
export function renderGrid(puzzle, givenMask, filled, onCellClick) {
  const sz  = cellPx();
  const fs  = Math.max(12, Math.floor(sz * 0.40)) + 'px';
  const gEl = $('grid');
  gEl.style.gridTemplateColumns = `repeat(9, ${sz}px)`;
  gEl.style.width = (sz * 9 + 8 + 2 * 2 + 4) + 'px';
  gEl.innerHTML   = '';

  const sel = state.selectedCell;

  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      const el        = document.createElement('div');
      el.className    = 'cell';
      el.style.width  = sz + 'px';
      el.style.height = sz + 'px';
      el.style.fontSize = fs;
      if (c === 2 || c === 5) el.style.borderRight  = '2px solid #1a4a6e';
      if (r === 2 || r === 5) el.style.borderBottom = '2px solid #1a4a6e';

      const val = filled ? filled[r][c] : puzzle[r][c];

      if (givenMask[r][c]) {
        el.classList.add('given');
        el.textContent = val;
      } else {
        if (val !== null) {
          el.classList.add('filled');
          el.textContent = val;
        }
        if (sel && sel.r === r && sel.c === c) {
          el.classList.add('selected');
        }
        if (onCellClick) {
          el.style.cursor = 'pointer';
          el.addEventListener('click', () => onCellClick(r, c, el));
        }
      }
      gEl.appendChild(el);
    }
  }
}

// onSymbolClick(sym) — if provided, makes symbol badges clickable
export function renderMeta(p, onSymbolClick) {
  $('puz-num').textContent  = `PUZZLE #${p.id} / ${p.total || '—'}`;
  $('puz-meta').innerHTML   = `Niveau: <span style="color:#4fc3f7">${p.level}</span> &nbsp;|&nbsp; ${p.symbols.length} symboles`;
  $('puz-hint').textContent = p.hint;

  const sr = $('syms-row');
  sr.innerHTML = '';
  p.symbols.forEach(s => {
    const sp       = document.createElement('span');
    sp.className   = 'sym';
    sp.textContent = s;
    if (onSymbolClick) {
      sp.classList.add('clickable');
      sp.addEventListener('click', () => onSymbolClick(s));
    }
    sr.appendChild(sp);
  });
}
