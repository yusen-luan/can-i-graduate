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
from model import load_iter2, load_yaml  # noqa: E402
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
