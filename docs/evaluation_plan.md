# Evaluation plan — LLM-direct vs LLM→solver on the iter2 degree CSP

The graded research question (see `docs/project_brief.md`):

> On the NUS degree-planning CSP, how does a frontier LLM that **reasons directly** over a
> natural-language planning request compare with an LLM that **translates** the request into a
> formal spec that our **classical CP-SAT solver** then solves?

This doc is the blueprint for the evaluation deliverable: the benchmark corpus, the two pipelines,
the metrics/ablations, and the mapping from evidence → report sections. It assumes iter2 is frozen
(`build_and_solve_iter2` / `solve_iter2` / `explain_infeasible_iter2` in `src/solver.py`;
`check_plan_iter2` in `src/checker.py`; constraint semantics I2.1–I2.13 in
`docs/solver_constraints.md`).

---

## 0. Why our setup is a strong instance of this question

- We own a **verified ground-truth oracle**: the CP-SAT solver *and* an independent `check_plan_iter2`
  that never imports the solver. The checker grades **both** pipelines impartially (including the one
  that used the solver). State this explicitly — it is our main methodological advantage.
- The CSP is **binding and real** (real NUSMods AY2026/27 facts, single-sem offerings, deep prereq
  chains, focus/L4000 depth, 160u accounting), not a synthetic puzzle — so failure modes are the
  realistic ones (stale catalog data, ambiguous NL, preclusion edge cases).

## 1. Prior work we position against (full citations in the report)

| Work | Relevance to us |
|---|---|
| Reality Check of LMs as Formalizers on CSPs (arXiv 2505.13252) | Closest prior art: same solver-vs-formalizer question on CSPs. Findings to test against: formalizer is **more robust to complexity** but underperforms direct in 15/24 settings; **translation fidelity** is the bottleneck. Our novelty: a real, verified, single-domain oracle. |
| Logic-LM (Pan et al., EMNLP-F 2023, 2305.12295) | Template for the translator pipeline + the **self-refinement** loop (feed solver errors back). +39.2% over prompting, +18.4% over CoT. Source of our refinement ablation. |
| PlanBench (Valmeekam et al., NeurIPS 2022, 2206.10498) | Benchmark-construction method (NL template + canonical formal file + mechanical validation); finding that LLM planning collapses under **label obfuscation** → motivates our obfuscation ablation. |
| ConstraintBench (2602.22465) | Metric framing: **feasibility is the primary bottleneck**; separate feasibility-decision from plan validity/optimality. |
| ConstraintLLM (EMNLP 2025); BACP / university timetabling CSP canon | External-validity + "this is a recognized NP-hard CSP family, CP-SAT is standard" framing. |

## 2. Benchmark corpus

### 2.0 There is ONE input, in two parts; difficulty is MEASURED, not assumed
Everything the planner consumes is user-provided input. It splits into three sources by the repo's
"three data layers" convention — but only the last two are per-instance input:

- **World facts** (NOT input) — module offerings, prereq trees, preclusions. Fixed NUSMods snapshot.
- **Student profile** (input) — *who the student is / their history*. → `student_*.yaml` (§2.1).
- **Planning request** (input) — *what they are asking for / their goal*. → `scenario_*.yaml` (§2.2).

So an instance's input is the pair **(profile, request)**. "Difficulty" is **not** a third input axis —
it is an *emergent property* of the whole instance (a 7-semester target is trivial for an on-track
student and infeasible for one who is behind). We therefore **measure** difficulty per instance from
solver signals (§2.4) and analyse accuracy against the measured value, rather than asserting a tier
ordering. The old T0–T6 ladder survives only as a **sampling recipe** to guarantee easy→hard coverage
and to exercise each constraint family (§2.5).

### 2.1 What is inside the PROFILE (student state) — `data/profiles/*.yaml`
Facts about the student, true before planning. Current schema (from `student_iter2.yaml`):

| Field | Meaning |
|---|---|
| `completed: {CODE: …}` | modules already passed |
| `exempted: {CODE: …}` | waived without credit (satisfies requirement, no units) |
| `conditions.needs_math_bridging` | true ⇒ must schedule MA1301/X before MA1521/MA1522/CS1231S |
| `conditions.english_path` | `direct_es2660` \| `es1103_required` \| `es1000_then_es1103` |
| `has_h2_math` | false ⇒ MA1301/X needed, consumes a UE slot |
| `eligible_fyp` | true ⇒ CP4101 may substitute industrial experience |
| `per_semester_cap: {s: u}` | 🔶 iter3 (§I2.14, request-side): per-sem cap; `0` = unavailable (exchange/SEP), low = chill semester |

**Representative profiles** (✅ buildable now, 🔶 needs iter3 field):

| # | Archetype | Expressed via | Status |
|---|---|---|---|
| P0 | On-track fresh Y1 (baseline) | default student | ✅ |
| P1 | Mid-degree Y2/Y3 on track | `completed` = foundation + some GE | ✅ |
| P2 | No-H2-math (poly/arts-JC) | `has_h2_math:false`, `needs_math_bridging:true` | ✅ |
| P3 | English-bridging | `english_path: es1103_required` / `es1000_then_es1103` | ✅ |
| P4 | Transfer / APC exemptions | `exempted` = {CS1101S, MA1521, …} | ✅ |
| P5 | Behind / retaking (tight horizon) | `completed` missing a blocking prereq | ✅ |
| P6 | FYP-eligible high-GPA | `eligible_fyp:true` → CP4101 substitute | ✅ |
| P7 | Non-canonical history (preclusion bite) | `completed` ⊇ {CS1010/CS2040C} (I2.3) | ✅ |
| P8 | Internship-heavy (6-mo/NOC) | `industrial_option` set in request (see §2.2) | ✅ (true NOC term-block → iter3) |
| P9 | Exchange / SEP semester | `per_semester_cap` cap-0 term (request) | 🔶 iter3 |
| P10 | Part-load (works/health) | low `max_units` + `min_units` in request | ✅ |

### 2.2 What is inside the REQUEST (planning knobs + preferences) — `data/scenario_*.yaml`
The goal and constraints the student asks for *now*. Current schema (from `scenario_iter2.yaml`):

| Field | Kind | Meaning |
|---|---|---|
| `target_semesters` | hard | graduate within T semesters |
| `max_units_per_semester` | hard | per-sem unit cap (≤ `max_overload_units`=28) |
| `focus_area` | hard | a key from `focus_areas.yaml`, or `any` |
| `industrial_option` | hard | a specific internship option, or `any` |
| `preferences.min_units_per_semester` | soft/per-instance | floor on a non-empty semester |
| `preferences.no_empty_semesters` | soft/per-instance | forbid gaps between enrolled semesters |
| `preferences.heavy_conflicts` | soft/per-instance | module pairs that may not share a semester |
| `preferences.per_semester_cap` | soft/per-instance | 🔶 iter3 (§I2.14): per-sem unit cap; `0`=exchange block, low=chill semester |
| `preferences.max_cs_modules_per_sem` | soft/per-instance | 🔶 iter3 (§I2.15): ≤ N Computing modules/sem |

Per B2/D9, preferences are **per-instance hard constraints** (active only when set) and **never**
graduation rules — baseline feasibility must not depend on them. The NL prompt must state any
preference so the LLM sees it too.

### 2.3 Instance = quadruple
`{nl_prompt, formal_instance, ground_truth, meta}`:
- **nl_prompt** — profile + request in prose (hand-authored per member for linguistic variety).
- **formal_instance** — the `(profile.yaml, request.yaml)` pair it was generated from.
- **ground_truth** — `solve_iter2` output: SAT/UNSAT; if SAT a valid plan + min feasible horizon; if
  UNSAT the blocking requirement from `explain_infeasible_iter2`.
- **meta** — coverage tags (§2.5) + **measured difficulty** signals (§2.4).

**Generate NL from formal, never the reverse**, so ground truth is always exact.

### 2.4 Measured difficulty (solver-emitted, per instance)
Computed by re-solving the formal instance with tightened knobs — all available from `SolveResult`
(`status`, `wall_time_s`, `num_variables`, `num_constraints`) + `solve_iter2` overrides:
- **near-UNSAT margin** — smallest ΔT (and Δunits) that flips SAT→UNSAT. Small margin ⇒ binding/hard.
- **solution count / backbone** — enumerate up to K feasible plans (CP-SAT solution callback); fewer
  solutions and more forced assignments ⇒ harder.
- **active binding-constraint count** — how many requirement/preference groups are tight at optimum.
- **model size / solve time** — `num_variables`, `num_constraints`, `wall_time_s` (also feeds the
  cost-analysis section).

Headline analysis = **pipeline accuracy vs measured difficulty** (not vs an assumed tier), which
sidesteps the "is the tier ordering real?" objection and is itself a reportable finding if accuracy
does *not* fall monotonically.

### 2.5 Coverage recipe (how we sample the (profile × request) space)
We do not enumerate the full Cartesian product. We sample to guarantee span + constraint coverage,
then label each instance with its measured difficulty (§2.4). The old tiers are the coverage checklist:

| Tag | Constraint family exercised (§) |
|---|---|
| C-base | unit cap + required modules |
| C-order | real single-sem offerings (I2.1) |
| C-depth | focus area + ≥12u L4000 (I2.5/I2.6) |
| C-acct | 32u B&D + CP cap + ≥160u (I2.7/I2.9) |
| C-compl | industrial off-cap (I2.8), C&E split (I2.13), preclusion history (I2.3) |
| C-pref | preferences (I2.11 + iter3 §I2.15) |
| C-unsat | genuinely infeasible (both pipelines must *detect* infeasibility) |

Sampling plan (≈80–120 instances, within the ≤$100 budget):
- **dense diagonal** — each profile P0–P10 paired with its *natural* request (fresh→C-base/order;
  FYP-eligible→C-acct/compl; behind or exchange→C-unsat).
- **full coverage sweep on 3 anchor profiles** (P0 on-track, P5 behind, P8 internship) across all
  C-tags, so the accuracy-vs-difficulty curve has clean within-profile variation.
- every C-tag appears with **both SAT and UNSAT** instances.

### 2.6 Generator
A seeded script: for each sampled `(profile, request)` → merge → `solve_iter2` → compute §2.4 signals
→ write the quadruple to `eval/instances/`. Validate every instance against `src/model.py` first.

## 3. The two pipelines (both graded by `check_plan_iter2`)

1. **LLM-direct** — prompt = NL instance + degree rules in prose → model outputs SAT/UNSAT and, if
   SAT, a plan as `{"1":[...],"2":[...],...}` JSON (same shape the checker consumes).
2. **LLM-as-translator** — prompt = NL instance → model emits a `student`+`scenario` spec →
   `solve_iter2` runs → plan. Solver is always correct, so this pipeline's errors are pure
   **translation** errors (isolates the Reality-Check bottleneck for our domain).

Run `check_plan_iter2` on every produced plan. Prompt-cache the static rule text to stay within the
≤$100 budget.

## 4. Models (decided)

Compare the **Claude family for a size ablation**: `claude-opus-4-8`, `claude-sonnet-4-6`,
`claude-haiku-4-5-20251001`. Same prompts across all three; report accuracy and cost per model so the
scaling effect is visible. (Optional later: SoC-hosted open-weight model, Logic-LM refinement loop.)

## 5. Metrics (report separated)

- **Feasibility-decision accuracy** — SAT vs UNSAT correct? (binary/instance).
- **Plan validity** — for claimed-SAT, does `check_plan_iter2` pass? Record **which** constraint it
  violated (prereq / offered-term / units / focus / L4000 / preclusion / preference) → this histogram
  *is* the failure-mode analysis.
- **Horizon/optimality match** — graduated in the min feasible T, or overshot? (objective pins 160u,
  so there's an exact reference).
- **UNSAT diagnosis quality** — on infeasible instances, did it name the right blocking requirement?
- **Translator-specific** — spec parse/validity rate; semantic fidelity (did it drop a stated
  preference?). Isolates translation error from the (always-correct) solver.
- **Cost/latency** — tokens, wall-clock, $ per instance per pipeline per model.

## 6. Ablations (rubric explicitly rewards these)

1. **Label obfuscation** (do this first — cheap, high signal): rename module codes to arbitrary
   strings. If LLM-direct collapses but the translator holds, LLM-direct was relying on memorized NUS
   curricula, not reasoning.
2. **Model size** — Opus vs Sonnet vs Haiku (built into §4).
3. **Translate-once vs translate-with-refinement** (Logic-LM self-repair on checker errors).
4. **Prompt richness** — rules-in-prose vs rules-as-structured-tables for the direct pipeline.
5. **Checker-strength probe** — disable one constraint in a copy of the checker; count how many
   "valid" LLM plans only passed under the weaker check → motivates each constraint's necessity.

## 7. Headline figures/tables for the report

- **Accuracy vs measured difficulty** (§2.4 near-UNSAT margin / solution count on the x-axis), both
  pipelines, all three models — the single most important figure. Whether LLM-direct falls
  monotonically with difficulty is itself the finding.
- **Profile × constraint-family accuracy heatmap** (§2.1 × §2.5 C-tags) — shows which student
  populations and which constraint families each pipeline fails on (fairness/RAI evidence).
- Constraint-violation histogram (per pipeline).
- UNSAT-detection rate table.
- Translation-fidelity rate (translator only).
- Cost/latency table.
- Solver difficulty illustration: naive assignment space ≈ 2^(|modules|·T) ≈ 2^760 vs CP-SAT actual
  solve time (OPTIMAL at T=8, fast); plus a (T, focus, cap) → SAT/UNSAT table showing the constraints
  genuinely interact.

## 8. Report section → evidence map

| Report section | Evidence from this plan |
|---|---|
| Problem understanding / RAI | NUSMods-vs-faculty-page disagreement (`validation_report.md`); harm = mis-enrolment; mitigation = verifiable solver+checker plans & infeasibility explanation; **fairness: profile×tier heatmap shows if LLM-direct degrades on non-default students** (§2.3) |
| Technical depth / universe | ~95 modules, 11 focus areas, 160u/5 buckets; I2.1–I2.13 constraint table; 81 tests + checker parity |
| Difficulty analysis | §7 state-space vs solve-time; (T,focus,cap) SAT/UNSAT table; the difficulty–accuracy curve |
| Methodology & results | §2–§6: corpus, pipelines, metrics, ablations; the "where/why LLM-direct diverges" narrative |
| Assumptions & failure cases | I2.12 + `program_cs.yaml: assumptions`, critiqued for realism & adversarial phrasing |
| Effort & contributions | 3-way split: (1) solver/checker/data, (2) corpus+pipelines, (3) eval/analysis/RAI+writeup — state actuals |

## 9. Build order (toward Nov 13 report)

1. Freeze/tag the iter2 oracle so ground truth is reproducible.
2. Instance generator (§2.3) + hand-authored NL per tier.
3. Wire both pipelines (§3) with `check_plan_iter2` as grader + prompt caching.
4. Run **T0→T6 + obfuscation ablation first** (highest signal), then remaining ablations and models.
5. Produce §7 figures; write up per §8.
