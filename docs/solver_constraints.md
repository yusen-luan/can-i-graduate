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
