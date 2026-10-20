"""Plan-quality evaluator: how *reasonable / realistic* is a valid plan?

The checker (src/checker.py) decides HARD validity — does a plan satisfy every
degree rule. It says nothing about whether a human advisor would actually
recommend the plan: a plan can be perfectly valid yet lopsided (8 MC then 28 MC),
scattered (all GEs dumped in the final semester), or out of order (a level-4000
module in year 1).

This module is the SOFT counterpart: a solver-independent scorer that rates a
valid plan 0-100 on advising-sensible heuristics, with per-metric sub-scores and
human-readable flags. It is NOT a constraint — the CSP stays a pure feasibility
problem (decision D9); this only *judges* a finished plan, so it can score plans
from the solver AND from an LLM on the same footing (a plan-quality axis for the
evaluation, distinct from plan validity).

    python src/plan_quality.py plan.json            # score a plan (iter2 data)

Heuristics are deliberately transparent, not learned; realism is subjective, so
the score is calibrated by ranking (a balanced plan must out-score a degraded
one), not by an absolute ground truth. See docs/plan_quality.md.
"""
import json
import sys
from pathlib import Path
from statistics import pstdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import load_iter2, load_scenario, is_computing  # noqa: E402


def _industrial_mods(program):
    bd = program["breadth_depth"]
    return {m for o in bd["industrial_experience"]["options"] for m in o["set"]}


def _clamp(x):
    return max(0.0, min(1.0, x))


def score_plan(plan, modules, program, student=None, scenario=None):
    """Return {overall: 0..100, metrics: [...], flags: [...]}. Each metric is a
    0..1 sub-score (1 = ideal) with a weight; overall is their weighted mean."""
    plan = {int(s): list(ms) for s, ms in plan.items() if ms}
    industrial = _industrial_mods(program)
    T = (scenario or {}).get("target_semesters") or (max(plan) if plan else 1)
    active = sorted(plan)
    flags = []

    def units(m):
        return modules[m]["units"] if m in modules else 0

    def pillar(m):
        return modules.get(m, {}).get("pillar")

    def level(m):
        return modules.get(m, {}).get("level", 0)

    # academic load per active semester (industrial is off-cap / vacation work)
    load = {s: sum(units(m) for m in plan[s] if m not in industrial) for s in active}

    # 1) workload BALANCE — two failure modes: lumpy (uneven across semesters)
    # AND absurd per-semester loads. Evenness alone would reward cramming
    # everything into a few equal-but-huge semesters, so combine it with a
    # "within a sane cap" term (reference = the requested cap).
    cap_ref = (scenario or {}).get("max_units_per_semester") or 24
    loads = [v for v in load.values() if v > 0]
    if not loads:
        balance = 1.0
    else:
        mean = sum(loads) / len(loads)
        cv = pstdev(loads) / mean if mean else 0
        evenness = _clamp(1 - cv)
        within = sum(1 for v in loads if v <= cap_ref) / len(loads)
        balance = 0.5 * evenness + 0.5 * within
    for s, v in load.items():
        if v > 24:
            flags.append(f"Semester {s}: {v} MC — very heavy")
        elif 0 < v < 12:
            flags.append(f"Semester {s}: only {v} MC — very light")

    # 2) CONTIGUITY — penalise empty semesters between enrolled ones
    if active:
        span = active[-1] - active[0] + 1
        gaps = span - len(active)
        contiguity = 1.0 if gaps == 0 else _clamp(1 - gaps / span)
        if gaps:
            flags.append(f"{gaps} empty semester(s) between enrolled semesters")
    else:
        contiguity = 1.0

    # 3) CS INTENSITY — too many hard (>=3000-level Computing) modules together
    def hard_cs(s):
        return sum(1 for m in plan[s] if is_computing(m) and level(m) >= 3000
                   and m not in industrial)
    intens = []
    for s in active:
        n = hard_cs(s)
        intens.append(1.0 if n <= 3 else _clamp(1 - (n - 3) / 3))
        if n >= 5:
            flags.append(f"Semester {s}: {n} hard CS modules — punishing")
    intensity = sum(intens) / len(intens) if intens else 1.0

    # 4) LEVEL PROGRESSION — advanced (L4000) work belongs in the later half
    l4 = [(m, s) for s in active for m in plan[s] if level(m) >= 4000]
    if l4:
        progression = sum(1 for _, s in l4 if s / T >= 0.4) / len(l4)
        early = [m for m, s in l4 if s <= 2]
        if early:
            flags.append(f"Level-4000 module(s) scheduled very early: {', '.join(sorted(early))}")
    else:
        progression = 1.0

    # 5) FOUNDATION EARLY — core CS foundation belongs in the first half
    found = [(m, s) for s in active for m in plan[s] if pillar(m) == "cs_foundation"]
    foundation_early = (sum(1 for _, s in found if s / T <= 0.5) / len(found)
                        if found else 1.0)

    # 6) BREADTH SPREAD — don't cram all GE/ULR into one semester
    ge = [(m, s) for s in active for m in plan[s]
          if pillar(m) == "university_level_requirements"]
    if len(ge) > 1:
        distinct = len({s for _, s in ge})
        breadth_spread = _clamp(distinct / min(len(ge), len(active)))
        per_sem = {}
        for _, s in ge:
            per_sem[s] = per_sem.get(s, 0) + 1
        for s, c in per_sem.items():
            if c >= 3:
                flags.append(f"Semester {s}: {c} GE/ULR modules clustered together")
    else:
        breadth_spread = 1.0

    # 7) INTERNSHIP / FYP TIMING — experiential work belongs in the later years
    fyp = program["breadth_depth"].get("fyp", {}).get("code")
    exp = [(m, s) for s in active for m in plan[s]
           if m in industrial or m == fyp]
    if exp:
        timing = sum(1 for _, s in exp if s / T >= 0.5) / len(exp)
        early_exp = [m for m, s in exp if s / T < 0.5]
        if early_exp:
            flags.append(f"Internship/FYP scheduled early: {', '.join(sorted(early_exp))}")
    else:
        timing = 1.0

    metrics = [
        ("workload_balance", balance, 0.25),
        ("contiguity", contiguity, 0.15),
        ("cs_intensity", intensity, 0.20),
        ("level_progression", progression, 0.15),
        ("foundation_early", foundation_early, 0.10),
        ("breadth_spread", breadth_spread, 0.10),
        ("experiential_timing", timing, 0.05),
    ]
    overall = round(100 * sum(score * w for _, score, w in metrics), 1)
    return {
        "overall": overall,
        "metrics": [{"name": n, "score": round(s, 2), "weight": w} for n, s, w in metrics],
        "flags": flags,
    }


def format_quality(q):
    lines = [f"Plan reasonableness: {q['overall']}/100"]
    for m in q["metrics"]:
        bar = "#" * int(round(m["score"] * 10))
        lines.append(f"  {m['name']:20s} {m['score']:.2f}  {bar:<10s} (w={m['weight']})")
    if q["flags"]:
        lines.append("  Notes:")
        lines += [f"    - {f}" for f in q["flags"]]
    return "\n".join(lines)


if __name__ == "__main__":
    modules, program, student, focus, precl = load_iter2()
    scenario = load_scenario(Path(__file__).resolve().parents[1] / "data" / "scenario_iter2.yaml")
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(format_quality(score_plan(plan, modules, program, student, scenario)))
