"""Pipeline A harness + shared scorer, offline (no API calls).

The LLM is replaced by fakes: a "perfect" model that echoes the oracle's plans
(writing generic electives as "UE") must score 100% through the real
parse -> bind -> checker path, and broken answers must be scored as wrong.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))
import run_pipe_a  # noqa: E402
import score  # noqa: E402
from llm.client import LLMResult  # noqa: E402
from llm.prompts import UE_TOKEN, bind_electives, parse_response, render_system_prompt  # noqa: E402

INSTANCES = score.load_instances()
BY_NAME = {i["name"]: i for i in INSTANCES}
SYSTEM = render_system_prompt(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)


def answer(feasible, plan=None, reason="x"):
    """Model-style JSON: plan as a list, UE_GENERIC_n written as the UE token."""
    entries = [{"semester": int(s), "modules": [UE_TOKEN if m.startswith("UE_GENERIC") else m
                                                for m in ms]}
               for s, ms in (plan or {}).items()]
    return json.dumps({"feasible": feasible, "plan": entries, "reason": reason})


def fake_call(text, stop="end_turn"):
    def call(client, model_key, system, user, schema, effort="high", max_tokens=0):
        return LLMResult(model="fake", text=text, stop_reason=stop, latency_s=1.0,
                         cost_usd=0.01, request_id="", usage={"cache_read_input_tokens": 0})
    return call


def run_with(monkeypatch, inst, text, stop="end_turn"):
    monkeypatch.setattr(run_pipe_a.llm, "call", fake_call(text, stop))
    return run_pipe_a.run_one(None, "haiku", inst, SYSTEM, "sha", "high")


def as_pred(rec):
    pr = rec["prediction"] or {"feasible": None, "plan": None}
    return {"feasible": pr["feasible"], "plan": pr["plan"], "latency_s": 1.0, "cost_usd": 0.01}


# --- prompt ---------------------------------------------------------------------
def test_system_prompt_is_static_and_covers_the_universe():
    assert SYSTEM == render_system_prompt(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)
    for code, m in score.MODULES.items():
        if m.get("kind") != "generic_placeholder":
            assert f"\n{code} | " in SYSTEM, code
    for i in INSTANCES:   # nothing instance-specific leaks into the cached prefix
        assert i["nl_prompt"] not in SYSTEM


# --- parsing / elective binding ---------------------------------------------------
def test_ue_tokens_bind_around_completed_placeholders():
    st = BY_NAME["final_year_audit"]["formal"]["student"]   # completed UE_GENERIC_1 and _8
    ues = score.PROGRAM["unrestricted_electives"]["candidates"]
    out = bind_electives({1: ["UE", "CS3243"], 2: ["UE_GENERIC_1"]}, st, ues)
    assert out == {1: ["UE_GENERIC_2", "CS3243"], 2: ["UE_GENERIC_3"]}
    many = bind_electives({1: ["UE"] * 9}, st, ues)[1]
    assert many[-1] == "UE_GENERIC_EXTRA_1"          # only 8 free -> unknown code


def test_parse_rejects_non_json_and_missing_verdict():
    with pytest.raises(ValueError):
        parse_response("Sure! Here is your plan...")
    with pytest.raises(ValueError):
        parse_response(json.dumps({"plan": [], "reason": ""}))


# --- end to end through the harness and the scorer ----------------------------------
def test_perfect_fake_llm_scores_100(monkeypatch):
    preds = {}
    for i in INSTANCES:
        gt = i["ground_truth"]
        rec = run_with(monkeypatch, i, answer(gt["feasible"], gt.get("plan")))
        assert rec["parse_error"] is None
        preds[i["name"]] = as_pred(rec)
    s, rows = score.grade_all("fake", INSTANCES, preds)
    assert [r["violations"] for r in rows if r["violations"]] == []
    assert s["feasibility_accuracy"]["pct"] == 100.0
    assert s["plan_validity"] == {"n": 17, "d": 17, "pct": 100.0}
    assert s["unsat_t1_recall"]["d"] == 7 and s["unsat_t2_4_recall"]["d"] == 11
    assert s["cost_total_usd"] == pytest.approx(0.35)


def test_broken_answers_count_as_wrong(monkeypatch):
    inst = BY_NAME["on_track_fresh"]
    garbage = run_with(monkeypatch, inst, "not json")
    truncated = run_with(monkeypatch, inst, answer(True, inst["ground_truth"]["plan"]),
                         stop="max_tokens")
    assert garbage["parse_error"] and truncated["parse_error"]
    for rec in (garbage, truncated):
        row = score.grade_instance(inst, as_pred(rec))
        assert row["decision_correct"] is False and row["plan_valid"] is False
    # right verdict, broken plan: decision counts, plan does not
    plan = {k: list(v) for k, v in inst["ground_truth"]["plan"].items()}
    plan["1"], plan["2"] = plan["2"], plan["1"]
    row = score.grade_instance(inst, as_pred(run_with(monkeypatch, inst, answer(True, plan))))
    assert row["decision_correct"] and row["plan_valid"] is False and row["violations"]
    assert row["realism"] is None
    # a missing record is wrong too
    assert score.grade_instance(inst, None)["decision_correct"] is False


# --- scorer reproduces the report's control rows -----------------------------------
def test_controls_match_report_table3():
    always, fixed = score.baseline_predictions(INSTANCES)
    a, _ = score.grade_all("always-SAT", INSTANCES, always)
    c, _ = score.grade_all("canonical-4yr", INSTANCES, fixed)
    assert a["feasibility_accuracy"]["n"] == 17 and a["plan_validity"]["n"] == 0
    assert a["unsat_t1_recall"]["n"] == a["unsat_t2_4_recall"]["n"] == 0
    assert c["plan_validity"] == {"n": 3, "d": 17, "pct": 17.6}
    assert c["realism_mean"] == 94.0


def test_tiers_and_violation_buckets():
    from collections import Counter
    assert Counter(i["meta"]["tier"] for i in INSTANCES) == {"SAT": 17, "T1": 7, "T4": 10, "T2": 1}
    _, fixed = score.baseline_predictions(INSTANCES)
    _, rows = score.grade_all("canonical-4yr", INSTANCES, fixed)
    msgs = [v for r in rows for v in r["violations"]]
    assert msgs and all(score.violation_rule(v) != "other" for v in msgs)


# --- bare-student condition ----------------------------------------------------------
def test_bare_prompt_has_conventions_but_no_rules_or_catalog():
    from llm.prompts import render_bare_system_prompt
    bare = render_bare_system_prompt()
    assert len(bare) < len(SYSTEM) / 5
    assert f'"{UE_TOKEN}"' in bare and "Special Term 3" in bare
    for leak in ("160", "CS3230", "prereq", "CP-coded", "12 MC", "focus area"):
        assert leak not in bare, leak


def test_out_of_universe_codes_are_classified_and_lenient_regraded():
    if not score.NUS_MODULES:
        pytest.skip("module_list.json not ingested")
    assert score.violation_rule("GEC1001: unknown module") == "unmodelled real NUS module"
    assert score.violation_rule("CS4232: unknown module") == "not an AY2026/27 NUS module"
    assert score.violation_rule("UE_GENERIC_EXTRA_1: unknown module") == "too many generic electives"
    inst = BY_NAME["on_track_fresh"]
    st, sc = inst["formal"]["student"], inst["formal"]["scenario"]
    plan = {k: list(v) for k, v in inst["ground_truth"]["plan"].items()}
    s, i = next((s, i) for s, ms in plan.items() for i, m in enumerate(ms) if m.startswith("UE_GENERIC"))
    real = dict(plan, **{s: plan[s][:i] + ["GEC1001"] + plan[s][i + 1:]})   # elective -> real GE
    fake = dict(plan, **{s: plan[s][:i] + ["CS4232"] + plan[s][i + 1:]})    # retired code
    for p_, lenient in ((real, True), (fake, False)):
        row = score.grade_instance(inst, {"feasible": True, "plan": p_, "latency_s": 0, "cost_usd": 0})
        assert row["plan_valid"] is False and row["plan_valid_lenient"] is lenient
