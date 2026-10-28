# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-28_

## Iteration 3: richer requests + the benchmark (scope FROZEN 2026-10-20: no iter4, no new features)

**Goal:** add realistic per-request constraints, prove the oracle (solver + checker) correct, and build
the LLM-direct vs LLM→solver benchmark. Plans: `docs/iter3_plan.md`, `docs/benchmark_design.md`
(Part A oracle proof, Part B corpus), `docs/evaluation_plan.md`, `docs/ui_ux_plan.md`.

**Where we are:** iter3 + review fixes + Pipe A committed on branch `iter3-benchmark-oracle-ui` (not
pushed). Pipe B built + swept (uncommitted, ~$0.92 incl. a superseded run). Both pipelines are at
ceiling on auto-draft prompts; they currently separate on cost, and from Pipe A `bare` on accuracy. **269 tests pass.**

### Done
- Constraints: C5 special-term `term_layout` (§I2.14), C1 per-sem cap vector (§I2.15), C2 CS-count cap
  (§I2.16), C3 internship+FYP+UROP w/ CP-cap interaction (§I2.17), C4 pin/forbid/deadline (§I2.18).
  CP4101 dissertation may replace the internship for `eligible_fyp` students (D29). Decisions D25–D30.
- Oracle proof `tests/test_oracle.py` (A1 mutation, A3 metamorphic, A4 UNSAT); A5 external validation PASSED.
- Corpus: 19 profiles (`benchmark_profiles.yaml`, `tests/test_profiles.py`) + stress slice → 35 instances
  (17 SAT / 18 UNSAT; `meta.tier` 7 T1 / 1 T2 / 10 T4) with measured difficulty; baselines always-SAT 49%,
  canonical-4yr 3/17 (D33). Realism scorer `src/plan_quality.py` (D31, D33); app per `docs/ui_ux_plan.md` (D32).
- Iter3 review fixes (2026-10-21): prompts built only from the formal instance (D36); C4 code validation +
  waived-bridge parity (D35); exact `no_empty_semesters`; exempted units count (D34).
- Pipe A (LLM-direct, D37–D40): `full` 35/35 + 17/17 valid for Haiku/Sonnet/Opus 5.5; `bare` Feas 83–91%,
  Plan Valid 0/17 → `eval/results/pipe_a_2026-10-27.md`.
- Pipe B (LLM→spec→solver, D41–D44): `llm/spec.py`, translator prompt, `eval/run_pipe_b.py`, fidelity +
  warm/cold cost profile in `eval/score.py`, `tests/test_pipe_b.py`. All 3 models 35/35, 17/17 valid,
  exact spec 35/35; 3.6–10× cheaper per request (warm cache), 2.4–5× (cold) → `eval/results/pipe_b_2026-10-28.md`.

### Active simplifications — see program_cs.yaml `assumptions`
- Canonical CS modules only; by-arrangement modules default to both semesters.
- No per-bucket unit partition: UE is a residual filler to 160u; Computing units beyond 32u B&D count as UE.
- Only Unrestricted Electives remain generic placeholders (`*_GENERIC*`).
- Industrial experience is excluded from the per-semester cap (approximates vacation/special-term internship).
- Math/English bridging handled by placement waiver for the default student, not scheduled.
- A5 benign: Critique = ES2660 only, Data Literacy = GEA1000 only, industry experience as fixed bundles.

### Next
1. Commit Pipe B; freeze/tag the oracle.
2. Hand-author the NL prompts (B7: variety/implicitness) over the auto-drafts. This is the only way
   Pipe A `full` vs Pipe B can separate on accuracy; re-sweep both after (Pipe B ~$0.46/sweep).
3. Repeats for variance, obfuscation ablation (`rename` hook in `llm/prompts.py` + `llm/spec.py`),
   Pipe B refinement ablation (feed back spec-validation errors only, D41); rewrite report §7.2.

### Open issues
- A solver timeout (`UNKNOWN`) is read as infeasible (`SolveResult.feasible`); Pipe B already treats it as
  no verdict, but `eval/generate.py` should refuse `UNKNOWN` before harder instances are added.
- App default deadlines (CS1101S→sem 1, GEA1000→sem 2, D32) make a blocked or Special-Term sem 1/2
  infeasible in the app only. App workload editor holds one light + one heavy cap value only.
- `docs/solver_constraints.md` iter1 §7 wording (cap lives in scenario, not `program_cs_iter1.yaml`).
- `model.py --iter2` prints 464 benign external-prereq warnings.
- Bare grading is closed-world: 3/51 bare plans use real GE/ID-CD courses outside the wired subset; a
  pillar-aware lenient re-grade is a pending team decision.
- Report errata (vs `eval/score.py`): oracle realism is 89.2 (not 89.4), oracle time ~0.3s incl. model
  build; canonical-4yr passes focus_switch/nearbnd_min_horizon/on_track_fresh (not behind_retaking).
- `generate.py`: `part_load_worklife` regenerates to a different optimal plan on ortools 9.15; kept as committed.
- Haiku Pipe B lists the closing question under `unsupported_requests` on 7/35 (harmless; prompt tweak
  would need a re-sweep).
