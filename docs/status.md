# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-14_

## Iteration 1: baseline CSP for the canonical CS degree

**Goal:** a working solver that decides feasibility and produces a semester-by-semester plan for one
student under a simplified CS degree model (22 modules / 88 units on the canonical path).

### Done
- Task 1: three-layer data model (modules / program / student) + planning scenario, validator
  (`src/model.py`), prerequisite graph, formal semantics (`docs/solver_constraints.md`).

### Next
- Implement the solver from `docs/solver_constraints.md` (solver library not chosen yet).

### Active simplifications (Iteration 1)
- Canonical CS modules only (no CS1010-family substitutes); CS2105/CS2107 excluded.
- All modules offered in both semesters.
- GE (GEC/GES/GEN) and ID/CD are generic placeholders. ES2660 and GEA1000 are fixed choices.
- No preclusions or "must not have taken" rules.
- The English bridging path exists in the data, but no bridging module rule beyond ES1000→ES1103→ES2660.

### Open issues
- `docs/solver_constraints.md` §7 says the unit cap lives in `program_cs_iter1.yaml`, but it is now in
  `planning_scenario.yaml`.
- `program_cs_iter1.yaml: planning_horizon_semesters` duplicates `planning_scenario.yaml: target_semesters`.
- Not started: NL problem instances, LLM-direct pipeline, LLM→spec pipeline, evaluation harness.
