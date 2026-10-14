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
    load_scenario,
    term_of,
    pre_satisfied,
    prereq_clauses,
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
