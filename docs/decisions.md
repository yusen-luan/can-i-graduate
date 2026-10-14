# Modelling decisions

One entry per decision, ≤ 3 lines: **what** was decided and **why**. Newest at the bottom.
If a decision is reversed, mark the old entry `(superseded by Dn)` instead of deleting it.

- **D1 (Iter 1):** Separate module facts, program rules and student state into separate YAML files. Why: the same
  module data must serve many programs and students, and exemptions are facts about a student, not about a module.
- **D2 (Iter 1):** `exempted=true` satisfies the module and its downstream prerequisites, and it uses no slot or units.
  Why: this matches how NUS exemptions work.
- **D3 (Iter 1):** Bridging modules (MA1301/X, ES1000/ES1103) are part of the global domain but are not program requirements.
  They are activated by student conditions. Why: they only apply to some students.
- **D4 (Iter 1):** English placement is one enum, `english_path`, not several booleans. Why: exactly one pathway applies.
- **D5 (Iter 1):** CS2101 + CS2103T form an atomic 8-unit same-semester bundle, not a prerequisite edge. Why: neither
  module comes strictly before the other.
- **D6 (Iter 1):** Run knobs (`target_semesters`, `max_units_per_semester`) are in `planning_scenario.yaml`.
  Why: the same student and program can then be tested against 5–8 semester targets without editing the degree data.
- **D7 (Iter 1):** ID/CD is modelled as exactly 3 placeholder modules with ≥ 2 ID and ≤ 1 CD. Why: this is the simplest
  encoding of the 12-unit rule while elective choice is out of scope.
- **D8 (Iter 1):** The solver is OR-Tools CP-SAT over boolean `x[m,s]`. Why: the formulation is already 0/1-linear, so it maps
  one-to-one, and it proves infeasibility. A hand-written backtracking search could be added later as an ablation.
- **D9 (Iter 1):** Objective = minimise the number of scheduled modules. This is only a tie-breaker, and the problem stays a CSP. Why: it stops
  pointless optional picks (e.g. both MA1301 and MA1301X). Modules outside required ∪ ID/CD ∪ prerequisite closure get no variables.
- **D10 (Iter 1):** `src/checker.py` re-implements the constraints without the solver. Why: it cross-checks the solver,
  and it will grade plans from the LLM-direct pipeline.
