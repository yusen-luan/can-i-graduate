"""Author + validate the A9-A19 benchmark archetypes (benchmark_design.md B2).

Each profile must resolve to its declared `expect`; feasible ones must pass the
independent checker; UNSAT ones get an A4 mechanism check (relax the stated
binding constraint -> must flip SAT). Prints a report and, if all pass, dumps a
YAML block ready to append to data/profiles/benchmark_profiles.yaml.
"""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

MODULES, PROGRAM, STUDENT0, FOCUS, PRECL = load_iter2()

BASE_STUDENT = {
    "conditions": {"needs_math_bridging": False, "english_path": "direct_es2660"},
    "has_h2_math": True, "eligible_fyp": False, "eligible_urop": True,
    "completed": {}, "exempted": {},
}
BASE_PREFS = {"per_semester_cap": {}, "max_cs_modules_per_sem": 0,
              "min_units_per_semester": 0, "no_empty_semesters": False,
              "heavy_conflicts": [], "require_modules": [], "forbid_modules": [],
              "deadline": {}}


def mk_student(**over):
    s = copy.deepcopy(BASE_STUDENT)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k] = {**s[k], **v}
        else:
            s[k] = v
    return s


def mk_scenario(**over):
    s = {"target_semesters": 8, "max_units_per_semester": 20,
         "focus_area": "artificial_intelligence", "industrial_option": "any",
         "want_fyp": False, "want_urop": False,
         "preferences": copy.deepcopy(BASE_PREFS)}
    prefs = over.pop("preferences", {})
    s.update(over)
    s["preferences"].update(prefs)
    return s


def solve(student, scenario):
    return build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario)


# derive an "almost done" student: complete the first 6 semesters of a real plan
def derive_almost_done():
    r = solve(mk_student(), mk_scenario())
    done = {m: True for s in range(1, 7) for m in r.plan.get(s, [])}
    return done


ALMOST = derive_almost_done()

PROFILES = {
    "mid_degree_y2": dict(
        label="Mid-degree check-in (Year 2/3)",
        description="Done the CS foundation + a few GE pillars; wants to confirm the rest fits in 4 years.",
        expect="feasible",
        student=mk_student(completed={m: True for m in
            ["CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "MA1521",
             "MA1522", "ST2334", "ES2660", "GEA1000"]}),
        scenario=mk_scenario(target_semesters=8, focus_area="artificial_intelligence")),

    "final_year_audit": dict(
        label="Final-year audit (almost done)",
        description="Has cleared the first three years; checking the last two semesters complete the degree.",
        expect="feasible",
        student=mk_student(completed=ALMOST),
        scenario=mk_scenario(target_semesters=8, focus_area="artificial_intelligence")),

    "behind_retaking": dict(
        label="Behind / retaking a core module",
        description="Failed CS2040S and is a semester behind; needs a 9-semester plan to recover.",
        expect="feasible",
        student=mk_student(completed={m: True for m in ["CS1101S", "CS1231S", "MA1521"]}),
        scenario=mk_scenario(target_semesters=9, focus_area="algorithms_theory")),

    "preclusion_deadend": dict(
        label="Preclusion dead-end (CS1010 without credit transfer)",
        description="Holds CS1010 from a prior course (precludes CS1101S) but it was not exempted, so the "
                    "required CS1101S cannot be taken — infeasible until the credit is formally recognised.",
        expect="infeasible",
        student=mk_student(completed={"CS1010": True}),
        scenario=mk_scenario(target_semesters=9)),

    "over_credited": dict(
        label="Over-credited (many exemptions, unit shortfall)",
        description="Arrives with large advanced-placement exemptions (no units), so the plan must backfill "
                    "unrestricted electives to reach 160 MC.",
        expect="feasible",
        student=mk_student(exempted={m: True for m in
            ["CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "MA1521", "MA1522"]}),
        scenario=mk_scenario(target_semesters=8)),

    "two_internships": dict(
        label="Two 3-month internships",
        description="Prefers two shorter internships (CP3200 + CP3202) over one 6-month stint; SE focus.",
        expect="feasible",
        student=mk_student(),
        scenario=mk_scenario(target_semesters=9, focus_area="software_engineering",
                             industrial_option="CP3200")),

    "fyp_urop_trap": dict(
        label="FYP + UROP (CP-cap trap)",
        description="GPA-eligible student wants BOTH a CP4101 dissertation and a UROP — infeasible because "
                    "CP4101 alone fills the 12 MC CP-coded cap.",
        expect="infeasible",
        student=mk_student(eligible_fyp=True),
        scenario=mk_scenario(target_semesters=9, want_fyp=True, want_urop=True)),

    "deep_focus_pinned": dict(
        label="Deep focus with a pinned module",
        description="Algorithms & Theory focus, insists on taking CS3230 and finishing CS2040S by semester 3.",
        expect="feasible",
        student=mk_student(),
        scenario=mk_scenario(target_semesters=9, focus_area="algorithms_theory",
                             preferences={"require_modules": ["CS3230"],
                                          "deadline": {"CS2040S": 3}})),

    "leave_of_absence": dict(
        label="Leave of absence (blocked semester)",
        description="Takes one semester off (no modules), stretching the plan to 9 semesters.",
        expect="feasible",
        student=mk_student(),
        scenario=mk_scenario(target_semesters=9,
                             preferences={"per_semester_cap": {5: 0}})),

    "focus_switch": dict(
        label="Focus switch mid-degree",
        description="Took Computer-Security electives early, then switched to an AI focus; the security "
                    "modules still count toward Breadth & Depth and the 160 MC total.",
        expect="feasible",
        student=mk_student(completed={m: True for m in ["CS2107", "CS3235"]}),
        scenario=mk_scenario(target_semesters=9, focus_area="artificial_intelligence")),
}

# A4 relax-and-flip for the UNSAT profiles: (name -> relaxation function)
RELAX = {
    "preclusion_deadend": lambda s, sc: (mk_student(completed={"CS1010": True},
                                                    exempted={"CS1101S": True}), sc),
    "fyp_urop_trap": lambda s, sc: (s, {**sc, "want_urop": False}),
}


def main():
    ok = True
    for name, p in PROFILES.items():
        r = solve(p["student"], p["scenario"])
        got = "feasible" if r.feasible else "infeasible"
        tag = "OK" if got == p["expect"] else "MISMATCH"
        extra = ""
        if r.feasible:
            v = check_plan_iter2(r.plan, MODULES, PROGRAM, p["student"], FOCUS, PRECL, p["scenario"])
            extra = "checker-clean" if not v else f"CHECKER FAIL: {v[:2]}"
            if v:
                tag = "MISMATCH"
        elif name in RELAX:
            st2, sc2 = RELAX[name](p["student"], p["scenario"])
            flip = solve(st2, sc2)
            extra = "A4 relax->SAT OK" if flip.feasible else "A4 relax STILL UNSAT (wrong mechanism!)"
            if not flip.feasible:
                tag = "MISMATCH"
        if tag != "OK":
            ok = False
        print(f"[{tag}] {name:20s} expect={p['expect']:10s} got={got:10s} {extra}")

    if ok:
        print("\nALL PASS. YAML block:\n")
        out = {name: {"label": p["label"], "description": p["description"],
                      "expect": p["expect"], "student": p["student"],
                      "scenario": p["scenario"]}
               for name, p in PROFILES.items()}
        print(yaml.safe_dump(out, sort_keys=False, default_flow_style=False, width=100))
    else:
        print("\nFIX MISMATCHES before writing YAML.")
        sys.exit(1)


if __name__ == "__main__":
    main()
