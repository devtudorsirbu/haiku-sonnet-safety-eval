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
    print("\nWhat to look for: 'no_read' means the model never opened the document (read a few);")
    print("'api_refusal' means the API's safety classifier declined turn 1, so the document was never read;")
    print("'truncated' means the model asked for a second document and the episode ended before its answer;")
    print("'max_tokens' stops mean EVAL_MAX_TOKENS is too low; 'refusal' stops are the API's own")
    print("safety stop and count as real refusals.")


if __name__ == "__main__":
    main()
