# Iteration 2 Plan — Full BComp(CS) AY2026/27, NUSMods-validated

> **Corrections:** parts of this plan (a team-project requirement; industrial experience as a
> separate bucket) were found wrong when re-verified against authoritative sources. The binding
> source of truth for the *implemented* model is **`docs/iter2_verification.md`** (B&D is a single
> 32u bucket containing industrial experience; no team project; internships are off the semester cap).

Planning doc for Iteration 2. Scope stays **canonical modules only** but expands
the Iteration-1 baseline to the **full 160-unit BComp(CS) AY2026/27 degree**, with
the module universe **validated against the NUSMods API** (the faculty pages are
sometimes stale — e.g. the CS2040S preclusion set on NUSMods is
`CS1020/CS1020E/CS2010/CS2020/CS2040/CS2040C/CS2040DE/CS2040HS`, wider than the
course page implies).

> **Why this matters for the project (not just "more modules").** The research
> question is LLM-direct vs LLM→solver. `docs/status.md` already flags that
> Iteration-1 instances are *too easy*: the unit cap alone fixes the minimum
> horizon, so both pipelines trivially agree. **Iteration 2's real goal is to add
> genuinely *binding* constraints** (real term offerings, preclusions, focus-area
> depth, level-4000, industrial experience) so that LLM-direct starts to diverge
> from the solver — that divergence is the evaluation's payload.

---

## 0. Baseline: what Iteration 1 already is (corrected)

Iter1 is **not** just data — it already has a working solver and checker (the
GitHub `main` repo; the local working copy on branch `iter1-task1` is behind and
is missing these — **see §10, sync first**):

- `data/modules.yaml` — module facts (units, kind, `offered_terms`, prereqs as
  `all_of` + `conditional`→`one_of`, coreqs). No student info.
- `data/program_cs_iter1.yaml` — degree requirements for iter1 (required list,
  ULR/GE groups, ID/CD rule, CS2101+CS2103T bundle).
- `data/student_example.yaml` — one student: `completed`, `exempted`,
  `conditions` (math bridging, `english_path`).
- `data/planning_scenario.yaml` — run knobs: `target_semesters`, `max_units_per_semester`.
- `src/model.py` — load + validate + shared helpers (`prereq_clauses`, `term_of`,
  `pre_satisfied`, `must_satisfy_groups`, `same_semester_groups`).
- `src/solver.py` — **OR-Tools CP-SAT** over boolean `x[m,s]` → `SolveResult`.
  Objective is only a tie-breaker (minimise scheduled modules), so it stays a
  pure CSP (decision **D8/D9**).
- `src/checker.py` — solver-independent plan validator (grades plans the LLM
  produces; must never import the solver — **D10**).
- `tests/` — 49 pytest tests. Result: min feasible horizon **T=5** for all 6
  (bridging × english_path) student types at cap 20.

**Hard conventions to obey (from `CLAUDE.md`), they shape every task below:**
1. Keep the three data layers separate (module / program / student / scenario).
2. Change semantics in `docs/solver_constraints.md` **first**, then data + code.
3. Every new constraint goes in **both** `solver.py` **and** `checker.py`, plus a
   test. Checker never imports solver.
4. Placeholders use `*_GENERIC*`; real codes only for real modules.
5. Log each decision in `docs/decisions.md` (≤3 lines); keep `status.md` ≤60 lines.
6. Platform is Windows; scripts run via `python` from repo root.

So CP-SAT is already chosen — Iteration 2 does **not** re-pick a solver; it
**extends** the existing one.

---

## 1. Target degree — BComp(CS) AY2026/27 (160 units)

| Bucket | Units | Canonical content |
|---|---|---|
| **Common Curriculum** | 40 | ULR 6 pillars (Digital Lit = CS1101S; Critique&Expr = **ES2660 or UTW/RVX** — new in 26/27; Cultures = GEC%; Data Lit = GEA1000/BT1101/ST1131/DSA1101; Singapore = GES%; Communities = GEN%) + Computer Ethics IS1108 + **ID/CD 12u (≥2 ID, ≤1 CD)** |
| **CS Foundation** | 36 | CS1231S, CS2030S, CS2040S, CS2100, CS2101, CS2103T, CS2106, CS2109S, CS3230 |
| **Math & Sciences** | 12 | MA1521, MA1522, ST2334 |
| **CS Breadth & Depth** | 32 | ≥1 focus area (3 primaries, ≥1 @L4000+); **≥12u @L4000+**; industrial experience 6–12u; team project ≥8u; **≤12u CP-coded** (excl. industry exp); non-industry courses must be CS/IFS/CP-coded |
| **Unrestricted Electives** | 40 | free; absorbs MA1301/X bridging if the student lacks A-level H2 Math |

Iter1 covers Common-Curriculum (minus real GE/ID/CD choices), Foundation, and
Math. **Iter2's new modelling is the whole Breadth & Depth bucket, the UE sink,
and real term offerings / preclusions across all of them.**

---

## 2. Where we store all the modules (storage design)

Keep iter1's layered split; add new files and a **versioned NUSMods snapshot**.

```
data/
  snapshot_2026-2027/
    modules.raw.json     # NEW: unmodified NUSMods module JSON (provenance)
    modules.yaml         # NEW: generated canonical universe (our schema)
  program_cs.yaml        # RENAME of program_cs_iter1.yaml, full 160u buckets
  focus_areas.yaml       # NEW: 11 areas → primaries/electives (validated)
  id_cd.yaml             # NEW: real ID- and CD-coded course lists + offered terms
  preclusions.yaml       # NEW: mutual-exclusion groups (from NUSMods preclusion)
  student_example.yaml   # extended (see §4)
  planning_scenario.yaml # extended with constraint inputs (see §4)
```

Per-module schema (superset of iter1 — only adds fields, existing code keeps
working):

```yaml
CS2040S:
  title: Data Structures and Algorithms
  units: 4                         # = NUSMods moduleCredit
  level: 2000                      # NEW: first digit-block of the code (L4000 rule)
  offered_terms: [1, 2]            # NEW SOURCE: from NUSMods semesterData (not assumed!)
  kind: canonical                  # canonical | bridging | generic_placeholder
  pillar: cs_foundation            # kept, drives the prereq graph grouping
  prerequisites:                   # §2.1 — real tree, back-compatible with iter1
    tree:
      all_of:
        - one_of: [CS1101S]        # canonical-only: non-canonical alts dropped here,
        - one_of: [CS1231S]        #   but preserved as preclusions (§2.2)
    conditional: []                # unchanged iter1 mechanism (student-state gates)
  preclusion_group: data_structures   # NEW: points into preclusions.yaml
  tags:                            # NEW: which requirement buckets it can fill
    focus: {algorithms_theory: primary}
    cp_coded: false
    team_project: false
    industrial_experience: false
```

**Division of truth:** NUSMods owns *module facts* (units, terms, prereqTree,
preclusion). The *degree rules* (bucket unit targets, focus-area membership,
internship/FYP options) are **not** in NUSMods — curate them by hand in
`program_cs.yaml` / `focus_areas.yaml` with a source-URL + date comment per rule.

### 2.1 Prerequisites: migrate to a NUSMods-shaped tree
Iter1's `all_of` cannot express "(A or B) and (C or D)". NUSMods publishes exactly
this as a recursive `and`/`or` tree with `CODE:grade` leaves. **Decision (new,
log as D11):** store prereqs as a nested `all_of`/`one_of` tree (rename of
NUSMods `and`/`or`; strip grade suffixes — we don't model grades). iter1's flat
`all_of` is just a one-level tree, so `prereq_clauses()` generalises to a
recursive walk and existing data still loads. `conditional` stays as the
orthogonal student-state wrapper (D3).

### 2.2 Preclusions / non-canonical conflicts (new, D12)
The "CS1101S precludes CS1010" rule. Store **named groups** (≤1 may count), not
N×N edges, sourced from NUSMods `preclusion`/`preclusionRule`:
```yaml
# data/preclusions.yaml
groups:
  intro_programming: [CS1101S, CS1010, CS1010S, CS1010X, CS1010E, CS1010J, CS1010A, CS1010HS]
  data_structures:   [CS2040S, CS1020, CS1020E, CS2010, CS2020, CS2040, CS2040C, CS2040DE, CS2040HS]
  discrete_math:     [CS1231S, CS1231, MA1100, MA1100T]
```
CSP/checker: for each group, `Σ (completed ∨ exempted ∨ scheduled) ≤ 1`. In a
canonical-only run the solver only ever *places* the canonical member, but the
group still correctly reads a student's prior non-canonical `completed` history.

---

## 3. Requirements → CSP (extend solver.py AND checker.py AND tests)

Carry over all iter1 constraints. Each item below is a *paired* change: edit
`docs/solver_constraints.md` first, then add to both `solver.py` and
`checker.py`, then a test.

| New constraint | Formulation sketch | §in solver_constraints.md |
|---|---|---|
| **Prereq tree** (generalises §3) | recursive AND/OR over `satisfied_before(p,s)` → CNF clauses, reuse existing clause loop | §3 rewrite |
| **Preclusions** | per group `Σ take[m] ≤ 1` | new §13 |
| **Real offered terms** (replaces "both sems") | `x[m,s]=0` when `term_of(s)∉offered_terms[m]` (already coded; now fed real data) | §6 (data-only) |
| **Choose-k / choose-u-units** (reusable) | `Σ_{m∈C} take[m]·units[m] ≥ u` or count ≥ k — covers ULR pick-lists, ID/CD, team project, UE, L4000 | new §14 |
| **Focus area** | indicator `satA`; `satA→(Σprimaries≥3 ∧ Σ{primary,L≥4000}≥1)`; degree: `ΣsatA≥1`, or fix A from scenario (§4) | new §15 |
| **Level-4000 depth** | `Σ_{L≥4000} take[m]·units[m] ≥ 12` | new §16 |
| **Industrial experience** | choose-units with 12u-single vs 6u+6u pairing; internship term blocks academic load (§6) | new §17 |
| **Team project** | pick a valid set (CS3203 \| CS3216+3217 \| CS3281+3282) ≥8u with intra-set ordering | new §18 |
| **Bucket accounting / UE sink** | `assign[m,bucket]` with `Σ_bucket assign = take[m]` to forbid double-count; per-bucket unit targets; overall ≥160 | new §19 |

`take[m] := completed[m] ∨ exempted[m] ∨ Σ_s x[m,s]` (already exists as
`satisfied(m)`/`taken(m)` in solver.py). The domain-closure trick in
`schedulable_modules()` keeps the model small — extend its frontier to pull in
focus/team/industrial/CP candidates and their prereq closure.

**Keep it a CSP, not an optimiser.** Per D9, the objective stays a tie-breaker.
Workload-balance "don't stack CS2030S/CS2040S/CS2100" is better modelled as a
**hard pairwise `x[a,s]+x[b,s] ≤ 1`** over a `heavy_conflicts` list in
`program_cs.yaml` (deterministic, checkable, keeps ground truth crisp) rather
than a soft objective — this also makes instances *more binding*, which is the
point (§0). A soft/optimising variant can be a separate **ablation** later.

---

## 4. How the user inputs the constraints they want

The constraints the user named map onto the existing two input files — extend,
don't invent a new mechanism.

**`planning_scenario.yaml` (run knobs) — extend:**
```yaml
name: my_run
target_semesters: 8            # how many semesters to graduate within  ✅ user ask
max_units_per_semester: 20     # units/sem cap                          ✅ user ask
min_units_per_semester: 0      # NEW: optional floor (realistic: ~12 when enrolled)
start_term: 1                  # NEW: plan sem 1 maps to Term 1 or 2
focus_area: artificial_intelligence   # NEW: fix the focus area, or `any`  ✅ user ask
heavy_conflicts: [[CS2030S, CS2040S], [CS2040S, CS2100]]  # NEW: don't co-schedule
industrial_experience: two_three_month | six_month | fyp_substitute  # NEW
```
**`student_example.yaml` (student state) — extend:** add `completed`/`exempted`
for the new modules, keep `conditions` (math bridging, english_path), add
`has_h2_math: true|false` (drives MA1301/X), `gpa`/`eligible_fyp` if we gate
CP4101.

Validation (`src/model.py`): every referenced code exists in the snapshot; every
prereq-tree leaf exists; `focus_area` is a known area or `any`; bucket targets
sum to ≥160; `min ≤ max` units.

---

## 5. "Is it satisfiable, and what's the plan?" — the answer path

`solve()` already returns `SolveResult.status ∈ {OPTIMAL, FEASIBLE, INFEASIBLE,
...}` plus `plan: {semester → [modules]}`. Iteration 2 adds:
- **Satisfiability** is just `result.feasible`. For **INFEASIBLE**, add
  *explanation*: post each requirement/bucket as a reified indicator and use
  CP-SAT `sufficient_assumptions_for_infeasibility` (or iteratively drop
  requirement groups) to report *which* requirement can't be met within T
  semesters — far more useful than a bare "no", and a great demo/eval artifact.
- **Checker parity:** run `check_plan()` on every solved plan in tests (iter1
  already does this) so the ground truth stays trustworthy for grading LLM plans.

---

## 6. Complications (industrial experience / team project / FYP / NOC / NUSC)

```yaml
# program_cs.yaml (excerpt)
industrial_experience:
  options:
    - {set: [CP3880], units: 12}          # 6-month ATAP
    - {set: [IS4010], units: 12}
    - {set: [ETP3201L], units: 12}
    - {set: [CP3200, CP3202], units: 6, each: true}   # two 3-month
    - {set: [CP3107, CP3110], units: 6, each: true}   # CVWO I/II
    - {set: [ETP3205], units: 6}
  fyp_substitute: {set: [CP4101], units: 12, requires: eligible_fyp}  # GPA≥4.0 @70%
team_project:
  min_units: 8
  valid_sets: [[CS3203], [CS3216, CS3217], [CS3281, CS3282]]   # ordered pairs get prereq edges
cp_coded:
  max_units: 12                           # excludes industrial experience
  options: [CP3106, CP3209, CP4101, CP4106]   # + UROP research codes
```
- **Internship term semantics:** internships usually run in a Special Term or a
  dedicated semester. Model via a student `conditions.internship_term: k` that
  blocks/relaxes academic load in that term (lowers its effective unit cap).
- **NOC** → TR-coded internship units (e.g. TR3202) + a whole-term block.
- **NUSC** → a separate `program_cs_nusc.yaml` overlay swapping the ULR group's
  `satisfied_by` lists; keep the base CS program clean. Treat NOC/NUSC/UROP as
  **optional overlays**, add them only after the core Breadth&Depth works.

---

## 7. Frontend — input constraints, see satisfiability, see the sem-by-sem plan

**Recommend Streamlit** (pure Python on top of the existing `solve()` objects,
no JS build, runs on Windows, fastest route to a demo for the Week-of-9-Nov
presentation). One app, three panels:

1. **Inputs** — form bound to `planning_scenario` + `student`: sliders for
   units/sem cap + target semesters, a focus-area dropdown, checkboxes for
   completed/exempted modules and conditions, internship option. "Solve" button.
2. **Result** — big SAT/UNSAT banner from `result.status`; on UNSAT show the
   blocking requirement (§5). Shows vars/constraints/solve-time (nice for the
   report's cost analysis).
3. **Plan grid** — the solved schedule as a **semester × modules table** (Term
   label, per-sem unit load, a per-sem load bar so imbalance is visible), colour
   modules by bucket (foundation / math / breadth&depth / ULR / UE). Optional
   prereq-tree popover per module (reuse `generate_prereq_graph.py`).

`src/solver.py` already has `--json`; the Streamlit app just calls `solve()`
in-process. A later iteration can add the NL→spec input box (the actual LLM
pipeline) feeding the same form.

---

## 8. NUSMods validation pipeline (`scripts/ingest_nusmods.py`, new)

AY2026/27 is live on the API (verified). Snapshot, don't live-call:
1. `GET https://api.nusmods.com/v2/2026-2027/moduleList.json` → all codes.
2. For each code we care about (foundation+math+ULR + every focus/team/CP/ID/CD
   code we list), `GET /2026-2027/modules/<CODE>.json`; keep raw JSON for
   provenance, then extract `moduleCredit`, `semesterData`→`offered_terms`,
   `prereqTree`, `preclusion`.
3. Transform → our schema: `and/or`→`all_of/one_of`, strip grades, derive
   `level`, attach our own focus/cp/team tags, map `preclusion` into
   `preclusions.yaml` groups.
4. **Validation report:** flag every code in our requirement lists that is
   missing / discontinued / has changed units or offered-terms vs what the
   course page claims — this *is* the "website is sometimes outdated" check the
   user asked for. Pin the output under `data/snapshot_2026-2027/`.

---

## 9. Iteration-2 milestones (order)

1. **M0 — Sync local repo to GitHub `main`** (§10) so solver/checker/tests exist locally.
2. **M1 — NUSMods snapshot + schema** (`ingest_nusmods.py`, snapshot dir, extend validator, prereq tree D11).
3. **M2 — Preclusions + real offered terms** (D12) in solver+checker+tests — first *binding* realism.
4. **M3 — Full program_cs.yaml buckets** + focus_areas.yaml + id_cd.yaml; choose-k/focus/L4000/bucket constraints.
5. **M4 — Complications**: industrial experience, team project, FYP/CP cap, internship-term blocking.
6. **M5 — Infeasibility explanations** + checker parity on everything.
7. **M6 — Streamlit frontend** (§7).
8. **M7 — Docs + regenerate graph + demo scenarios**; run `/checkpoint`; compress iter1 into `history.md`.

Each M follows the convention loop: `solver_constraints.md` → data → `solver.py`
+ `checker.py` → test → `decisions.md`.

---

## 10. Repo-sync note (do first)
The local working dir (`iter1-task1` branch) is **missing** `src/solver.py`,
`src/checker.py`, `tests/`, `CLAUDE.md`, and the planning docs that exist on
GitHub `main` (`yusen-luan/can-i-graduate`). Before building iter2, sync local to
`main` (fetch + merge/rebase, or branch from the GitHub state) so we're not
rebuilding work. I did not modify the local git state — flagging for a decision.

---

## 11. Open decisions — RESOLVED in the audit below
Superseded by Part B. Summary: Streamlit (minimal), scenario-fixed focus area with
`any` option, curated-but-broad canonical subset, workload balance is an **optional
per-instance preference (not a degree rule)**, sync = fast-forward (done).

---

# PART B — Critical audit & FINAL Iteration-2 scope

Audited as engineer + researcher after syncing the real repo. The plan above is
directionally right but had real flaws. Findings, most important first.

## B1. Ground-truth correctness beats model completeness (research-critical)
The CSP+checker are the **oracle** that grades the LLM pipelines. A model that is
*wrong* (rejects plans a real advisor accepts, or vice-versa) silently corrupts
the entire evaluation. Therefore: (a) preserve the solver/checker **two-implementation
parity** discipline without exception; (b) every simplification is written down in
`program_cs.yaml: assumptions` + `status.md`; (c) prefer a **smaller model that is
provably correct** over a sprawling one that is plausibly buggy.

## B2. BUG in my own plan: "hard `heavy_conflicts`" would corrupt ground truth
I earlier argued workload-balance ("don't stack CS2030S/CS2040S/CS2100") should be a
**hard degree constraint** "to keep ground truth crisp." That is wrong: it is **not a
real graduation rule**, so hard-coding it makes the oracle reject genuinely valid
plans — exactly the ground-truth corruption of B1. **Correction:** workload balance is
a **per-instance user preference**. It lives in the scenario and is only active when
the instance requests it (then it's a hard constraint *for that instance*, and the NL
problem statement must mention it so the LLM sees it too). Baseline degree feasibility
never depends on it. This also serves the research: preference-laden instances are
precisely where LLM-direct tends to diverge from the solver.

## B3. Over-engineering to cut from iter2 (serve the graded question, not maximalism)
- **Drop `assign[m,bucket]` double-counting ILP.** NUS lets a required module that is
  also a focus primary count structurally toward the focus area; the hard part is only
  *unit accounting* to 160. Full per-module bucket assignment is NP-ish and brittle.
  **Replace with:** structural "take ≥k from set S" constraints (which may share
  modules) + a **global `total_units ≥ 160`** floor, with **UE generic placeholders
  absorbing slack**. Documented simplification; revisit only if the eval needs exact
  per-bucket unit partitioning.
- **Defer NOC / NUSC / UROP overlays** to iter3. They multiply program variants for
  little extra discriminating power now.
- **Frontend is secondary.** It contributes nothing to the LLM-vs-solver evaluation;
  it's a presentation aid the user asked for. Build a **minimal** Streamlit app, don't
  gold-plate it.

## B4. prereq tree: reify in solver, evaluate in checker — do NOT force CNF
NUSMods trees can be disjunctions of conjunctions (DNF), e.g. `or:[A, and:[B,C]]`.
iter1's `prereq_clauses()` returns CNF (list of OR-clauses); CNF-converting a DNF tree
can blow up and is easy to get wrong. **Correction:**
- **Checker:** recursively *evaluate* the boolean tree against `satisfied_before(p,s)`
  — trivial and exact.
- **Solver:** recursively build a reified BoolVar "tree satisfied before `s`" with
  `AddBoolAnd`/`AddBoolOr`/`OnlyEnforceIf`, then `x[m,s] → tree_sat_before`. No CNF
  distribution, no blow-up. Keep the flat `all_of`/`conditional` path working so the
  49 existing tests stay green (a flat list is just a one-level `all_of` tree).

## B5. What actually makes iter2 instances *binding* (the real point)
status.md: iter1 is too easy (unit cap alone fixes the horizon). The features that add
genuine binding-ness, in order of value:
1. **Real single-semester offerings** (from NUSMods) — forces ordering across years;
   the focus-elective pool naturally supplies sem-1-only / sem-2-only modules.
2. **Focus-area depth + ≥12u @L4000** — forces choosing a coherent set of advanced
   modules with their own deep prereq chains (CS2109S→CS3243→CS4243…).
3. **Preclusions** — mostly matter for reading prior `completed` history.
4. **Optional preferences** (workload balance, min load, no-gap) — tunable difficulty.
Industrial-experience term-blocking also bites. These are what should differ between
"easy" and "hard" NL instances in the eval set.

## B6. UE and ID/CD stay generic (documented simplification)
Modelling all 40 UE units as free choice over every NUS module explodes the domain and
tests nothing about reasoning. Keep **UE = N generic 4u placeholders (units only)** and
**ID/CD generic** (iter1's `*_GENERIC*`). Real term-offering variety for the
"sem-1-only vs sem-2-only" goal comes from the **focus pool**, which is real.

## B7. Ingestion must self-validate, not be hand-checked
~100 canonical codes (foundation+math+ULR+all focus primaries/electives+project+CP)
is too many to verify by hand. `ingest_nusmods.py` pulls them in one pass and **emits a
report**: missing/discontinued codes, unit mismatches, and offered-term mismatches vs
what we assumed — that report *is* the "website is sometimes outdated" safeguard.

## FINAL iteration-2 scope (what we will actually build now)
1. **M1** NUSMods AY2026/27 ingestion → `data/snapshot_2026-2027/` + enriched schema
   (prereq tree, `level`, real `offered_terms`, preclusion groups) + extended validator.
2. **M2** solver+checker+tests: recursive prereq tree (B4), preclusion groups, real
   offered terms. Existing 49 tests must stay green.
3. **M3** `program_cs.yaml` full 160u buckets + `focus_areas.yaml`; structural
   choose-k, focus-area indicator, ≥12u@L4000, `total_units ≥ 160` with UE slack.
4. **M4** industrial experience (6/12u options, internship-term load block) + team
   project (valid sets, intra-set ordering).
5. **M5** minimal Streamlit app: inputs (units/sem, #sems, focus area, prefs) →
   SAT/UNSAT (+ which requirement blocks, if infeasible) → semester-by-semester grid.
6. **M6** docs kept in lockstep (`solver_constraints.md` first, then `decisions.md`,
   `status.md`, `CLAUDE.md`, `README.md`). No commit/push until the user says so.
Deferred to iter3: NOC/NUSC/UROP overlays, soft-objective workload optimisation
(as an ablation), exact per-bucket unit partitioning, NL-instance + LLM pipelines.

## Sources
- CS Cohort 2026/2027 — https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/
- CS Focus Areas — https://www.comp.nus.edu.sg/programmes/ug/focus
- NUS Bulletin AY2025/26 SoC — https://www.nus.edu.sg/nusbulletin/ay202526/programmes/school-of-computing/undergraduate-education/
- NUSMods API v2 (AY2026/2027 verified) — https://api.nusmods.com/v2/2026-2027/modules/CS2040S.json
