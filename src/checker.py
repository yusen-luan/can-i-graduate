"""Independent plan checker: does a given semester plan satisfy every constraint?

Written directly from docs/solver_constraints.md without using the solver, so it
can (a) cross-check solver output and (b) grade plans produced by other means,
e.g. an LLM reasoning directly.

    python src/checker.py plan.json   # {"1": ["CS1101S", ...], "2": [...], ...}
"""
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
    pre_satisfied,
    prereq_clauses,
    prereq_tree_of,
    tree_satisfied,
    bridging_waived,
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
        if term_of(s) not in modules[m].get("offered_terms", [1, 2]):
            errors.append(f"{m} (sem {s}): not offered in Term {term_of(s)}")
    bd = program["breadth_depth"]
    industrial_mods = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}
    ceiling = program.get("max_overload_units")
    for s, ms in plan.items():
        # industrial experience is done over the vacation / special term and does
        # not consume a regular semester's unit budget.
        u = sum(units[m] for m in ms if m not in industrial_mods)
        if u > cap:
            errors.append(f"semester {s}: {u} units > cap {cap}")
        if ceiling and u > ceiling:
            errors.append(f"semester {s}: {u} units > overload ceiling {ceiling}")

    # ID/CD
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    n_id = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "ID")
    n_cd = sum(satisfied(m) for m in idcd["candidates"] if modules[m].get("category") == "CD")
    if n_id + n_cd != idcd["total_modules_required"]:
        errors.append(f"ID/CD: {n_id + n_cd} modules, need {idcd['total_modules_required']}")
    if n_id < idcd["min_id_modules"]:
        errors.append(f"ID/CD: {n_id} ID, need >= {idcd['min_id_modules']}")
    if n_cd > idcd["max_cd_modules"]:
        errors.append(f"ID/CD: {n_cd} CD, allow <= {idcd['max_cd_modules']}")

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
    if sat_units(lambda m: modules[m]["level"] >= 4000) < bd["level4000"]["min_units"]:
        errors.append(f"level-4000: < {bd['level4000']['min_units']} units")

    # Breadth & Depth 32u bucket (Computing courses incl. industrial experience)
    bd_pillars = {"breadth_depth", "industrial_experience"}
    bd_units = sat_units(lambda m: modules[m].get("pillar") in bd_pillars)
    if bd_units < bd["min_units"]:
        errors.append(f"breadth & depth: {bd_units} units < {bd['min_units']}")

    # industrial experience: exactly one option; nothing extra
    opts = bd["industrial_experience"]["options"]
    full = [i for i, o in enumerate(opts) if all(satisfied(m) for m in o["set"])]
    all_ind = {m for o in opts for m in o["set"]}
    if len(full) != 1:
        errors.append(f"industrial experience: {len(full)} options fully satisfied, need exactly 1")
    taken_ind = {m for m in all_ind if satisfied(m)}
    chosen_ind = set().union(*[set(opts[i]["set"]) for i in full]) if full else set()
    if taken_ind - chosen_ind:
        errors.append(f"industrial experience: extra modules {sorted(taken_ind - chosen_ind)}")

    # year-long C&E service learning: X (Sem 1 half) then Y in the contiguous
    # next semester; neither half may appear without the other in sequence.
    for X, Y in program.get("service_learning_pairs", []):
        sx, sy = sem_of.get(X), sem_of.get(Y)
        if sx is not None and sy != sx + 1:
            errors.append(f"service learning {X}->{Y}: Y must be the semester after X")
        if sy is not None and sx != sy - 1:
            errors.append(f"service learning {X}->{Y}: Y present without X in the previous semester")

    # CP cap, total units
    if sat_units(lambda m: m in bd["cp_coded"]["codes"]) > bd["cp_coded"]["max_units"]:
        errors.append(f"cp-coded: > {bd['cp_coded']['max_units']} units")
    total = sat_units(lambda m: True)
    if total < program["total_units_required"]:
        errors.append(f"total units {total} < {program['total_units_required']}")

    # optional per-instance preferences
    prefs = scenario.get("preferences", {}) or {}
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
