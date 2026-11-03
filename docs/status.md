# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-11-02_

## Iteration 3: richer requests + the benchmark (scope FROZEN 2026-10-20: no iter4, no new features)

**Goal:** add realistic per-request constraints, prove the oracle (solver + checker) correct, and build
the LLM-direct vs LLM→solver benchmark. Plans: `docs/iter3_plan.md`, `docs/benchmark_design.md`
(Part A oracle proof, Part B corpus), `docs/evaluation_plan.md`, `docs/ui_ux_plan.md`.

**Where we are:** iter3 + the 14 `Issues.md` corrections done (docs-first, solver/checker parity,
`tests/test_rule_fixes.py`); corpus regenerated against the fixed oracle (36 instances, 18 SAT / 18
UNSAT, 0 mismatches); both pipelines re-swept and re-scored. **291 tests pass.** Report §5.4/6/7/8
filled in `cs3263.tex`. Branch `iter3-benchmark-oracle-ui`, not committed/pushed.

**Headline:** the realism corrections now SEPARATE the pipelines (were both at ceiling). Pipe B
(translator+solver) = 100% feasibility + 100% valid plans; Pipe A (direct, full) = 97.2% feasibility
but only 2–3/18 valid plans (internship-occupancy violations) and misses `fyp_and_urop` (reproduces the
old CP-cap bug). Full table: `eval/results/pipe_a_2026-11-02.md`, `pipe_b_2026-11-02.md`, `table3*`.

### Done
- Constraints C1–C5 (§I2.14–I2.18), CP4101 may replace the internship (D29). Decisions D25–D30.
- Oracle proof `tests/test_oracle.py` (A1/A3/A4); A5 external validation PASSED. Realism scorer
  `src/plan_quality.py` (D31,D33); app per `docs/ui_ux_plan.md` (D32).
- **Issues.md fixes (D45–D50 + reporting):** ID/CD = qualifying allocation (D45); `nOf` at-least-n
  threshold through ingest/solver/checker/prompt (D46); 12u CP cap is B&D-ALLOCATED, FYP+UROP feasible
  (D47); English bridges mandatory per QET band, Band 2 waives only ES1000 (D48); UROP=CP3209 + distinct
  CP3106 (D49); CP3209 2-sem before FYP + full-semester internship occupancy (D50); solver status honesty
  (UNKNOWN≠infeasible), app hides checker-rejected plans, total-var count, monotone/bounded probes,
  separate semester/cap slacks. See `docs/solver_constraints.md` I2.1/I2.2/I2.4/I2.9/I2.17/I2.19.
- Pipe A (D37–D40) + Pipe B (D41–D44) re-run on the 36-instance corpus; baselines always-SAT 50%,
  canonical-4yr 3/18 realism 90.5.

### Active simplifications — see program_cs.yaml `assumptions`
- Canonical CS modules only; by-arrangement modules default to both semesters.
- No per-bucket unit partition: UE is a residual filler to 160u; Computing units beyond 32u B&D count as UE.
- Only Unrestricted Electives remain generic placeholders (`*_GENERIC*`).
- Part-time / sequential internships stay off the per-semester cap (vacation); 6-month full-semester
  internships occupy their slot (I2.19) but their 12u still land in one slot (not load-split).
- CP3209 UROP counts credit once in its start slot (2-sem load-split deferred); math bridging via waiver.
- A5 benign: Critique = ES2660 only, Data Literacy = GEA1000 only, industry experience as fixed bundles.

### Next
1. Commit + push the Issues.md fixes, refreshed corpus and re-swept results; freeze/tag the oracle.
2. Hand-author the NL prompts (B7: variety/implicitness) over the auto-drafts, then re-sweep for the
   accuracy comparison under implicit phrasing; add repeats for variance.
3. Obfuscation (`rename`) ablation + Pipe B refinement ablation (spec-validation errors only, D41).

### Open issues
- App default deadlines (CS1101S→sem 1, GEA1000→sem 2, D32) can make a blocked / Special-Term sem 1/2
  infeasible in the app only; workload editor holds one light + one heavy cap value.
- `docs/solver_constraints.md` iter1 §7 wording (cap lives in scenario, not `program_cs_iter1.yaml`).
- `model.py --iter2` prints 464 benign external-prereq warnings.
- Bare grading is closed-world (real GE/ID-CD codes outside the wired subset score invalid); a
  pillar-aware lenient re-grade is a pending team decision.
- `generate.py`: `part_load_worklife` can regenerate to a different optimal plan across ortools builds.
