"""Corpus guard: every benchmark profile must resolve to its declared `expect`,
and every feasible one must pass the independent checker.

This keeps data/profiles/benchmark_profiles.yaml (the app picker + eval corpus)
honest — a profile that silently drifts to the wrong verdict is a bad benchmark
item and a bad demo.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2, load_yaml, with_horizon  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()
PROFILES = load_yaml(ROOT / "data" / "profiles" / "benchmark_profiles.yaml")


@pytest.mark.parametrize("name", list(PROFILES))
def test_profile_matches_expected_verdict(name):
    p = PROFILES[name]
    student, scenario = p["student"], p["scenario"]
    r = build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario)
    assert r.feasible == (p["expect"] == "feasible"), (
        f"{name}: expected {p['expect']}, solver said "
        f"{'feasible' if r.feasible else 'infeasible'}")
    if r.feasible:
        viol = check_plan_iter2(r.plan, MODULES, PROGRAM, student, FOCUS, PRECL, scenario)
        assert viol == [], f"{name}: solver plan failed the checker: {viol}"


# A4 mechanism check for every UNSAT profile: relaxing exactly the STATED
# blocker must flip it to SAT (it is infeasible for the reason it claims).
def _relax_preclusion(st, sc):
    return {**st, "exempted": {**st.get("exempted", {}), "CS1101S": True}}, sc


RELAX = {
    "preclusion_deadend": _relax_preclusion,                       # credit recognised
    "fyp_urop_trap": lambda st, sc: (st, {**sc, "want_urop": False}),  # drop UROP
    "infeasible_3yr": lambda st, sc: (st, with_horizon(sc, 8)),        # 4-year horizon
}


def test_every_unsat_profile_has_a_relaxation():
    unsat = {n for n, p in PROFILES.items() if p["expect"] == "infeasible"}
    assert unsat == set(RELAX), f"add an A4 relaxation for: {sorted(unsat - set(RELAX))}"


@pytest.mark.parametrize("name", sorted(RELAX))
def test_unsat_profile_flips_when_blocker_relaxed(name):
    p = PROFILES[name]
    student, scenario = RELAX[name](p["student"], p["scenario"])
    assert build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario).feasible
