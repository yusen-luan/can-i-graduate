"""Pipeline B (LLM-as-translator) harness + scorer rows, offline (no API calls).

The LLM is replaced by fakes: a "perfect" translator that returns each gold
`formal` as a spec must score 100% (verdicts, plans, fidelity) through the real
spec -> solver -> checker path, so the harness itself adds no error; broken or
unfaithful specs must be caught and scored as wrong.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))
import run_pipe_b  # noqa: E402
import score  # noqa: E402
from llm.client import LLMResult  # noqa: E402
from llm.prompts import render_system_prompt, render_translator_prompt  # noqa: E402
from llm.spec import formal_to_spec, spec_schema  # noqa: E402

INSTANCES = score.load_instances()
BY_NAME = {i["name"]: i for i in INSTANCES}
SYSTEM = render_translator_prompt(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)
SCHEMA = spec_schema(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)


def gold_spec(inst):
    f = inst["formal"]
    return formal_to_spec(f["student"], f["scenario"], score.PROGRAM)


def fake_call(text, stop="end_turn"):
    def call(client, model_key, system, user, schema, effort="high", max_tokens=0):
        return LLMResult(model="claude-haiku-5-5", text=text, stop_reason=stop, latency_s=1.0,
                         cost_usd=0.01, request_id="",
                         usage={"input_tokens": 100, "output_tokens": 400,
                                "cache_read_input_tokens": 3000,
                                "cache_creation_input_tokens": 0})
    return call


def run_with(monkeypatch, inst, spec, stop="end_turn"):
    text = spec if isinstance(spec, str) else json.dumps(spec)
    monkeypatch.setattr(run_pipe_b.llm, "call", fake_call(text, stop))
    return run_pipe_b.run_one(None, "haiku", inst, SYSTEM, "sha", "high")


def as_pred(rec):
    pr = rec["prediction"] or {"feasible": None, "plan": None}
    return {"feasible": pr["feasible"], "plan": pr["plan"], "latency_s": rec["latency_s"],
            "cost_usd": rec["cost_usd"], "record": rec}


# --- prompt / schema ----------------------------------------------------------------
def test_translator_prompt_is_static_and_has_no_degree_rules():
    assert SYSTEM == render_translator_prompt(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)
    for i in INSTANCES:   # nothing instance-specific leaks into the cached prefix
        assert i["nl_prompt"] not in SYSTEM
    for leak in ("160", "prereq:", "offered:", "CP-coded cap", "12 MC", "level 4000"):
        assert leak not in SYSTEM, leak
    full = render_system_prompt(score.MODULES, score.PROGRAM, score.FOCUS, score.PRECL)
    assert len(SYSTEM) < len(full) / 2


def test_schema_is_structured_output_compatible():
    def walk(node):
        if isinstance(node, dict):
            assert not {"minimum", "maximum", "minLength", "maxLength"} & set(node)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(SCHEMA)


def test_every_gold_spec_is_expressible_in_the_schema():
    """A perfect translator must be ABLE to write each gold spec: every code it
    needs is in the enums (e.g. CS1010 exists only in preclusions.yaml)."""
    jsonschema = pytest.importorskip("jsonschema")
    for i in INSTANCES:
        jsonschema.validate(gold_spec(i), SCHEMA)


# --- end to end: a perfect translator reproduces the oracle --------------------------
def test_perfect_translator_scores_100(monkeypatch):
    preds = {}
    for i in INSTANCES:
        rec = run_with(monkeypatch, i, gold_spec(i))
        assert rec["spec_error"] is None and rec["parse_error"] is None, i["name"]
        assert rec["latency_s"] >= rec["llm_latency_s"] == 1.0
        preds[i["name"]] = as_pred(rec)
    s, rows = score.grade_all("fake-B", INSTANCES, preds)
    assert [r["violations"] for r in rows if r["violations"]] == []
    assert s["feasibility_accuracy"]["pct"] == 100.0
    assert s["plan_validity"] == {"n": 17, "d": 17, "pct": 100.0}
    t = s["translator"]
    assert t["fidelity_exact"]["n"] == t["spec_valid"]["n"] == 35
    assert t["wrong_field_histogram"] == {} and t["lucky_decisions"] == 0
    c = s["cost_profile"]
    # steady state, Haiku list prices: (100*0.10 + 3000*0.01 + 400*0.50) / 1e6 per request
    assert c["usd_per_1k_steady"] == pytest.approx(0.24)


def test_pipe_a_rows_have_no_translator_metrics():
    _, fixed = score.baseline_predictions(INSTANCES)
    s, rows = score.grade_all("canonical-4yr", INSTANCES, fixed)
    assert s["translator"] is None and s["cost_profile"] is None
    assert all(r["spec_diff"] is None for r in rows)


# --- unfaithful translations are caught -------------------------------------------
def test_dropped_request_is_a_fidelity_error_and_plan_is_graded_against_gold(monkeypatch):
    inst = BY_NAME["leave_of_absence"]          # "take semester 5 off entirely"
    spec = gold_spec(inst)
    spec["request"]["semester_caps"] = []       # translator drops the request
    rec = run_with(monkeypatch, inst, spec)
    row = score.grade_instance(inst, as_pred(rec))
    assert row["decision_correct"]              # still SAT ...
    assert row["plan_valid"] is False           # ... but the plan uses semester 5
    assert any("blocked" in v for v in row["violations"])
    _, rows = score.grade_all("x", [inst], {inst["name"]: as_pred(rec)})
    assert rows[0]["spec_diff"] == ["per_semester_cap"]


def test_lucky_wrong_spec_right_verdict(monkeypatch):
    inst = BY_NAME["unsat_t1_5sem"]
    spec = gold_spec(inst)
    spec["request"]["max_units_per_semester"] = 24   # misread, still UNSAT
    s, rows = score.grade_all("x", [inst], {inst["name"]: as_pred(run_with(monkeypatch, inst, spec))})
    assert rows[0]["decision_correct"] and rows[0]["spec_diff"] == ["max_units_per_semester"]
    assert s["translator"]["lucky_decisions"] == 1


def test_equivalent_specs_are_not_penalised():
    inst = BY_NAME["two_internships"]                # gold option written as CP3200
    st, sc = inst["formal"]["student"], inst["formal"]["scenario"]
    sp = formal_to_spec(st, sc, score.PROGRAM)
    sp["request"]["semester_caps"] = [{"semester": 2, "max_units": sc["max_units_per_semester"]}]
    sp["request"]["term_layout"] = [1 if s % 2 else 2 for s in range(1, sc["target_semesters"] + 1)]
    rec = {"spec": sp}
    assert score.translation_diff(inst, rec) == []   # no-op cap + explicit default layout


# --- broken specs -----------------------------------------------------------------
def test_broken_specs_count_as_wrong(monkeypatch):
    inst = BY_NAME["on_track_fresh"]
    bad_layout = copy.deepcopy(gold_spec(inst))
    bad_layout["request"]["term_layout"] = [1, 2, 3]   # length != target_semesters
    too_many_ue = copy.deepcopy(gold_spec(inst))
    too_many_ue["student"]["completed_unrestricted_electives"] = 99
    for spec, field in (("not json", "parse_error"), (bad_layout, "spec_error"),
                        (too_many_ue, "spec_error")):
        rec = run_with(monkeypatch, inst, spec)
        assert rec[field] and rec["prediction"] is None
        row = score.grade_instance(inst, as_pred(rec))
        assert row["decision_correct"] is False and row["plan_valid"] is False
    truncated = run_with(monkeypatch, inst, gold_spec(inst), stop="max_tokens")
    assert truncated["parse_error"] and truncated["spec"] is None
    s, _ = score.grade_all("x", [inst], {inst["name"]: as_pred(truncated)})
    assert s["translator"]["spec_valid"]["n"] == 0


def test_cap_above_ceiling_is_answered_infeasible(monkeypatch):
    inst = BY_NAME["unsat_t1_4sem_overload"]
    spec = gold_spec(inst)
    spec["request"]["max_units_per_semester"] = score.PROGRAM["max_overload_units"] + 2
    rec = run_with(monkeypatch, inst, spec)
    assert rec["spec_error"] is None and rec["solve"]["status"] == "REJECTED_OVER_CEILING"
    assert rec["prediction"]["feasible"] is False


def test_resolve_recomputes_from_stored_spec(monkeypatch):
    inst = BY_NAME["mid_degree_y2"]
    rec = run_with(monkeypatch, inst, gold_spec(inst))
    rec["prediction"] = rec["solve"] = None
    again = run_pipe_b.finish(rec, rec["llm_latency_s"])
    assert again["prediction"]["feasible"] is True and again["solve"]["status"] == "OPTIMAL"
