# Iteration 2 — Universe & constraint verification (AY2026/27)

Systematic re-check of every requirement category and every constraint against
authoritative sources, done 2026-10-19 after the first iter2 build. Verdicts:
**✓ confirmed**, **✗ corrected** (bug found), **? flag** (cannot verify
programmatically — needs a human / portal login).

## Sources of truth (what to refer to)
| For | Authoritative source |
|---|---|
| Degree structure, unit buckets, B&D composition | CS Cohort 2026/27 page + NUS Bulletin AY25/26 SoC undergraduate |
| Focus-area membership (primaries/electives) | CS Focus Areas page (but cross-check each code on NUSMods) |
| Module **facts** (units, offered terms, prereq tree, preclusion) | **NUSMods API** `/v2/2026-2027/modules/<CODE>.json` — overrides the faculty pages |
| ID/CD and GE pick-lists (actual course codes) | NUS Bulletin SoC Common Curriculum appendix + course-registration portal (not open JSON) |
| Internship timing, overload, APC, early graduation | SoC UG FAQ + Registrar continuation/graduation rules |

Links: CS 26/27 https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/ ·
Focus https://www.comp.nus.edu.sg/programmes/ug/focus/ ·
Bulletin https://www.nus.edu.sg/nusbulletin/ay202526/programmes/school-of-computing/undergraduate-education/ ·
NUSMods https://api.nusmods.com/v2/2026-2027/

---

## 1. Core major (CS Foundation) — ✓ confirmed
CS1231S, CS2030S, CS2040S, CS2100, CS2101, CS2103T, CS2106, CS2109S, CS3230
(36u). Matches cohort page + bulletin exactly. All 9 verified present in the
NUSMods AY26/27 snapshot at 4u each. **Math & Science** MA1521, MA1522, ST2334
(12u) ✓. (Note CS1101S is *Digital Literacy ULR*, not Foundation — modelled
correctly as a required ULR module.)

## 2. ID / CD — ? flag (generic placeholders; real list not open)
Rule ✓: 12u, ≥2 ID, ≤1 CD. The actual ID/CD **course-code list** is a large
curated set in the Bulletin appendix / registration portal, not available as open
JSON. We keep `*_GENERIC*` placeholders (units-only). This is a *documented
simplification*, acceptable because the specific ID/CD course does not change
plan feasibility. To make it real later, scrape the Bulletin SoC Common-Curriculum
ID & CD appendix. **No hallucinated ID/CD codes exist in the model** (only generics).

## 3. Pillar / ULR (Common Curriculum, 24u) — ✓ with noted simplifications
| Pillar | Truth | Our model |
|---|---|---|
| Digital Literacy | CS1101S | CS1101S ✓ |
| Critique & Expression | ES2660 **or** UTW% **or** RVX% | ES2660 only (canonical pick) — simplification noted |
| Cultures & Connections | GEC% (many) | GEC_GENERIC placeholder |
| Data Literacy | GEA1000 / BT1101 / ST1131 / DSA1101 | GEA1000 (canonical pick) |
| Singapore Studies | GES% | GES_GENERIC |
| Communities & Engagement | GEN% | GEN_GENERIC |
Computer Ethics: IS1108 ✓. All pick-lists modelled as fixed canonical choice or
generic placeholder — consistent with the canonical-only scope.

## 4. Focus areas — ✓ corrected via NUSMods (faculty page is stale)
11 areas; our `focus_areas.yaml` primaries match the Focus page **except** we drop
**CS4232** — the faculty page still lists it as an Algorithms primary but **NUSMods
has no CS4232 in AY26/27** (ingestion flagged it). This is the headline example of
"refer to NUSMods, the website is outdated." HCI is valid ("CS cohort 2025 and
after"). We store **primaries only**, which is all the focus-satisfaction rule
needs; electives matter only as B&D unit fillers (handled by the B&D bucket, §6).
Every primary we keep was verified to exist in the NUSMods snapshot.

## 5. "Focus area" vs "Breadth & Depth" — corrected understanding
- **Focus area** = a *structural* rule: satisfy ≥1 area by taking **3 Area-Primary
  courses incl. ≥1 at level-4000+**. CS Foundation courses that are also primaries
  (CS2109S, CS2103T, CS3230) **count**, so typically only ~2 extra courses are
  needed. It does **not** have its own unit quota.
- **Breadth & Depth** = a *32-unit bucket* of Computing (CS/IFS/CP) courses that
  **contains** the focus-area courses, the ≥12u at level-4000, **and** the
  industrial experience. These are the same 32 units viewed through different
  rules, not additive buckets.

## 6. Industrial experience / FYP and the B&D overlap — ✗ corrected (big one)
**Bug in the first iter2 build:** it (a) invented a *Computer Systems Team Project*
requirement (CS3203 / CS3216+17 / CS3281+82), and (b) treated **industrial
experience as a separate requirement** on top of B&D. Both are wrong for 26/27:
- **No team-project requirement exists** in the 26/27 BComp(CS). Cohort page and
  Bulletin both list B&D as exactly {focus area, ≥12u L4000, 6–12u industrial}.
  → **Remove `team_project` entirely.**
- **Industrial experience (6–12u) is a subset *inside* the 32u B&D**, not separate.
  → Model B&D as a 32u bucket (pillar ∈ {breadth_depth, industrial_experience})
  with industrial (6–12u), L4000 (≥12u) and the focus area all *within* it.
- **FYP:** CP4101 (12u dissertation) may *replace* the industrial experience for
  GPA ≥ 4.0 / Honours-Highest-Distinction students. CP-coded cap 12u (excl.
  industrial). Modelled as an optional substitute gated on `eligible_fyp`.

Corrected unit map (sums to 160): CC 40 + Foundation 36 + Math 12 + **B&D 32
(incl. industrial)** + UE 40.

## 7. Minimum semesters — ✗ clarified (not a hard 8)
160u / 20u-cap ⇒ **8 is the arithmetic floor at a 20-unit load**, not a rule. The
model already supports finishing earlier via (a) a higher per-semester cap
(overload — the UI allows up to 28), and (b) `exempted`/advanced-placement credits
that reduce the units left to schedule. We will add a regression test that e.g.
T=7 becomes feasible at a higher cap, and document that early graduation = overload
and/or APC. We should **not** hard-code 8.

## 8. Internships in special terms — ✗ corrected
NUSMods `CP3880.semesterData` spans **terms 1–4** (incl. special terms 3 & 4);
3-month internships (CP3200/CP3107) are typically done over the **vacation /
special term**. The first build modelled only regular Terms 1 & 2 and let an
internship consume a regular-semester unit-cap slot, which wrongly inflated the
horizon. **Correction:** industrial-experience units are **excluded from the
regular per-semester unit cap** (they are done over the vacation / as a block),
while still counting toward the 160u total and the 32u B&D and still respecting
their prerequisites. Documented limitation: the 6-month ATAP (CP3880) in reality
occupies a whole semester with little other load, which this cap-exclusion
approximates loosely; full special-term slots are deferred to iter3.

## 9. Module facts accuracy / no hallucination — ✓
Every module **fact** (units, offered terms, prereq tree, preclusion) is taken
verbatim from the NUSMods AY26/27 snapshot (`scripts/ingest_nusmods.py` →
`data/snapshot_2026-2027/`), not typed by hand. The only hand-authored data are
(a) which codes belong to which requirement list — each cross-checked to exist in
the snapshot — and (b) the degree *rules* (from the cohort page/bulletin).
Hand-authored items that are simplifications (not errors): generic GE/ID/CD/UE
placeholders. The ingestion `validation_report.md` is the running "is NUSMods
different from what we assumed" check.

---

## Corrections to apply (this pass)
1. Remove the `team_project` requirement from `program_cs.yaml`, solver, checker, tests.
2. Add a **B&D ≥ 32u** bucket constraint (pillar ∈ breadth_depth / industrial_experience).
3. Exclude **industrial-experience units from the per-semester unit cap** (vacation/special-term).
4. Keep industrial = exactly one option (already correct); keep L4000 ≥ 12, focus rule.
5. Add a test that early graduation (T < 8) is feasible under overload (cap > 20).
6. Update `solver_constraints.md` (I2.7 removed, I2.8/I2.9 reworded, new B&D bucket rule),
   `decisions.md` (supersede D15/D18; add D19–D21), `status.md`, `program_cs.yaml` assumptions.

## Update 2026-10-19b — real GE/ID/CD + service learning wired in
After the user supplied the authoritative lists, the generic ULR/ID/CD
placeholders were replaced with **verified real NUSMods courses** (full lists
captured in `data/ge_pillars.yaml` and `data/id_cd.yaml`; the CSP wires a
verified subset). Corrections made: Singapore-Studies prefix **GES → GESS**;
Data Literacy / Critique / Digital are the CS-prescribed fixed choices; **GEC1000
dropped** (not offered in 26/27 — another stale-list catch). New constraint added:
**year-long Communities & Engagement service learning** = two contiguous semesters
(GEN..X Term 1 → GEN..Y Term 2), solver + checker + tests. Only Unrestricted
Electives remain generic. 81 tests pass.

## Still open / for a human to confirm (don't guess)
- The GE/ID/CD **full** lists are captured for reference but the CSP wires only a
  verified subset; wiring every code (100s) is deferred as low-value for feasibility.
- CP3107/CP3110 appear in **both** the C&E list and Industrial Experience — the
  model does not yet handle that single-module double-role (kept them as industrial).
- Whether any niche B&D rule (level-1000 cap, must-include course) applies beyond
  the three listed constraints.
- APC credit limits (Registrar policy). **Overload ceiling: assumed 28 units/sem
  for iter2** (`program_cs.yaml: max_overload_units`); an instance requesting a
  higher per-semester cap is rejected by the solver and flagged by the checker.
