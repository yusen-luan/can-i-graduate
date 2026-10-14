import copy
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import load_model  # noqa: E402
from solver import build_and_solve  # noqa: E402
from checker import check_plan  # noqa: E402

MODULES, PROGRAM, BASE_STUDENT = load_model()
CAP = 20
ENGLISH_PATHS = ["direct_es2660", "es1103_required", "es1000_then_es1103"]


def student(needs_math_bridging=False, english_path="direct_es2660",
            completed=(), exempted=()):
    s = copy.deepcopy(BASE_STUDENT)
    s["conditions"]["needs_math_bridging"] = needs_math_bridging
    s["conditions"]["english_path"] = english_path
    for m in completed:
        s["completed"][m] = True
    for m in exempted:
        s["exempted"][m] = True
    return s


def solve(st, T=8, cap=CAP):
    return build_and_solve(MODULES, PROGRAM, st, T, cap)


def sem_of(plan):
    return {m: s for s, ms in plan.items() for m in ms}


# --- solver output always passes the independent checker --------------------

@pytest.mark.parametrize(
    "bridging,english,T",
    list(itertools.product([False, True], ENGLISH_PATHS, range(3, 9))),
)
def test_solver_plans_pass_checker(bridging, english, T):
    st = student(bridging, english)
    result = solve(st, T)
    if result.feasible:
        assert check_plan(result.plan, MODULES, PROGRAM, st, T, CAP) == []


# --- feasibility boundaries -------------------------------------------------

def test_default_student_needs_five_semesters():
    # 88 units at 20/semester: 4 semesters hold only 80.
    assert not solve(student(), T=4).feasible
    assert solve(student(), T=5).feasible


def test_bridging_heavy_student_fits_exactly_five_semesters():
    # Math bridging + ES1000 + ES1103 = 100 units = 5 x 20: every semester full.
    st = student(True, "es1000_then_es1103")
    assert not solve(st, T=4).feasible
    result = solve(st, T=5)
    assert result.feasible
    assert all(sum(MODULES[m]["units"] for m in ms) == CAP
               for ms in result.plan.values())


def test_bundle_cannot_fit_under_tiny_cap():
    assert not solve(student(), T=8, cap=4).feasible


# --- constraint semantics ---------------------------------------------------

def test_math_bridging_takes_exactly_one_bridge_before_targets():
    plan = solve(student(needs_math_bridging=True)).plan
    s = sem_of(plan)
    bridges = [m for m in ("MA1301", "MA1301X") if m in s]
    assert len(bridges) == 1
    for target in ("MA1521", "MA1522", "CS1231S"):
        assert s[bridges[0]] < s[target]


def test_no_bridging_modules_when_not_needed():
    s = sem_of(solve(student()).plan)
    assert not {"MA1301", "MA1301X", "ES1000", "ES1103"} & set(s)


def test_english_chain_ordering():
    s = sem_of(solve(student(english_path="es1000_then_es1103")).plan)
    assert s["ES1000"] < s["ES1103"] < s["ES2660"]


def test_bundle_same_semester():
    s = sem_of(solve(student()).plan)
    assert s["CS2101"] == s["CS2103T"]


def test_exempted_module_not_scheduled_and_unlocks_successors():
    st = student(exempted=["CS1101S"])
    s = sem_of(solve(st).plan)
    assert "CS1101S" not in s
    # 84 units still need 5 semesters; CS2030S may now start in semester 1.
    assert solve(st, T=5).feasible


def test_completed_half_of_bundle_releases_other_half():
    st = student(completed=["CS2101"])
    result = solve(st)
    assert result.feasible
    assert "CS2101" not in sem_of(result.plan)


def test_idcd_pattern():
    s = sem_of(solve(student()).plan)
    picked = [m for m in ("ID_GENERIC_1", "ID_GENERIC_2", "ID_GENERIC_3", "CD_GENERIC_1") if m in s]
    assert len(picked) == 3
    assert sum(m.startswith("CD") for m in picked) <= 1


# --- checker catches bad plans ----------------------------------------------

def valid_plan():
    return copy.deepcopy(solve(student()).plan)


def test_checker_flags_prerequisite_violation():
    plan = valid_plan()
    s = sem_of(plan)
    plan[s["CS2030S"]].remove("CS2030S")
    plan[s["CS1101S"]].append("CS2030S")  # same semester as its prerequisite
    assert any("CS2030S" in e and "prerequisite" in e
               for e in check_plan(plan, MODULES, PROGRAM, student(), 8, CAP))


def test_checker_flags_missing_requirement_and_split_bundle():
    plan = valid_plan()
    s = sem_of(plan)
    plan[s["CS2101"]].remove("CS2101")
    errs = check_plan(plan, MODULES, PROGRAM, student(), 8, CAP)
    assert any("CS2101: required" in e for e in errs)
    assert any("same semester" in e for e in errs)


def test_checker_flags_unit_cap():
    plan = {1: [m for m in PROGRAM["required_modules"]][:6]}
    errs = check_plan(plan, MODULES, PROGRAM, student(), 8, CAP)
    assert any("units > cap" in e for e in errs)
