from pathlib import Path
from typing import Dict, Any
import yaml

ROOT = Path(__file__).resolve().parents[1]

def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_model():
    return (
        load_yaml(ROOT / "data" / "modules.yaml"),
        load_yaml(ROOT / "data" / "program_cs_iter1.yaml"),
        load_yaml(ROOT / "data" / "student_example.yaml"),
    )

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
