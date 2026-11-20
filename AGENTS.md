# Desk UI

Desk uses native Qt widgets with PySide6. Use the official Meta Astryx CLI to review
patterns and token roles before changing the interface:

- `astryx docs tokens` for the shared foundations.
- `astryx component Button`, `astryx component Card`, and `astryx component Dialog`
  for component behavior and accessibility.
- If the tool is missing, install `npm install -g @astryxdesign/cli@0.7.16` from the
  official npm registry. The unscoped package name is unrelated.

Adapt the reference to Qt in `src/novoacesso/desk_theme.py`. Reuse existing
widgets and handlers so keyboard shortcuts, permission states and session
controls continue to work. Verify layout changes in the offscreen UI tests,
with synthetic content and a temporary identity directory.
