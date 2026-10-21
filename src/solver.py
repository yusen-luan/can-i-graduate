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
    validate_scenario_iter2,
    term_of,
    with_horizon,
    effective_term,
    per_semester_cap,
    is_computing,
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
    # CP-coded independent-project modules (FYP etc.) are not scheduled as filler
    # in the baseline; they only bound the CP cap. iter3 C3: pull them in when the
    # request asks for a FYP / UROP (docs/solver_constraints.md I2.17).
    # FYP (CP4101) enters the domain when requested OR when the student is
    # eligible (so the dissertation MAY replace the industrial experience, I2.8).
    if (scenario.get("want_fyp") or student.get("eligible_fyp")) and bd.get("fyp", {}).get("code"):
        frontier.append(bd["fyp"]["code"])
    if scenario.get("want_urop"):
        frontier += bd.get("urop", {}).get("codes", [])
    # iter3 C4 (I2.18): pinned / deadline modules must be schedulable, so pull
    # them (and their prereq closure) into the domain even if no bucket needed them.
    prefs = scenario.get("preferences", {}) or {}
    frontier += list(prefs.get("require_modules", []) or [])
    frontier += list((prefs.get("deadline", {}) or {}).keys())
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
    validate_scenario_iter2(program, scenario, modules)   # iter3 knob validation
    semesters = range(1, T + 1)
    domain = _iter2_domain(modules, program, student, focus_areas, scenario)
    units = {m: modules[m]["units"] for m in modules}
    waived = bridging_waived(student)
    bd = program["breadth_depth"]
    prefs = scenario.get("preferences", {}) or {}
    fyp_code = bd.get("fyp", {}).get("code")
    industrial_mods = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}

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
    # §6 real offering terms (I2.14: term layout, special terms 3/4)
    for m in domain:
        offered = modules[m].get("offered_terms", [1, 2])
        for s in semesters:
            if effective_term(s, scenario) not in offered:
                model.Add(x[m, s] == 0)
    # §7 unit cap -- industrial-experience modules are done over the vacation /
    # special term, so they do NOT consume a regular semester's unit budget.
    # I2.15: per-slot cap override; a cap of 0 blocks EVERYTHING in that slot
    # (incl. off-cap industrial) -- a fully unavailable leave-of-absence semester.
    for s in semesters:
        cap_s = per_semester_cap(scenario, s, cap)
        if cap_s == 0:
            for m in domain:
                model.Add(x[m, s] == 0)
            continue
        model.Add(sum(units[m] * x[m, s] for m in domain
                      if m not in industrial_mods) <= cap_s)
    # I2.16: CS-count-per-semester cap (Computing modules, excl. off-cap industrial)
    max_cs = prefs.get("max_cs_modules_per_sem", 0)
    if max_cs:
        computing = [m for m in domain if is_computing(m) and m not in industrial_mods]
        for s in semesters:
            model.Add(sum(x[m, s] for m in computing) <= max_cs)
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
    # §17 industrial experience (I2.8, corrected): satisfied by AT MOST ONE
    # internship option (no padding) OR -- for a GPA-eligible student -- by the
    # CP4101 dissertation replacing it. A fixed `industrial_option` still forces
    # that internship; `any` lets the eligible dissertation substitute.
    # dissertation counts only for an eligible student (parity with the checker);
    # sat() covers both a scheduled and an already-completed CP4101.
    diss = sat(fyp_code) if (fyp_code and student.get("eligible_fyp")) else 0
    industrial_choice = scenario.get("industrial_option", "any")
    opt_bools = []
    for i, o in enumerate(bd["industrial_experience"]["options"]):
        s_set = o["set"]
        if industrial_choice != "any" and industrial_choice not in s_set:
            continue
        b = model.NewBoolVar(f"ind[{i}]")
        for m in s_set:
            model.Add(sat(m) >= 1).OnlyEnforceIf(b)
        opt_bools.append((b, set(s_set)))
    n_opts = sum(b for b, _ in opt_bools)
    model.Add(n_opts <= 1)                       # at most one internship (no padding)
    if industrial_choice != "any":
        model.Add(n_opts == 1)                   # an explicit internship request is honoured
    else:
        model.Add(n_opts + diss >= 1)            # internship OR eligible dissertation
    # an industrial module may be taken only if an option containing it is chosen
    for m in industrial_mods:
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

    # I2.17 FYP / UROP (iter3 C3). FYP (CP4101) and UROP research are cp_coded, so
    # the 12u CP cap above binds them: want_fyp + want_urop is infeasible.
    if fyp_code and fyp_code in domain:
        if not student.get("eligible_fyp", False):
            model.Add(sat(fyp_code) == 0)          # gate: only if GPA-eligible
        if scenario.get("want_fyp"):
            model.Add(sat(fyp_code) >= 1)
    urop_codes = [m for m in bd.get("urop", {}).get("codes", []) if m in domain]
    if urop_codes:
        if not student.get("eligible_urop", True):
            for m in urop_codes:
                model.Add(sat(m) == 0)             # gate: standing to do UROP
        if scenario.get("want_urop"):
            model.Add(sum(sat(m) for m in urop_codes) >= 1)

    # -- optional per-instance preferences (scenario) ------------------------
    for a, bmod in prefs.get("heavy_conflicts", []) or []:
        if a in domain and bmod in domain:
            for s in semesters:
                model.Add(x[a, s] + x[bmod, s] <= 1)
    # iter3 C4 (I2.18): module pin / forbid / deadline. Codes are validated to
    # exist; a pre-satisfied or placement-waived module satisfies a pin/deadline
    # trivially (parity with the checker), so every other code is in the domain.
    for m in prefs.get("require_modules", []) or []:
        if not pre_satisfied(m, student) and m not in waived:
            model.Add(taken(m) == 1)
    for m in prefs.get("forbid_modules", []) or []:
        if m in domain:
            model.Add(taken(m) == 0)
    for m, by in (prefs.get("deadline", {}) or {}).items():
        if pre_satisfied(m, student) or m in waived:
            continue
        last = min(int(by), T)
        model.Add(sum(x[m, s] for s in range(1, last + 1)) == 1)

    min_load = prefs.get("min_units_per_semester", 0)
    no_gaps = prefs.get("no_empty_semesters", False)
    if min_load or no_gaps:
        # used[s] <=> semester s holds at least one module (incl. industrial), the
        # checker's notion of an enrolled semester. Encoded exactly, so the unit
        # cap stays with §7 / I2.15 (per-slot caps, industrial off-cap).
        used = {s: model.NewBoolVar(f"used[{s}]") for s in semesters}
        for s in semesters:
            in_s = [x[m, s] for m in domain]
            for v in in_s:
                model.Add(v <= used[s])
            model.Add(used[s] <= sum(in_s))
            if min_load:
                model.Add(sum(units[m] * x[m, s] for m in domain) >= min_load * used[s])
        if no_gaps:
            # enrolled semesters form one contiguous block: no empty s between used r < t
            for r in semesters:
                for s in range(r + 1, T + 1):
                    for t in range(s + 1, T + 1):
                        model.Add(used[r] + used[t] - 1 <= used[s])

    # Objective (still a CSP -- only disambiguates equally-valid plans; never
    # changes feasibility). Priority, by weight:
    #   1. total units  -> lands at exactly 160 (no padding with big modules).
    #   2. Computing (CS/IFS/CP) module COUNT -> among 160u plans, prefer FEWER
    #      Computing modules, so the slack toward 160u is filled with non-CS
    #      unrestricted electives rather than piling on unneeded CS courses.
    #      Required CS, the focus area and the 32u B&D bucket are hard
    #      constraints, so this only trims *discretionary* CS filler.
    #   3. OFF-FOCUS Computing modules -> when a focus area is chosen, fill the
    #      mandatory B&D / L4000 depth with that area's courses, not arbitrary
    #      unrelated high-level CS. Only discretionary (non-required, non-industrial)
    #      Computing courses outside the focus primaries are penalised.
    #   4. total module count -> final tie-break.
    # Net effect: take the MINIMAL must-take modules; fill free units with non-CS
    # unrestricted electives; keep any required CS depth coherent with the focus.
    total_scheduled = sum(units[m] * x[m, s] for m in domain for s in semesters)
    n_computing = sum(x[m, s] for m in domain for s in semesters if is_computing(m))
    obj = 100 * total_scheduled + 10 * n_computing + sum(x.values())
    if chosen != "any":
        fset = set(focus_areas["areas"][chosen]["primaries"])
        required = set(program["required_modules"])
        off_focus = [(m, s) for m in domain for s in semesters
                     if is_computing(m) and m not in fset
                     and m not in required and m not in industrial_mods]
        obj = obj + 5 * sum(x[m, s] for m, s in off_focus)
    model.Minimize(obj)

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


def explain_infeasible_iter2(modules, program, student, focus_areas, preclusions,
                             scenario) -> str:
    """Best-effort explanation of an infeasible iter2 instance: relax ONE knob of
    the given (student, scenario) at a time and report which relaxations make it
    feasible. Probes the exact instance that failed, not the default files."""
    ceiling = program.get("max_overload_units") or 99

    def feasible(sc):
        try:
            return build_and_solve_iter2(modules, program, student, focus_areas,
                                         preclusions, sc).feasible
        except ValueError:          # relaxation produced an invalid instance
            return False

    def without_pref(*keys):
        prefs = {k: v for k, v in (scenario.get("preferences", {}) or {}).items()
                 if k not in keys}
        return {**scenario, "preferences": prefs}

    reasons = []
    cur_T = scenario["target_semesters"]
    cur_cap = scenario["max_units_per_semester"]
    for T in range(cur_T + 1, cur_T + 5):
        if feasible(with_horizon(scenario, T)):
            reasons.append(f"feasible at target_semesters={T} (you asked for {cur_T})")
            break
    for cap in sorted({min(cur_cap + d, ceiling) for d in (2, 4, 6)} - {cur_cap}):
        if feasible({**scenario, "max_units_per_semester": cap}):
            reasons.append(f"feasible at max_units_per_semester={cap} (you set {cur_cap})")
            break
    probes = [
        (scenario.get("focus_area", "any") != "any",
         {**scenario, "focus_area": "any"}, "feasible if the focus area is not fixed"),
        (scenario.get("industrial_option", "any") != "any",
         {**scenario, "industrial_option": "any"},
         "feasible with a different industrial-experience option"),
        (scenario.get("want_fyp"), {**scenario, "want_fyp": False},
         "feasible without the final-year-project request"),
        (scenario.get("want_urop"), {**scenario, "want_urop": False},
         "feasible without the UROP request"),
    ]
    prefs = scenario.get("preferences", {}) or {}
    for keys, label in [(("require_modules", "forbid_modules", "deadline"),
                         "feasible without the module pins / forbids / deadlines"),
                        (("per_semester_cap",), "feasible without the per-semester caps"),
                        (("max_cs_modules_per_sem",), "feasible without the CS-modules-per-semester cap"),
                        (("min_units_per_semester", "no_empty_semesters", "heavy_conflicts"),
                         "feasible without the workload preferences")]:
        probes.append((any(prefs.get(k) for k in keys), without_pref(*keys), label))
    for applies, sc, label in probes:
        if applies and feasible(sc):
            reasons.append(label)
    return "; ".join(reasons) or "no single relaxation of your request helped"


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
            loaded = load_iter2()
            print(format_plan(result, loaded[0]))
            if not result.feasible:
                scenario = {**load_scenario(DATA / "scenario_iter2.yaml"), **over}
                print("Why: " + explain_infeasible_iter2(*loaded, scenario))
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
