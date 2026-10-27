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
| `data/modules.yaml`, `program_cs_iter1.yaml`, `student_example.yaml`, `planning_scenario.yaml` | **Iter 1** data: module facts, degree rules, one student, run knobs. |
| `data/snapshot_2026-2027/` | **Iter 2** frozen NUSMods snapshot: `modules.yaml` (+ `.raw.json`), `preclusions.yaml`, `validation_report.md`, `module_list.json` (all 6,769 AY codes; eval only). |
| `data/program_cs.yaml` | **Iter 2** full 160u degree: required, ULR/ID-CD, breadth_depth (focus/L4000/team/industrial/CP), UE, `assumptions`. |
| `data/focus_areas.yaml`, `generic_modules.yaml`, `student_iter2.yaml`, `scenario_iter2.yaml` | **Iter 2** focus lists, UE placeholders + C&E service-learning halves, student, scenario (+ preferences). |
| `data/ge_pillars.yaml`, `data/id_cd.yaml` | **Iter 2** authoritative full GE-pillar and ID/CD course lists (CSP wires a verified subset). |
| `src/model.py` | Loads + validates both iters; shared helpers (`prereq_clauses`/`tree_satisfied`, `bridging_waived`, `term_of`, ...). |
| `src/solver.py` | CP-SAT solver: iter1 `build_and_solve` / iter2 `build_and_solve_iter2`, `solve_iter2`, `explain_infeasible_iter2` → `SolveResult`. |
| `src/checker.py` | Solver-independent validators: `check_plan` (iter1) / `check_plan_iter2`. Never imports the solver. |
| `src/plan_quality.py` | Soft 0–100 realism scorer for a *valid* plan (solver or LLM); not a constraint. |
| `eval/` | Benchmark: `generate.py` → `instances/*.json` {nl_prompt, formal, ground_truth, meta}; `baselines.py` trivial controls; `run_pipe_a.py` LLM-direct runs (`--condition full|bare`) → `runs/`; `score.py` grades all Table-3 rows → `results/`. |
| `llm/` | Claude API layer: `client.py` (models, `.env` key, cost), `prompts.py` (Pipe A rules+catalog / bare prompts, answer parsing). Key in git-ignored `.env`. |
| `app/app.py` | Streamlit frontend over `solve_iter2`: benchmark-profile picker + iter3 controls → SAT/UNSAT → plan grid. |
| `data/profiles/benchmark_profiles.yaml` | Representative student archetypes (student+scenario bundles) for the app picker + eval corpus; `demo_iter3_*` = CLI example. |
| `scripts/ingest_nusmods.py` | Rebuilds the NUSMods snapshot. `scripts/generate_prereq_graph.py` regenerates `docs/prerequisite_graph.*`. |
| `tests/` | pytest: `test_solver.py` iter1, `test_iter2.py`, `test_oracle.py` (oracle proof), `test_profiles.py`, `test_eval_prompts.py`, `test_pipe_a.py` (offline harness). |
| `docs/developer_guide.md`; `AGENTS.md` | **Start here for iter2+ work**: architecture, schema, the add-a-constraint recipe. `AGENTS.md` is the agent entry point. |
| `docs/solver_constraints.md` | **Authoritative** formal semantics (x[m,s]); iter2 section `I2.*`. `iter2_verification.md` = universe/rule verification; `iter2_plan.md` = plan + audit. |
| `docs/decisions.md` | Modelling decisions + rationale (read before changing semantics). `docs/history.md` = finished iterations. |
| `docs/evaluation_plan.md`, `docs/iter3_plan.md` | Research deliverable blueprint (LLM-direct vs LLM→solver: corpus, profiles, pipelines, metrics); iter3 preference roadmap. |
| `README.md`; `misc/` | Human overview; course handouts (untracked, digest in `docs/project_brief.md`). |

## Commands

```bash
pip install -r requirements.txt
python src/model.py [--iter2]            # validate data (iter1 / iter2)
python scripts/ingest_nusmods.py         # rebuild data/snapshot_2026-2027/ from NUSMods
python src/solver.py [--target-semesters N] [--max-units U] [--student F] [--json]   # iter1
python src/solver.py --iter2 [--target-semesters N] [--max-units U] [--focus-area A] [--industrial-option C]
python src/checker.py plan.json          # validate a {"1": [...], ...} plan (iter1)
python -m pytest tests -q
python eval/generate.py                  # regenerate the benchmark corpus (deterministic)
python eval/baselines.py                 # score always-SAT / canonical-4yr controls
python eval/run_pipe_a.py --model haiku|sonnet|opus|all [--condition bare] [--dry-run] [--limit N]   # Pipe A (.env key)
python eval/score.py                     # Table-3 metrics for controls + Pipe A runs + oracle
streamlit run app/app.py                 # iter2 frontend
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
