# Status — current iteration only (≤ 60 lines; older iterations → docs/history.md)

_Last updated: 2026-10-21_

## Iteration 3: richer requests + the benchmark (scope FROZEN 2026-10-20: no iter4, no new features)

**Goal:** add realistic per-request constraints, prove the oracle (solver + checker) correct, and build
the LLM-direct vs LLM→solver benchmark. Plans: `docs/iter3_plan.md`, `docs/benchmark_design.md`
(Part A oracle proof, Part B corpus), `docs/evaluation_plan.md`, `docs/ui_ux_plan.md`.

**Where we are:** iter3 + review fixes committed on branch `iter3-benchmark-oracle-ui` (0da4558,
4272f7a; not pushed). Solver/checker/corpus/app complete; the LLM harness is not started.
**249 tests pass.**

### Done
- Constraints: C5 special-term `term_layout` (§I2.14), C1 per-sem cap vector (§I2.15), C2 CS-count cap
  (§I2.16), C3 internship+FYP+UROP w/ CP-cap interaction (§I2.17), C4 pin/forbid/deadline (§I2.18).
  CP4101 dissertation may replace the internship for `eligible_fyp` students (D29). Decisions D25–D30.
- Oracle proof `tests/test_oracle.py`: A1 one-mutation-per-rule, A3 metamorphic M1–M5, A4 UNSAT mechanism.
  A5 external validation vs CS cohort 2026/27 page PASSED (`iter2_verification.md` A5).
- Corpus: 19 profiles in `data/profiles/benchmark_profiles.yaml` (`tests/test_profiles.py`: verdict,
  checker-clean, A4 relax→SAT for every UNSAT one) + stress slice in `eval/generate.py` → 35 instances
  (17 SAT / 18 UNSAT, 0 mismatches) in `eval/instances/`, measured difficulty + coverage tags.
  `eval/baselines.py`: always-SAT 49%, canonical-4yr plan valid 3/17. SEP/exchange + NOC dropped (D33).
- Realism: `src/plan_quality.py` soft 0–100 scorer (in eval meta, not the app); objective prefers fewer
  and focus-aligned Computing modules (D31, D33).
- App `app/app.py` reworked (`docs/ui_ux_plan.md`): profile picker seeds every control incl. module
  requests; app-only advising defaults (D32).
- Iter3 review fixes (2026-10-21): prompts built only from the formal instance — 16/35 leaked the
  verdict (D36, `tests/test_eval_prompts.py`); C4 codes validated + waived-bridge parity (D35);
  `used`/`no_empty_semesters` encoded exactly (old one was a no-op and capped heavy semesters);
  explainer probes the real instance; difficulty probes keep `term_layout`; no `wall_time_s` in meta
  (regeneration now byte-identical); exempted units count toward totals (D34). Corpus regenerated —
  the committed instances were stale w.r.t. the committed solver.

### Active simplifications — see program_cs.yaml `assumptions`
- Canonical CS modules only; by-arrangement modules default to both semesters.
- No per-bucket unit partition: UE is a residual filler to 160u; Computing units beyond 32u B&D count as UE.
- Only Unrestricted Electives remain generic placeholders (`*_GENERIC*`).
- Industrial experience is excluded from the per-semester cap (approximates vacation/special-term internship).
- Math/English bridging handled by placement waiver for the default student, not scheduled.
- A5 benign: Critique = ES2660 only, Data Literacy = GEA1000 only, industry experience as fixed bundles.

### Next
1. Freeze/tag the oracle.
2. Hand-author the NL prompts (B7: variety/implicitness) over the auto-drafts.
3. Build the harness per `docs/evaluation_plan.md`: LLM-direct + LLM→solver graded by `check_plan_iter2`
   + `plan_quality`, Opus/Sonnet/Haiku + obfuscation ablation (needs API budget/keys).

### Open issues
- A solver timeout (`UNKNOWN`) is read as infeasible (`SolveResult.feasible`); every current instance
  resolves, but `eval/generate.py` should refuse `UNKNOWN` before harder instances are added.
- App default deadlines (CS1101S→sem 1, GEA1000→sem 2, D32) make a blocked or Special-Term sem 1/2
  infeasible in the app only.
- App workload editor holds one light and one heavy cap value; profiles with differing caps collapse.
- `docs/solver_constraints.md` iter1 §7 wording (cap lives in scenario, not `program_cs_iter1.yaml`).
- `model.py --iter2` prints 464 benign external-prereq warnings.
