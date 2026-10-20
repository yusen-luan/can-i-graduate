# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-20_

## Iteration 2: full BComp(CS) AY2026/27 degree, NUSMods-validated

**Goal:** scale the CSP from the 88-unit canonical skeleton to the full 160-unit degree with real
module facts, so instances become *binding* (the thing iter1 lacked) — the point being a sharper
LLM-direct vs LLM→solver comparison later. Full plan + audit: `docs/iter2_plan.md`.

**Where we are:** iter2 build is merged on branch `iter2` (commit a34b3c9, pushed to `origin/iter2`).
Solver/checker/data/frontend are complete; the evaluation harness has not been started.

### Done
- NUSMods AY2026/27 snapshot via `scripts/ingest_nusmods.py` → `data/snapshot_2026-2027/` (units, real
  offerings, prereq trees, preclusions; caught faculty-page staleness, e.g. CS4232 discontinued).
- Full degree data: `program_cs.yaml` (160u: ULR, ethics, ID/CD, CS foundation, maths, 32u B&D, UE),
  `focus_areas.yaml` (11 areas), `ge_pillars.yaml` + `id_cd.yaml` (real verified pick-lists, D22),
  `generic_modules.yaml`, `student_iter2.yaml`, `scenario_iter2.yaml`.
- Solver + independent checker for the full degree: prereq trees, bridging waiver, preclusions, real
  offerings, focus area, ≥12u L4000, 32u B&D bucket (D19), industrial experience off-cap (D18/D20),
  C&E service-learning pair (D23), CP cap, ≥160u UE filler, 28u overload ceiling (D24), preferences.
- **91 tests pass** (49 iter1 + 42 iter2, incl. seed-sweep solver↔checker parity). Default instance:
  OPTIMAL at T=8/cap 20, exactly 160u; T=8 is the arithmetic floor, not a rule (D21).
- Rule/universe verification vs NUSMods + cohort page + Bulletin: `docs/iter2_verification.md`.
- Streamlit frontend `app/app.py` (NUSMods-styled): student + plan settings → SAT/UNSAT (+ infeasibility
  explanation via `explain_infeasible_iter2`) → semester grid + requirement breakdown.
- Agent/dev docs: `AGENTS.md`, `docs/developer_guide.md` (add-a-constraint recipe).

### Next
- **Start the research deliverable:** NL problem instances with solver ground truth, the LLM-direct
  pipeline, the LLM→spec→solver pipeline, and the evaluation (difficulty, ablations, failures).
- Decide whether to close iter2 (`/checkpoint iteration-end`) before building the harness.
- Possible iter3 realism: special terms, NOC/NUSC/UROP overlays, exact per-bucket unit partitioning,
  real UE choices, soft workload objective (ablation).

### Active simplifications (Iteration 2) — see program_cs.yaml `assumptions`
- Canonical CS modules only; Special Terms (3,4) not modelled; by-arrangement modules default to both semesters.
- No per-bucket unit partition: UE is a residual filler to 160u; Computing units beyond 32u B&D count as UE.
- Only Unrestricted Electives remain generic placeholders (`*_GENERIC*`).
- Industrial experience is excluded from the per-semester cap (approximates vacation/special-term internship).
- Math/English bridging handled by placement waiver for the default student, not scheduled.

### Open issues
- `docs/solver_constraints.md` iter1 §7 wording (says cap lives in `program_cs_iter1.yaml`, not scenario) still unfixed.
- `model.py --iter2` reports 464 external-prereq warnings (prereqs outside the modelled universe); benign but noisy.
