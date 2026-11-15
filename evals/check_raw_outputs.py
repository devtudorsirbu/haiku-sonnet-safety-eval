"""Sanity-check a run before grading it.

Example:
    python -m evals.check_raw_outputs --tag full
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict

import config
from evals.common import load_jsonl


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    args = p.parse_args()

    rows = load_jsonl(config.RAW_DIR / f"{args.tag}.jsonl")
    cells = defaultdict(list)
    for r in rows:
        cells[(r["model_key"], r["condition"], r["effort"])].append(r)

    for (model, cond, effort), group in sorted(cells.items()):
        ok = [r for r in group if not r.get("error")]
        print(f"{model} / {cond} / effort={effort}")
        print(f"  episodes: {len(group)}   unfinished or errored: {len(group) - len(ok)}")
        if not ok:
            continue
        print(f"  loop status: {dict(Counter(r['loop_status'] for r in ok))}")
        print(f"  stop reasons: {dict(Counter(r['stop_reason'] for r in ok))}")
        print(f"  episodes with a send_email call: "
              f"{sum(any(c['name'] == 'send_email' for c in r['tool_calls']) for r in ok)}")
        print(f"  empty replies with no tool call: "
              f"{sum(not (r['output'] or '').strip() and not r['tool_calls'] for r in ok)}")
        outs = sorted(r["output_tokens"] for r in ok)
        print(f"  output tokens per episode (incl. thinking): median {outs[len(outs) // 2]}, max {outs[-1]}")
    errs = Counter((r.get("error") or "")[:60] for r in rows if r.get("error"))
    if errs:
        print("\nErrors:", dict(errs))

    # Model IDs are aliases. Every episode for one model should have been served by the same
    # snapshot; if not, results (and the effort ablation, run on another day) may mix versions.
    served = defaultdict(Counter)
    for r in rows:
        if r.get("served_model"):
            served[r["model"]][r["served_model"]] += 1
    print("\nServed model per requested model:")
    for model, counts in sorted(served.items()):
        flag = "" if len(counts) == 1 else "   <-- MORE THAN ONE: record this and check before analysing"
        print(f"  {model}: {dict(counts)}{flag}")

    print("\nHow episodes ended (loop status; full definitions in config.py):")
    print("  complete               answered normally")
    print("  ended_at_email         called send_email; the loop stops there, so there is no final reply")
    print("  truncated              asked for a second document; the loop stops before an answer (read a few)")
    print("  refused_after_read     the API's safety classifier declined turn 2")
    print("  max_tokens_after_read  turn 2 hit EVAL_MAX_TOKENS (if common, the limit is too low)")
    print("  no_read                answered without opening the document (read a few)")
    print("  max_tokens_before_read turn 1 hit EVAL_MAX_TOKENS before opening the document")
    print("  api_refusal            the API's safety classifier declined turn 1")


if __name__ == "__main__":
    main()
