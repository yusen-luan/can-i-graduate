"""Independent plan checker: does a given semester plan satisfy every constraint?

Written directly from docs/solver_constraints.md without using the solver, so it
can (a) cross-check solver output and (b) grade plans produced by other means,
e.g. an LLM reasoning directly.

    python src/checker.py plan.json   # {"1": ["CS1101S", ...], "2": [...], ...}
"""
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import (  # noqa: E402
    load_model,
    load_iter2,
    load_scenario,
    term_of,
    effective_term,
    per_semester_cap,
    is_computing,
    pre_satisfied,
    prereq_clauses,
    prereq_tree_of,
    tree_satisfied,
    bridging_waived,
    required_bridges,
    same_semester_groups,
    must_satisfy_groups,
)


def check_plan(
    plan: Dict[int, List[str]],
    modules: dict,
    program: dict,
    student: dict,
    target_semesters: int,
    max_units_per_semester: int,
) -> List[str]:
    """Return a list of human-readable violations (empty list = valid plan)."""
    errors = []
    plan = {int(s): list(ms) for s, ms in plan.items()}
    sem_of = {}

    # Plan shape, unknown modules, at-most-once, no re-taking
    counts = Counter(m for ms in plan.values() for m in ms)
    for m, c in counts.items():
        if m not in modules:
            errors.append(f"{m}: unknown module")
        elif c > 1:
            errors.append(f"{m}: scheduled {c} times")
        elif pre_satisfied(m, student):
            errors.append(f"{m}: already completed/exempted but scheduled again")
    for s, ms in plan.items():
        if not 1 <= s <= target_semesters:
            errors.append(f"semester {s}: outside horizon 1..{target_semesters}")
        for m in ms:
            sem_of.setdefault(m, s)
    if errors:
        return errors  # later checks assume a well-formed plan

    def satisfied(m):
        return pre_satisfied(m, student) or m in sem_of

    def satisfied_before(m, s):
        return pre_satisfied(m, student) or sem_of.get(m, s) < s

    # Required modules
    for m in program["required_modules"]:
        if not satisfied(m):
            errors.append(f"{m}: required but not satisfied")

    for name, satisfied_by, k in must_satisfy_groups(program):
        if sum(satisfied(m) for m in satisfied_by) < k:
            errors.append(f"{name}: needs {k} of {satisfied_by}")

    # Prerequisites (ordinary + active conditional)
    for m, s in sem_of.items():
        for clause in prereq_clauses(modules[m], student):
            if not any(satisfied_before(p, s) for p in clause):
                need = clause[0] if len(clause) == 1 else "one of " + "/".join(clause)
                errors.append(f"{m} (sem {s}): prerequisite {need} not satisfied earlier")

    # Same-semester bundles / corequisites
    for group in same_semester_groups(modules, program):
        if any(pre_satisfied(m, student) for m in group):
            continue
        sems = {sem_of.get(m) for m in group}
        if len(sems) > 1:
            errors.append(f"{'+'.join(group)}: must be taken in the same semester")

    # Offering
    for m, s in sem_of.items():
        if term_of(s) not in modules[m].get("offered_terms", [1, 2]):
            errors.append(f"{m} (sem {s}): not offered in Term {term_of(s)}")

    # Unit cap
    for s, ms in plan.items():
        units = sum(modules[m]["units"] for m in ms)
        if units > max_units_per_semester:
            errors.append(f"semester {s}: {units} units > cap {max_units_per_semester}")

    # ID/CD
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    n_id = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "ID")
    n_cd = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "CD")
    if n_id + n_cd != idcd["total_modules_required"]:
        errors.append(f"ID/CD: {n_id + n_cd} modules, need exactly {idcd['total_modules_required']}")
    if n_id < idcd["min_id_modules"]:
        errors.append(f"ID/CD: {n_id} ID modules, need at least {idcd['min_id_modules']}")
    if n_cd > idcd["max_cd_modules"]:
        errors.append(f"ID/CD: {n_cd} CD modules, at most {idcd['max_cd_modules']} allowed")

    return errors


def check_plan_iter2(plan, modules, program, student, focus_areas, preclusions,
                     scenario) -> List[str]:
    """Independent validator for the full iter2 degree. Returns human-readable
    violations (empty = valid). Re-implements every constraint in
    build_and_solve_iter2 without importing the solver."""
    T = scenario["target_semesters"]
    cap = scenario["max_units_per_semester"]
    errors: List[str] = []
    plan = {int(s): list(ms) for s, ms in plan.items()}
    waived = bridging_waived(student)

    counts = Counter(m for ms in plan.values() for m in ms)
    for m, c in counts.items():
        if m not in modules:
            errors.append(f"{m}: unknown module")
        elif c > 1:
            errors.append(f"{m}: scheduled {c} times")
        elif pre_satisfied(m, student):
            errors.append(f"{m}: already satisfied but scheduled again")
    sem_of = {}
    for s, ms in plan.items():
        if not 1 <= s <= T:
            errors.append(f"semester {s}: outside horizon 1..{T}")
        for m in ms:
            sem_of.setdefault(m, s)
    if errors:
        return errors

    units = {m: modules[m]["units"] for m in modules}

    def satisfied(m):
        return pre_satisfied(m, student) or m in sem_of

    def held(m):
        """Credit held (completed or scheduled, not exempted); for preclusions."""
        if student["completed"].get(m, False):
            return True
        if student["exempted"].get(m, False):
            return False
        return m in sem_of

    def sat_units(pred):
        return (sum(units[m] for m in sem_of if pred(m))
                + sum(units[m] for m in modules
                      if pre_satisfied(m, student) and pred(m)))

    # required modules + ULR/ethics groups
    for m in program["required_modules"]:
        if not satisfied(m):
            errors.append(f"{m}: required but not satisfied")
    # §10 mandatory English bridges by QET band (Issue #2)
    for m in required_bridges(student):
        if not satisfied(m):
            errors.append(f"{m}: required English bridge (placement band) not satisfied")
    for name, satisfied_by, k in must_satisfy_groups(program):
        if sum(satisfied(m) for m in satisfied_by) < k:
            errors.append(f"{name}: needs {k} of {satisfied_by}")

    # prerequisite tree (evaluated against what is satisfied strictly earlier)
    for m, s in sem_of.items():
        tree = prereq_tree_of(modules[m])
        pred = lambda p: (pre_satisfied(p, student) or p in waived
                          or (p in sem_of and sem_of[p] < s))
        if not tree_satisfied(tree, pred):
            errors.append(f"{m} (sem {s}): prerequisite tree not satisfied earlier")

    # bundles, offering, unit cap
    for group in same_semester_groups(modules, program):
        if any(pre_satisfied(g, student) for g in group):
            continue
        sems = {sem_of.get(g) for g in group if g in sem_of or not pre_satisfied(g, student)}
        if len([g for g in group if g in sem_of]) not in (0, len(group)) or len(sems) > 1:
            errors.append(f"{'+'.join(group)}: must be taken in the same semester")
    for m, s in sem_of.items():
        et = effective_term(s, scenario)           # I2.14 term layout
        if et not in modules[m].get("offered_terms", [1, 2]):
            errors.append(f"{m} (sem {s}): not offered in Term {et}")
    bd = program["breadth_depth"]
    prefs = scenario.get("preferences", {}) or {}
    fyp_code = bd.get("fyp", {}).get("code")
    industrial_mods = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}
    ceiling = program.get("max_overload_units")
    for s, ms in plan.items():
        cap_s = per_semester_cap(scenario, s, cap)  # I2.15 per-slot cap
        if cap_s == 0:
            if ms:  # fully unavailable slot (leave of absence): nothing may be placed
                errors.append(f"semester {s}: blocked (per_semester_cap 0) but has {sorted(ms)}")
            continue
        # industrial experience is done over the vacation / special term and does
        # not consume a regular semester's unit budget.
        u = sum(units[m] for m in ms if m not in industrial_mods)
        if u > cap_s:
            errors.append(f"semester {s}: {u} units > cap {cap_s}")
        if ceiling and u > ceiling:
            errors.append(f"semester {s}: {u} units > overload ceiling {ceiling}")
    # I2.16 CS-count-per-semester cap (Computing modules, excl. off-cap industrial)
    max_cs = prefs.get("max_cs_modules_per_sem", 0)
    if max_cs:
        for s, ms in plan.items():
            n = sum(1 for m in ms if is_computing(m) and m not in industrial_mods)
            if n > max_cs:
                errors.append(f"semester {s}: {n} Computing modules > cap {max_cs}")

    # ID/CD (Issue #14 / I2.4 / D45): a qualifying allocation of exactly
    # total_modules_required courses must EXIST among the taken candidates (>= min
    # ID, <= max CD); surplus eligible ID/CD courses are allowed (they count as UE).
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    n_id = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "ID")
    n_cd = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "CD")
    total = idcd["total_modules_required"]
    min_id = idcd["min_id_modules"]
    max_cd = idcd["max_cd_modules"]
    # best allocation: take as many ID as needed, fill the remainder with up to
    # max_cd CD. A qualifying subset exists iff enough ID AND enough total.
    if not (n_id >= min_id and n_id + min(n_cd, max_cd) >= total):
        errors.append(
            f"ID/CD: {n_id} ID + {n_cd} CD cannot supply a qualifying allocation "
            f"({total} total, >= {min_id} ID, <= {max_cd} CD)")

    # preclusions
    for name, grp in preclusions["groups"].items():
        if sum(bool(held(m)) for m in grp) > 1:
            errors.append(f"preclusion {name}: more than one credit-bearing module")

    # focus area, level-4000
    fr = focus_areas["rule"]
    chosen = scenario.get("focus_area", "any")

    def area_ok(area):
        prim = [m for m in focus_areas["areas"][area]["primaries"] if m in modules]
        got = sum(satisfied(m) for m in prim)
        got4k = sum(satisfied(m) for m in prim if modules[m]["level"] >= 4000)
        return got >= fr["courses_per_area"] and got4k >= fr["min_level4000_in_area"]

    if chosen == "any":
        if not any(area_ok(a) for a in focus_areas["areas"]):
            errors.append("focus area: no area satisfied (3 primaries incl >=1 L4000)")
    elif not area_ok(chosen):
        errors.append(f"focus area {chosen}: not satisfied (3 primaries incl >=1 L4000)")
    # Breadth & Depth 32u bucket + >=12u L4000 depth + 12u CP-coded cap (Issue #1 /
    # I2.9 / D47). CP-coded credit counts toward B&D only when ALLOCATED, and the
    # allocation is capped at 12u; non-CP B&D modules count in full. The plan is
    # valid iff SOME cap-respecting allocation of CP credit meets both floors
    # (enumerate the few taken CP modules). Surplus CP credit counts as UE.
    bd_pillars = {"breadth_depth", "industrial_experience"}
    cp_codes = set(bd["cp_coded"]["codes"])
    cp_cap = bd["cp_coded"]["max_units"]
    non_cp_bd = sat_units(lambda m: modules[m].get("pillar") in bd_pillars
                          and m not in cp_codes)
    non_cp_l4000 = sat_units(lambda m: modules[m]["level"] >= 4000 and m not in cp_codes)
    cp_taken = [m for m in cp_codes if satisfied(m)]
    need_bd = bd["min_units"]
    need_l4 = bd["level4000"]["min_units"]
    bd_ok = l4_ok = both_ok = False
    for r in range(len(cp_taken) + 1):
        for combo in itertools.combinations(cp_taken, r):
            if sum(units[m] for m in combo) > cp_cap:
                continue                      # allocation over the 12u CP cap
            bd_tot = non_cp_bd + sum(units[m] for m in combo)
            l4_tot = non_cp_l4000 + sum(units[m] for m in combo if modules[m]["level"] >= 4000)
            bd_ok = bd_ok or bd_tot >= need_bd
            l4_ok = l4_ok or l4_tot >= need_l4
            both_ok = both_ok or (bd_tot >= need_bd and l4_tot >= need_l4)
    if not both_ok:
        if not bd_ok:
            errors.append(f"breadth & depth: < {need_bd} units even allocating "
                          f"<= {cp_cap}u of CP to B&D")
        if not l4_ok:
            errors.append(f"level-4000: < {need_l4} units within B&D")
        if bd_ok and l4_ok:
            errors.append(f"breadth & depth / level-4000: cannot meet both {need_bd}u "
                          f"and {need_l4}u jointly within the {cp_cap}u CP cap")

    # industrial experience (I2.8, corrected): at most one internship option, OR
    # a GPA-eligible CP4101 dissertation replacing it; no internship padding.
    opts = bd["industrial_experience"]["options"]
    full = [i for i, o in enumerate(opts) if all(satisfied(m) for m in o["set"])]
    diss =bool(fyp_code and satisfied(fyp_code) and student.get("eligible_fyp", False))
    industrial_choice = scenario.get("industrial_option", "any")
    if len(full) > 1:
        errors.append(f"industrial experience: {len(full)} options fully satisfied, at most 1 allowed")
    if industrial_choice != "any":
        want = next((o for o in opts if industrial_choice in o["set"]), None)
        if want is None:
            errors.append(f"industrial experience: unknown industrial_option {industrial_choice}")
        elif not all(satisfied(m) for m in want["set"]):
            errors.append(f"industrial experience: requested option {industrial_choice} not completed")
    elif len(full) == 0 and not diss:
        errors.append("industrial experience: not satisfied (need an internship or eligible dissertation)")
    taken_ind = {m for m in industrial_mods if satisfied(m)}
    chosen_ind = set().union(*[set(opts[i]["set"]) for i in full]) if full else set()
    if taken_ind - chosen_ind:
        errors.append(f"industrial experience: extra modules {sorted(taken_ind - chosen_ind)}")
    # §17b Issue #6 (I2.19): a full-semester (6-month) internship occupies its slot;
    # concurrent non-internship coursework must be <= full_semester_concurrent_cap.
    ie = bd["industrial_experience"]
    full_sem_mods = {m for o in ie["options"] if o.get("full_semester") for m in o["set"]}
    fs_cap = ie.get("full_semester_concurrent_cap", 0)
    for m in full_sem_mods:
        s = sem_of.get(m)
        if s is not None:
            concurrent = sum(units[q] for q in plan.get(s, []) if q not in industrial_mods)
            if concurrent > fs_cap:
                errors.append(f"semester {s}: {concurrent} units of coursework alongside the "
                              f"full-semester internship {m} (concurrent cap {fs_cap})")

    # year-long C&E service learning: X (Sem 1 half) then Y in the contiguous
    # next semester; neither half may appear without the other in sequence.
    for X, Y in program.get("service_learning_pairs", []):
        sx, sy = sem_of.get(X), sem_of.get(Y)
        if sx is not None and sy != sx + 1:
            errors.append(f"service learning {X}->{Y}: Y must be the semester after X")
        if sy is not None and sx != sy - 1:
            errors.append(f"service learning {X}->{Y}: Y present without X in the previous semester")

    # total units (the CP cap is enforced inside the B&D allocation above: excess
    # CP credit beyond the 12u B&D allocation counts here as Unrestricted Electives)
    total = sat_units(lambda m: True)
    if total < program["total_units_required"]:
        errors.append(f"total units {total} < {program['total_units_required']}")

    # I2.17 FYP / UROP (iter3 C3): requested, gated by eligibility.
    if fyp_code:
        if satisfied(fyp_code) and not student.get("eligible_fyp", False):
            errors.append(f"FYP {fyp_code}: taken but student not eligible_fyp")
        if scenario.get("want_fyp") and not satisfied(fyp_code):
            errors.append(f"FYP requested but {fyp_code} not taken")
    urop = bd.get("urop", {})
    urop_codes = urop.get("codes", [])               # UROP = CP3209 (Issue #4)
    if urop_codes:
        urop_taken = [m for m in urop_codes if satisfied(m)]
        if urop_taken and not student.get("eligible_urop", True):
            errors.append(f"UROP {urop_taken}: taken but student not eligible_urop")
        if scenario.get("want_urop") and not urop_taken:
            errors.append("UROP requested but no UROP module taken")
        # Issue #5: UROP spans 2 consecutive semesters and must finish before the FYP.
        span = urop.get("consecutive_semesters", 1)
        before = urop.get("before")
        for uc in urop_codes:
            su = sem_of.get(uc)
            if su is None:
                continue
            if span >= 2 and su == T:
                errors.append(f"UROP {uc}: spans {span} semesters but starts in the final "
                              f"semester {T} (no room for its continuation)")
            sb = sem_of.get(before) if before else None
            if sb is not None and su + (span - 1) >= sb:
                errors.append(f"UROP {uc} must finish before the FYP {before} starts "
                              f"(UROP ends sem {su + span - 1}, FYP sem {sb})")
    # Issue #4: a requested independent project (CP3106) is distinct from UROP.
    ip = bd.get("independent_project", {}).get("code")
    if ip and scenario.get("want_independent_project") and not satisfied(ip):
        errors.append(f"independent project requested but {ip} not taken")

    # optional per-instance preferences
    # iter3 C4 (I2.18): module pin / forbid / deadline. A pre-satisfied or
    # placement-waived module satisfies a pin / deadline trivially.
    for m in prefs.get("require_modules", []) or []:
        if m not in modules:
            errors.append(f"required (pinned) module {m}: unknown module")
        elif not satisfied(m) and m not in waived:
            errors.append(f"required (pinned) module {m} not scheduled")
    for m in prefs.get("forbid_modules", []) or []:
        if m in sem_of:
            errors.append(f"forbidden module {m} scheduled in semester {sem_of[m]}")
    for m, by in (prefs.get("deadline", {}) or {}).items():
        if pre_satisfied(m, student) or m in waived:
            continue
        if m not in sem_of:
            errors.append(f"deadline module {m} not scheduled (due by semester {by})")
        elif sem_of[m] > int(by):
            errors.append(f"{m}: scheduled in semester {sem_of[m]}, past its deadline {by}")
    for a, b in prefs.get("heavy_conflicts", []) or []:
        if a in sem_of and b in sem_of and sem_of[a] == sem_of[b]:
            errors.append(f"preference: {a} and {b} share a semester")
    min_load = prefs.get("min_units_per_semester", 0)
    if min_load:
        for s, ms in plan.items():
            u = sum(units[m] for m in ms)
            if 0 < u < min_load:
                errors.append(f"semester {s}: {u} units < min load {min_load}")
    if prefs.get("no_empty_semesters", False):
        used = [s for s in range(1, T + 1) if plan.get(s)]
        if used and sorted(used) != list(range(used[0], used[0] + len(used))):
            errors.append("preference: empty semester between enrolled semesters")

    return errors


if __name__ == "__main__":
    modules, program, student = load_model()
    scenario = load_scenario()
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errs = check_plan(
        plan, modules, program, student,
        scenario["target_semesters"], scenario["max_units_per_semester"],
    )
    print("VALID" if not errs else "\n".join(errs))
    sys.exit(1 if errs else 0)
