"""Shared grader for every Table-3 row (report §7.1, evaluation_plan.md §5).

Grades each pipeline's per-instance predictions {feasible, plan} the SAME way:
  - feasibility decision vs ground truth (overall, SAT recall, UNSAT T1, UNSAT T2-4)
  - plan validity: on ground-truth-SAT instances, predicted SAT AND the plan
    passes check_plan_iter2 (out of all SAT instances)
  - realism: mean plan_quality.score_plan over VALID plans only
  - time / cost: mean seconds per instance, total USD
  - constraint-violation histogram (checker messages bucketed by rule); codes outside
    the modelled universe are split into real-but-unmodelled AY2026/27 NUS modules
    (NUSMods module_list.json) vs codes NUSMods does not list (hallucinated/retired)
  - lenient plan validity (diagnostic, not a Table-3 column): real-but-unmodelled
    modules re-graded as 4 MC generic electives, so a `bare`-condition plan is not
    failed only for using a real module outside our 129-module universe

Rows: the two non-reasoning controls, the CP-SAT oracle (timed here), and every
run directory under eval/runs/pipe_a/ (eval/run_pipe_a.py). A missing or
unparseable record counts as a wrong decision and an invalid plan.

    python eval/score.py                 # all rows -> console + eval/results/
    python eval/score.py --no-oracle     # skip re-solving the oracle
"""
import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
from model import load_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402
from plan_quality import score_plan  # noqa: E402

INST = ROOT / "eval" / "instances"
RUNS = ROOT / "eval" / "runs" / "pipe_a"
OUT = ROOT / "eval" / "results"
MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()
_LIST = ROOT / "data" / "snapshot_2026-2027" / "module_list.json"
NUS_MODULES = json.loads(_LIST.read_text(encoding="utf-8")) if _LIST.exists() else {}
UE_CODES = PROGRAM["unrestricted_electives"]["candidates"]

MODEL_NAMES = {"haiku": "Haiku 5.5", "sonnet": "Sonnet 5.5", "opus": "Opus 5.5"}

# checker message -> rule family, first match wins (order matters: specific first)
VIOLATION_RULES = [
    ("duplicate", r"scheduled \d+ times"),
    ("retakes completed", r"already satisfied"),
    ("outside horizon", r"outside horizon"),
    ("blocked semester", r"blocked \(per_semester_cap 0\)"),
    ("overload ceiling", r"overload ceiling"),
    ("unit cap", r"units > cap"),
    ("CS-count cap", r"Computing modules > cap"),
    ("min load", r"< min load"),
    ("prerequisite", r"prerequisite"),
    ("offered term", r"not offered in Term"),
    ("same-semester bundle", r"same semester"),
    ("required module", r"required but not satisfied"),
    ("ID/CD", r"^ID/CD"),
    ("preclusion", r"^preclusion"),
    ("focus area", r"^focus area"),
    ("level-4000", r"^level-4000"),
    ("breadth & depth", r"^breadth & depth"),
    ("industrial experience", r"^industrial experience"),
    ("service learning", r"^service learning"),
    ("CP-coded cap", r"^cp-coded"),
    ("total units", r"^total units"),
    ("FYP", r"^FYP"),
    ("UROP", r"^UROP"),
    ("pinned module", r"required \(pinned\)"),
    ("forbidden module", r"^forbidden module"),
    ("deadline", r"deadline"),
    ("heavy conflict", r"share a semester"),
    ("empty-semester gap", r"empty semester"),
    ("ULR group", r"needs \d+ of"),
]


def unknown_kind(code):
    if code.startswith("UE_GENERIC_EXTRA"):
        return "too many generic electives"
    return ("unmodelled real NUS module" if code in NUS_MODULES
            else "not an AY2026/27 NUS module")


def violation_rule(msg):
    if msg.endswith(": unknown module"):
        return unknown_kind(msg.split(":")[0])
    return next((name for name, pat in VIOLATION_RULES if re.search(pat, msg)), "other")


def lenient_check(plan, st, sc, errs):
    """Re-check with real-but-unmodelled modules swapped for free UE placeholders.
    None if the plan has no such module (lenient == strict); False if it also has a
    non-real code or the swap runs out of placeholders."""
    unknown = [e.split(":")[0] for e in errs if e.endswith(": unknown module")]
    if not unknown:
        return None
    if any(unknown_kind(c) != "unmodelled real NUS module" for c in unknown):
        return False
    used = {m for ms in plan.values() for m in ms} | {
        c for c in UE_CODES if st.get("completed", {}).get(c) or st.get("exempted", {}).get(c)}
    free = iter([c for c in UE_CODES if c not in used])
    swapped = {}
    for s, ms in plan.items():
        swapped[s] = []
        for m in ms:
            if m in unknown:
                m = next(free, None)
                if m is None:
                    return False
            swapped[s].append(m)
    return not check_plan_iter2(swapped, MODULES, PROGRAM, st, FOCUS, PRECL, sc)


def load_instances():
    files = sorted(p for p in INST.glob("*.json") if p.name != "_index.json")
    if not files:
        sys.exit("No instances. Run `python eval/generate.py` first.")
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


# --------------------------------------------------------------- predictions
# A prediction is {"feasible": bool, "plan": {sem: [codes]} | None,
#                  "latency_s": float, "cost_usd": float} or None (missing/unparseable).
def baseline_predictions(instances):
    from baselines import canonical_plan
    canon = canonical_plan(instances)
    always = {i["name"]: {"feasible": True, "plan": None, "latency_s": 0.0, "cost_usd": 0.0}
              for i in instances}
    fixed = {i["name"]: {"feasible": True, "plan": canon, "latency_s": 0.0, "cost_usd": 0.0}
             for i in instances}
    return always, fixed


def oracle_predictions(instances):
    from solver import build_and_solve_iter2
    preds = {}
    for i in instances:
        st, sc = i["formal"]["student"], i["formal"]["scenario"]
        t0 = time.perf_counter()
        r = build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, sc)
        preds[i["name"]] = {"feasible": r.feasible, "plan": r.plan if r.feasible else None,
                            "latency_s": time.perf_counter() - t0, "cost_usd": 0.0}
    return preds


def run_predictions(run_dir):
    preds = {}
    for p in sorted(run_dir.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        # an unparseable answer (feasible=None) still costs time and money
        pr = rec.get("prediction") or {"feasible": None, "plan": None}
        preds[rec["instance"]] = {"feasible": pr["feasible"], "plan": pr["plan"],
                                  "latency_s": rec["latency_s"], "cost_usd": rec["cost_usd"]}
    return preds


# --------------------------------------------------------------- grading
def grade_instance(inst, pred):
    gt = inst["ground_truth"]["feasible"]
    row = {"instance": inst["name"], "tier": inst["meta"]["tier"], "gt_feasible": gt,
           "pred_feasible": None if pred is None else pred["feasible"],
           "decision_correct": False, "plan_valid": None, "plan_valid_lenient": None,
           "violations": [], "realism": None,
           "latency_s": None if pred is None else pred["latency_s"],
           "cost_usd": 0.0 if pred is None else pred["cost_usd"]}
    if pred is None or pred["feasible"] is None:
        row["plan_valid"] = row["plan_valid_lenient"] = False if gt else None
        return row
    row["decision_correct"] = pred["feasible"] == gt
    if gt:   # plan validity is judged on ground-truth-SAT instances
        if not pred["feasible"] or not pred["plan"]:
            row["plan_valid"] = row["plan_valid_lenient"] = False
        else:
            st, sc = inst["formal"]["student"], inst["formal"]["scenario"]
            errs = check_plan_iter2(pred["plan"], MODULES, PROGRAM, st, FOCUS, PRECL, sc)
            row["violations"] = errs
            row["plan_valid"] = not errs
            lenient = lenient_check(pred["plan"], st, sc, errs)
            row["plan_valid_lenient"] = row["plan_valid"] if lenient is None else lenient
            if not errs:
                plan = {int(s): ms for s, ms in pred["plan"].items()}
                row["realism"] = score_plan(plan, MODULES, PROGRAM, st, sc)["overall"]
    return row


def frac(n, d):
    return {"n": n, "d": d, "pct": round(100 * n / d, 1) if d else None}


def summarize(label, rows, n_records):
    def sub(pred):
        rs = [r for r in rows if pred(r)]
        return frac(sum(r["decision_correct"] for r in rs), len(rs))
    sat = [r for r in rows if r["gt_feasible"]]
    real = [r["realism"] for r in rows if r["realism"] is not None]
    lat = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    hist = Counter(violation_rule(v) for r in rows for v in r["violations"])
    plans_with = Counter(rule for r in rows
                         for rule in {violation_rule(v) for v in r["violations"]})
    return {
        "pipeline": label,
        "records": n_records, "instances": len(rows),
        "feasibility_accuracy": frac(sum(r["decision_correct"] for r in rows), len(rows)),
        "sat_recall": sub(lambda r: r["gt_feasible"]),
        "unsat_t1_recall": sub(lambda r: r["tier"] == "T1"),
        "unsat_t2_4_recall": sub(lambda r: r["tier"] in ("T2", "T3", "T4")),
        "plan_validity": frac(sum(bool(r["plan_valid"]) for r in sat), len(sat)),
        "plan_validity_lenient": frac(sum(bool(r["plan_valid_lenient"]) for r in sat), len(sat)),
        "realism_mean": round(sum(real) / len(real), 1) if real else None,
        "latency_mean_s": round(sum(lat) / len(lat), 3) if lat else None,
        "cost_total_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "violation_histogram": dict(hist.most_common()),
        "plans_violating_rule": dict(plans_with.most_common()),
    }


def grade_all(label, instances, preds):
    rows = [grade_instance(i, preds.get(i["name"])) for i in instances]
    return summarize(label, rows, len(preds)), rows


# --------------------------------------------------------------- output
def _pct(f, counts=True):
    if f["pct"] is None:
        return "---"
    return f"{f['pct']:.1f}% ({f['n']}/{f['d']})" if counts else f"{f['pct']:.1f}%"


def _time(s):
    t = s["latency_mean_s"]
    t = "---" if t is None else ("<1ms" if t < 1e-3 else f"{t:.2f}s")
    return f"{t} / ${s['cost_total_usd']:.2f}"


def latex_row(s):
    tex = lambda x: x.replace("%", r"\%").replace("$", r"\$").replace("_", r"\_")  # noqa: E731
    real = "---" if s["realism_mean"] is None else f"{s['realism_mean']:.1f}"
    cells = [_pct(s["feasibility_accuracy"]), _pct(s["sat_recall"], False),
             _pct(s["unsat_t1_recall"]), _pct(s["unsat_t2_4_recall"]),
             _pct(s["plan_validity"]), real, "---", _time(s)]
    return rf"\textbf{{{tex(s['pipeline'])}}} & " + " & ".join(tex(c) for c in cells) + r" \\"


def print_table(summaries):
    hdr = ["Pipeline / Model", "Feas.Acc.", "SAT Rec.", "UNSAT T1", "UNSAT T2-4",
           "Plan Valid", "Realism", "Time / Cost"]
    body = [[s["pipeline"], _pct(s["feasibility_accuracy"]), _pct(s["sat_recall"], False),
             _pct(s["unsat_t1_recall"]), _pct(s["unsat_t2_4_recall"]),
             _pct(s["plan_validity"]),
             "---" if s["realism_mean"] is None else f"{s['realism_mean']:.1f}", _time(s)]
            for s in summaries]
    w = [max(len(r[c]) for r in [hdr] + body) for c in range(len(hdr))]
    for r in [hdr] + body:
        print("  ".join(x.ljust(w[c]) for c, x in enumerate(r)))
    for s in summaries:
        if s["records"] < s["instances"]:
            print(f"! {s['pipeline']}: only {s['records']}/{s['instances']} instances have a "
                  f"record; missing ones are scored as wrong.")
        if s["plan_validity_lenient"]["n"] != s["plan_validity"]["n"]:
            print(f"  {s['pipeline']}: plan valid if unmodelled real NUS modules count as "
                  f"generic electives: {_pct(s['plan_validity_lenient'])}")
        if s["plans_violating_rule"]:
            top = ", ".join(f"{k} {v}" for k, v in list(s["plans_violating_rule"].items())[:6])
            print(f"  {s['pipeline']}: plans violating (rule: #plans) {top}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-oracle", action="store_true", help="skip re-solving the oracle row")
    ap.add_argument("--runs", type=Path, default=RUNS, help="dir of Pipe-A run folders")
    args = ap.parse_args(argv)

    instances = load_instances()
    always, fixed = baseline_predictions(instances)
    jobs = [("Control: always-SAT", always), ("Control: canonical-4yr", fixed)]
    order = {k: n for n, k in enumerate(MODEL_NAMES)}
    run_dirs = sorted((d for d in args.runs.glob("*") if d.is_dir()),
                      key=lambda d: (order.get(d.name.split("-")[0], 99), d.name)) \
        if args.runs.exists() else []
    for d in run_dirs:
        base, _, suffix = d.name.partition("-")
        name = MODEL_NAMES.get(base, base) + (f", {suffix}" if suffix else "")
        jobs.append((f"Pipe A: Direct ({name})", run_predictions(d)))
    if not args.no_oracle:
        jobs.append(("Gold Oracle (solve_iter2)", oracle_predictions(instances)))

    summaries, per_instance = [], []
    for label, preds in jobs:
        s, rows = grade_all(label, instances, preds)
        summaries.append(s)
        per_instance += [{"pipeline": label, **r} for r in rows]

    n_sat = sum(i["ground_truth"]["feasible"] for i in instances)
    print(f"Corpus: {len(instances)} instances ({n_sat} SAT, {len(instances) - n_sat} UNSAT)\n")
    print_table(summaries)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "table3.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    (OUT / "table3_rows.tex").write_text("\n".join(latex_row(s) for s in summaries) + "\n",
                                         encoding="utf-8")
    with (OUT / "per_instance.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["pipeline", "instance", "tier", "gt_feasible", "pred_feasible",
                "decision_correct", "plan_valid", "plan_valid_lenient", "realism",
                "latency_s", "cost_usd",
                "n_violations", "violations"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in per_instance:
            w.writerow({**{c: r.get(c) for c in cols}, "n_violations": len(r["violations"]),
                        "violations": " | ".join(r["violations"])})
    print(f"\nWrote {OUT.relative_to(ROOT)}/table3.json, table3_rows.tex, per_instance.csv")


if __name__ == "__main__":
    main()
