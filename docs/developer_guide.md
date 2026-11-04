# Developer guide — working on can-i-graduate from Iteration 2 onwards

For a future Claude / Codex (or human) picking this up. Read this + `CLAUDE.md`
(repo map, conventions, commands) + `docs/iter2_verification.md` (what the degree
rules actually are and why) before changing anything. `docs/solver_constraints.md`
is the **authoritative** formal spec — change it first, then code.

## 1. What this project is (one paragraph)
A CS3263 research project: model the NUS BComp(CS) degree as a CSP that answers
"can this student graduate in T semesters, and with what schedule?". The CSP +
an **independent checker** are the *ground-truth oracle* for the real research
question — comparing an LLM that reasons directly vs an LLM that translates to a
spec a solver solves. So **correctness of the oracle beats feature breadth**.

## 2. Architecture / data flow
```
NUSMods API ──ingest_nusmods.py──> data/snapshot_2026-2027/modules.yaml (+raw, +preclusions)
                                            │
 data/program_cs.yaml  (degree rules) ──────┤
 data/focus_areas.yaml (11 areas)           │
 data/generic_modules.yaml (UE + C&E halves)├─ model.load_iter2() ─> (modules, program,
 data/ge_pillars.yaml / id_cd.yaml (ref)    │                         student, focus, preclusions)
 data/student_iter2.yaml (student)          │
 data/scenario_iter2.yaml (run knobs) ──────┘
                                            │
         solver.build_and_solve_iter2() ── CP-SAT ──> SolveResult(status, plan{sem:[mods]})
                                            │                  │
         checker.check_plan_iter2() <───────┘ (independent) ───┘  (tests assert checker(plan)==[])
                                            │
              app/app.py (Streamlit) ───────┘  src/solver.py --iter2 (CLI)

eval/generate.py ─> eval/instances/*.json {nl_prompt, formal, ground_truth (solver), meta}
eval/run_pipe_a.py (llm/ prompts + Claude API) ─> eval/runs/pipe_a/<model>[-bare]/*.json
eval/score.py ─ check_plan_iter2 + plan_quality ─> eval/results/ (Table-3 rows)
```

**Two-layer split, do not merge:** module *facts* (NUSMods snapshot) vs degree
*rules* (hand-curated YAML from the cohort page / Bulletin). Student state and run
scenario are separate again (iter1 convention, D1).

## 3. The module schema (snapshot + generics)
```yaml
CS2040S:
  title: ...            units: 4        level: 2000        # level = first digit*1000
  offered_terms: [1, 2]                                    # from NUSMods semesterData
  kind: canonical       pillar: cs_foundation              # pillar drives bucket membership
  prerequisites: {tree: {all_of:[{one_of:[...]}, ...]}, conditional: []}
  preclusion_group: data_structures                        # -> preclusions.yaml
  category: ID|CD       # only on ID/CD modules
```
`pillar` values and what they mean for constraints: `cs_foundation`,
`math_statistics`, `university_level_requirements`, `computing_ethics`,
`interdisciplinary_cross_disciplinary`, `breadth_depth`, `industrial_experience`,
`unrestricted_electives`, `*_bridging`, `service_learning`. **B&D unit bucket =
pillar ∈ {breadth_depth, industrial_experience}.** Buckets are disjoint by pillar,
which is what prevents unit over-counting.

## 4. How a constraint is implemented (THE recipe — follow every time)
A constraint lives in **three** places and must stay consistent:
1. `docs/solver_constraints.md` — write/update the formal rule first (section `I2.x`).
2. `src/solver.py :: build_and_solve_iter2` — add CP-SAT constraints over `x[m,s]`.
   Helpers available in scope: `taken(m)`, `sat(m)` (pre-satisfied ∨ scheduled),
   `held(m)` (completed ∨ scheduled, NOT exempted — for preclusions),
   `units_where(pred)`, `reify_before(tree, s)` (prereq-tree boolean).
3. `src/checker.py :: check_plan_iter2` — re-implement the SAME rule by *reading*
   the plan (never import the solver). Mirror helper: `satisfied(m)`, `held(m)`,
   `sat_units(pred)`, `tree_satisfied(tree, pred)`.
4. Add a test in `tests/test_iter2.py`: (a) a solved plan satisfies it, (b) the
   checker flags a hand-broken plan.
5. Log a one-line decision in `docs/decisions.md` (Dn) and update `status.md`.

**Parity is sacred:** the test `solver plan ⇒ checker == []` must stay green,
including the **seed-sweep** test (`test_solver_checker_parity_across_seeds`),
which runs the solver under several CP-SAT seeds so parity bugs that only appear
for *some* optimal solutions get caught. The solver is `num_workers=1` + fixed
`seed` for reproducibility.

## 5. The constraints currently enforced (both sides)
at-most-once · required modules · ULR pillars (≥1 of each `satisfied_by`) ·
prerequisite tree (AND/OR, DNF-safe) · placement-waived bridging · preclusions ·
CS2101+CS2103T same-semester bundle · real offered terms · per-sem unit cap
(industrial excluded — vacation) · overload ceiling 28 · ID/CD (3; ≥2 ID ≤1 CD) ·
focus area (3 primaries incl ≥1 L4000) · ≥12u L4000 · B&D ≥32u · industrial =
exactly one option (no extras) · CP-coded ≤12u · year-long C&E service-learning
(X Term1 → contiguous Y Term2, X not in last sem) · total ≥160u · optional
scenario preferences (heavy_conflicts / min-load / no-gaps). **Iter3:** Special-Term
`term_layout` (I2.14) · per-semester cap vector, 0 = leave (I2.15) · CS-count cap
(I2.16) · FYP/UROP with eligibility + CP cap, CP4101 may replace the internship
(I2.17) · pin / forbid / deadline (I2.18).

Objective: `minimise 100·total_units + module_count` — only a tie-break, so it
stays a feasibility CSP; with the 160 floor it lands at exactly 160.

## 6. Adding / refreshing modules
`python scripts/ingest_nusmods.py --ay <AY>`: edit the `SEED` set (and the
`ID_CODES`/`CD_CODES`/`ULR_GE_PREFIXES` tags + `pillar_of`) to add codes, then
re-run. It writes the snapshot and a `validation_report.md` (missing codes, unit
or offered-term anomalies vs assumptions). Always trust NUSMods over faculty pages.

## 7. Running
```bash
pip install -r requirements.txt
python src/model.py --iter2                 # validate the iter2 model
python src/solver.py --iter2 [--target-semesters N --max-units U --focus-area A --industrial-option C]
python -m pytest tests -q                    # full suite, must stay green
streamlit run app/app.py                     # frontend
```

## 8. Known limitations / deliberate simplifications (iter2)
- ULR pick-lists (GEC/GESS/GEN), ID/CD wire a *verified subset* of the full lists
  (`data/ge_pillars.yaml`, `data/id_cd.yaml`); UE is generic placeholders.
- Special Terms (3,4) only when a request sets `term_layout` (I2.14); by default
  plans use Sem 1/2 and internships are handled by excluding their units from the
  per-sem cap.
- CP3107/CP3110 appear in both C&E and Industrial Experience; the double-role is
  not modelled (kept as industrial).
- The 32u B&D is a floor; extra Computing counts as UE (no label partition, D15).
- Corequisites beyond the CS2101+CS2103T bundle are not modelled.
- `program_cs_iter1.yaml` + iter1 solver/checker/tests are kept intact; iter2 is
  additive. Don't break the 49 iter1 tests.

## 9. Roadmap
Iter3 scope is frozen (no iter4): Special Terms, UROP and the benchmark + Pipe A
and Pipe B (LLM → spec → solver, D41–D43) harnesses are done (NOC dropped, D33). Remaining:
ablations, write-up — see `docs/status.md` "Next". Not planned: full GE/ID/CD
lists in the CSP (only a verified subset is wired), accurate ATAP occupancy.
