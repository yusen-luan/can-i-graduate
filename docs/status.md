# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-19_

## Iteration 2: full BComp(CS) AY2026/27 degree, NUSMods-validated

**Goal:** scale the CSP from the 88-unit canonical skeleton to the full 160-unit degree with real
module facts, so instances become *binding* (the thing iter1 lacked) — the point being a sharper
LLM-direct vs LLM→solver comparison later. Full plan + audit: `docs/iter2_plan.md`.

### Done
- NUSMods AY2026/27 snapshot: `scripts/ingest_nusmods.py` → `data/snapshot_2026-2027/`
  (95 modules + raw JSON + preclusions + `validation_report.md`). Caught real faculty-page staleness
  (CP/CS unit sizes, single-sem offerings, CS4232 discontinued).
- Degree data: `program_cs.yaml` (160u buckets), `focus_areas.yaml` (11 areas), `generic_modules.yaml`,
  `student_iter2.yaml`, `scenario_iter2.yaml`.
- Solver+checker+tests: prereq tree (reified / evaluated), placement-waived bridging, preclusions,
  real offered terms, focus area, ≥12u L4000, **32u Breadth&Depth bucket** (focus + L4000 + industrial
  inside it; NO team project — verified), industrial experience (exactly one, **off the semester cap**
  as vacation/special-term), CP cap, ≥160u with UE filler, optional preferences.
  `build_and_solve_iter2` + `check_plan_iter2`; **81 tests pass** (49 iter1 + 32 iter2).
  Default instance: OPTIMAL at T=8/cap20, exactly 160u; T=8 is the arithmetic floor (early grad via overload/APC).
- Full universe + constraint re-verification against NUSMods + cohort page + Bulletin: `docs/iter2_verification.md`.
- Real GE/ID/CD: ULR pick-list pillars (GEC%/GESS%/GEN%) and ID/CD now use verified real NUSMods courses
  (full authoritative lists in `data/ge_pillars.yaml`, `data/id_cd.yaml`); year-long C&E service-learning
  modelled as two contiguous semesters (GEN..X Term1 -> GEN..Y Term2). Only UE stays generic.
- Frontend: `app/app.py` (Streamlit) — constraint inputs → SAT/UNSAT (+ infeasibility explanation)
  → semester-by-semester plan grid. `src/solver.py --iter2` CLI + `explain_infeasible_iter2`.

### Next
- Decide: start the NL-instance + LLM-direct + LLM→spec evaluation harness (the actual research deliverable)?
- Possible iter3: NOC/NUSC/UROP overlays, special terms, soft-objective workload (ablation),
  exact per-bucket unit partitioning, real ID/CD + GE pick-lists.

### Active simplifications (Iteration 2) — see program_cs.yaml `assumptions`
- Canonical-only; special terms (3,4) not modelled; by-arrangement modules default to both semesters.
- 32u Breadth&Depth aggregate not enforced (sub-rules are); UE/ULR-picklist/ID-CD are generic placeholders.
- Math/English bridging handled by placement waiver, not scheduled, for the default student.

### Open issues
- `docs/solver_constraints.md` iter1 §7 wording (cap lives in scenario, not program) still unfixed.
- Focus/ID/CD/GE pick-lists are not real course lists yet (generic); fine for feasibility, not for realism.
- Repo not committed/pushed yet (per request): iter2 work is staged in the working tree only.
