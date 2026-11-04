# CS course-planning CSP

A constraint-satisfaction planner that answers *"can this student graduate in T
semesters, and with what schedule?"* for the NUS BComp(CS) degree. Built in
iterations of increasing realism (see `docs/history.md`, `docs/decisions.md`).

## Iteration 3 — richer requests + the LLM benchmark (current)

Adds per-request constraints (Special Terms, per-semester caps / leave of absence, CS-count cap,
FYP/UROP with the CP cap, pin/forbid/deadline), a proof suite for the oracle, a 35-instance
natural-language benchmark (`eval/instances/`), Pipeline A (Claude answering directly) and Pipeline B
(Claude translating the request into a spec that the CP-SAT solver solves), both graded by the
independent checker. Status and results: `docs/status.md`, `eval/results/`.

```bash
python eval/generate.py                                   # rebuild the benchmark corpus
cp .env.example .env                                      # then add ANTHROPIC_API_KEY
python eval/run_pipe_a.py --model all [--condition bare]  # LLM-direct runs -> eval/runs/
python eval/run_pipe_b.py --model all                     # LLM->spec->solver runs -> eval/runs/
python eval/score.py                                      # Table-3 metrics -> eval/results/
```

## Iteration 2 — full BComp(CS) AY2026/27

The whole 160-unit degree over module facts **frozen from the NUSMods AY2026/27
API** (units, real semester offerings, prerequisite trees, preclusions). Adds, on
top of the iter1 baseline: recursive prerequisite trees, placement-waived
bridging, preclusion groups, focus areas (3 primaries incl. one level-4000+),
≥12 units at level-4000, a 32-unit Breadth & Depth bucket, industrial experience
(exactly one option), a CP-coded cap, a 160-unit floor with Unrestricted-Elective
fillers, and optional per-instance preferences (workload balance, minimum load,
no gaps). Full write-up and the critical design audit: **`docs/iter2_plan.md`**;
formal semantics: `docs/solver_constraints.md` §`I2.*`.

```bash
pip install -r requirements.txt
python scripts/ingest_nusmods.py          # (re)build data/snapshot_2026-2027/
python src/model.py --iter2               # validate the iter2 model
python src/solver.py --iter2 --focus-area artificial_intelligence
streamlit run app/app.py                  # pick constraints, see SAT/UNSAT + plan
python -m pytest tests -q                 # full suite (iter1 + iter2 + iter3 + eval)
```

The solver (`src/solver.py`, OR-Tools CP-SAT) and an **independent** checker
(`src/checker.py`) implement every constraint twice, so the checker can both
cross-validate the solver and grade plans produced by other means (e.g. an LLM) —
the ground truth for the project's LLM-direct vs LLM→solver comparison.

---

# Iteration 1 model

This repo scaffold separates the problem into three data layers.

## 1. Module data

`data/modules.yaml`

Describes reusable facts about modules:

- units
- canonical / bridging / placeholder type
- semester offering
- ordinary prerequisites (`all_of`)
- conditional bridging prerequisites (`conditional -> one_of`)
- corequisites

It does **not** store whether a particular student is exempted.

## 2. Program data

`data/program_cs_iter1.yaml`

Describes what the Iteration 1 CS degree model requires:

- 8-semester planning horizon
- currently supplied required CS / Math / ULR / Ethics modules
- canonical GEA1000 / ES2660 choices
- generic GEC, GES and GEN placeholders
- the 12-unit ID/CD rule as exactly three 4-unit placeholder modules
- configurable semester unit cap (20 units for current Iteration 1 testing)

## 3. Student data

`data/student_example.yaml`

Describes one student:

- `completed[module]`
- `exempted[module]`
- `conditions.needs_math_bridging`
- `conditions.english_path`

In this Iteration 1 model, `exempted=true` means the module itself and downstream prerequisite requirement are treated as satisfied without scheduling that module.

## Bridging

MA1301 and MA1301X are in the global module domain but are not automatically degree requirements.

If:

```yaml
conditions:
  needs_math_bridging: true
```

then one of MA1301 / MA1301X must be satisfied before MA1521, MA1522, and CS1231S can be scheduled.

## Generate graph

```bash
pip install -r requirements.txt
python scripts/generate_prereq_graph.py
```

GitHub renders `docs/prerequisite_graph.md` as Mermaid.

## Validate data

```bash
python src/model.py
```

## Solve and check a plan

```bash
python src/solver.py                       # plan for the default student/scenario
python src/solver.py --target-semesters 5  # can they finish in 5 semesters?
python src/checker.py plan.json            # validate any plan, e.g. one written by an LLM
python -m pytest tests -q
```

## Current deliberate simplifications

- CS2105 and CS2107 are excluded from Iteration 1 because they are not part of the current graduation requirement set

- canonical CS modules only
- all modules assumed offered in both Semester 1 and Semester 2
- ES2660 fixed as the Critique & Expression choice
- GEA1000 fixed as the Data Literacy choice
- GEC/GES/GEN are generic placeholders
- ID/CD courses are generic placeholders
- preclusions and negative constraints are excluded
- English bridging field exists, but no bridging module is inserted until its actual code/rule is supplied


## English pathway

The student file contains exactly one `english_path`:

```yaml
conditions:
  english_path: direct_es2660
```

Allowed values:

- `direct_es2660`
- `es1103_required`
- `es1000_then_es1103`

This activates the appropriate conditional prerequisite chain without making ES1000/ES1103 universal CS-program requirements.


## Current canonical Iteration 1 size

The current canonical path contains **22 modules** and
**88 units**, excluding conditional bridging modules.

- Fixed required modules outside ID/CD: 19 modules = 76 units
- ID/CD pillar: exactly 3 modules = 12 units
- Total: 22 modules = 88 units

`CS2101 + CS2103T` are two separate 4-unit modules but form one 8-unit
same-semester scheduling bundle.

The completion horizon is configurable through `data/planning_scenario.yaml` (`target_semesters`).


## Planning scenario

Run-specific planning choices now live in `data/planning_scenario.yaml` rather
than in module or degree data.

```yaml
target_semesters: 8
max_units_per_semester: 20
```

This lets the same CS program and student profile be tested for different
completion targets (for example 5, 6, 7, or 8 semesters) without rewriting the
degree definition.
