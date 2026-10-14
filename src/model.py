from pathlib import Path
from typing import Dict, Any, List
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_yaml(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_model(
    modules_path: Path = DATA / "modules.yaml",
    program_path: Path = DATA / "program_cs_iter1.yaml",
    student_path: Path = DATA / "student_example.yaml",
):
    return (
        load_yaml(modules_path),
        load_yaml(program_path),
        load_yaml(student_path),
    )

def load_scenario(path: Path = DATA / "planning_scenario.yaml") -> dict:
    return load_yaml(path)

# ---------------------------------------------------------------------------
# Shared interpretation helpers (used by both the solver and the plan checker)
# ---------------------------------------------------------------------------

def term_of(semester: int) -> int:
    """Plan semesters 1,3,5,... are NUS Semester 1; 2,4,6,... are Semester 2."""
    return 1 if semester % 2 == 1 else 2

def condition_holds(condition: dict, student: dict) -> bool:
    value = student.get("conditions", {}).get(condition["field"])
    if "equals" in condition:
        return value == condition["equals"]
    return value in condition["in"]

def pre_satisfied(module: str, student: dict) -> bool:
    """Completed or exempted before planning starts."""
    return bool(
        student["completed"].get(module, False)
        or student["exempted"].get(module, False)
    )

def prereq_clauses(info: dict, student: dict) -> List[List[str]]:
    """Active prerequisites of a module in CNF form.

    Each clause is a list of alternatives; at least one alternative of every
    clause must be satisfied before the module is taken. `all_of: [a, b]`
    becomes `[[a], [b]]`; `one_of: [a, b]` becomes `[[a, b]]`. Conditional
    rules contribute only when their `when` condition holds for the student.
    """
    prereq = info.get("prerequisites", {})
    clauses = [[p] for p in prereq.get("all_of", [])]
    for rule in prereq.get("conditional", []):
        if not condition_holds(rule["when"], student):
            continue
        clauses += [[p] for p in rule.get("all_of", [])]
        if rule.get("one_of"):
            clauses.append(list(rule["one_of"]))
    return clauses

def same_semester_groups(modules: Dict[str, Any], program: dict) -> List[List[str]]:
    """Scheduling bundles plus module corequisites: all-or-nothing, same semester."""
    groups = [
        list(b["modules"]) for b in program.get("scheduling_bundles", {}).values()
    ]
    for module, info in modules.items():
        for coreq in info.get("corequisites", []):
            groups.append([module, coreq["module"]])
    return groups

def must_satisfy_groups(program: dict) -> List[tuple]:
    """(name, satisfied_by, modules_required) for each 'at least k of' group."""
    groups = []
    rg = program.get("requirement_groups", {})
    for name, g in rg.get("university_level_requirements", {}).items():
        groups.append((name, g["satisfied_by"], g["modules_required"]))
    for name, g in rg.items():
        if "satisfied_by" in g:
            groups.append((name, g["satisfied_by"], g["modules_required"]))
    return groups

def validate_condition(condition: dict) -> None:
    if not isinstance(condition, dict) or "field" not in condition:
        raise ValueError(f"Invalid condition: {condition}")
    if "equals" not in condition and "in" not in condition:
        raise ValueError(f"Condition needs 'equals' or 'in': {condition}")

def validate(modules: Dict[str, Any], program: dict, student: dict) -> None:
    codes = set(modules)

    for module, info in modules.items():
        prereq = info.get("prerequisites", {})

        for p in prereq.get("all_of", []):
            if p not in codes:
                raise ValueError(f"{module} references unknown prerequisite {p}")

        for rule in prereq.get("conditional", []):
            validate_condition(rule.get("when", {}))
            for key in ("all_of", "one_of"):
                for p in rule.get(key, []):
                    if p not in codes:
                        raise ValueError(
                            f"{module} references unknown conditional prerequisite {p}"
                        )

        for coreq in info.get("corequisites", []):
            p = coreq["module"]
            if p not in codes:
                raise ValueError(f"{module} references unknown corequisite {p}")

    for m in program.get("required_modules", []):
        if m not in codes:
            raise ValueError(f"Program requires unknown module {m}")

    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    for m in idcd["candidates"]:
        if m not in codes:
            raise ValueError(f"ID/CD group references unknown module {m}")

    for field in ("completed", "exempted"):
        missing = codes - set(student.get(field, {}))
        extra = set(student.get(field, {})) - codes
        if missing:
            raise ValueError(f"Student {field} missing module(s): {sorted(missing)}")
        if extra:
            raise ValueError(f"Student {field} has unknown module(s): {sorted(extra)}")

    overlap = [
        m for m in codes
        if student["completed"].get(m, False)
        and student["exempted"].get(m, False)
    ]
    if overlap:
        raise ValueError(f"Modules cannot be both completed and exempted: {overlap}")

    english_path = student.get("conditions", {}).get("english_path")
    allowed = {"direct_es2660", "es1103_required", "es1000_then_es1103"}
    if english_path not in allowed:
        raise ValueError(
            f"english_path must be one of {sorted(allowed)}; got {english_path}"
        )

if __name__ == "__main__":
    modules, program, student = load_model()
    validate(modules, program, student)
    print(
        f"Validated {len(modules)} modules for "
        f"{program['program']} Iteration {program['iteration']}."
    )
