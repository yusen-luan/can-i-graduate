# Iteration history

Compressed record of finished iterations (≤ 8 lines each): goal, what was added to the model,
key results/numbers, and the simplifications lifted. Details live in git history and `docs/decisions.md`.

## Iteration 1 — baseline CSP for the canonical CS degree
Goal: a solver that decides feasibility and builds a semester plan for one student under a simplified
22-module / 88-unit canonical degree. Added: three-layer data model (modules/program/student) + scenario,
validator, prerequisite graph, formal semantics; CP-SAT solver (`x[m,s]`) + independent checker + 49 tests.
Result: min feasible horizon T=5 for all 6 (bridging × english_path) student types at cap 20. Decisions D1–D10.
Simplifications: canonical-only, both-semester offerings, generic GE/ID/CD, no preclusions, no preferences.
