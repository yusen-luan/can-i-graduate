# Iteration history

Compressed record of finished iterations (≤ 8 lines each): goal, what was added to the model,
key results/numbers, and the simplifications lifted. Details live in git history and `docs/decisions.md`.

## Iteration 1 — baseline CSP for the canonical CS degree
Goal: a solver that decides feasibility and builds a semester plan for one student under a simplified
22-module / 88-unit canonical degree. Added: three-layer data model (modules/program/student) + scenario,
validator, prerequisite graph, formal semantics; CP-SAT solver (`x[m,s]`) + independent checker + 49 tests.
Result: min feasible horizon T=5 for all 6 (bridging × english_path) student types at cap 20. Decisions D1–D10.
Simplifications: canonical-only, both-semester offerings, generic GE/ID/CD, no preclusions, no preferences.

## Iteration 2 — full 160u BComp(CS) AY2026/27, NUSMods-validated
Goal: scale to the full degree with real module facts so instances become *binding*. Added: frozen NUSMods
snapshot (95 modules, preclusions, `scripts/ingest_nusmods.py`), `program_cs.yaml` 160u buckets, 11 focus
areas, prereq trees, placement-waived bridging, real offered terms, ≥12u L4000, 32u B&D bucket, industrial
experience (off the semester cap), CP cap, UE filler, preferences; real GE/ID/CD lists + year-long C&E halves;
Streamlit app; `explain_infeasible_iter2`. Result: default instance OPTIMAL at T=8/cap20, exactly 160u (T=8 is
the arithmetic floor); universe re-verified in `docs/iter2_verification.md`; 81 tests. Decisions D11–D24.
Simplifications lifted: generic GE/ID/CD, both-semester offerings, no preclusions. Branch `iter2`, a34b3c9.
