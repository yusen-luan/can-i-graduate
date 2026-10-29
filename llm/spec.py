"""Pipeline B (LLM-as-translator) spec: the JSON contract the LLM fills in, its
conversion to the solver's `student` + `scenario` input, and a canonical form
used to grade translation fidelity against the instance's gold `formal`.

The spec mirrors `formal` field for field. The only changes are shapes JSON
structured outputs cannot express (open-ended dicts become lists of pairs) and
completed generic electives, which the NL prompt states as a count. Semantics
are unchanged, so a perfect translation reproduces the gold instance exactly
(tests/test_pipe_b.py round-trips all of them).

`rename` ({code: alias}) is the label-obfuscation hook (evaluation_plan.md §6.1).
"""
from model import term_of

ENGLISH_PATHS = ["direct_es2660", "es1103_required", "es1000_then_es1103"]


def module_codes(modules):
    """Real module codes the LLM may name (generic UE placeholders excluded)."""
    return sorted(c for c, m in modules.items() if m.get("kind") != "generic_placeholder")


def held_only_codes(modules, preclusions):
    """Legacy / alternative codes that exist only as preclusion-group members: a
    student may already HOLD one (e.g. CS1010), but it is never schedulable."""
    return sorted({c for g in preclusions["groups"].values() for c in g} - set(modules))


def industrial_option_keys(program):
    """One key per industrial-experience option: its first module code."""
    return [o["set"][0] for o in program["breadth_depth"]["industrial_experience"]["options"]]


def spec_schema(modules, program, focus_areas, preclusions, rename=None):
    R = lambda c: (rename or {}).get(c, c)  # noqa: E731
    # one shared enum ($ref): inlined 7 times it would bill ~9k extra input tokens
    code = {"$ref": "#/$defs/module_code"}
    codes = {"type": "array", "items": code}
    held = {"type": "array", "items": {"$ref": "#/$defs/held_code"}}
    integer, boolean = {"type": "integer"}, {"type": "boolean"}

    def obj(**props):
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}

    student = obj(
        completed=held, completed_unrestricted_electives=integer, exempted=held,
        has_h2_math=boolean,
        english_path={"type": "string", "enum": ENGLISH_PATHS},
        eligible_fyp=boolean, eligible_urop=boolean)
    request = obj(
        target_semesters=integer, max_units_per_semester=integer,
        focus_area={"type": "string", "enum": ["any", *focus_areas["areas"]]},
        industrial_option={"type": "string",
                           "enum": ["any", *(R(k) for k in industrial_option_keys(program))]},
        want_fyp=boolean, want_urop=boolean,
        term_layout={"type": "array", "items": integer},
        semester_caps={"type": "array", "items": obj(semester=integer, max_units=integer)},
        max_cs_modules_per_sem=integer, min_units_per_semester=integer,
        no_empty_semesters=boolean,
        not_same_semester={"type": "array", "items": obj(a=code, b=code)},
        require_modules=codes, forbid_modules=codes,
        deadlines={"type": "array", "items": obj(module=code, semester=integer)})
    schema = obj(student=student, request=request,
                 unsupported_requests={"type": "array", "items": {"type": "string"}})
    legacy = {"type": "string", "enum": [R(c) for c in held_only_codes(modules, preclusions)]}
    schema["$defs"] = {
        "module_code": {"type": "string", "enum": [R(c) for c in module_codes(modules)]},
        "held_code": {"anyOf": [{"$ref": "#/$defs/module_code"}, legacy]}}
    return schema


class SpecError(ValueError):
    """The spec cannot be turned into a solver input (a translation error)."""


def spec_to_formal(spec, program, rename=None):
    """LLM spec -> (student, scenario) in the solver's input format. Raises
    SpecError on input the schema cannot rule out (e.g. too many electives)."""
    back = {v: k for k, v in (rename or {}).items()}
    U = lambda c: back.get(c, c)  # noqa: E731
    st, rq = spec["student"], spec["request"]
    ue = program["unrestricted_electives"]["candidates"]
    n_ue = st["completed_unrestricted_electives"]
    if not 0 <= n_ue <= len(ue):
        raise SpecError(f"completed_unrestricted_electives={n_ue} outside 0..{len(ue)}")
    T = rq["target_semesters"]
    if T < 1:
        raise SpecError(f"target_semesters={T} must be >= 1")
    if rq["max_units_per_semester"] < 0:
        raise SpecError("max_units_per_semester must be >= 0")
    student = {
        "conditions": {"needs_math_bridging": not st["has_h2_math"],
                       "english_path": st["english_path"]},
        "has_h2_math": st["has_h2_math"],
        "eligible_fyp": st["eligible_fyp"], "eligible_urop": st["eligible_urop"],
        "completed": {**{U(c): True for c in st["completed"]},
                      **{c: True for c in ue[:n_ue]}},
        "exempted": {U(c): True for c in st["exempted"]},
    }
    ind = rq["industrial_option"]
    scenario = {
        "target_semesters": T,
        "max_units_per_semester": rq["max_units_per_semester"],
        "focus_area": rq["focus_area"],
        "industrial_option": ind if ind == "any" else U(ind),
        "want_fyp": rq["want_fyp"], "want_urop": rq["want_urop"],
        "preferences": {
            "per_semester_cap": {str(e["semester"]): e["max_units"] for e in rq["semester_caps"]},
            "max_cs_modules_per_sem": rq["max_cs_modules_per_sem"],
            "min_units_per_semester": rq["min_units_per_semester"],
            "no_empty_semesters": rq["no_empty_semesters"],
            "heavy_conflicts": [[U(p["a"]), U(p["b"])] for p in rq["not_same_semester"]],
            "require_modules": [U(c) for c in rq["require_modules"]],
            "forbid_modules": [U(c) for c in rq["forbid_modules"]],
            "deadline": {U(d["module"]): d["semester"] for d in rq["deadlines"]},
        },
    }
    if rq["term_layout"]:
        scenario["term_layout"] = list(rq["term_layout"])
    return student, scenario


def formal_to_spec(student, scenario, program):
    """Inverse of spec_to_formal (gold instance -> the spec a perfect translator
    writes). Used by the offline tests and as the prompt's worked example."""
    ue = set(program["unrestricted_electives"]["candidates"])
    keys = industrial_option_keys(program)
    opts = program["breadth_depth"]["industrial_experience"]["options"]
    comp = sorted(c for c, v in (student.get("completed") or {}).items() if v)
    cond = student.get("conditions", {}) or {}
    prefs = scenario.get("preferences", {}) or {}
    ind = scenario.get("industrial_option", "any")
    if ind != "any":
        ind = keys[next(i for i, o in enumerate(opts) if ind in o["set"])]
    return {
        "student": {
            "completed": [c for c in comp if c not in ue],
            "completed_unrestricted_electives": sum(c in ue for c in comp),
            "exempted": sorted(c for c, v in (student.get("exempted") or {}).items() if v),
            "has_h2_math": not cond.get("needs_math_bridging", False)
                           and student.get("has_h2_math", True),
            "english_path": cond.get("english_path", "direct_es2660"),
            "eligible_fyp": student.get("eligible_fyp", False),
            "eligible_urop": student.get("eligible_urop", True),
        },
        "request": {
            "target_semesters": scenario["target_semesters"],
            "max_units_per_semester": scenario["max_units_per_semester"],
            "focus_area": scenario.get("focus_area") or "any",
            "industrial_option": ind,
            "want_fyp": scenario.get("want_fyp", False),
            "want_urop": scenario.get("want_urop", False),
            "term_layout": list(scenario.get("term_layout") or []),
            "semester_caps": [{"semester": int(s), "max_units": u} for s, u in
                              sorted((prefs.get("per_semester_cap") or {}).items(),
                                     key=lambda kv: int(kv[0]))],
            "max_cs_modules_per_sem": prefs.get("max_cs_modules_per_sem", 0),
            "min_units_per_semester": prefs.get("min_units_per_semester", 0),
            "no_empty_semesters": prefs.get("no_empty_semesters", False),
            "not_same_semester": [{"a": a, "b": b} for a, b in prefs.get("heavy_conflicts") or []],
            "require_modules": list(prefs.get("require_modules") or []),
            "forbid_modules": list(prefs.get("forbid_modules") or []),
            "deadlines": [{"module": c, "semester": s}
                          for c, s in (prefs.get("deadline") or {}).items()],
        },
        "unsupported_requests": [],
    }


def canonical(student, scenario, program):
    """Comparable form of a (student, scenario): defaults filled, no-op entries
    dropped, order removed. Two inputs with equal canonical forms pose the same
    CSP, so `spec_diff` against the gold formal measures translation fidelity."""
    ue = set(program["unrestricted_electives"]["candidates"])
    opts = program["breadth_depth"]["industrial_experience"]["options"]
    cond = student.get("conditions", {}) or {}
    comp = {c for c, v in (student.get("completed") or {}).items() if v}
    prefs = scenario.get("preferences", {}) or {}
    T, cap = scenario["target_semesters"], scenario["max_units_per_semester"]
    ind = scenario.get("industrial_option", "any")
    pcap = {int(s): u for s, u in (prefs.get("per_semester_cap") or {}).items() if u != cap}
    return {
        "completed": sorted(comp - ue),
        "completed_unrestricted_electives": len(comp & ue),
        "exempted": sorted(c for c, v in (student.get("exempted") or {}).items() if v),
        "math_bridging": bool(cond.get("needs_math_bridging")) or not student.get("has_h2_math", True),
        "english_path": cond.get("english_path", "direct_es2660"),
        "eligible_fyp": bool(student.get("eligible_fyp", False)),
        "eligible_urop": bool(student.get("eligible_urop", True)),
        "target_semesters": T,
        "max_units_per_semester": cap,
        "focus_area": scenario.get("focus_area") or "any",
        "industrial_option": "any" if ind == "any" else
            next((sorted(o["set"]) for o in opts if ind in o["set"]), [ind]),
        "want_fyp": bool(scenario.get("want_fyp", False)),
        "want_urop": bool(scenario.get("want_urop", False)),
        "term_layout": list(scenario.get("term_layout") or [term_of(s) for s in range(1, T + 1)]),
        "per_semester_cap": sorted(pcap.items()),
        "max_cs_modules_per_sem": prefs.get("max_cs_modules_per_sem", 0) or 0,
        "min_units_per_semester": prefs.get("min_units_per_semester", 0) or 0,
        "no_empty_semesters": bool(prefs.get("no_empty_semesters", False)),
        "heavy_conflicts": sorted(sorted(p) for p in prefs.get("heavy_conflicts") or []),
        "require_modules": sorted(prefs.get("require_modules") or []),
        "forbid_modules": sorted(prefs.get("forbid_modules") or []),
        "deadline": sorted((prefs.get("deadline") or {}).items()),
    }


def spec_diff(pred, gold):
    """Field names where two canonical forms differ (empty = faithful translation)."""
    return [k for k in gold if pred.get(k) != gold[k]]
