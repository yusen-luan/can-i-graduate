"""Regression tests for the Issues.md rule / reporting fixes.

Each test pins one fix from Issues.md so a later refactor cannot silently undo
it. Grouped by issue number. The modelling-semantics fixes (1-6, 13, 14) assert
solver + checker agreement; the reporting fixes (7-11) assert the honest
reporting contract.
"""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2, load_scenario, pre_satisfied  # noqa: E402
from solver import build_and_solve_iter2, SolveResult  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

MODULES, PROGRAM, STUDENT, FOCUS, PRECL = load_iter2()
SCEN = load_scenario(ROOT / "data" / "scenario_iter2.yaml")
INDUSTRIAL = {m for o in PROGRAM["breadth_depth"]["industrial_experience"]["options"]
              for m in o["set"]}


def scenario(**over):
    s = copy.deepcopy(SCEN)
    s.update(over)
    return s


def solve(**over):
    return build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario(**over))


# ===========================================================================
# Issue #7 -- solver status is not collapsed to a boolean
# ===========================================================================
def test_feasible_proven_infeasible_resolved_are_distinct():
    sat = SolveResult(status="OPTIMAL")
    assert sat.feasible and sat.resolved and not sat.proven_infeasible
    unsat = SolveResult(status="INFEASIBLE")
    assert unsat.proven_infeasible and unsat.resolved and not unsat.feasible
    for unresolved in ("UNKNOWN", "MODEL_INVALID"):
        r = SolveResult(status=unresolved)
        # an unresolved search is NOT feasible, NOT proven infeasible, NOT resolved
        assert not r.feasible
        assert not r.proven_infeasible
        assert not r.resolved


def test_default_instance_is_proven_infeasible_not_merely_not_feasible():
    r = solve(target_semesters=5, max_units_per_semester=20)   # below the 160 floor
    assert not r.feasible
    assert r.proven_infeasible          # the solver really proved it, didn't time out
    assert r.resolved


# ===========================================================================
# Issue #9 -- both scheduling and total variable counts are reported
# ===========================================================================
def test_total_variable_count_exceeds_scheduling_variable_count():
    r = solve()
    assert r.num_variables > 0
    # reified prerequisite / focus / occupancy auxiliaries live only in the proto,
    # so the total must strictly exceed the x[m,s] scheduling-variable count.
    assert r.num_total_variables > r.num_variables


# ===========================================================================
# Issues #10 / #11 -- honest difficulty probes
# ===========================================================================
sys.path.insert(0, str(ROOT / "eval"))
from generate import measure_difficulty, _probe_min, CAP_PROBE_FLOOR  # noqa: E402


def test_probe_min_flags_bounded_and_non_monotone():
    # feasible all the way to the floor -> bounded (minimum not established)
    mn, bounded, nonmono = _probe_min(lambda v: True, 10, 1)
    assert mn == 1 and bounded and not nonmono
    # a clean threshold at 5 -> not bounded, monotone
    mn, bounded, nonmono = _probe_min(lambda v: v >= 5, 10, 1)
    assert mn == 5 and not bounded and not nonmono
    # feasible BELOW an infeasible probe -> non-monotone is detected
    mn, bounded, nonmono = _probe_min(lambda v: v != 7, 10, 1)
    assert nonmono


def test_difficulty_reports_separate_slacks_not_a_combined_margin():
    r = solve()
    d = measure_difficulty(STUDENT, scenario(), r)
    # Issue #11: the two slacks are distinct keys; the combined min() margin is gone
    assert "semester_slack" in d and "cap_slack" in d
    assert "near_unsat_margin" not in d
    # Issue #9: total variable count is carried into the difficulty meta
    assert d["num_total_variables"] >= d["num_variables"]


# ===========================================================================
# Issue #14 -- ID/CD is a qualifying allocation, not a cap on every eligible course
# ===========================================================================
ID_CANDS = ["DTK1234", "IE2141", "IS1128", "HSI1000"]   # 4 ID-tagged candidates


def test_taking_a_fourth_eligible_idcd_course_is_feasible_and_valid():
    # Pin all 4 ID candidates. The old `sum(sat)==3` rule made this INFEASIBLE;
    # now 3 are allocated to the ID/CD quota and the 4th counts as a UE.
    s = scenario(target_semesters=10, max_units_per_semester=24, focus_area="any",
                 preferences={**copy.deepcopy(SCEN["preferences"]),
                              "require_modules": ID_CANDS})
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible, "4 eligible ID/CD courses must be schedulable (surplus -> UE)"
    assert all(m in {x for ms in r.plan.values() for x in ms} for m in ID_CANDS)
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s) == []


def test_checker_still_rejects_too_few_id_courses():
    r = solve()
    assert r.feasible
    plan = {s: list(ms) for s, ms in r.plan.items()}
    # strip every ID/CD candidate, then re-add a single ID course -> no qualifying
    # 3-course allocation exists, so the checker must flag it.
    cands = set(PROGRAM["requirement_groups"]
                ["interdisciplinary_cross_disciplinary"]["candidates"])
    for ms in plan.values():
        ms[:] = [m for m in ms if m not in cands]
    plan[1].append("DTK1234")
    errs = check_plan_iter2(plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario())
    assert any("ID/CD" in e for e in errs)


# ===========================================================================
# Issue #13 -- nOf prerequisites are an at-least-n threshold, not one_of
# ===========================================================================
from model import tree_satisfied, tree_leaves  # noqa: E402


def test_n_of_tree_semantics_is_at_least_n():
    tree = {"n_of": [2, ["A", "B", "C"]]}
    done = set()
    assert not tree_satisfied(tree, lambda p: p in done)          # 0 of 3
    done = {"A"}
    assert not tree_satisfied(tree, lambda p: p in done)          # 1 of 3 < 2
    done = {"A", "C"}
    assert tree_satisfied(tree, lambda p: p in done)              # 2 of 3 >= 2
    # n_of children are reachable in the leaf set (domain closure, prompts)
    assert set(tree_leaves(tree)) == {"A", "B", "C"}


def test_cs2109s_retains_the_nOf_both_maths_requirement():
    # the frozen snapshot keeps nOf (not weakened to one_of); CS2109S needs BOTH
    # MA1511 and MA1512 on that branch (or an alternative like MA1521).
    import json
    tree = MODULES["CS2109S"]["prerequisites"]["tree"]
    assert "n_of" in json.dumps(tree)


def test_solver_nOf_module_plan_passes_checker():
    # scheduling a module whose prereq tree carries nOf must agree solver<->checker
    r = solve(target_semesters=9, max_units_per_semester=22,
              focus_area="artificial_intelligence")
    assert r.feasible
    assert "CS2109S" in {m for ms in r.plan.values() for m in ms} or \
        pre_satisfied("CS2109S", STUDENT)
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, STUDENT, FOCUS, PRECL,
                            scenario(target_semesters=9, max_units_per_semester=22,
                                     focus_area="artificial_intelligence")) == []


# ===========================================================================
# Issues #2 / #3 -- English bridges are mandatory per band; Band 2 waives ES1000
# ===========================================================================
from model import bridging_waived, required_bridges  # noqa: E402


def _eng_student(path):
    s = copy.deepcopy(STUDENT)
    s["conditions"] = {**s.get("conditions", {}), "english_path": path}
    return s


def test_band_waivers_and_required_bridges_by_qet_band():
    # Band 3: no bridge; both waived
    s3 = _eng_student("direct_es2660")
    assert required_bridges(s3) == set() and {"ES1000", "ES1103"} <= bridging_waived(s3)
    # Band 2: ES1103 mandatory, ES1000 waived (Issue #3 -- NOT forced)
    s2 = _eng_student("es1103_required")
    assert required_bridges(s2) == {"ES1103"}
    assert "ES1000" in bridging_waived(s2) and "ES1103" not in bridging_waived(s2)
    # Band 1: both mandatory, neither waived
    s1 = _eng_student("es1000_then_es1103")
    assert required_bridges(s1) == {"ES1000", "ES1103"}
    assert "ES1000" not in bridging_waived(s1) and "ES1103" not in bridging_waived(s1)


def test_band2_plan_takes_es1103_without_es1000():
    st = _eng_student("es1103_required")
    s = scenario(target_semesters=9, max_units_per_semester=22)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    taken = {m for ms in r.plan.values() for m in ms}
    assert "ES1103" in taken          # Issue #2: mandatory
    assert "ES1000" not in taken       # Issue #3: NOT forced by placement
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


def test_band1_plan_takes_es1000_before_es1103():
    st = _eng_student("es1000_then_es1103")
    s = scenario(target_semesters=9, max_units_per_semester=22)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    sem = {m: sslot for sslot, ms in r.plan.items() for m in ms}
    assert "ES1000" in sem and "ES1103" in sem
    assert sem["ES1000"] < sem["ES1103"]   # ordering via the ES1103 -> ES1000 prereq
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


def test_checker_flags_missing_mandatory_bridge():
    st = _eng_student("es1103_required")
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL,
                              scenario(target_semesters=9, max_units_per_semester=22))
    plan = {s: [m for m in ms if m != "ES1103"] for s, ms in r.plan.items()}  # drop ES1103
    errs = check_plan_iter2(plan, MODULES, PROGRAM, st, FOCUS, PRECL,
                            scenario(target_semesters=9, max_units_per_semester=22))
    assert any("ES1103" in e for e in errs)


# ===========================================================================
# Issue #4 -- want_urop targets the real UROP (CP3209), distinct from CP3106/CP4106
# ===========================================================================
def _urop_student():
    s = copy.deepcopy(STUDENT)
    s["eligible_urop"] = True
    return s


def test_want_urop_schedules_cp3209_not_the_other_projects():
    st = _urop_student()
    s = scenario(target_semesters=10, max_units_per_semester=22, want_urop=True)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    taken = {m for ms in r.plan.values() for m in ms}
    assert "CP3209" in taken               # the UROP specifically (Issue #4)
    assert "CP3106" not in taken and "CP4106" not in taken  # distinct projects, not forced
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


# ===========================================================================
# Issue #5 -- CP3209 spans 2 consecutive semesters and finishes before the FYP
# ===========================================================================
def test_checker_rejects_urop_in_final_semester():
    st = _urop_student()
    s = scenario(target_semesters=10, max_units_per_semester=22, want_urop=True)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    plan = {sl: list(ms) for sl, ms in r.plan.items()}
    # move CP3209 into the final semester -> no room for its 2nd half
    for ms in plan.values():
        if "CP3209" in ms:
            ms.remove("CP3209")
    plan.setdefault(10, []).append("CP3209")
    errs = check_plan_iter2(plan, MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert any("CP3209" in e and "final" in e for e in errs)


def test_urop_finishes_before_fyp_in_solver():
    st = copy.deepcopy(STUDENT)
    st["eligible_urop"] = True
    st["eligible_fyp"] = True
    s = scenario(target_semesters=10, max_units_per_semester=24,
                 want_urop=True, want_fyp=True)
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    sem = {m: sl for sl, ms in r.plan.items() for m in ms}
    # CP3209 ends (start + 1) strictly before CP4101 starts
    assert sem["CP3209"] + 1 <= sem["CP4101"] - 1
    assert check_plan_iter2(r.plan, MODULES, PROGRAM, st, FOCUS, PRECL, s) == []


# ===========================================================================
# Issue #6 -- a full-semester internship occupies its slot (no concurrent coursework)
# ===========================================================================
def test_checker_rejects_coursework_alongside_full_semester_internship():
    st = copy.deepcopy(STUDENT)
    s = scenario(target_semesters=10, max_units_per_semester=22,
                 industrial_option="CP3880")
    r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert r.feasible
    sem = {m: sl for sl, ms in r.plan.items() for m in ms}
    islot = sem["CP3880"]
    # the internship's slot must carry no other (non-internship) coursework
    assert all(m in INDUSTRIAL for m in r.plan[islot]), r.plan[islot]
    # injecting a course into that slot must be rejected
    plan = {sl: list(ms) for sl, ms in r.plan.items()}
    # find a non-industrial module elsewhere and move it into the internship slot
    donor = next(m for sl, ms in r.plan.items() for m in ms
                 if m not in INDUSTRIAL and sl != islot)
    plan[sem[donor]].remove(donor)
    plan[islot].append(donor)
    errs = check_plan_iter2(plan, MODULES, PROGRAM, st, FOCUS, PRECL, s)
    assert any("full-semester internship" in e for e in errs)
