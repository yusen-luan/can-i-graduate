# Modelling decisions

One entry per decision, ≤ 3 lines: **what** was decided and **why**. Newest at the bottom.
If a decision is reversed, mark the old entry `(superseded by Dn)` instead of deleting it.

- **D1 (Iter 1):** Separate module facts, program rules and student state into separate YAML files. Why: the same
  module data must serve many programs and students, and exemptions are facts about a student, not about a module.
- **D2 (Iter 1):** `exempted=true` satisfies the module and its downstream prerequisites, and it uses no slot or units.
  Why: this matches how NUS exemptions work.
- **D3 (Iter 1):** Bridging modules (MA1301/X, ES1000/ES1103) are part of the global domain but are not program requirements.
  They are activated by student conditions. Why: they only apply to some students.
- **D4 (Iter 1):** English placement is one enum, `english_path`, not several booleans. Why: exactly one pathway applies.
- **D5 (Iter 1):** CS2101 + CS2103T form an atomic 8-unit same-semester bundle, not a prerequisite edge. Why: neither
  module comes strictly before the other.
- **D6 (Iter 1):** Run knobs (`target_semesters`, `max_units_per_semester`) are in `planning_scenario.yaml`.
  Why: the same student and program can then be tested against 5–8 semester targets without editing the degree data.
- **D7 (Iter 1):** ID/CD is modelled as exactly 3 placeholder modules with ≥ 2 ID and ≤ 1 CD. Why: this is the simplest
  encoding of the 12-unit rule while elective choice is out of scope.
- **D8 (Iter 1):** The solver is OR-Tools CP-SAT over boolean `x[m,s]`. Why: the formulation is already 0/1-linear, so it maps
  one-to-one, and it proves infeasibility. A hand-written backtracking search could be added later as an ablation.
- **D9 (Iter 1):** Objective = minimise the number of scheduled modules. This is only a tie-breaker, and the problem stays a CSP. Why: it stops
  pointless optional picks (e.g. both MA1301 and MA1301X). Modules outside required ∪ ID/CD ∪ prerequisite closure get no variables.
- **D10 (Iter 1):** `src/checker.py` re-implements the constraints without the solver. Why: it cross-checks the solver,
  and it will grade plans from the LLM-direct pipeline.
- **D11 (Iter 2):** Module facts come from a frozen NUSMods AY2026/27 snapshot (`data/snapshot_2026-2027/`, built by
  `scripts/ingest_nusmods.py`); degree rules stay hand-curated. Why: NUSMods is authoritative and the faculty pages are stale
  (it caught CP/CS unit sizes, single-sem offerings, and CS4232 no longer existing).
- **D12 (Iter 2):** Prerequisites use a recursive `all_of`/`one_of` tree mirroring NUSMods; the solver reifies it, the checker
  evaluates it. Why: real rules are DNF-capable (CS3244), which flat CNF clauses cannot express without blow-up.
- **D13 (Iter 2):** Bridging prerequisites (MA1301/X, ES1000/ES1103) are waived by placement (`bridging_waived`), not dropped.
  Why: NUSMods lists only the bridge as a prereq because the real prereq is an A-level; H2-math students take the target directly.
- **D14 (Iter 2):** Preclusions count `held` credit (completed ∨ scheduled), excluding exempted. Why: an exemption is a waiver
  with no credit, so it must not trip the "at most one of" rule.
- **D15 (Iter 2):** The 32u Breadth & Depth aggregate is not enforced; its sub-rules (focus area, ≥12u L4000, team project,
  industrial experience, CP cap) are. UE is a residual filler to 160u, not a fixed 40u. Why: avoids per-bucket unit
  partitioning and double-counting; extra B&D simply counts as UE. _(Aggregate + team-project parts superseded by D19.)_
- **D16 (Iter 2):** Objective minimises total units (then module count). Why: with the ≥160 floor it lands at exactly 160 and
  stops the solver padding with large optional modules (internships/FYP) as filler; stays a CSP (supersedes D9 for iter2).
- **D17 (Iter 2):** Workload balance / min-load / no-gaps are per-instance scenario preferences, never degree rules. Why: they
  are not graduation requirements, so hard-coding them would make the oracle reject genuinely valid plans.
- **D18 (Iter 2):** Industrial experience picks exactly one option and forbids any other internship module. Why: a student does
  one stint; otherwise the solver uses spare internships as unit filler.
- **D19 (Iter 2):** No Computer-Systems Team-Project requirement in AY2026/27; Breadth & Depth is a single 32-unit Computing
  bucket (`units_of(pillar∈{breadth_depth,industrial_experience}) ≥ 32`) containing focus/L4000/industrial. Why: verified against
  the cohort page + NUS Bulletin (docs/iter2_verification.md §6); the earlier team-project rule was a carried-over error.
- **D20 (Iter 2):** Industrial-experience units are excluded from the per-semester unit cap. Why: internships run over the
  vacation / special term (NUSMods shows CP3880 in terms 1–4), so they must not inflate the graduation horizon.
- **D21 (Iter 2):** The minimum horizon is not hard-coded; 8 semesters is just 160u/20u-cap. Early graduation comes from a higher
  cap (overload) or `exempted`/APC credits, both already supported. Why: students can and do finish in fewer than 8 semesters.
- **D22 (Iter 2):** ULR pick-list pillars (Cultures GEC%, Singapore GESS%, Communities GEN%) and ID/CD use a verified real-course
  subset from NUSMods (full lists in data/ge_pillars.yaml, data/id_cd.yaml); only UE stays generic. Supersedes D7. Why: real codes +
  real single-semester offerings add binding realism; fixed "GES" prefix corrected to "GESS".
- **D23 (Iter 2):** Year-long C&E service learning is a pair (X Term1, Y the contiguous Term2), modelled `x[Y,s]=x[X,s-1]`; X holds
  the 4u, Y is a 0u continuation. Why: real two-contiguous-semester requirement; keeps the pillar at 4u despite NUSMods showing 4u per half.
- **D24 (Iter 2):** Overload ceiling is 28 units/semester (`program_cs.yaml: max_overload_units`); the solver rejects a higher cap and
  the checker flags any semester over it. Why: a plan needing >28u/sem is not actually achievable, so the oracle must not produce it.
- **D25 (Iter 3 C5):** Calendar is an optional `scenario.term_layout` ([1-4] per plan slot, 3/4 = Special Terms); absent = the iter2
  parity mapping, so existing instances/tests are unchanged. Offering (§6) uses the layout. Why: faithful special terms without
  reindexing semesters; special-term load is just a per-slot cap (D26), keeping the change small and test-preserving. See I2.14.
- **D26 (Iter 3 C1):** `preferences.per_semester_cap: {s:u}` overrides the global cap per slot; u=0 blocks ALL modules there (incl.
  off-cap industrial) = a fully-unavailable exchange/SEP semester, a low u = a "chill" semester. Per-instance only. See I2.15.
- **D27 (Iter 3 C2):** `preferences.max_cs_modules_per_sem: N` caps Computing (CS/IFS/CP) modules scheduled per slot, excluding
  off-cap industrial (vacation work). A count, not a unit limit. Per-instance only. See I2.16.
- **D28 (Iter 3 C3):** `scenario.want_fyp`/`want_urop` schedule CP4101 / a UROP code IN ADDITION to the mandatory internship,
  gated by `student.eligible_fyp`/`eligible_urop`. Both are cp_coded, so the 12u CP cap binds them: FYP(12u) + UROP is infeasible.
  Why: realistic co-existence and a sharp binding interaction (off-cap internship vs in-cap FYP) for the LLM-vs-solver eval. See I2.17.
- **D29 (Iter 3, corrects D18):** Industry experience = **at most one** internship option OR, for a
  GPA-eligible student, the CP4101 dissertation replacing it (`Σopt_i ≤ 1`; `=1` if a specific option
  is requested; else `Σopt_i + diss ≥ 1`, `diss=sat(CP4101)` only when `eligible_fyp`). Both may co-exist.
  Why: the cohort page says GPA≥4.0 students may *replace* Industry Experience with CP4101; D18's
  "exactly one, always" wrongly forced an internship on dissertation-track students. See I2.8/I2.17.
- **D30 (Iter 3, C4):** Per-module `require_modules`/`forbid_modules`/`deadline:{code:S}` live in the
  scenario `preferences:` block (per-instance hard, never a degree rule). Pinned/deadline modules join
  the solver domain; any can force a legal UNSAT; `require∩forbid` and bad deadlines are validated out.
  Why: cheap, high user value, and makes offering-lock UNSAT authorable. See I2.18.
- **D31 (Iter 3, realism):** Objective gains a middle term — among 160u plans, minimise the COUNT of
  Computing (CS/IFS/CP) modules — so slack toward 160u is filled with non-CS unrestricted electives
  instead of gratuitous CS courses (default plan: 23→15 CS modules). Still only a tie-break (required
  CS, focus, 32u B&D are hard); feasibility unchanged. Why: the old tie-break piled on unneeded CS.
- **D32 (Iter 3, app only):** the Streamlit planner bakes sensible advising DEFAULTS (not degree
  rules, not in the oracle): CS1101S by semester 1 and GEA1000 in Year 1 (skipped if completed/
  exempted), and a default cap of 3 Computing modules/sem (user-overridable). The plan-reasonableness
  score is shown in `eval/` meta but NOT in the app UI. Why: realistic default plans for juniors.
- **D33 (Iter 3, realism):** objective also penalises OFF-FOCUS Computing modules when a focus area is
  chosen, so the mandatory 32u B&D / 12u L4000 depth is filled with that area's courses (default AI
  plan: all 5 discretionary CS electives now AI-area, 0 off-focus), not arbitrary unrelated high-level
  CS. Still a tie-break (no feasibility change). Also: SEP/exchange + NOC removed as corpus cases
  (`exchange_abroad` deleted, honours de-exchanged); blocked-semester mechanism kept for leave-of-
  absence only. A5 external validation vs cohort page passed (see iter2_verification.md).
- **D34 (Iter 3, review):** exempted modules' units COUNT toward the 160u total and every unit bucket
  (`units_of` uses `sat`); they are excluded only from preclusion `held` credit. Clarifies D2's "no
  units" (= consumes no semester slot/cap). Why: team decision; matches the solver/checker.
- **D35 (Iter 3, review):** C4 codes must exist (else ValueError); a pin/deadline on a placement-
  waived bridge is trivially satisfied in solver AND checker. Why: they disagreed (solver dropped
  the constraint, checker flagged it), which would silently corrupt LLM->solver grading.
- **D36 (Iter 3, benchmark):** `nl_prompt` is generated ONLY from the formal student + request; the
  curated `description` lives in `meta` and never reaches the prompt. Why: 16/35 prompts leaked the
  verdict ("infeasible because…"). Guarded by `tests/test_eval_prompts.py`.
- **D37 (Iter 3, Pipe A):** LLM sweep uses ONE generation, `claude-{haiku,sonnet,opus}-5-5`, all at adaptive
  thinking + explicit effort `high` (per-model defaults differ), no refusal fallback (a fallback model would
  answer for another). Why: a clean size ablation; supersedes the 4.5/4.6/4.8 mix in evaluation_plan.md §4.
- **D38 (Iter 3, Pipe A):** the LLM writes each generic elective as `UE`; the harness binds it to a
  UE_GENERIC id the student hasn't used. Why: placeholders are interchangeable and the NL prompt only says
  "N electives completed" (final_year_audit holds _1 and _8), so ids are unknowable, not a reasoning error.
- **D39 (Iter 3, scoring):** `eval/score.py` grades every Table-3 row: missing/unparseable answer = wrong,
  Plan Valid over all 17 GT-SAT, Realism = mean over VALID plans only. `meta.tier` is curated (label/
  PROFILE_TIERS), since no arithmetic floor rule reproduces the report's T1 vs T2–4 split.
- **D40 (Iter 3, Pipe A):** two Pipe A conditions: `full` (rules + catalog) and `bare` (answer conventions
  only). Why: `full` scored 100% because the prompt pre-formalises the spec; `bare` is how a student asks.
  Out-of-model codes are classified against the full NUSMods list, never silently accepted.
