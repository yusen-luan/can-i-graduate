# can-i-graduate — CLAUDE.md

CS3263 (Foundations of AI, NUS, AY2026/27 Sem 1) team project, 3-person team.
**Topic:** an AI assistant for NUS students' degree/module planning, which is built as a
**constraint satisfaction problem (CSP)** that answers "can this student graduate in T semesters,
and with what schedule?"

## The research question (why this repo exists)

The course project is **not** only about building a planner. The graded question is:

> On this problem, how does a frontier LLM that **reasons directly** over a natural-language planning
> request compare with an LLM that **translates** the request into a formal spec that a
> **classical solver** then solves?

So the repo has to end up containing: (1) a formal CSP model + solver, (2) many problem instances
written in natural language, with ground truth, (3) both LLM pipelines, and (4) an evaluation with
analysis (difficulty, ablations, failure cases, realism of assumptions, responsible AI).
See `docs/project_brief.md` for the full brief, grading criteria and deadlines.

## Strategy: iterative complexity

We start with a deliberately simplified degree model (Iteration 1) and add realism in each iteration,
for example real term offerings, preclusions, real elective choices and student preferences, so that the
model mirrors how real students plan more closely. Each iteration's simplifications are listed explicitly so
that the evaluation can show *where* LLM-direct reasoning breaks down as complexity grows.

## Current state

@docs/status.md

## Repo map

| Path | What it is |
|---|---|
| `data/modules.yaml` | Module facts: units, kind, offered terms, prereqs (`all_of`, `conditional`→`one_of`), coreqs. No student info. |
| `data/program_cs_iter1.yaml` | Degree requirements for the current iteration (required modules, ULR/GE groups, ID/CD rule, bundles). |
| `data/student_example.yaml` | One student: `completed`, `exempted`, `conditions` (math bridging, `english_path`). |
| `data/planning_scenario.yaml` | Per-run knobs: `target_semesters`, `max_units_per_semester`. |
| `src/model.py` | Loads + validates data; shared helpers (`prereq_clauses`, `term_of`, ...) used by solver and checker. |
| `src/solver.py` | CP-SAT solver: `build_and_solve(...)` → `SolveResult` (status, plan by semester). |
| `src/checker.py` | Solver-independent plan validator: `check_plan(...)` → list of violations. |
| `tests/` | pytest suite (solver plans always pass checker; semantics; checker negatives). |
| `scripts/generate_prereq_graph.py` | Regenerates `docs/prerequisite_graph.*`. |
| `docs/solver_constraints.md` | **Authoritative** formal semantics of every constraint (x[m,s] formulation). |
| `docs/decisions.md` | Log of modelling decisions + rationale. Read before changing semantics. |
| `docs/history.md` | Compressed summaries of finished iterations. |
| `README.md` | Human-facing overview of the data model. |
| `misc/` | Course handouts (untracked, local only). `docs/project_brief.md` is the committed digest. |

## Commands

```bash
pip install -r requirements.txt
python src/model.py                      # validate data
python scripts/generate_prereq_graph.py  # regenerate prerequisite graph
python src/solver.py [--target-semesters N] [--max-units U] [--student F] [--json]
python src/checker.py plan.json          # validate a {"1": [...], ...} plan
python -m pytest tests -q
```

## Conventions

- **Keep the three data layers separate.** Module facts, program rules, student state and run scenario
  never leak into each other (e.g. exemptions belong to the student, not the module).
- Change semantics in `docs/solver_constraints.md` **first**, then update data and code to match.
- Every simplification has to be written down (in the program YAML `assumptions` and in `status.md`).
  Unstated simplifications ruin the evaluation.
- A new constraint goes into **both** `solver.py` and `checker.py`, plus a test. The checker must never import the solver.
- Placeholders use the `*_GENERIC*` naming. Real module codes are only used for real modules.
- The platform is Windows. Scripts need to work with `python` from the repo root.

## Keeping context lean (anti-bloat rules)

This file is loaded in every session, so it must stay **≤ 100 lines** and describe only stable facts.
- Volatile state (in progress, next steps, open questions) belongs in `docs/status.md`, which is **≤ 60 lines** and only covers the current iteration.
- When an iteration ends, compress it into ≤ 8 lines in `docs/history.md` and reset `status.md`.
- Decisions go in `docs/decisions.md` as one entry of ≤ 3 lines each. Don't restate them elsewhere. Link instead.
- Details belong in topic docs (`docs/*.md`). Here, put a link, not a copy.
- Run the `/checkpoint` skill after finishing a task to apply these rules.
