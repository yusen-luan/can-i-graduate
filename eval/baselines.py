"""Non-reasoning baselines over the generated benchmark (benchmark_design.md B8 / #7).

A frontier-model accuracy number is uninterpretable on a deliberately
stress-weighted corpus without knowing what trivial strategies already score.
Two controls, graded exactly like the LLM pipelines (feasibility decision +
plan validity via check_plan_iter2):

  always-SAT        : predict every instance feasible, output no plan.
  canonical-4yr     : predict feasible + reuse ONE fixed 4-year plan for everyone.

Run eval/generate.py first. Then:  python eval/baselines.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

INST = ROOT / "eval" / "instances"
MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()


def load_instances():
    files = sorted(p for p in INST.glob("*.json") if p.name != "_index.json")
    if not files:
        sys.exit("No instances. Run `python eval/generate.py` first.")
    return [json.loads(p.read_text()) for p in files]


def canonical_plan(instances):
    for i in instances:
        if i["name"] == "on_track_fresh" and i["ground_truth"]["feasible"]:
            return {int(s): ms for s, ms in i["ground_truth"]["plan"].items()}
    return {}


def score(instances):
    n = len(instances)
    canon = canonical_plan(instances)
    rows = []
    for strat in ("always-SAT", "canonical-4yr"):
        feas_correct = plan_valid = n_feasible = 0
        for i in instances:
            actual = i["ground_truth"]["feasible"]
            n_feasible += actual
            pred_feasible = True                      # both baselines always say SAT
            if pred_feasible == actual:
                feas_correct += 1
            if strat == "canonical-4yr" and actual:
                st, sc = i["formal"]["student"], i["formal"]["scenario"]
                if check_plan_iter2(canon, MODULES, PROGRAM, st, FOCUS, PRECL, sc) == []:
                    plan_valid += 1
        rows.append((strat, feas_correct, n, plan_valid, n_feasible))
    return rows, n


def main():
    instances = load_instances()
    rows, n = score(instances)
    n_feas = sum(i["ground_truth"]["feasible"] for i in instances)
    print(f"Corpus: {n} instances ({n_feas} feasible, {n - n_feas} infeasible)\n")
    print(f"{'baseline':16s} feasibility-decision   plan-valid (of feasible)")
    for strat, fc, tot, pv, nf in rows:
        pvstr = f"{pv}/{nf} = {pv/nf:.0%}" if strat == "canonical-4yr" else "n/a (no plan)"
        print(f"{strat:16s} {fc}/{tot} = {fc/tot:4.0%}          {pvstr}")
    print("\nReading: always-SAT's feasibility accuracy is just the feasible-fraction of the\n"
          "corpus (the floor any 'always feasible' guesser hits). canonical-4yr shows a fixed\n"
          "plan does NOT generalise across students/requests -> a real planner must reason.")


if __name__ == "__main__":
    main()
