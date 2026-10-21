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
    load_iter2,
    load_scenario,
    validate,
    validate_iter2,
    term_of,
    pre_satisfied,
    prereq_clauses,
    prereq_tree_of,
    tree_leaves,
    bridging_waived,
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


# ===========================================================================
# Iteration 2: full BComp(CS) degree (NUSMods snapshot + focus/breadth/project)
# ===========================================================================

def _iter2_domain(modules, program, student, focus_areas, scenario):
    """Modules the iter2 solver may place: every requirement candidate pool plus
    the closure of their prerequisite-tree leaves (that we actually model)."""
    bd = program["breadth_depth"]
    frontier = list(program["required_modules"])
    frontier += program["requirement_groups"]["interdisciplinary_cross_disciplinary"]["candidates"]
    frontier += program["unrestricted_electives"]["candidates"]
    for _, satisfied_by, _ in must_satisfy_groups(program):
        frontier += satisfied_by
    for pair in program.get("service_learning_pairs", []):
        frontier += pair
    ind_choice = scenario.get("industrial_option", "any")
    for o in bd["industrial_experience"]["options"]:
        if ind_choice == "any" or ind_choice in o["set"]:
            frontier += o["set"]
    # CP-coded independent-project modules (FYP etc.) are not scheduled as
    # filler in the iter2 baseline; they only bound the CP cap. Excluded here.
    # All focus-area primaries are B&D-eligible CS courses, so include them all
    # as B&D fillers regardless of which area the focus constraint targets.
    for spec in focus_areas["areas"].values():
        frontier += spec["primaries"]
    seen = set()
    while frontier:
        m = frontier.pop()
        if m in seen or m not in modules:
            continue
        seen.add(m)
        frontier += [p for p in tree_leaves(prereq_tree_of(modules[m])) if p in modules]
    seen -= bridging_waived(student)      # placement-waived bridges aren't taken
    return sorted(m for m in seen if not pre_satisfied(m, student))


def build_and_solve_iter2(
    modules, program, student, focus_areas, preclusions, scenario,
    time_limit_s: float = 60.0, seed: int = 0,
) -> SolveResult:
    T = scenario["target_semesters"]
    cap = scenario["max_units_per_semester"]
    ceiling = program.get("max_overload_units")
    if ceiling and cap > ceiling:
        raise ValueError(
            f"max_units_per_semester {cap} exceeds the overload ceiling {ceiling}")
    semesters = range(1, T + 1)
    domain = _iter2_domain(modules, program, student, focus_areas, scenario)
    units = {m: modules[m]["units"] for m in modules}
    waived = bridging_waived(student)
    bd = program["breadth_depth"]

    model = cp_model.CpModel()
    x = {(m, s): model.NewBoolVar(f"x[{m},{s}]") for m in domain for s in semesters}

    def taken(m):
        return sum(x[m, s] for s in semesters) if m in domain else 0

    def sat(m):
        """1 if satisfied (pre-satisfied, or scheduled); linear expr."""
        return 1 if pre_satisfied(m, student) else taken(m)

    def held(m):
        """Credit the student actually holds: completed or scheduled, but NOT
        exempted (an exemption waives the module without granting its credit).
        Used for preclusions."""
        if student["completed"].get(m, False):
            return 1
        if student["exempted"].get(m, False):
            return 0
        return taken(m) if m in domain else 0

    def units_where(pred):
        """Units of satisfied modules matching pred, as a linear expression."""
        expr = [units[m] * x[m, s] for m in domain for s in semesters if pred(m)]
        const = sum(units[m] for m in modules
                    if pre_satisfied(m, student) and pred(m))
        return sum(expr) + const

    # -- prerequisite tree, reified per (module, semester) -------------------
    def reify_before(node, s):
        """BoolVar/int that is true iff `node` is satisfied strictly before s."""
        if node is None:
            return 1
        if isinstance(node, str):
            if pre_satisfied(node, student) or node in waived:
                return 1
            if node in domain:
                b = model.NewBoolVar(f"sb[{node},{s}]")
                model.Add(b == sum(x[node, t] for t in range(1, s)))
                return b
            return 0  # external non-canonical code we don't model
        children = [reify_before(c, s) for c in node.get("all_of", node.get("one_of", []))]
        is_const = lambda c, v: isinstance(c, int) and c == v
        is_and = "all_of" in node
        if is_and:
            if any(is_const(c, 0) for c in children):
                return 0
            cb = [c for c in children if not is_const(c, 1)]
            if not cb:
                return 1
        else:  # one_of
            if any(is_const(c, 1) for c in children):
                return 1
            cb = [c for c in children if not is_const(c, 0)]
            if not cb:
                return 0
        if len(cb) == 1:
            return cb[0]
        b = model.NewBoolVar("node")
        if is_and:
            model.AddBoolAnd(cb).OnlyEnforceIf(b)
            model.AddBoolOr([c.Not() for c in cb]).OnlyEnforceIf(b.Not())
        else:
            model.AddBoolOr(cb).OnlyEnforceIf(b)
            model.AddBoolAnd([c.Not() for c in cb]).OnlyEnforceIf(b.Not())
        return b

    # §1 at most once
    for m in domain:
        model.Add(taken(m) <= 1)
    # §2 required modules
    for m in program["required_modules"]:
        if not pre_satisfied(m, student):
            model.Add(taken(m) == 1)
    # ULR / ethics "at least k of"
    for _, satisfied_by, k in must_satisfy_groups(program):
        model.Add(sum(sat(m) for m in satisfied_by) >= k)
    # §3 prerequisites (tree form)
    for m in domain:
        tree = prereq_tree_of(modules[m])
        for s in semesters:
            model.Add(x[m, s] <= reify_before(tree, s))
    # §5/§11 same-semester bundles
    for group in same_semester_groups(modules, program):
        if any(pre_satisfied(g, student) for g in group):
            continue
        first, *rest = group
        if first not in domain:
            continue
        for other in rest:
            for s in semesters:
                model.Add(x[first, s] == x[other, s])
    # §6 real offering terms
    for m in domain:
        offered = modules[m].get("offered_terms", [1, 2])
        for s in semesters:
            if term_of(s) not in offered:
                model.Add(x[m, s] == 0)
    # §7 unit cap -- industrial-experience modules are done over the vacation /
    # special term, so they do NOT consume a regular semester's unit budget.
    industrial_mods = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}
    for s in semesters:
        model.Add(sum(units[m] * x[m, s] for m in domain
                      if m not in industrial_mods) <= cap)
    # §8 ID/CD
    idcd = program["requirement_groups"]["interdisciplinary_cross_disciplinary"]
    ids = [m for m in idcd["candidates"] if modules[m].get("category") == "ID"]
    cds = [m for m in idcd["candidates"] if modules[m].get("category") == "CD"]
    model.Add(sum(sat(m) for m in ids + cds) == idcd["total_modules_required"])
    model.Add(sum(sat(m) for m in ids) >= idcd["min_id_modules"])
    model.Add(sum(sat(m) for m in cds) <= idcd["max_cd_modules"])
    # §13 preclusions: at most one credit-bearing module per group
    for grp in preclusions["groups"].values():
        model.Add(sum(held(m) for m in grp) <= 1)
    # §14 unrestricted electives: residual fillers (optional) toward the 160u
    # floor. Not fixed at 40u -- B&D modules beyond the 32u bucket count as UE,
    # so UE is whatever remains after the fixed buckets (see docs/iter2_plan.md B3).
    # §15 focus area (fixed or any)
    fa_rule = focus_areas["rule"]
    chosen = scenario.get("focus_area", "any")
    area_indicators = []
    for area, spec in focus_areas["areas"].items():
        if chosen not in ("any", area):
            continue
        prim = [m for m in spec["primaries"] if m in modules]
        prim4k = [m for m in prim if modules[m]["level"] >= 4000]
        if chosen == area:
            model.Add(sum(sat(m) for m in prim) >= fa_rule["courses_per_area"])
            model.Add(sum(sat(m) for m in prim4k) >= fa_rule["min_level4000_in_area"])
        else:
            b = model.NewBoolVar(f"focus[{area}]")
            model.Add(sum(sat(m) for m in prim) >= fa_rule["courses_per_area"]).OnlyEnforceIf(b)
            model.Add(sum(sat(m) for m in prim4k) >= fa_rule["min_level4000_in_area"]).OnlyEnforceIf(b)
            area_indicators.append(b)
    if chosen == "any":
        model.Add(sum(area_indicators) >= bd["focus_area"]["required_areas"])
    # §16 level-4000 depth
    model.Add(units_where(lambda m: modules[m]["level"] >= 4000) >= bd["level4000"]["min_units"])
    # §17 industrial experience: choose EXACTLY one option; take exactly that
    # option's modules and no other industrial module (no internship padding).
    industrial_choice = scenario.get("industrial_option", "any")
    all_ind = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}
    opt_bools = []
    for i, o in enumerate(bd["industrial_experience"]["options"]):
        s_set = o["set"]
        if industrial_choice != "any" and industrial_choice not in s_set:
            continue
        b = model.NewBoolVar(f"ind[{i}]")
        for m in s_set:
            model.Add(sat(m) >= 1).OnlyEnforceIf(b)
        opt_bools.append((b, set(s_set)))
    model.Add(sum(b for b, _ in opt_bools) == 1)
    # an industrial module may be taken only if an option containing it is chosen
    for m in all_ind:
        if m in domain:
            model.Add(sat(m) <= sum(b for b, s_set in opt_bools if m in s_set))
    # §18 Breadth & Depth 32u bucket: Computing (CS/IFS/CP) courses tagged
    # breadth_depth or industrial_experience. Focus courses, the L4000 units and
    # the industrial experience all live inside this bucket (no team project).
    bd_pillars = {"breadth_depth", "industrial_experience"}
    model.Add(units_where(lambda m: modules[m].get("pillar") in bd_pillars) >= bd["min_units"])
    # §20 year-long C&E service learning: Y (continuation) in semester s iff X
    # (first half) in semester s-1 -- two contiguous semesters. X cannot sit in
    # the final semester (no room for its Y), else C&E would be "satisfied" by a
    # half-done year-long course.
    for X, Y in program.get("service_learning_pairs", []):
        if X in domain and Y in domain:
            model.Add(x[Y, 1] == 0)
            model.Add(x[X, T] == 0)
            for s in range(2, T + 1):
                model.Add(x[Y, s] == x[X, s - 1])

    # §19 CP-coded cap (excludes industrial experience)
    cp = bd["cp_coded"]
    model.Add(units_where(lambda m: m in cp["codes"]) <= cp["max_units"])
    # total units floor
    model.Add(units_where(lambda m: True) >= program["total_units_required"])

    # -- optional per-instance preferences (scenario) ------------------------
    prefs = scenario.get("preferences", {}) or {}
    for a, bmod in prefs.get("heavy_conflicts", []) or []:
        if a in domain and bmod in domain:
            for s in semesters:
                model.Add(x[a, s] + x[bmod, s] <= 1)
    min_load = prefs.get("min_units_per_semester", 0)
    no_gaps = prefs.get("no_empty_semesters", False)
    if min_load or no_gaps:
        used = {s: model.NewBoolVar(f"used[{s}]") for s in semesters}
        for s in semesters:
            load = sum(units[m] * x[m, s] for m in domain)
            model.Add(load <= cap * used[s])
            if min_load:
                model.Add(load >= min_load * used[s])
        if no_gaps:
            for s in list(semesters)[:-1]:
                model.Add(used[s] >= used[s + 1])

    # Objective: minimise total scheduled units. With the >=160u floor this
    # lands at exactly 160 and removes any incentive to pad with large optional
    # modules; a secondary term minimises module count as a tie-break. The
    # problem stays a CSP -- the objective only disambiguates equally-valid plans.
    total_scheduled = sum(units[m] * x[m, s] for m in domain for s in semesters)
    model.Minimize(100 * total_scheduled + sum(x.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1      # deterministic given the seed
    solver.parameters.random_seed = seed
    status = solver.Solve(model)
    result = SolveResult(
        status=solver.StatusName(status),
        target_semesters=T,
        max_units_per_semester=cap,
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


def solve_iter2(
    program_path: Path = DATA / "program_cs.yaml",
    student_path: Path = DATA / "student_iter2.yaml",
    scenario_path: Path = DATA / "scenario_iter2.yaml",
    overrides: Optional[dict] = None,
    **kwargs,
) -> SolveResult:
    modules, program, student, focus_areas, preclusions = load_iter2(
        program_path=program_path, student_path=student_path)
    validate_iter2(modules, program, student, focus_areas)
    scenario = load_scenario(scenario_path)
    if overrides:
        scenario = {**scenario, **overrides}
    return build_and_solve_iter2(
        modules, program, student, focus_areas, preclusions, scenario, **kwargs)


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


def explain_infeasible_iter2(base_overrides: dict) -> str:
    """Best-effort explanation of an infeasible iter2 instance: probe whether a
    larger horizon or a higher unit cap would make it feasible, and whether the
    chosen focus area / industrial option is the blocker."""
    reasons = []
    cur_T = (base_overrides or {}).get("target_semesters", SCEN_T())
    cur_cap = (base_overrides or {}).get("max_units_per_semester", SCEN_CAP())
    for T in range(cur_T + 1, cur_T + 5):
        if solve_iter2(overrides={**(base_overrides or {}), "target_semesters": T}).feasible:
            reasons.append(f"feasible at target_semesters={T} (you asked for {cur_T})")
            break
    for cap in (cur_cap + 2, cur_cap + 4, cur_cap + 6):
        if solve_iter2(overrides={**(base_overrides or {}), "max_units_per_semester": cap}).feasible:
            reasons.append(f"feasible at max_units_per_semester={cap} (you set {cur_cap})")
            break
    if (base_overrides or {}).get("focus_area", "any") != "any":
        if solve_iter2(overrides={**(base_overrides or {}), "focus_area": "any"}).feasible:
            reasons.append("feasible if the focus area is not fixed")
    if (base_overrides or {}).get("industrial_option", "any") != "any":
        if solve_iter2(overrides={**(base_overrides or {}), "industrial_option": "any"}).feasible:
            reasons.append("feasible with a different industrial-experience option")
    return "; ".join(reasons) or "no simple relaxation (horizon/cap/focus/internship) helped"


def SCEN_T():
    return load_scenario(DATA / "scenario_iter2.yaml")["target_semesters"]


def SCEN_CAP():
    return load_scenario(DATA / "scenario_iter2.yaml")["max_units_per_semester"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--iter2", action="store_true", help="solve the full iter2 degree")
    ap.add_argument("--student", type=Path, default=DATA / "student_example.yaml")
    ap.add_argument("--scenario", type=Path, default=DATA / "planning_scenario.yaml")
    ap.add_argument("--target-semesters", type=int)
    ap.add_argument("--max-units", type=int)
    ap.add_argument("--focus-area")
    ap.add_argument("--industrial-option")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.iter2:
        over = {}
        if args.target_semesters:
            over["target_semesters"] = args.target_semesters
        if args.max_units:
            over["max_units_per_semester"] = args.max_units
        if args.focus_area:
            over["focus_area"] = args.focus_area
        if args.industrial_option:
            over["industrial_option"] = args.industrial_option
        result = solve_iter2(overrides=over or None)
        if args.json:
            print(json.dumps(result.__dict__, indent=2))
        else:
            modules, *_ = load_iter2()
            print(format_plan(result, modules))
            if not result.feasible:
                print("Why: " + explain_infeasible_iter2(over))
        return 0 if result.feasible else 1

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
