"""Instance generator for the iter3 benchmark (benchmark_design.md B8 / evaluation_plan.md §2.3).

For every formal instance (a benchmark profile = student + request) it emits the
evaluation quadruple
    { nl_prompt, formal, ground_truth, meta }
to eval/instances/<name>.json, with ground truth from the frozen oracle and
MEASURED difficulty (near-UNSAT margins + model size; NOT CP-SAT solve time as
an LLM-difficulty axis, per B6). Ground truth is generated FROM the formal
instance, never the reverse, so it is exact.

    python eval/generate.py            # (re)generate all instances
    python eval/generate.py --summary  # print the index table only
"""
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2, load_yaml  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from plan_quality import score_plan  # noqa: E402

OUT = ROOT / "eval" / "instances"
MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()
CEIL = int(PROGRAM.get("max_overload_units", 28))

FOCUS_LABELS = {"any": "any focus area"}


def solve(student, scenario):
    return build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario)


# A fresh on-track student + request builders, for the synthetic stress slice
# (UNSAT tiers + near-boundary SAT) that the profile diagonal under-covers.
BASE_STUDENT = {"conditions": {"needs_math_bridging": False, "english_path": "direct_es2660"},
                "has_h2_math": True, "eligible_fyp": False, "eligible_urop": True,
                "completed": {}, "exempted": {}}
BASE_PREFS = {"per_semester_cap": {}, "max_cs_modules_per_sem": 0, "min_units_per_semester": 0,
              "no_empty_semesters": False, "heavy_conflicts": [], "require_modules": [],
              "forbid_modules": [], "deadline": {}}


def req(T=8, cap=20, focus="any", **over):
    sc = {"target_semesters": T, "max_units_per_semester": cap, "focus_area": focus,
          "industrial_option": "any", "want_fyp": False, "want_urop": False,
          "preferences": {**BASE_PREFS, **over.pop("preferences", {})}}
    sc.update(over)
    return sc


def stu(**over):
    s = copy.deepcopy(BASE_STUDENT)
    s.update(over)
    return s


# name -> (label, description, expect, student, scenario). Chosen to add the
# UNSAT tiers (benchmark_design.md B4) + near-boundary SAT (B5) the diagonal lacks.
STRESS = {
    # --- UNSAT T1: arithmetic floor (capacity < 160) --------------------------
    "unsat_t1_5sem": ("UNSAT T1: 5-semester floor",
        "Fresh student asking for 5 semesters at 20 MC (100 MC < 160) — below the arithmetic floor.",
        "infeasible", stu(), req(T=5, cap=20)),
    "unsat_t1_4sem_overload": ("UNSAT T1: 4 semesters even maxed out",
        "Four semesters at the 28 MC overload ceiling is still only 112 MC — cannot reach 160.",
        "infeasible", stu(), req(T=4, cap=28)),
    "unsat_t1_7sem_standard": ("UNSAT T1: 7 semesters at standard load",
        "Seven semesters at 20 MC is 140 MC — a common 'can I finish in 3.5 years at normal load?' miss.",
        "infeasible", stu(), req(T=7, cap=20)),
    "unsat_t1_6sem_cap25": ("UNSAT T1: 6 semesters at 25 MC",
        "Six semesters at 25 MC is 150 MC — just short of 160.",
        "infeasible", stu(), req(T=6, cap=25)),
    "unsat_t1_two_blocked": ("UNSAT T1: two blocked semesters",
        "An 8-semester plan with two fully-blocked semesters leaves only 6 usable (120 MC) — infeasible.",
        "infeasible", stu(), req(T=8, cap=20, preferences={"per_semester_cap": {1: 0, 2: 0}})),
    # --- UNSAT T2: bin-packing residue (capacity >= 160 but still UNSAT) -------
    "unsat_t2_6sem_cap27": ("UNSAT T2: bin-packing residue",
        "Six semesters at 27 MC gives 162 MC nominal capacity but is infeasible once 4-MC granularity "
        "and single-semester offerings are respected.",
        "infeasible", stu(), req(T=6, cap=27)),
    # --- UNSAT T4: policy / interaction (fine print) --------------------------
    "unsat_t4_offering_lock": ("UNSAT T4: offering-window lock",
        "Insists on taking CS2108 (a Term-2-only module) by semester 1 (a Term-1 slot) — impossible.",
        "infeasible", stu(), req(T=9, preferences={"require_modules": ["CS2108"],
                                                   "deadline": {"CS2108": 1}})),
    "unsat_t4_forbid_required": ("UNSAT T4: forbidding a required module",
        "Refuses to take CS2100 (Computer Organisation), which is a required core module.",
        "infeasible", stu(), req(T=9, preferences={"forbid_modules": ["CS2100"]})),
    "unsat_t4_forbid_two_core": ("UNSAT T4: forbidding two core modules",
        "Wants to avoid both CS2100 and CS2103T — both are required, so no plan exists.",
        "infeasible", stu(), req(T=9, preferences={"forbid_modules": ["CS2100", "CS2103T"]})),
    "unsat_t4_ineligible_fyp": ("UNSAT T4: FYP without eligibility",
        "A student who is not GPA-eligible insists on doing the CP4101 dissertation.",
        "infeasible", stu(eligible_fyp=False), req(T=9, want_fyp=True)),
    "unsat_t4_cs_starved": ("UNSAT T4: CS-count cap too tight",
        "Limits CS/IFS/CP modules to 1 per semester over 8 semesters — far too few slots for the CS core.",
        "infeasible", stu(), req(T=8, cap=20, preferences={"max_cs_modules_per_sem": 1})),
    "unsat_t4_deadline_prereq": ("UNSAT T4: deadline beneath prereq depth",
        "Wants CS3230 done by semester 2, but its chain (CS1101S -> CS2040S -> CS3230) needs 3 ordered "
        "semesters — structurally impossible.",
        "infeasible", stu(), req(T=9, preferences={"deadline": {"CS3230": 2}})),
    "unsat_t4_tight_focus_overload_block": ("UNSAT T4: blocked term under a tight overload horizon",
        "Seven-semester overload (26 MC) but with one semester fully blocked — drops below 160.",
        "infeasible", stu(), req(T=7, cap=26, preferences={"per_semester_cap": {4: 0}})),
    "unsat_t1_6sem_cap26": ("UNSAT T1: 6 semesters at 26 MC",
        "Six semesters at 26 MC is 156 MC — four short of the 160 MC degree.",
        "infeasible", stu(), req(T=6, cap=26)),
    "unsat_t4_forbid_three_core": ("UNSAT T4: forbidding three core modules",
        "Wants to skip CS2100, CS2103T and CS2040S — all required, so the degree is unsatisfiable.",
        "infeasible", stu(), req(T=9, preferences={"forbid_modules": ["CS2100", "CS2103T", "CS2040S"]})),
    # --- near-boundary SAT (forced placement, zero slack) ---------------------
    "nearbnd_min_horizon": ("Near-boundary: minimum horizon",
        "Fresh student at the exact 8-semester floor, 20 MC cap — zero slack, every placement forced.",
        "feasible", stu(), req(T=8, cap=20, focus="artificial_intelligence")),
    "nearbnd_overload_floor": ("Near-boundary: 7-semester overload",
        "Early graduation in 7 semesters, overloading to 26 MC — just feasible.",
        "feasible", stu(), req(T=7, cap=26, focus="computer_security")),
}


def _feasible(student, scenario, **over):
    sc = copy.deepcopy(scenario)
    sc.update(over)
    # term_layout length must track target_semesters; drop it when probing T
    if "target_semesters" in over and "term_layout" in sc:
        sc.pop("term_layout")
    try:
        return solve(student, sc).feasible
    except ValueError:
        return False


# ---------------------------------------------------------------- difficulty
def measure_difficulty(student, scenario, base):
    """Solver-emitted, per-instance (B6). Near-UNSAT margin = how far the request
    can be tightened before it flips; small margin => binding/hard."""
    T = scenario["target_semesters"]
    cap = scenario["max_units_per_semester"]
    d = {"num_variables": base.num_variables, "num_constraints": base.num_constraints,
         "wall_time_s": round(base.wall_time_s, 3)}
    has_layout = bool(scenario.get("term_layout"))
    if base.feasible:
        # slack: largest tightening still feasible
        min_T = T
        if not has_layout:
            for t in range(T - 1, 0, -1):
                if _feasible(student, scenario, target_semesters=t):
                    min_T = t
                else:
                    break
        min_cap = cap
        for c in range(cap - 1, 3, -1):
            if _feasible(student, scenario, max_units_per_semester=c):
                min_cap = c
            else:
                break
        d["min_feasible_semesters"] = min_T
        d["semester_slack"] = T - min_T          # 0 => horizon is binding (hard)
        d["min_feasible_cap"] = min_cap
        d["cap_slack"] = cap - min_cap            # 0 => unit cap is binding (hard)
        d["near_unsat_margin"] = min(T - min_T, cap - min_cap)
    else:
        # distance to feasibility: smallest relaxation that flips SAT
        dT = next((t - T for t in range(T + 1, T + 7)
                   if _feasible(student, scenario, target_semesters=t)), None)
        dCap = next((c - cap for c in range(cap + 1, CEIL + 1)
                     if _feasible(student, scenario, max_units_per_semester=c)), None)
        d["extra_semesters_to_feasible"] = dT
        d["extra_cap_to_feasible"] = dCap
        d["near_unsat_margin"] = 0                # it IS unsat
    return d


# ---------------------------------------------------------------- tags
def coverage_tags(student, scenario, feasible):
    prefs = scenario.get("preferences", {}) or {}
    tags = ["C-base", "C-order", "C-acct"]        # always exercised
    if scenario.get("focus_area", "any") != "any":
        tags.append("C-depth")
    if (scenario.get("industrial_option", "any") != "any" or scenario.get("want_fyp")
            or scenario.get("want_urop") or student.get("completed") or student.get("exempted")):
        tags.append("C-compl")
    if any(prefs.get(k) for k in ("per_semester_cap", "max_cs_modules_per_sem",
                                   "require_modules", "forbid_modules", "deadline",
                                   "heavy_conflicts", "min_units_per_semester")) \
            or scenario.get("term_layout"):
        tags.append("C-pref")
    if not feasible:
        tags.append("C-unsat")
    return tags


# ---------------------------------------------------------------- NL draft
def nl_draft(label, description, student, scenario):
    """Deterministic English draft FROM the formal instance. Marked auto-draft;
    the real corpus prose is hand-authored per B7 (variety/implicitness)."""
    sc = scenario
    lines = [description.rstrip(".") + "."]
    ask = [f"graduate within {sc['target_semesters']} semesters",
           f"take at most {sc['max_units_per_semester']} MC per semester"]
    if sc.get("focus_area", "any") != "any":
        ask.append(f"specialise in {sc['focus_area'].replace('_',' ')}")
    if sc.get("industrial_option", "any") != "any":
        ask.append(f"do the {sc['industrial_option']} internship option")
    if sc.get("want_fyp"):
        ask.append("do a final-year project (CP4101)")
    if sc.get("want_urop"):
        ask.append("do a UROP research project")
    prefs = sc.get("preferences", {}) or {}
    for s, u in (prefs.get("per_semester_cap", {}) or {}).items():
        ask.append(f"keep semester {s} {'blocked (no modules)' if u == 0 else f'under {u} MC'}")
    if prefs.get("require_modules"):
        ask.append("be sure to take " + ", ".join(prefs["require_modules"]))
    if prefs.get("forbid_modules"):
        ask.append("avoid " + ", ".join(prefs["forbid_modules"]))
    for c, by in (prefs.get("deadline", {}) or {}).items():
        ask.append(f"finish {c} by semester {by}")
    lines.append("I want to " + "; ".join(ask) + ".")
    lines.append("Can it be done, and if so what is my semester-by-semester plan?")
    return " ".join(lines)


# ---------------------------------------------------------------- build
def build_instance(name, p):
    student, scenario = p["student"], p["scenario"]
    r = solve(student, scenario)
    gt = {"feasible": r.feasible, "status": r.status}
    quality = None
    if r.feasible:
        gt["plan"] = {str(s): ms for s, ms in r.plan.items() if ms}
        gt["total_units"] = sum(MODULES[m]["units"] for ms in r.plan.values() for m in ms)
        q = score_plan(r.plan, MODULES, PROGRAM, student, scenario)
        quality = {"realism": q["overall"], "flags": q["flags"]}
    diff = measure_difficulty(student, scenario, r)
    if not r.feasible:
        dT, dC = diff.get("extra_semesters_to_feasible"), diff.get("extra_cap_to_feasible")
        bits = []
        if dT:
            bits.append(f"needs {scenario['target_semesters']+dT} semesters")
        if dC:
            bits.append(f"or a cap of {scenario['max_units_per_semester']+dC} MC")
        gt["reason"] = ("infeasible: " + "; ".join(bits)) if bits else "infeasible under any simple relaxation"
    return {
        "name": name,
        "declared_expect": p["expect"],
        "nl_prompt": nl_draft(p["label"], p["description"], student, scenario),
        "prompt_source": "auto-draft",
        "formal": {"student": student, "scenario": scenario},
        "ground_truth": gt,
        "meta": {"label": p["label"], "tags": coverage_tags(student, scenario, r.feasible),
                 "difficulty": diff, "quality": quality},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary", action="store_true", help="print the index only, don't write")
    args = ap.parse_args(argv)
    profiles = load_yaml(ROOT / "data" / "profiles" / "benchmark_profiles.yaml")
    # merge the synthetic stress slice (UNSAT tiers + near-boundary) into the corpus
    for name, (label, desc, expect, student, scenario) in STRESS.items():
        profiles[name] = {"label": label, "description": desc, "expect": expect,
                          "student": student, "scenario": scenario}
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.summary:   # prune stale instance files so the dir is authoritative
        keep = {f"{n}.json" for n in profiles} | {"_index.json"}
        for f in OUT.glob("*.json"):
            if f.name not in keep:
                f.unlink()
    index = []
    for name, p in profiles.items():
        inst = build_instance(name, p)
        if not args.summary:
            (OUT / f"{name}.json").write_text(json.dumps(inst, indent=2), encoding="utf-8")
        d = inst["meta"]["difficulty"]
        ok = inst["ground_truth"]["feasible"] == (p["expect"] == "feasible")
        index.append({"name": name, "expect": p["expect"],
                      "feasible": inst["ground_truth"]["feasible"], "ok": ok,
                      "margin": d.get("near_unsat_margin"),
                      "tags": inst["meta"]["tags"]})
    if not args.summary:
        (OUT / "_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"{'instances':26s} expect     SAT  margin  tags")
    for r in index:
        flag = "" if r["ok"] else "  <-- MISMATCH"
        print(f"{r['name']:26s} {r['expect']:10s} {str(r['feasible'])[:1]}    "
              f"{str(r['margin']):>5s}   {','.join(t for t in r['tags'] if t!='C-base')}{flag}")
    n_feas = sum(r["feasible"] for r in index)
    n_bad = sum(not r["ok"] for r in index)
    print(f"\n{len(index)} instances  |  {n_feas} feasible ({n_feas/len(index):.0%}), "
          f"{len(index)-n_feas} infeasible  |  {n_bad} mismatch(es)"
          + ("" if args.summary else f"  |  written to {OUT.relative_to(ROOT)}/"))


if __name__ == "__main__":
    main()
