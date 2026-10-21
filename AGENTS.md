# AGENTS.md

Entry point for coding agents (Codex / Claude). Start here, then read the files
below before changing anything.

- **`CLAUDE.md`** — repo map, hard conventions, commands. (Lean, always read.)
- **`docs/developer_guide.md`** — architecture, the module schema, and the exact
  recipe for adding a constraint (solver + checker + test + docs, in that order).
- **`docs/solver_constraints.md`** — AUTHORITATIVE formal semantics. Edit this
  *first* when changing any rule.
- **`docs/iter2_verification.md`** — what the real degree rules are and how they
  were verified against NUSMods + the cohort page + the NUS Bulletin.
- **`docs/decisions.md`** / **`docs/status.md`** — decision log / current state.

## Golden rules
1. Module **facts** come from the NUSMods snapshot (`data/snapshot_<AY>/`), never
   hand-typed; degree **rules** are hand-curated YAML. Keep them separate.
2. Every constraint lives in BOTH `src/solver.py` (CP-SAT) and `src/checker.py`
   (independent), plus a test. The checker must never import the solver.
3. Keep `python -m pytest tests -q` green (91 tests), including the seed-sweep
   parity test. Trust NUSMods over faculty web pages.

## Quick commands
```bash
pip install -r requirements.txt
python src/model.py --iter2
python src/solver.py --iter2 --focus-area artificial_intelligence
python -m pytest tests -q
streamlit run app/app.py
```
