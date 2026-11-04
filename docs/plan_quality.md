# Plan-quality (realism) evaluator

## Why it exists
The repo has two oracles already: the **solver** (produces a plan) and the **checker** (decides HARD
validity — does a plan satisfy every degree rule). Neither answers *"is this a plan a human advisor
would actually recommend?"* A plan can be perfectly valid yet unreasonable: 8 MC one semester then
28 the next, all GE modules dumped in the final semester, a level-4000 module in year 1, or gaps
between enrolled semesters. `src/plan_quality.py` is the **soft** third oracle: it scores a valid plan
0–100 on advising-sensible heuristics, with per-metric sub-scores and human-readable flags.

## What it is *not*
- **Not a constraint.** The CSP stays a pure feasibility problem (decision D9). This module only
  *judges* a finished plan; it never feeds back into the solver's hard constraints.
- **Not a validity check.** A high realism score on an *invalid* plan is meaningless — always run
  `check_plan_iter2` first. Quality is only interesting among valid plans.
- **Not learned / not absolute.** Realism is subjective, so the heuristics are transparent and the
  score is calibrated by **ranking** (a balanced plan must out-score a degraded one — see
  `tests/test_plan_quality.py`), not against an absolute ground truth.

## The metrics (weighted mean → 0–100)
| Metric | w | Rewards |
|---|---|---|
| `workload_balance` | .25 | even per-semester loads **and** loads within the requested cap (not lumpy, not absurd) |
| `cs_intensity` | .20 | ≤ 3 hard (≥3000-level Computing) modules per semester |
| `contiguity` | .15 | no empty semesters between enrolled ones |
| `level_progression` | .15 | level-4000 work in the later half of the plan |
| `foundation_early` | .10 | CS-foundation core in the first half |
| `breadth_spread` | .10 | GE/ULR spread across semesters, not clustered |
| `experiential_timing` | .05 | internship / FYP in the later years |

Weights are a deliberate, documented editorial choice (balance and intensity dominate because those
are what students complain about most); they are easy to re-tune and the ranking tests guard the
*directions*, not the exact weights.

## How it plugs into the research
- **A plan-quality axis for the evaluation** (distinct from plan validity): score the solver's plan,
  the LLM-direct plan and the translator's plan on the same footing and compare — *valid-but-worse*
  plans become visible. `eval/generate.py` already records the solver plan's `meta.quality.realism`
  and flags per instance.
- **The scoring function for a future soft-objective ablation** (iter3_plan.md "Soft workload
  objective"): if we ever add an optimisation variant that *maximises* realism, this is its objective
  — kept strictly as an ablation, never the feasibility baseline (D9).

## Usage
```bash
python src/plan_quality.py plan.json      # {"1": ["CS1101S", ...], ...} against the iter2 data
```
Programmatic: `score_plan(plan, modules, program, student, scenario) -> {overall, metrics, flags}`.
