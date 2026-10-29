"""Pipeline B (LLM-as-translator) runner (evaluation_plan.md §3.2).

For every benchmark instance the LLM reads the static translator system prompt
(llm/prompts.py, prompt-cached) plus the instance's `nl_prompt` and returns ONLY
a formal spec (llm/spec.py). This harness, not the LLM, then runs the CP-SAT
solver on that spec in-process; the LLM never sees the solver's answer, so it
cannot relax a request until the instance turns SAT (decisions.md D41). The
solver is the proven oracle, so every Pipe B error is a translation error.

Records go to eval/runs/pipe_b/<model>/<instance>.json in the same shape as
Pipe A's (eval/score.py grades both), plus the raw `spec`, `spec_error` and the
`solve` outcome. Existing records are skipped, so an interrupted run resumes.

    python eval/run_pipe_b.py --model haiku --dry-run      # token count, no generation
    python eval/run_pipe_b.py --model haiku --limit 2      # smoke test
    python eval/run_pipe_b.py --model all                  # full sweep
    python eval/run_pipe_b.py --resolve                    # re-solve stored specs (free)
"""
import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from model import load_iter2  # noqa: E402
from solver import build_and_solve_iter2  # noqa: E402
from llm import client as llm  # noqa: E402
from llm.prompts import render_translator_prompt  # noqa: E402
from llm.spec import SpecError, spec_schema, spec_to_formal  # noqa: E402

INST = ROOT / "eval" / "instances"
RUNS = ROOT / "eval" / "runs" / "pipe_b"
MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()
CEIL = PROGRAM.get("max_overload_units")
SCHEMA = spec_schema(MODULES, PROGRAM, FOCUS, PRECL)


def load_instances(only=None):
    files = sorted(p for p in INST.glob("*.json") if p.name != "_index.json")
    insts = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    return [i for i in insts if not only or i["name"] in only]


def solve_spec(spec):
    """Spec -> (prediction, solve_info, spec_error). A cap above the overload
    ceiling is a faithful translation of an unachievable request, so it is
    answered INFEASIBLE (program_cs.yaml assumption) rather than as a spec error."""
    try:
        student, scenario = spec_to_formal(spec, PROGRAM)
    except (SpecError, KeyError, TypeError) as e:
        return None, None, f"{type(e).__name__}: {e}"
    caps = [scenario["max_units_per_semester"],
            *scenario["preferences"]["per_semester_cap"].values()]
    if CEIL and max(caps) > CEIL:
        return ({"feasible": False, "plan": {}, "reason": f"cap above {CEIL} MC ceiling"},
                {"status": "REJECTED_OVER_CEILING", "wall_time_s": 0.0}, None)
    t0 = time.perf_counter()
    try:
        r = build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario)
    except ValueError as e:   # validate_scenario_iter2: term_layout length, clashes, ...
        return None, None, f"ValueError: {e}"
    info = {"status": r.status, "wall_time_s": round(time.perf_counter() - t0, 3),
            "num_variables": r.num_variables, "num_constraints": r.num_constraints}
    if r.status == "UNKNOWN":   # timeout: no verdict (never silently read as UNSAT)
        return None, info, None
    plan = {str(s): ms for s, ms in sorted(r.plan.items())} if r.feasible else {}
    return {"feasible": r.feasible, "plan": plan, "reason": r.status}, info, None


def finish(rec, llm_latency):
    """Fill prediction/solve fields of a record from its stored `spec`."""
    rec["prediction"], rec["solve"], rec["spec_error"] = solve_spec(rec["spec"])
    rec["llm_latency_s"] = llm_latency
    rec["latency_s"] = round(llm_latency + (rec["solve"] or {}).get("wall_time_s", 0.0), 3)
    return rec


def run_one(client, model_key, inst, system, prompt_sha, effort):
    res = llm.call(client, model_key, system, inst["nl_prompt"], SCHEMA, effort=effort)
    rec = {"instance": inst["name"], "pipeline": "B-translator", "condition": "full",
           "model_key": model_key,
           **res.to_dict(), "effort": effort, "prompt_sha256": prompt_sha,
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "spec": None, "spec_error": None, "solve": None,
           "prediction": None, "parse_error": None}
    if res.stop_reason not in ("end_turn", "stop_sequence"):
        rec["parse_error"] = f"stop_reason={res.stop_reason}"
        rec["llm_latency_s"] = res.latency_s
        return rec
    try:
        rec["spec"] = json.loads(res.text)
    except ValueError as e:
        rec["parse_error"] = f"{type(e).__name__}: {e}"
        rec["llm_latency_s"] = res.latency_s
        return rec
    return finish(rec, res.latency_s)


def resolve_all(models):
    """Re-run the solver on every stored spec (after an oracle change); no API calls."""
    for mk in models:
        d = RUNS / mk
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec.get("spec") is not None:
                finish(rec, rec["llm_latency_s"])
                p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        print(f"[{mk}] re-solved stored specs in {d.relative_to(ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="haiku", choices=[*llm.MODELS, "all"])
    ap.add_argument("--only", nargs="*", help="instance names (default: all)")
    ap.add_argument("--limit", type=int, help="first N instances only")
    ap.add_argument("--effort", default=llm.DEFAULT_EFFORT,
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--workers", type=int, default=4, help="parallel requests")
    ap.add_argument("--force", action="store_true", help="re-run instances that have a record")
    ap.add_argument("--dry-run", action="store_true", help="count input tokens only (free)")
    ap.add_argument("--resolve", action="store_true", help="re-solve stored specs only (free)")
    args = ap.parse_args(argv)
    models = list(llm.MODELS) if args.model == "all" else [args.model]
    if args.resolve:
        return resolve_all(models)

    system = render_translator_prompt(MODULES, PROGRAM, FOCUS, PRECL)
    sha = hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]
    insts = load_instances(args.only)[: args.limit]
    client = llm.get_client()

    for mk in models:
        out = RUNS / "-".join([mk] + ([args.effort] if args.effort != llm.DEFAULT_EFFORT else []))
        if args.dry_run:
            n = llm.count_tokens(client, mk, system, insts[0]["nl_prompt"], SCHEMA, args.effort)
            print(f"{mk}: ~{n} input tokens per request (system prompt sha {sha}), "
                  f"{len(insts)} instances")
            continue
        out.mkdir(parents=True, exist_ok=True)
        (out / "_prompt.txt").write_text(system, encoding="utf-8")
        todo = [i for i in insts if args.force or not (out / f"{i['name']}.json").exists()]
        print(f"[{mk}] {len(todo)} to run ({len(insts) - len(todo)} cached) -> {out.relative_to(ROOT)}")
        if not todo:
            continue

        def save(inst):
            rec = run_one(client, mk, inst, system, sha, args.effort)
            (out / f"{inst['name']}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
            pred, err = rec["prediction"], rec["parse_error"] or rec["spec_error"]
            verdict = (f"ERR {err}" if err else "UNKNOWN") if pred is None else \
                ("SAT" if pred["feasible"] else "UNSAT")
            print(f"  {inst['name']:36s} {verdict:10s} {rec['latency_s']:6.1f}s  ${rec['cost_usd']:.4f}"
                  f"  out={rec['usage']['output_tokens']}"
                  f"  cache_read={rec['usage']['cache_read_input_tokens']}")
            return rec

        def safe_save(inst):
            try:
                return save(inst)
            except Exception as e:   # API failure: no record written, so a rerun retries it
                print(f"  {inst['name']:36s} ERROR {type(e).__name__}: {e}")
                return None

        # first request alone so it writes the prompt cache the others then read
        recs = [safe_save(todo[0])]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(safe_save, i) for i in todo[1:]]
            recs += [f.result() for f in as_completed(futs)]
        done = [r for r in recs if r]
        print(f"[{mk}] done {len(done)}/{len(todo)}, cost ${sum(r['cost_usd'] for r in done):.4f}. "
              f"Grade with: python eval/score.py")


if __name__ == "__main__":
    main()
