# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-20_

## Iteration 2: full BComp(CS) AY2026/27 degree, NUSMods-validated

**Goal:** scale the CSP from the 88-unit canonical skeleton to the full 160-unit degree with real
module facts, so instances become *binding* (the thing iter1 lacked) — the point being a sharper
LLM-direct vs LLM→solver comparison later. Full plan + audit: `docs/iter2_plan.md`.

**Where we are:** iter2 build is merged on branch `iter2` (commit a34b3c9, pushed to `origin/iter2`).
Solver/checker/data/frontend are complete; the evaluation harness has not been started.

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

  ### Active simplifications (Iteration 2) — see program_cs.yaml `assumptions`
- Canonical CS modules only; Special Terms (3,4) not modelled; by-arrangement modules default to both semesters.
- No per-bucket unit partition: UE is a residual filler to 160u; Computing units beyond 32u B&D count as UE.
- Only Unrestricted Electives remain generic placeholders (`*_GENERIC*`).
- Industrial experience is excluded from the per-semester cap (approximates vacation/special-term internship).
- Math/English bridging handled by placement waiver for the default student, not scheduled.

### Iteration 3 (in progress — `docs/iter3_plan.md`)
- **Done:** C5 special-term `term_layout` (§I2.14), C1 per-sem cap vector (§I2.15), C2 CS-count cap
  (§I2.16), C3 internship+FYP+UROP w/ the CP-cap interaction (§I2.17). **Correction D29:** the CP4101
  dissertation may *replace* the internship for `eligible_fyp` students (was wrongly "exactly one
  internship always"); §I2.8 reworded. Solver+checker+tests **113 pass** (+22, incl. 3 app smoke tests).
  Decisions D25–D29.
- **Profiles + UI:** 9 representative archetypes in `data/profiles/benchmark_profiles.yaml`
  (on-track, no-H2-math, transfer, overloader, exchange, part-load, honours-dissertation, internship+UROP,
  infeasible-3yr). `app/app.py` rewired: benchmark-profile picker (seeds all controls) + iter3 controls
  (eligibility, FYP/UROP, per-sem cap via exchange/light, CS-count cap, special-term layout); plan grid
  labels Terms 1/2/Special.
- **Done (2026-10-20):** oracle-correctness suite `tests/test_oracle.py` (A1 one-mutation-per-rule
  checker soundness, A3 metamorphic M1–M5 monotonicity/tightening, A4 UNSAT mechanism-verification);
  **C4** pin/forbid/deadline (§I2.18, D30). Solver+checker+tests **149 pass** (+36 vs 113).
- **Scope frozen (2026-10-20, per request): no iter4, no more features.** All remaining work is the
  iter3 **benchmark**. Done: 10 new corpus archetypes (A9–A19, NOC dropped) in `benchmark_profiles.yaml`
  — 19 total, each validated to its `expect`, feasible ones checker-clean, UNSAT ones A4 relax→SAT
  verified (`scripts/validate_new_profiles.py`), guarded by `tests/test_profiles.py`. **168 tests pass.**
- **Done:** `eval/generate.py` writes the {nl_prompt, formal, ground_truth, meta} quadruple per
  instance to `eval/instances/` with MEASURED difficulty (near-UNSAT margin, model size — not solve
  time) + coverage tags; a synthetic stress slice adds UNSAT tiers T1/T2/T4 + near-boundary SAT.
  `eval/baselines.py` (always-SAT, canonical-4yr) calibrates the floor. **24 instances.**
- **Rebalanced to 50/50 (36 instances, 18 SAT / 18 UNSAT):** the stress slice now spans UNSAT tiers
  T1 (arithmetic floor ×5), T2 (bin-packing), T4 (offering-lock, forbid-required ×3, ineligible-FYP,
  CS-count-starved, deadline-under-prereq-depth, blocked-overload) + near-boundary SAT. always-SAT and
  always-UNSAT both floor at 50% (neither trivial strategy wins); canonical-4yr valid for only 2/18.
  Generator flags any declared-vs-oracle mismatch (0) and prunes stale instance files.
- **Plan-quality (realism) evaluator** `src/plan_quality.py` (+5 tests, `docs/plan_quality.md`): a
  solver-independent SOFT oracle scoring a *valid* plan 0–100 (workload balance, CS intensity,
  contiguity, level progression, foundation-early, GE spread, experiential timing) + flags. Not a
  constraint (D9) — judges solver AND LLM plans alike (a plan-quality eval axis). Wired into
  `eval/generate.py` meta. **Finding:** the solver's tie-breaker objective yields valid-but-punishing
  plans (default on-track plan has a 5-hard-CS semester) — motivates a future soft-objective ablation.
- **Test count: 173 pass** (113 iter2 baseline + 28 oracle + 8 C4 + 19 profiles + 5 plan-quality).
- **UI reworked** (`app/app.py`, `docs/ui_ux_plan.md` §6b/§8): removed all vibe-coded anti-patterns
  (web font, emoji, 999px pills, marketing hero); system font + tokens, **dropdown + hero student
  card**, **stat-tile verdict**, flat cards, pillar-labelled cells, progress-bar tracker, and a
  per-semester load editor taking **multiple blocked/light/heavy** semesters (grid shows Heavy/Light).
- **Realism (D31/D32/D33):** objective prefers FEWER Computing modules and FOCUS-ALIGNED depth among
  160u plans (default AI plan: 15 CS, all 5 discretionary electives AI-area, 0 off-focus; free units
  go to UE generics). App bakes sensible defaults (CS1101S→S1, GEA1000→Y1, ≤3 CS/sem, overridable);
  plan-reasonableness score removed from the app UI (kept in `eval/` meta); requirement panel + tiles
  now count prior (completed/exempted) credit so they match the checker verdict.
- **A5 external validation vs CS cohort 2026/27 page: PASSED** (`iter2_verification.md` A5). Every unit
  total + structural rule matches; 3 benign simplifications (Critique=ES2660-only, DataLit=GEA1000-only,
  industry-as-fixed-bundles). **SEP/exchange + NOC removed** as corpus cases (per request).
- **Corpus now 35 instances (17 SAT / 18 UNSAT), 0 mismatches. 173 tests pass.**
- **Next (benchmark only, both have external gates):** A5 external validation + freeze/tag oracle
  (needs cohort-page check + the still-uncommitted repo) → LLM-direct vs LLM→solver harness (needs
  API budget/keys). Then rebalance the corpus.
- **Planning docs added (2026-10-20):** `docs/benchmark_design.md` — **Part A** proves the oracle
  correct (A1 one-mutation-per-constraint checker-soundness matrix, A2 completeness, A3 metamorphic
  properties, A4 UNSAT mechanism-verification, A5 external semantic validation, A6 differential
  cross-check) **before** freezing it; **Part B** the representative corpus (archetypes A0–A19 with a
  faithful/approx realism assessment + dual stress/realistic reporting, 4-tier UNSAT, baselines). And
  `docs/ui_ux_plan.md` (senior-designer review of `app/app.py`: vibe-coded anti-pattern checklist
  V1–V10, NUSMods-decoded principles, tokens, line-level remediation). Neither implemented yet.
- Then freeze/tag the oracle and build the eval harness per `docs/evaluation_plan.md`
  (tiered NL corpus + ground truth, LLM-direct + LLM→solver graded by `check_plan_iter2`,
  Opus/Sonnet/Haiku + obfuscation ablation).



### Open issues
- `docs/solver_constraints.md` iter1 §7 wording (says cap lives in `program_cs_iter1.yaml`, not scenario) still unfixed.
- `model.py --iter2` reports 464 external-prereq warnings (prereqs outside the modelled universe); benign but noisy.
