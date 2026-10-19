# Iteration 1 solver semantics

Let:

- `x[m,s] ∈ {0,1}` mean module `m` is scheduled in semester `s`.
- `completed[m]` be student input.
- `exempted[m]` be student input.
- `satisfied_before(m,s)` mean `m` was completed/exempted before planning, or was scheduled in an earlier semester.

## 1. Schedule each module at most once

For every module `m`:

`Σ_s x[m,s] <= 1`

If `completed[m] = 1` or `exempted[m] = 1`, force:

`Σ_s x[m,s] = 0`

because the student should not schedule it again.

## 2. Required module satisfaction

For each program-required module `m`:

`completed[m] OR exempted[m] OR Σ_s x[m,s] = 1`

Conceptually, exemption counts as satisfying the program requirement without consuming a semester slot or units.

## 3. Ordinary prerequisite

For prerequisite edge `p -> m`, if `m` is taken in semester `s`:

`x[m,s] <= completed[p] + exempted[p] + Σ_{t < s} x[p,t]`

Examples:

- `CS1101S -> CS2030S`
- `CS1101S AND CS1231S -> CS2040S`
- `CS2040S -> CS3230`

For an `all_of` list, apply this constraint once for every prerequisite in the list.

## 4. Conditional bridging prerequisite

For MA1521, MA1522, and CS1231S:

If `student.conditions.needs_math_bridging = true`, then before taking the target module the student must have satisfied at least one of:

- MA1301
- MA1301X

For target `m` in semester `s`:

`x[m,s] <= satisfied_before(MA1301,s) + satisfied_before(MA1301X,s)`

If `needs_math_bridging = false`, this constraint is not activated.

The bridge modules are therefore in the global module domain, but they are not program-required modules.

## 5. Corequisite

Current model:

`CS2101 <-> CS2103T`

If neither has already been completed/exempted, they must be scheduled in the same semester.

This is represented as:

`same_semester_unless_already_satisfied`

rather than as a prerequisite edge.

## 6. Semester offering

All Iteration 1 modules currently have:

`offered_terms: [1, 2]`

Planning semesters map to NUS terms as:

- plan semesters 1,3,5,7 -> Semester 1
- plan semesters 2,4,6,8 -> Semester 2

Then `x[m,s] = 0` whenever module `m` is not offered in that term.

## 7. Semester unit limit

For each semester `s`:

`Σ_m units[m] * x[m,s] <= max_units_per_semester`

For current Iteration 1 testing:

`max_units_per_semester = 20`

The value remains configurable in `program_cs_iter1.yaml`. In later iterations, it should be supplied as part of the planning scenario / student preferences rather than treated as a permanent hard-coded constant.

## 8. ID/CD requirement

Candidates:

- ID_GENERIC_1
- ID_GENERIC_2
- ID_GENERIC_3
- CD_GENERIC_1

Require exactly 3 modules total, with at least 2 ID and at most 1 CD.

So valid patterns are exactly:

- 3 ID
- 2 ID + 1 CD

## 9. No preclusions yet

Iteration 1 deliberately ignores:

- "must not have taken X"
- module preclusions
- mutually exclusive equivalents
- non-canonical CS1010-family substitutions

These can be added after the baseline CSP is working.


## 10. English placement / bridging

English placement is modelled as a single student-state variable:

`english_path ∈ {direct_es2660, es1103_required, es1000_then_es1103}`

This is preferable to multiple booleans because exactly one English pathway should apply.

### direct_es2660

No additional English bridging prerequisite is activated.

### es1103_required

Before ES2660 can be scheduled, ES1103 must already be satisfied:

`x[ES2660,s] <= satisfied_before(ES1103,s)`

### es1000_then_es1103

Before ES1103 can be scheduled, ES1000 must already be satisfied:

`x[ES1103,s] <= satisfied_before(ES1000,s)`

and before ES2660 can be scheduled:

`x[ES2660,s] <= satisfied_before(ES1103,s)`

ES1000 and ES1103 are in the global domain but are not unconditional CS-program requirements. They are activated only by the student's English placement pathway.


## 11. Atomic scheduling bundle: CS2101 + CS2103T

CS2101 and CS2103T remain two separate 4-unit modules in module/program data,
but the scheduler treats them as one atomic 8-unit scheduling bundle.

For each semester `s`:

`x[CS2101,s] = x[CS2103T,s]`

unless one/both modules are already satisfied before planning.

For the standard unsatisfied case, this gives an all-or-nothing 8-unit bundle:
both modules are scheduled in the same semester and consume 8 units together.

This is preferable to modelling them as an ordinary prerequisite edge because
neither module is meant to be taken strictly before the other.


## 12. Configurable completion horizon

The planning scenario contains:

`target_semesters`

For a target of `T` semesters, the solver may assign modules only to semesters
`1..T`.

Current default:

`target_semesters = 8`

This should remain configurable so experiments can ask whether the same
requirements can be completed in 5, 6, 7, or 8 semesters.

A requested target is feasible only if all prerequisite, bundle, requirement,
offering, and unit-load constraints can be satisfied within `1..T`.


# Iteration 2 semantics (full BComp(CS) AY2026/27)

Iteration 2 keeps every iter1 constraint and adds the rest of the 160-unit
degree. Module *facts* come from a frozen NUSMods AY2026/27 snapshot
(`data/snapshot_2026-2027/`); degree *rules* are curated in `data/program_cs.yaml`,
`data/focus_areas.yaml`, `data/snapshot_2026-2027/preclusions.yaml`. The iter2
solver is `build_and_solve_iter2`; its independent checker is `check_plan_iter2`.
Variables are unchanged: `x[m,s] ∈ {0,1}`.

Definitions used below:
- `sat(m) = completed[m] ∨ exempted[m] ∨ Σ_s x[m,s]` (requirement satisfaction).
- `held(m) = completed[m] ∨ Σ_s x[m,s]` (credit held; **excludes exempted** — a
  waiver grants no credit). Used only by preclusions.
- `units_of(P) = Σ units[m]·sat(m)` over modules matching predicate `P`.

## I2.1 Prerequisite tree (generalises §3)
NUSMods publishes prerequisites as a recursive `and`/`or` tree with `CODE:grade`
leaves; we store it as `prerequisites.tree` with `all_of`/`one_of`/leaf (grades
stripped). For module `m` in semester `s`, `x[m,s] ⇒ tree_satisfied_before(s)`,
where a leaf `p` is satisfied-before-`s` iff `completed[p] ∨ exempted[p] ∨ p∈waived
∨ Σ_{t<s} x[p,t]`. The solver reifies the tree with BoolAnd/BoolOr (handles DNF
trees, e.g. CS3244, without CNF blow-up); the checker evaluates the tree directly.
Leaves that are external non-canonical codes we do not model are unsatisfiable
via scheduling (only `completed`/`exempted`/`waived` can satisfy them).

## I2.2 Placement waiver for bridging prerequisites
MA1521/MA1522/CS1231S list only `one_of:[MA1301, MA1301X]` on NUSMods, because the
real prerequisite is A-level H2 Maths (not a module). `bridging_waived(student)`
returns the bridges that a placement stands in for: A-level H2 Maths waives
MA1301/X (when `needs_math_bridging=false`); the direct ES2660 path waives
ES1000/ES1103. Waived bridges are treated as satisfied prereq leaves and are not
scheduled. A student who *needs* bridging must schedule a bridge before the target.

## I2.3 Preclusions (non-canonical conflicts)
For each group in `preclusions.yaml` (e.g. `intro_programming`,
`data_structures`, `discrete_math`): `Σ_{m∈group} held(m) ≤ 1`. Canonical-only
planning places only the canonical member, but the group still reads a student's
prior non-canonical `completed` history.

## I2.4 ULR / ID-CD / ethics
`must_satisfy_groups` (≥1 of each pillar's `satisfied_by`), ID/CD exactly-3 with
≥2 ID ≤1 CD (by `category` tag). Pick-list pillars (Cultures = GEC%, Singapore =
**GESS%**, Communities = GEN%) and ID/CD now use a **verified real-course subset**
(NUSMods facts; full authoritative lists in `data/ge_pillars.yaml`,
`data/id_cd.yaml`), not generic placeholders. Digital Literacy = CS1101S,
Critique & Expression = ES2660, Data Literacy = GEA1000 are the CS-prescribed
fixed choices. Only Unrestricted Electives remain generic placeholders.

## I2.13 Year-long Communities & Engagement service learning
The C&E pillar may be satisfied by a year-long Service-Learning course split over
**two contiguous semesters**: an X half (Term 1) and a Y continuation (Term 2).
Modelled as `x[Y,s] = x[X,s-1]` for s≥2 and `x[Y,1]=0`, so Y sits in exactly the
semester after X. X carries the 4u pillar credit; Y is a 0u continuation (NUSMods
shows 4u on each half of the single year-long course — documented in
`data/generic_modules.yaml`). Picking an X in a pillar `satisfied_by` list thus
commits the student to its contiguous Y.

## I2.5 Focus area
Rule (`focus_areas.yaml`): an area is satisfied by `courses_per_area` (3)
primaries with `≥ min_level4000_in_area` (1) at level-4000+. If the scenario fixes
`focus_area = A`: `Σ_{m∈prim(A)} sat(m) ≥ 3` and `Σ_{m∈prim(A), L≥4000} sat(m) ≥ 1`.
If `focus_area = any`: introduce `satA` per area implying both conditions, and
require `Σ_A satA ≥ 1`.

## I2.6 Level-4000 depth
`units_of(level ≥ 4000) ≥ 12`.

## I2.7 Breadth & Depth 32-unit bucket (verified AY2026/27)
B&D is a **single 32-unit bucket** of Computing (CS/IFS/CP) courses — pillar ∈
{`breadth_depth`, `industrial_experience`} — that **contains** the focus-area
courses, the ≥12u at level-4000, and the 6–12u industrial experience:
`units_of(pillar ∈ B&D) ≥ 32`. There is **no** separate Computer-Systems
Team-Project requirement in AY2026/27 (cohort page + NUS Bulletin confirm; the
earlier build's team-project rule was removed — see docs/iter2_verification.md §6).
Computing units beyond 32 legitimately count as Unrestricted Electives (UE is
unrestricted), so the bucket is a floor, not a partition.

## I2.8 Industrial experience (inside B&D; done over the vacation)
Choose **exactly one** option; take exactly that option's modules and no other
industrial module (no padding). `Σ_i opt_i = 1`; `opt_i ⇒ sat(m) ∀m∈set_i`;
`sat(m) ≤ Σ_{i: m∈set_i} opt_i`. Options: 12u single stints (CP3880/IS4010/ETP3201L)
or two sequential 6u stints (CP3200→CP3202, CP3107→CP3110, with a real prereq edge).
Because internships run over the **vacation / special term** (NUSMods `CP3880`
`semesterData` spans terms 1–4), their units are **excluded from the per-semester
unit cap** (§7 is summed over non-industrial modules only); they still count toward
the 160u total and the 32u B&D and still respect prerequisites. This stops an
internship from inflating the graduation horizon. Limitation: the 6-month ATAP in
reality fills a whole semester; the cap-exclusion approximates this loosely (full
special-term slots deferred to iter3).

## I2.9 CP-coded cap and unit total
`units_of(m ∈ cp_coded.codes) ≤ 12`. `units_of(true) ≥ 160`. Unrestricted
Electives are modelled as optional `UE_GENERIC_*` fillers (4u, both terms, no
prereqs) that absorb whatever remains up to 160 — UE is **not** fixed at 40u,
because B&D modules beyond the 32u bucket count as UE (avoids double-counting;
see docs/iter2_plan.md B3).

## I2.10 Objective (still a CSP)
`minimise 100·(total scheduled units) + (module count)`. With the ≥160 floor this
lands at exactly 160 units and removes any incentive to pad with large optional
modules; it only disambiguates equally-valid plans, so the problem stays a pure
feasibility CSP (cf. D9).

## I2.11 Optional per-instance preferences (scenario, not degree rules)
Active only when the scenario sets them; never affect baseline feasibility:
- `heavy_conflicts`: pairs `(a,b)` with `x[a,s]+x[b,s] ≤ 1 ∀s`.
- `min_units_per_semester`: with a per-semester `used_s`, `load_s ≥ min·used_s`.
- `no_empty_semesters`: `used_s ≥ used_{s+1}` (no gaps).

## I2.12 Deliberate iteration-2 simplifications
Canonical-only; special terms (3,4) not modelled (special-term-only offerings
treated as unavailable); by-arrangement modules without `semesterData` default to
both semesters; the 32u B&D aggregate is not enforced (its sub-rules are);
UE/ULR-picklist/ID-CD are generic placeholders; NOC/NUSC/UROP overlays deferred.
