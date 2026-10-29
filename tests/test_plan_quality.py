"""Calibration tests for the plan-quality (realism) evaluator.

Realism is subjective, so we validate by RANKING, not absolute values: a sensible
plan must out-score a deliberately degraded one, and each degradation must hit the
sub-score it targets. This is the plan-quality analogue of the oracle's A3
metamorphic properties.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import load_iter2, load_scenario  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from plan_quality import score_plan  # noqa: E402

MODULES, PROGRAM, STUDENT, FOCUS, PRECL = load_iter2()
SCEN = load_scenario(Path(__file__).resolve().parents[1] / "data" / "scenario_iter2.yaml")


def solver_plan(**over):
    s = {**copy.deepcopy(SCEN), **over}
    r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, s)
    assert r.feasible
    return {k: v for k, v in r.plan.items() if v}, s


def q(plan, scenario):
    return score_plan(plan, MODULES, PROGRAM, STUDENT, scenario)


def sub(res, name):
    return next(m["score"] for m in res["metrics"] if m["name"] == name)


def test_score_is_bounded():
    plan, sc = solver_plan()
    assert 0 <= q(plan, sc)["overall"] <= 100


def test_solver_plan_is_reasonably_good():
    # the real solver plan should be a decent (not perfect) plan.
    plan, sc = solver_plan()
    assert q(plan, sc)["overall"] >= 55


def test_lumpy_plan_scores_worse_on_balance():
    plan, sc = solver_plan()
    # cram every module into the first two semesters -> extreme lumpiness
    allmods = [m for ms in plan.values() for m in ms]
    half = len(allmods) // 2
    lumpy = {1: allmods[:half], 2: allmods[half:]}
    good, bad = q(plan, sc), q(lumpy, sc)
    assert bad["overall"] < good["overall"]
    assert sub(bad, "workload_balance") <= sub(good, "workload_balance")


def test_gap_plan_scores_worse_on_contiguity():
    plan, sc = solver_plan()
    used = sorted(plan)
    # push the last semester's modules far away, opening a gap
    gapped = {s: list(plan[s]) for s in used[:-1]}
    gapped[used[-1] + 3] = list(plan[used[-1]])
    sc2 = {**sc, "target_semesters": used[-1] + 3}
    assert sub(q(gapped, sc2), "contiguity") < 1.0


def test_clustered_ge_scores_worse_on_spread():
    plan, sc = solver_plan()
    ge = [m for ms in plan.values() for m in ms
          if MODULES[m].get("pillar") == "university_level_requirements"]
    if len(ge) < 2:
        return
    # dump every GE/ULR module into semester 1
    clustered = {s: [m for m in ms if m not in ge] for s, ms in plan.items()}
    clustered.setdefault(1, [])
    clustered[1] = list(clustered.get(1, [])) + ge
    assert sub(q(clustered, sc), "breadth_spread") < 1.0
