export const DEMO_LIMIT = 2;

export const state = {
  token:        null,
  nPuzzles:     0,
  curPuzzle:    null,
  solutions:    {},
  demoUsed:     0,
  running:      false,
  resetting:    false,
  selectedCell: null,   // { r, c } | null
  editedGrid:   null,   // mutable 9×9 working copy of the current puzzle
};
