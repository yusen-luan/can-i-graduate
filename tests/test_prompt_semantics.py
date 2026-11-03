"""Prompt-semantics regression guard (R1-R3).

The Pipe A (full) system prompt is prose rendered from the same YAML the oracle
grades against, but prose can still describe the WRONG operation even when the
data is right (the R1/R2/R3 review finding: the prompt stated a global CP cap,
omitted full-semester internship occupancy, and said "exactly 3" ID/CD). These
tests pin the corrected wording so the prompt cannot silently drift back out of
step with solver.py / checker.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm.prompts import render_system_prompt  # noqa: E402
from model import load_iter2  # noqa: E402

MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()
PROMPT = render_system_prompt(MODULES, PROGRAM, FOCUS, PRECL)


def test_cp_cap_is_bd_allocation_not_global():
    # R1: the 12 MC CP cap applies to the B&D allocation, not a global unit total.
    assert "allocation cap, not a limit on how many you may take" in PROMPT
    assert "counts toward" in PROMPT and "as unrestricted electives" in PROMPT
    # must NOT re-introduce the global-cap phrasing
    assert "together may total at most" not in PROMPT


def test_full_semester_internship_occupancy_stated():
    # R2: the dominant plan-invalidity rule must be in the prompt, naming the
    # full-semester options and forbidding concurrent coursework.
    for code in ("CP3880", "ETP3201L", "IS4010"):
        assert code in PROMPT
    assert "NO other credit-bearing module may be scheduled" in PROMPT


def test_idcd_is_qualifying_allocation_not_exactly_three():
    # R3: at-least-3 qualifying set, extras count as UE (not "exactly 3").
    assert "at least 3 qualifying modules" in PROMPT
    assert "exactly" not in PROMPT.split("Interdisciplinary")[1].split("Focus area")[0]


def test_urop_duration_and_ordering_stated_but_listed_once():
    # R3 + the checker trap: UROP spans 2 semesters but is LISTED ONCE at its start,
    # cannot start in the final semester, and finishes before the FYP.
    assert "consecutive regular semesters" in PROMPT
    assert "list it ONLY in its starting semester" in PROMPT
    assert "cannot be the final semester" in PROMPT
    assert "at least 2 semesters after the UROP start" in PROMPT


def test_independent_project_distinct_from_urop():
    # R3/Issue #4: CP3106 is a distinct module, not UROP.
    assert "CP3106 is a separate independent-project module" in PROMPT


def test_band2_english_waiver_stated():
    # R3: Band 2 waives only the ES1000 prerequisite (no credit); not both.
    assert "Band 2 must take ES1103" in PROMPT
    assert "ES1000 prerequisite is waived" in PROMPT
