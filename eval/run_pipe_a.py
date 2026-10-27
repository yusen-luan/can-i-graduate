"""Pipeline A (LLM-direct) runner (evaluation_plan.md §3.1).

For every benchmark instance it sends the static rules+catalog system prompt
(llm/prompts.py, prompt-cached) plus the instance's `nl_prompt`, and stores the
raw answer, parsed plan, usage, latency and $ to
    eval/runs/pipe_a/<model>/<instance>.json
Grading is NOT done here (eval/score.py does it), so records can be re-graded
for free. Existing records are skipped, so an interrupted run just resumes.

    python eval/run_pipe_a.py --model haiku --dry-run      # token count, no generation
    python eval/run_pipe_a.py --model haiku --limit 2      # smoke test
    python eval/run_pipe_a.py --model all                  # full sweep
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from model import load_iter2  # noqa: E402
from llm import client as llm  # noqa: E402
from llm.prompts import PLAN_SCHEMA, render_system_prompt, parse_response, bind_electives  # noqa: E402

INST = ROOT / "eval" / "instances"
RUNS = ROOT / "eval" / "runs" / "pipe_a"
MODULES, PROGRAM, _, FOCUS, PRECL = load_iter2()


def load_instances(only=None):
    files = sorted(p for p in INST.glob("*.json") if p.name != "_index.json")
    insts = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    return [i for i in insts if not only or i["name"] in only]


def run_one(client, model_key, inst, system, prompt_sha, effort):
    res = llm.call(client, model_key, system, inst["nl_prompt"], PLAN_SCHEMA, effort=effort)
    rec = {"instance": inst["name"], "pipeline": "A-direct", "model_key": model_key,
           **res.to_dict(), "effort": effort, "prompt_sha256": prompt_sha,
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "prediction": None, "parse_error": None}
    if res.stop_reason not in ("end_turn", "stop_sequence"):
        rec["parse_error"] = f"stop_reason={res.stop_reason}"
    else:
        try:
            p = parse_response(res.text)
            st = inst["formal"]["student"]
            p["plan"] = {str(s): ms for s, ms in sorted(bind_electives(
                p["plan"], st, PROGRAM["unrestricted_electives"]["candidates"]).items())}
            rec["prediction"] = p
        except (ValueError, KeyError, TypeError) as e:
            rec["parse_error"] = f"{type(e).__name__}: {e}"
    return rec


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
    args = ap.parse_args(argv)

    system = render_system_prompt(MODULES, PROGRAM, FOCUS, PRECL)
    sha = hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]
    insts = load_instances(args.only)[: args.limit]
    client = llm.get_client()
    models = list(llm.MODELS) if args.model == "all" else [args.model]

    for mk in models:
        out = RUNS / mk if args.effort == llm.DEFAULT_EFFORT else RUNS / f"{mk}-{args.effort}"
        if args.dry_run:
            n = llm.count_tokens(client, mk, system, insts[0]["nl_prompt"], PLAN_SCHEMA, args.effort)
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
            pred = rec["prediction"]
            verdict = ("PARSE-ERR " + rec["parse_error"]) if pred is None else \
                ("SAT" if pred["feasible"] else "UNSAT")
            print(f"  {inst['name']:36s} {verdict:10s} {rec['latency_s']:6.1f}s  ${rec['cost_usd']:.4f}"
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
