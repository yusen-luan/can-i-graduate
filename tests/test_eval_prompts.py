"""Benchmark-prompt guard: the NL prompt an LLM sees must describe the student and
the request, and must NEVER state or hint at the verdict.

The curated profile `description` is written for humans and often names the answer
("infeasible because ..."), so it must not reach `nl_prompt`. Every hard knob of the
formal request must, however, be stated, or the LLM is graded on an instance it was
never told about.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import generate  # noqa: E402

PROFILES = generate.load_yaml(ROOT / "data" / "profiles" / "benchmark_profiles.yaml")
CASES = {**{n: (p["description"], p["student"], p["scenario"]) for n, p in PROFILES.items()},
         **{n: (d, st, sc) for n, (_, d, _, st, sc) in generate.STRESS.items()}}
LEAK = re.compile(r"feasib|impossible|cannot|unsatisf|no plan|slack|floor|short of|"
                  r"too (few|tight|many)|trap|dead.?end|binding", re.I)


@pytest.mark.parametrize("name", sorted(CASES))
def test_prompt_does_not_leak_verdict(name):
    description, student, scenario = CASES[name]
    prompt = generate.nl_draft(student, scenario)
    assert description.rstrip(".") not in prompt
    assert not LEAK.search(prompt), f"{name}: {LEAK.search(prompt).group()!r} in {prompt!r}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_prompt_states_every_module_request(name):
    _, student, scenario = CASES[name]
    prompt = generate.nl_draft(student, scenario)
    prefs = scenario.get("preferences", {}) or {}
    codes = (list(prefs.get("require_modules", []) or []) + list(prefs.get("forbid_modules", []) or [])
             + list((prefs.get("deadline", {}) or {})) + [m for pair in prefs.get("heavy_conflicts", []) or []
                                                          for m in pair])
    for code in codes:
        assert code in prompt, f"{name}: {code} missing from prompt"
    for s in (prefs.get("per_semester_cap", {}) or {}):
        assert f"semester {s}" in prompt, f"{name}: per-semester cap for {s} missing"
