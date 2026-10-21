"""Iteration-2 tests: full BComp(CS) degree over the NUSMods AY2026/27 snapshot.

Mirror the iter1 discipline: the solver's plan must always pass the independent
checker, feasibility boundaries are pinned, and the checker catches bad plans.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import load_iter2, load_scenario  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

MODULES, PROGRAM, STUDENT, FOCUS, PRECL = load_iter2()
SCEN = load_scenario(Path(__file__).resolve().parents[1] / "data" / "scenario_iter2.yaml")

FOCUS_AREAS = list(FOCUS["areas"])


def scenario(**over):
    s = copy.deepcopy(SCEN)
    s.update(over)
    return s


def solve(**over):
    return build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario(**over))


def sem_of(plan):
    return {m: s for s, ms in plan.items() for m in ms}


def units(ms):
    return sum(MODULES[m]["units"] for m in ms)


# --- solver output always passes the independent checker --------------------

@pytest.mark.parametrize("area", FOCUS_AREAS)
def test_solver_plan_passes_checker_each_focus_area(area):
    s = scenario(focus_area=area)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    # some areas may be infeasible at the tight default horizon; only check feasible ones
    if r.feasible:
        assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


@pytest.mark.parametrize("T", [8, 9, 10])
def test_solver_plan_passes_checker_any_focus(T):
    s = scenario(focus_area="any", target_semesters=T)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


@pytest.mark.parametrize("seed", range(8))
def test_solver_checker_parity_across_seeds(seed):
    # different random seeds explore different optimal plans; EVERY one the
    # solver returns must pass the independent checker (guards parity bugs that
    # only surface for some solutions, e.g. service-learning X in the last sem).
    s = scenario(focus_area="any", target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s, seed=seed)
    assert r.feasible
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


# --- feasibility boundaries -------------------------------------------------

def test_min_horizon_is_eight_at_cap_twenty():
    # ~148-154 academic units at 20/sem: 7 semesters hold only 140.
    assert not solve(target_semesters=7).feasible
    assert solve(target_semesters=8).feasible


def test_early_graduation_with_overload():
    # 8 is only the arithmetic floor at a 20-unit load, not a hard rule:
    # overloading lets a student finish in 7 semesters.
    assert not solve(target_semesters=7, max_units_per_semester=20).feasible
    assert solve(target_semesters=7, max_units_per_semester=26).feasible


def test_overload_ceiling_is_28():
    # iter2 assumption: a request above the 28-unit overload ceiling is rejected.
    assert PROGRAM["max_overload_units"] == 28
    solve(max_units_per_semester=28)  # at the ceiling: allowed
    with pytest.raises(ValueError):
        solve(max_units_per_semester=30)


def test_checker_flags_semester_over_overload_ceiling():
    # even if an instance set a high cap, no semester may exceed the 28u ceiling
    plan = {1: ["CS1101S", "CS1231S", "CS2100", "CS2101", "CS2102", "CS2104", "CS2108", "CS2111"]}
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL,
                            scenario(max_units_per_semester=40))
    assert any("overload ceiling" in e for e in errs)


def test_internship_does_not_consume_a_semester():
    # Industrial experience is done over the vacation/special term, so even the
    # 12-unit 6-month ATAP fits the 8-semester plan without needing a 9th.
    assert solve(industrial_option="CP3880", target_semesters=8).feasible


# --- requirement semantics --------------------------------------------------

def test_plan_hits_exactly_160_units():
    assert units([m for ms in solve().plan.values() for m in ms]) == 160


def test_focus_area_satisfied():
    plan = solve(focus_area="artificial_intelligence").plan
    taken = {m for ms in plan.values() for m in ms}
    prim = [m for m in FOCUS["areas"]["artificial_intelligence"]["primaries"] if m in taken]
    assert len(prim) >= 3
    assert any(MODULES[m]["level"] >= 4000 for m in prim)


def test_at_least_12_units_level4000():
    taken = [m for ms in solve().plan.values() for m in ms]
    assert sum(MODULES[m]["units"] for m in taken if MODULES[m]["level"] >= 4000) >= 12


def test_breadth_depth_at_least_32_units():
    taken = [m for ms in solve().plan.values() for m in ms]
    bd = sum(MODULES[m]["units"] for m in taken
             if MODULES[m].get("pillar") in ("breadth_depth", "industrial_experience"))
    assert bd >= PROGRAM["breadth_depth"]["min_units"]


def test_exactly_one_industrial_stint():
    taken = {m for ms in solve().plan.values() for m in ms}
    opts = PROGRAM["breadth_depth"]["industrial_experience"]["options"]
    full = [o for o in opts if all(m in taken for m in o["set"])]
    assert len(full) == 1


def test_single_semester_offering_respected():
    # CS3243 is offered in Semester 2 only (NUSMods AY26/27); if scheduled it
    # must land in an even plan-semester (Term 2).
    plan = solve(focus_area="artificial_intelligence").plan
    s = sem_of(plan)
    if "CS3243" in s:
        assert s["CS3243"] % 2 == 0


def test_no_bridging_for_h2_math_direct_english_student():
    taken = {m for ms in solve().plan.values() for m in ms}
    assert not ({"MA1301", "MA1301X", "ES1000", "ES1103"} & taken)


def test_heavy_conflicts_preference_separates_modules():
    s = scenario(preferences={"min_units_per_semester": 0, "no_empty_semesters": False,
                              "heavy_conflicts": [["CS2030S", "CS2040S"]]})
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    so = sem_of(r.plan)
    assert so["CS2030S"] != so["CS2040S"]
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


# --- checker catches bad plans ----------------------------------------------

def valid_plan():
    return copy.deepcopy(solve().plan)


def test_checker_flags_prereq_tree_violation():
    plan = valid_plan()
    s = sem_of(plan)
    # move CS2103T before its prerequisites by dumping it into semester 1
    plan[s["CS2103T"]].remove("CS2103T")
    plan[1].append("CS2103T")
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, SCEN)
    assert any("CS2103T" in e and "prerequisite" in e for e in errs)


def test_checker_flags_focus_area_not_satisfied():
    # strip every primary of a target area, then require that area: must flag it
    area = "parallel_computing"
    prims = set(FOCUS["areas"][area]["primaries"])
    plan = {s: [m for m in ms if m not in prims] for s, ms in valid_plan().items()}
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL,
                            scenario(focus_area=area))
    assert any("focus area" in e for e in errs)


def test_checker_flags_extra_industrial_module():
    plan = valid_plan()
    # add a second, different industrial stint on top of the chosen one
    plan[1].append("CP3880")
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, SCEN)
    assert any("industrial" in e for e in errs)


def test_checker_flags_unit_cap():
    plan = {1: PROGRAM["required_modules"][:6]}
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, SCEN)
    assert any("units > cap" in e for e in errs)


# --- real GE/ID/CD data + year-long service learning ------------------------

def test_uses_real_ge_and_idcd_courses_not_generics():
    taken = {m for ms in solve().plan.values() for m in ms}
    # ULR pick-list pillars resolve to real GE codes, not *_GENERIC placeholders
    assert not any(m.endswith("_GENERIC") and m.startswith(("GEC", "GES", "GEN"))
                   for m in taken)
    idcd = [m for m in taken if MODULES[m].get("category") in ("ID", "CD")]
    n_id = sum(MODULES[m]["category"] == "ID" for m in idcd)
    n_cd = sum(MODULES[m]["category"] == "CD" for m in idcd)
    assert n_id + n_cd == 3 and n_id >= 2 and n_cd <= 1


def _program_forcing_service_learning():
    prog = copy.deepcopy(PROGRAM)
    ce = prog["requirement_groups"]["university_level_requirements"]["communities_and_engagement"]
    ce["satisfied_by"] = ["GEN2050X", "GEN2070X"]
    return prog


def test_service_learning_is_two_contiguous_semesters():
    prog = _program_forcing_service_learning()
    r = build_and_solve_iter2(MODULES, prog, STUDENT, FOCUS, PRECL, scenario())
    assert r.feasible
    s = sem_of(r.plan)
    pairs = [(X, Y) for X, Y in prog["service_learning_pairs"] if X in s or Y in s]
    assert pairs, "a service-learning pair should be scheduled"
    for X, Y in pairs:
        assert s[X] % 2 == 1            # X in a Term-1 (odd) plan semester
        assert s[Y] == s[X] + 1         # Y in the immediately following semester
    assert check_plan_iter2(r.plan, MODULES, prog, STUDENT, FOCUS, PRECL, scenario()) == []


def test_checker_flags_broken_service_learning_contiguity():
    prog = _program_forcing_service_learning()
    r = build_and_solve_iter2(MODULES, prog, STUDENT, FOCUS, PRECL, scenario())
    plan = copy.deepcopy(r.plan)
    s = sem_of(plan)
    X, Y = next((X, Y) for X, Y in prog["service_learning_pairs"] if X in s)
    plan[s[Y]].remove(Y)                # drop the Y continuation -> broken year-long
    errs = check_plan_iter2(plan, MODULES, prog, STUDENT, FOCUS, PRECL, scenario())
    assert any("service learning" in e for e in errs)


# === iter3 C1 — per-semester unit-cap vector (I2.15) ========================

def test_blocked_semester_costs_a_horizon():
    # a fully-blocked semester (cap 0, e.g. leave of absence) removes 20 units of capacity,
    # so an 8-semester plan that was tight goes infeasible but 9 recovers.
    pref = {"per_semester_cap": {1: 0}}
    assert not solve(preferences=pref).feasible
    assert solve(preferences=pref, target_semesters=9).feasible


def test_chill_semester_cap_respected_by_solver():
    pref = {"per_semester_cap": {4: 8}}
    s = scenario(preferences=pref, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert units(r.plan.get(4, [])) <= 8
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_checker_flags_module_in_blocked_semester():
    s = scenario(preferences={"per_semester_cap": {2: 0}})
    errs = check_plan_iter2({2: ["CS1101S"]}, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert any("blocked" in e for e in errs)


def test_per_semester_cap_validation():
    with pytest.raises(ValueError):
        solve(preferences={"per_semester_cap": {1: 40}})  # above the 28u ceiling


# === iter3 C2 — CS-count-per-semester cap (I2.16) ===========================

def test_cs_count_cap_respected_by_solver():
    s = scenario(preferences={"max_cs_modules_per_sem": 2}, target_semesters=10)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    ind = {m for o in PROGRAM["breadth_depth"]["industrial_experience"]["options"] for m in o["set"]}
    for ms in r.plan.values():
        n = sum(1 for m in ms if m.startswith(("CS", "IFS", "CP")) and m not in ind)
        assert n <= 2
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_checker_flags_too_many_cs_in_a_semester():
    s = scenario(preferences={"max_cs_modules_per_sem": 2})
    errs = check_plan_iter2({1: ["CS1101S", "CS1231S", "CS2100"]},
                            MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert any("Computing modules > cap" in e for e in errs)


# === iter3 C5 — special-term calendar / term layout (I2.14) =================

def test_term_layout_changes_offering():
    # CS3243 is Semester-2-only. Under a layout that makes plan-slot 1 a Term-2
    # slot, placing it there is allowed; under the default parity (slot 1 = Term 1)
    # it is an offering violation.
    off = [e for e in check_plan_iter2({1: ["CS3243"]}, MODULES, PROGRAM, STUDENT,
                                       FOCUS, PRECL, scenario()) if "not offered" in e]
    assert any("CS3243" in e for e in off)
    layout = [2, 1, 2, 1, 2, 1, 2, 1]
    off2 = [e for e in check_plan_iter2({1: ["CS3243"]}, MODULES, PROGRAM, STUDENT,
                                        FOCUS, PRECL, scenario(term_layout=layout))
            if "not offered" in e]
    assert not any("CS3243" in e for e in off2)


def test_term_layout_validation():
    with pytest.raises(ValueError):
        solve(term_layout=[1, 2, 3])          # length != target_semesters


def test_special_term_plan_still_graduates():
    # a Special Term (Term 3) as slot 3 leaves 8 usable regular semesters at T=9.
    s = scenario(term_layout=[1, 2, 3, 1, 2, 1, 2, 1, 2], target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


# === iter3 C3 — internship + FYP + UROP (I2.17) =============================

def _eligible_student(**flags):
    st = copy.deepcopy(STUDENT)
    st.update(flags)
    return st


def test_fyp_requires_eligibility():
    # default student is not eligible_fyp -> requesting the FYP is infeasible
    assert not solve(want_fyp=True, target_semesters=9).feasible


def test_fyp_feasible_when_eligible():
    st = _eligible_student(eligible_fyp=True)
    s = scenario(want_fyp=True, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    assert "CP4101" in {m for ms in r.plan.values() for m in ms}
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


def test_fyp_and_urop_conflict_on_cp_cap():
    # CP4101 (FYP) is 12u and fills the whole 12u CP cap, so FYP + UROP together
    # is infeasible -- the headline binding interaction (I2.17).
    st = _eligible_student(eligible_fyp=True)
    s = scenario(want_fyp=True, want_urop=True, target_semesters=9)
    assert not build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s).feasible


def test_urop_alone_is_feasible():
    s = scenario(want_urop=True, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    urop = set(PROGRAM["breadth_depth"]["urop"]["codes"])
    assert urop & {m for ms in r.plan.values() for m in ms}
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_checker_flags_fyp_requested_but_absent():
    s = scenario(want_fyp=True)
    errs = check_plan_iter2(valid_plan(), MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert any("FYP requested" in e for e in errs)


def test_checker_flags_ineligible_fyp_taken():
    plan = valid_plan()
    plan[1].append("CP4101")             # default student is not eligible_fyp
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario())
    assert any("not eligible_fyp" in e for e in errs)


# --- iter3 industry-experience correction: dissertation may REPLACE internship -

ALL_IND = {m for o in PROGRAM["breadth_depth"]["industrial_experience"]["options"]
           for m in o["set"]}


def test_dissertation_replaces_industry_for_eligible_student():
    # website rule: GPA>=4.0 students may replace Industry Experience with CP4101.
    st = _eligible_student(eligible_fyp=True)
    s = scenario(want_fyp=True, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    # dissertation-only variant: strip any internship modules the optimizer added
    diss_plan = {k: [m for m in v if m not in ALL_IND] for k, v in r.plan.items()}
    assert "CP4101" in {m for ms in diss_plan.values() for m in ms}
    ind_err = lambda errs: [e for e in errs if "industrial experience" in e]
    # eligible: the dissertation satisfies the industry-experience requirement
    assert ind_err(check_plan_iter2(diss_plan, MODULES, PROGRAM, st, FOCUS, PRECL, s)) == []
    # ineligible: the SAME plan must be flagged (no dissertation substitute)
    assert ind_err(check_plan_iter2(diss_plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s))


def test_ineligible_student_must_do_an_internship():
    r = solve(target_semesters=9)          # default student is not eligible_fyp
    taken = {m for ms in r.plan.values() for m in ms}
    opts = [set(o["set"]) for o in PROGRAM["breadth_depth"]["industrial_experience"]["options"]]
    assert sum(1 for o in opts if o <= taken) == 1
    assert "CP4101" not in taken


def test_fixed_industrial_option_is_honoured_even_if_eligible():
    # an explicit internship request is not substituted away by the dissertation
    st = _eligible_student(eligible_fyp=True)
    s = scenario(industrial_option="CP3880", want_fyp=True, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    taken = {m for ms in r.plan.values() for m in ms}
    assert "CP3880" in taken and "CP4101" in taken      # both: co-existence
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


def test_checker_flags_two_internships_as_padding():
    plan = valid_plan()                    # default student already has one internship
    plan[1].append("CP3880")               # add a second full option -> padding
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario())
    assert any("at most 1" in e for e in errs)


# === iter3 C4 — module pin / forbid / deadline (I2.18) ======================

def test_require_module_is_scheduled():
    # CS3216 is a Term-1-only elective the baseline would not otherwise pick.
    s = scenario(preferences={"require_modules": ["CS3216"]}, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert "CS3216" in {m for ms in r.plan.values() for m in ms}
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_forbid_module_is_excluded():
    # forbid a popular AI primary; the solver must satisfy the area another way.
    s = scenario(preferences={"forbid_modules": ["CS3243"]},
                 focus_area="artificial_intelligence", target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert "CS3243" not in {m for ms in r.plan.values() for m in ms}
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_forbidding_a_required_module_is_infeasible():
    # CS2100 is a required module; forbidding it is a legal-but-UNSAT request.
    s = scenario(preferences={"forbid_modules": ["CS2100"]}, target_semesters=9)
    assert not build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s).feasible


def test_deadline_places_module_early_enough():
    s = scenario(preferences={"deadline": {"CS2103T": 4}}, target_semesters=9)
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    assert sem_of(r.plan)["CS2103T"] <= 4
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_checker_flags_forbidden_module_scheduled():
    s = scenario(preferences={"forbid_modules": ["CS3241"]})
    errs = check_plan_iter2({1: ["CS3241"]}, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert any("forbidden module CS3241" in e for e in errs)


def test_checker_flags_required_module_absent():
    s = scenario(preferences={"require_modules": ["CS3216"]})
    errs = check_plan_iter2(valid_plan(), MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert any("required (pinned) module CS3216" in e for e in errs)


def test_checker_flags_module_past_deadline():
    plan = valid_plan()
    s = sem_of(plan)
    # pin CS2103T's deadline to one semester BEFORE where the valid plan placed it
    deadline = max(1, s["CS2103T"] - 1)
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL,
                            scenario(preferences={"deadline": {"CS2103T": deadline}}))
    assert any("CS2103T" in e and "deadline" in e for e in errs)


def test_require_and_forbid_contradiction_rejected():
    with pytest.raises(ValueError):
        solve(preferences={"require_modules": ["CS3230"], "forbid_modules": ["CS3230"]})
