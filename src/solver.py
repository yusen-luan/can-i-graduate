"""Iteration 1 CSP solver: assign modules to semesters with OR-Tools CP-SAT.

Implements the constraints in docs/solver_constraints.md. Variables are the
booleans x[m, s] ("module m is taken in plan semester s"); every constraint is
linear over them.

    python src/solver.py                          # default student + scenario
    python src/solver.py --target-semesters 5 --max-units 20
    python src/solver.py --student data/student_example.yaml --json
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import (  # noqa: E402
    DATA,
    load_model,
    load_scenario,
    validate,
    term_of,
    pre_satisfied,
    prereq_clauses,
    same_semester_groups,
    must_satisfy_groups,
)


@dataclass
class SolveResult:
    status: str                      # OPTIMAL | FEASIBLE | INFEASIBLE | MODEL_INVALID | UNKNOWN
    plan: Dict[int, List[str]] = field(default_factory=dict)  # semester -> modules
    target_semesters: int = 0
    max_units_per_semester: int = 0
    wall_time_s: float = 0.0
    num_variables: int = 0
    num_constraints: int = 0

    @property
    def feasible(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


def schedulable_modules(modules: dict, program: dict, student: dict) -> List[str]:
    """Modules the solver may place: requirements, ID/CD candidates, and the
    closure of their active prerequisites. Everything else stays unscheduled
    (e.g. MA1301 for a student without math bridging)."""
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    frontier = list(program["required_modules"]) + list(idcd["candidates"])
    for _, satisfied_by, _ in must_satisfy_groups(program):
        frontier += satisfied_by
    seen = set()
    while frontier:
        m = frontier.pop()
        if m in seen:
            continue
        seen.add(m)
        for clause in prereq_clauses(modules[m], student):
            frontier += clause
    return sorted(m for m in seen if not pre_satisfied(m, student))


def build_and_solve(
    modules: dict,
    program: dict,
    student: dict,
    target_semesters: int,
    max_units_per_semester: int,
    minimize_extra_modules: bool = True,
    time_limit_s: float = 30.0,
) -> SolveResult:
    T = target_semesters
    semesters = range(1, T + 1)
    domain = schedulable_modules(modules, program, student)

    model = cp_model.CpModel()
    x = {
        (m, s): model.NewBoolVar(f"x[{m},{s}]") for m in domain for s in semesters
    }

    def taken(m):
        """Linear expr: 1 if m is scheduled anywhere in the plan, else 0."""
        return sum(x[m, s] for s in semesters) if m in domain else 0

    def satisfied_before(m, s):
        """1 if m was completed/exempted, or scheduled in a semester < s."""
        if pre_satisfied(m, student):
            return 1
        if m not in domain:
            return 0
        return sum(x[m, t] for t in range(1, s))

    def satisfied(m):
        return 1 if pre_satisfied(m, student) else taken(m)

    # §1 each module at most once (completed/exempted modules have no variables)
    for m in domain:
        model.Add(taken(m) <= 1)

    # §2 required modules satisfied
    for m in program["required_modules"]:
        if not pre_satisfied(m, student):
            model.Add(taken(m) == 1)

    # ULR / computing-ethics groups: at least k of satisfied_by
    for _, satisfied_by, k in must_satisfy_groups(program):
        model.Add(sum(satisfied(m) for m in satisfied_by) >= k)

    # §3, §4, §10 prerequisites (ordinary + active conditional), CNF clauses
    for m in domain:
        for clause in prereq_clauses(modules[m], student):
            for s in semesters:
                model.Add(x[m, s] <= sum(satisfied_before(p, s) for p in clause))

    # §5, §11 same-semester bundles / corequisites (unless one is already satisfied)
    for group in same_semester_groups(modules, program):
        if any(pre_satisfied(m, student) for m in group):
            continue
        first, *rest = group
        for other in rest:
            for s in semesters:
                model.Add(x[first, s] == x[other, s])

    # §6 semester offering
    for m in domain:
        offered = modules[m].get("offered_terms", [1, 2])
        for s in semesters:
            if term_of(s) not in offered:
                model.Add(x[m, s] == 0)

    # §7 unit cap
    for s in semesters:
        model.Add(
            sum(modules[m]["units"] * x[m, s] for m in domain)
            <= max_units_per_semester
        )

    # §8 ID/CD: exactly N total, >= min ID, <= max CD
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    ids = [m for m in idcd["candidates"] if modules[m].get("category") == "ID"]
    cds = [m for m in idcd["candidates"] if modules[m].get("category") == "CD"]
    model.Add(sum(satisfied(m) for m in ids + cds) == idcd["total_modules_required"])
    model.Add(sum(satisfied(m) for m in ids) >= idcd["min_id_modules"])
    model.Add(sum(satisfied(m) for m in cds) <= idcd["max_cd_modules"])

    # Tie-breaker, not a constraint: avoid unnecessary optional modules
    # (e.g. taking both MA1301 and MA1301X).
    if minimize_extra_modules:
        model.Minimize(sum(x.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1  # deterministic; the model is tiny
    status = solver.Solve(model)

    result = SolveResult(
        status=solver.StatusName(status),
        target_semesters=T,
        max_units_per_semester=max_units_per_semester,
        wall_time_s=solver.WallTime(),
        num_variables=len(x),
        num_constraints=len(model.Proto().constraints),
    )
    if result.feasible:
        result.plan = {
            s: sorted(m for m in domain if solver.Value(x[m, s])) for s in semesters
        }
    return result


def solve(
    student_path: Path = DATA / "student_example.yaml",
    scenario_path: Path = DATA / "planning_scenario.yaml",
    target_semesters: Optional[int] = None,
    max_units_per_semester: Optional[int] = None,
    **kwargs,
) -> SolveResult:
    modules, program, student = load_model(student_path=student_path)
    validate(modules, program, student)
    scenario = load_scenario(scenario_path)
    return build_and_solve(
        modules,
        program,
        student,
        target_semesters or scenario["target_semesters"],
        max_units_per_semester or scenario["max_units_per_semester"],
        **kwargs,
    )


def format_plan(result: SolveResult, modules: dict) -> str:
    lines = [
        f"Status: {result.status}  (T={result.target_semesters}, "
        f"cap={result.max_units_per_semester} units, "
        f"{result.num_variables} vars, {result.wall_time_s:.3f}s)"
    ]
    if not result.feasible:
        lines.append("No plan satisfies all constraints within the target semesters.")
        return "\n".join(lines)
    for s, mods in result.plan.items():
        units = sum(modules[m]["units"] for m in mods)
        lines.append(f"  Sem {s} (Term {term_of(s)}, {units:>2} units): {', '.join(mods) or '-'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--student", type=Path, default=DATA / "student_example.yaml")
    ap.add_argument("--scenario", type=Path, default=DATA / "planning_scenario.yaml")
    ap.add_argument("--target-semesters", type=int)
    ap.add_argument("--max-units", type=int)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    result = solve(
        args.student, args.scenario, args.target_semesters, args.max_units
    )
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        modules, _, _ = load_model()
        print(format_plan(result, modules))
    return 0 if result.feasible else 1


if __name__ == "__main__":
    sys.exit(main())
