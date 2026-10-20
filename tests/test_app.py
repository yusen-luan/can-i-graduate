"""Smoke tests for the Streamlit frontend via AppTest (no browser needed).

Guards the profile picker + iter3 controls: the app must run without exceptions,
seed controls from the chosen benchmark profile, and show the right verdict.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "app.py"
sys.path.insert(0, str(ROOT / "src"))

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


def _run():
    return AppTest.from_file(str(APP), default_timeout=90).run()


def test_app_runs_default_profile_feasible():
    at = _run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "semesters" in md and "CS modules" in md and "checker" in md   # verdict stat tiles


def test_app_infeasible_profile_shows_no_plan():
    at = _run()
    at.selectbox(key="profile_name").set_value("infeasible_3yr").run()
    assert not at.exception
    assert "No valid plan" in " ".join(m.value for m in at.markdown)


def test_app_honours_profile_seeds_iter3_controls():
    at = _run()
    at.selectbox(key="profile_name").set_value("honours_dissertation").run()
    assert not at.exception
    assert at.checkbox(key="want_fyp").value is True
    assert at.multiselect(key="specials").value == [3]
    md = " ".join(m.value for m in at.markdown)
    assert "Special Term" in md          # term layout labelled in the plan grid
    assert "CP4101" in md or "Final-Year Project" in md


def test_app_supports_multiple_light_and_heavy_semesters():
    # v2 workload editor: any number of blocked/light/heavy semesters round-trips.
    at = _run()
    at.selectbox(key="profile_name").set_value("part_load_worklife").run()
    at.multiselect(key="light_sems").set_value([4, 5]).run()
    at.multiselect(key="heavy_sems").set_value([7]).run()
    assert not at.exception
