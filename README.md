# CS course-planning CSP — Iteration 1 model

This repo scaffold separates the problem into three data layers.

## 1. Module data

`data/modules.yaml`

Describes reusable facts about modules:

- units
- canonical / bridging / placeholder type
- semester offering
- ordinary prerequisites (`all_of`)
- conditional bridging prerequisites (`conditional -> one_of`)
- corequisites

It does **not** store whether a particular student is exempted.

## 2. Program data

`data/program_cs_iter1.yaml`

Describes what the Iteration 1 CS degree model requires:

- 8-semester planning horizon
- currently supplied required CS / Math / ULR / Ethics modules
- canonical GEA1000 / ES2660 choices
- generic GEC, GES and GEN placeholders
- the 12-unit ID/CD rule as exactly three 4-unit placeholder modules
- configurable semester unit cap (20 units for current Iteration 1 testing)

## 3. Student data

`data/student_example.yaml`

Describes one student:

- `completed[module]`
- `exempted[module]`
- `conditions.needs_math_bridging`
- `conditions.english_path`

In this Iteration 1 model, `exempted=true` means the module itself and downstream prerequisite requirement are treated as satisfied without scheduling that module.

## Bridging

MA1301 and MA1301X are in the global module domain but are not automatically degree requirements.

If:

```yaml
conditions:
  needs_math_bridging: true
```

then one of MA1301 / MA1301X must be satisfied before MA1521, MA1522, and CS1231S can be scheduled.

## Generate graph

```bash
pip install -r requirements.txt
python scripts/generate_prereq_graph.py
```

GitHub renders `docs/prerequisite_graph.md` as Mermaid.

## Validate data

```bash
python src/model.py
```

## Current deliberate simplifications

- CS2105 and CS2107 are excluded from Iteration 1 because they are not part of the current graduation requirement set

- canonical CS modules only
- all modules assumed offered in both Semester 1 and Semester 2
- ES2660 fixed as the Critique & Expression choice
- GEA1000 fixed as the Data Literacy choice
- GEC/GES/GEN are generic placeholders
- ID/CD courses are generic placeholders
- preclusions and negative constraints are excluded
- English bridging field exists, but no bridging module is inserted until its actual code/rule is supplied


## English pathway

The student file contains exactly one `english_path`:

```yaml
conditions:
  english_path: direct_es2660
```

Allowed values:

- `direct_es2660`
- `es1103_required`
- `es1000_then_es1103`

This activates the appropriate conditional prerequisite chain without making ES1000/ES1103 universal CS-program requirements.


## Current canonical Iteration 1 size

The current canonical path contains **22 modules** and
**88 units**, excluding conditional bridging modules.

- Fixed required modules outside ID/CD: 19 modules = 76 units
- ID/CD pillar: exactly 3 modules = 12 units
- Total: 22 modules = 88 units

`CS2101 + CS2103T` are two separate 4-unit modules but form one 8-unit
same-semester scheduling bundle.

The completion horizon is configurable through `data/planning_scenario.yaml` (`target_semesters`).


## Planning scenario

Run-specific planning choices now live in `data/planning_scenario.yaml` rather
than in module or degree data.

```yaml
target_semesters: 8
max_units_per_semester: 20
```

This lets the same CS program and student profile be tested for different
completion targets (for example 5, 6, 7, or 8 semesters) without rewriting the
degree definition.
