# Iteration 3 plan — realism preferences for CS juniors

Iter2 froze a correct 160u oracle. Iter3's job is **not** more degree rules — it is the
**per-instance preference layer** that makes the planner actually *helpful* to a real CS junior, and
that stresses the LLM-direct-vs-translator gap (preferences are stated implicitly in prose, are easy
to drop in translation, and have no memorized-curriculum shortcut — so the pipelines should diverge
most here). It also feeds the student-profile axis of the evaluation (`docs/evaluation_plan.md` §2.3),
specifically profile **P9 (exchange/SEP)**.

**Discipline (unchanged, CLAUDE.md):** semantics into `docs/solver_constraints.md` **first**, then
data, then **both** `src/solver.py` and `src/checker.py`, then a test; checker never imports solver;
every preference is per-instance and **never** a graduation rule (D9/B2 — baseline feasibility must
not depend on it). Preferences live in the scenario `preferences:` block (mechanism I2.11).

---

## Committed scope (build this iter3): C1–C6 + ID/CD finalize + profile library
Full-depth build (per 2026-10-20 decision): special-term calendar, per-sem cap vector, CS-count cap,
internship+FYP+UROP, pin/forbid/deadline, and an **approximated** NOC. NUSC + second major deferred.

> **DONE (2026-10-20): C5, C1, C2, C3 + dissertation correction.** Implemented in solver+checker+tests
> (**110 pass, +19**), semantics in `docs/solver_constraints.md` §I2.14 (special-term `term_layout`, C5),
> §I2.15 (per-sem cap vector, C1), §I2.16 (CS-count cap, C2), §I2.17 (internship+FYP+UROP, C3); decisions
> D25–D29. **Correction D29/§I2.8:** the CP4101 dissertation may *replace* the internship for
> `eligible_fyp` students (verified against the cohort page; was wrongly "exactly one internship always").
> Data: scenario knobs `term_layout`/`per_semester_cap`/`max_cs_modules_per_sem`/`want_fyp`/`want_urop`,
> student `eligible_urop`, program `breadth_depth.fyp`/`urop`. **Tests: 113 pass** (incl. 3 Streamlit
> AppTest smoke tests). **Profiles + UI done:** 9 archetypes in `data/profiles/benchmark_profiles.yaml`
> + `app/app.py` rewired with a profile picker and all iter3 controls (`demo_iter3_*` = CLI example).
> **Still TODO:** C4 (pin/forbid/deadline), C6 (NOC approx) + ID/CD offered-terms, more eval-corpus
> profiles.

### C1. Per-semester unit-cap vector (unifies exchange block + "chill semester")  → §I2.15 ✅DONE
Generalize the single global `max_units_per_semester` into an optional **per-semester cap override** so
students can say "keep sem 5 light so I can do a part-time internship" *and* "I'm on exchange in sem 6":
```yaml
preferences:
  per_semester_cap: {5: 12, 6: 0}   # sem5 chill (12u), sem6 blocked (exchange/SEP)
```
Semantics (the effective cap for semester `s` is `per_semester_cap.get(s, global_cap)`):
- Solver: `Σ_m units[m]·x[m,s] ≤ cap_s` (replaces the flat §7 cap with a per-`s` cap). Cap `0` ⇒
  `x[m,s]=0 ∀ non-industrial m` (full block). Decide + document whether an internship may occupy a
  cap-0 term (default **no** — fully unavailable); internships stay off-cap elsewhere (I2.8).
- Checker: recompute per-semester load against `cap_s`; reject overloads and any academic module in a
  cap-0 term.
- **Exchange/SEP is just the cap-0 special case** — so profile **P9** and the chill-semester request
  are one mechanism, not two.
- Interaction to verify: tight/blocked semesters shrink usable capacity, so some `(T, caps)` combos
  that were SAT go UNSAT — the binding effect we want, and a clean `explain_infeasible` case.

### C2. Per-semester CS-count cap  → §I2.16 ✅DONE
Generalizes `heavy_conflicts` (pairwise) to a **count** limit: "≤ N Computing (CS/IFS/CP) modules per
semester" — the realistic workload-sanity knob juniors ask for. Scenario field
`max_cs_modules_per_sem: N`. Semantics:
- Solver: for each semester `s`, `Σ_{m ∈ computing} x[m,s] ≤ N` (count, not units — units are the
  existing cap §7).
- Checker: mirror the count per semester.
- Keep it a **per-instance hard** preference (active only when set); document that it can make
  otherwise-feasible instances UNSAT at tight horizons.

### C3. Internship AND FYP + UROP as a requestable, gated option  → §I2.17 ✅DONE
Today `industrial_option` (request) picks one internship and `eligible_fyp` (profile) lets CP4101
*substitute* industrial experience — so a student cannot ask for **both**, and UROP/research
(CP3106/CP3209/CP4106, already in `cp_coded.codes`) is not requestable or gated. Iter3:
- Request flags `want_fyp`, `want_urop` (bool) + keep `industrial_option`. FYP/UROP modelled as
  **co-existing** B&D/CP electives, not substitutes.
- Gate: `want_fyp ⇒ eligible_fyp` (GPA condition); `want_urop ⇒` year/standing condition.
- **THE binding interaction to get exactly right (`cp_coded.max_units = 12`):** industrial experience
  is **excluded** from the CP cap (I2.9), but FYP (CP4101 = **12u**) and UROP are **inside** it. So FYP
  alone fills the whole 12u cap ⇒ `want_fyp ∧ want_urop` is INFEASIBLE, while `want_fyp` + a 6-month
  off-cap internship is fine. This is a prime LLM-direct trap (it misses that the internship is
  cap-exempt but the FYP is not) → make a benchmark instance of it.

### C4. Pin / forbid / deadline per-module preferences  → §I2.18 ✅DONE
Cheap, high user value. Request: `require_modules:[...]` (`Σ_s x[m,s]=1`), `forbid_modules:[...]`
(`Σ_s x[m,s]=0`), `deadline:{CODE:S}` (`Σ_{s≤S} x[m,s]=1`, e.g. "finish CS2103T before I intern").
Per-instance hard; checker mirrors; document each can force UNSAT. **Done:** scenario `preferences`
knobs + domain pull-in + `validate_scenario_iter2` guards; solver+checker+8 tests; decision D30.

### C5. Special Terms 3 & 4 (faithful calendar)  → §I2.14 ✅DONE
Lifts the iter2 "Sem 1/2 only" simplification (I2.12). Plan semesters gain two special-term slots per
year (NUS Terms 3,4); `term_of(s)` and the offering constraint (§6) extend to 4 terms/year. Special
terms have their own (usually lower) default cap and carry special-term-only offerings (incl. the real
internship calendar). This is the big change — do it first because C6 rides on it. Keep Sem 1/2 as the
default; special terms are opt-in via the request so existing instances/tests stay valid.

### C6. NOC — approximate  → ❌ DESCOPED (2026-10-20, per request: no iter4, no more features)
NOC stays only as a named *not-representable* limitation in the report (see `benchmark_design.md` §B3).
The rest of this section is retained for the record but is **not** being built.


NOC (overseas college, whole-semester internship + entrepreneurship) is **approximated**, not modelled
faithfully (NUSC-style overlay deferred — see below). Model: a `per_semester_cap:0` academic block
(C1) on the NOC semester **plus** an off-cap internship occupying it (now natural given C5 special
terms), its units counting toward industrial experience / the 160u total. Document the gap: real NOC
also grants entrepreneurship units we fold into UE. This is the one deliberately-loose feature — flag
it in `assumptions` and use it as a report "failure-of-assumptions" case.

### Also finalize (correctness, not new features)
- **ID/CD offered-terms** — `wired_subset` is real but verify each course's real `offered_terms` so
  ID/CD placement is genuinely binding, not trivially both-sem.
- **Profile library P0–P10** → `data/profiles/` (P9 exchange = `per_semester_cap:0`; P8 internship now
  can use a special term). Verify each SAT/UNSAT as intended; wire into the generator
  (`docs/evaluation_plan.md` §2.6).

---

## Deferred (report "what we'd add" / failure-of-assumptions, NOT built)
- **NUSC overlay** — honours college with a different ULR; a whole program variant. Iter4.
- **Second major / minor** — extra requirement bucket. Iter4.
- **Soft workload objective** — weighted optimization that *spreads* difficulty; build only as a
  **separate ablation variant**, never the baseline (D9). High research value (ConstraintBench: LLMs
  weakest at objective reasoning), kept out of the feasibility oracle.
- **Exact per-bucket unit partition** — keep floors + UE slack (iter2 B3).
- **Grades / CAP gating** beyond `eligible_fyp` — we don't model grades.

## Explicitly out of scope (note in report so graders see it was considered)
Anything needing a **timetable** — avoid-8am, lecture-clash, specific lecturers/slots. NUSMods has the
data, but it is a different and much larger CSP that dilutes the research question.

---

## Build order (docs-first loop each step: solver_constraints.md → data → solver+checker → test → decisions.md)
1. **C5 special terms** first (everything else rides on the calendar); keep Sem 1/2 default so iter2
   tests stay green.
2. **C1 per-semester cap vector** (§I2.15): cap-0 exchange term + cap-12 chill term; `(T,caps)` UNSAT
   case + `explain_infeasible`.
3. **C2 CS-count cap** (§I2.16).
4. **C3 internship+FYP+UROP** (§I2.16): nail the CP-cap interaction; test `want_fyp∧want_urop` UNSAT
   and `want_fyp` + off-cap internship SAT.
5. **C4 pin/forbid/deadline** (§I2.17).
6. **C6 NOC approximation** (§I2.18) + ID/CD offered-terms finalize.
7. **Profiles P0–P10** → `data/profiles/`.

## Pre-benchmark finalization checklist (gates freezing the oracle)
- Checker parity + a test for **every** C1–C6 constraint (the checker is the grader — never skip).
- All iter2 tests still green after the special-term calendar change.
- **Freeze/tag the oracle** version used for the benchmark (reproducible ground truth).
- Reconcile stale `status.md` open-issue (ID/CD is now real, not generic).
- Fix the lingering `solver_constraints.md` iter1 §7 cap-wording issue.
- `assumptions` (program_cs.yaml) + `status.md` updated for every new simplification (esp. the NOC
  approximation and any special-term looseness).

## Sources (same authoritative set as iter2)
- CS Cohort 2026/27 — https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/
- NUSMods API v2 (AY2026/2027) — https://api.nusmods.com/v2/2026-2027/
