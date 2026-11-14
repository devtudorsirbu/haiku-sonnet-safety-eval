"""Report what a run cost, and project the full run from pilot measurements.

Examples:
    python -m evals.estimate_cost --tag pilot --project data/dataset.jsonl
    python -m evals.estimate_cost --tag full --batch

Thinking length varies a lot, so measure it on the pilot rather than trusting
any up-front estimate (including the plan's). Token counts are per episode,
so agent items include both turns.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import config
from evals.common import cost_usd, load_jsonl


def averages(rows, in_f, out_f, key_fn):
    acc = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r.get(in_f) is None:
            continue
        a = acc[key_fn(r)]
        a[0] += 1
        a[1] += r[in_f]
        a[2] += r[out_f]
    return {k: (n, i / n, o / n) for k, (n, i, o) in acc.items()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    p.add_argument("--batch", action="store_true", help="Price the actual run at Batch API rates")
    p.add_argument("--project", default=None, help="Item file to project the cost of, e.g. data/dataset.jsonl")
    p.add_argument("--samples", type=int, default=config.SAMPLES_PER_ITEM)
    args = p.parse_args()

    raw = list({r["custom_id"]: r for r in load_jsonl(config.RAW_DIR / f"{args.tag}.jsonl")}.values())
    scored = list({r["custom_id"]: r for r in load_jsonl(config.SCORED_DIR / f"{args.tag}.jsonl")}.values())

    print(f"Actual usage for '{args.tag}' ({'batch' if args.batch else 'standard'} prices)")
    print(f"{'model':<22}{'episodes':>9}{'avg in':>9}{'avg out':>9}{'cost $':>10}")
    total = 0.0
    eval_avg = averages(raw, "input_tokens", "output_tokens", lambda r: r["model"])
    judge_avg = averages([r for r in scored if r.get("judged")], "judge_input_tokens",
                         "judge_output_tokens", lambda r: config.JUDGE_MODEL)
    for stats in (eval_avg, judge_avg):
        for model, (n, ai, ao) in stats.items():
            c = cost_usd(model, n * ai, n * ao, args.batch)
            total += c
            print(f"{model:<22}{n:>9}{ai:>9.0f}{ao:>9.0f}{c:>10.3f}")
    print(f"{'total':<22}{'':>27}{total:>10.3f}\n")

    if args.project:
        items = load_jsonl(Path(args.project))
        agent = lambda r: r["category"] in config.AGENT_CATEGORIES  # noqa: E731
        per_kind = averages(raw, "input_tokens", "output_tokens", lambda r: (r["model"], agent(r)))
        n_agent = sum(agent(i) for i in items)
        n_chat = len(items) - n_agent
        runs = len(config.CONDITIONS) * args.samples
        print(f"Projection: {len(items)} items ({n_agent} agent, {n_chat} chat) x "
              f"{len(config.CONDITIONS)} conditions x {args.samples} samples, per model")
        std = 0.0
        for model in config.MODELS.values():
            tin = tout = 0.0
            for is_agent, n in ((True, n_agent), (False, n_chat)):
                if (model, is_agent) in per_kind:
                    _, ai, ao = per_kind[(model, is_agent)]
                    tin, tout = tin + n * runs * ai, tout + n * runs * ao
            c = cost_usd(model, tin, tout)
            std += c
            print(f"  {model:<22} ~${c:.2f} standard")
        if config.JUDGE_MODEL in judge_avg:
            _, ai, ao = judge_avg[config.JUDGE_MODEL]
            n = len(items) * runs * len(config.MODELS)
            c = cost_usd(config.JUDGE_MODEL, n * ai, n * ao)
            std += c
            print(f"  {config.JUDGE_MODEL:<22} ~${c:.2f} standard ({n} judgements)")
        print(f"  Total: ~${std:.2f} standard, ~${std * config.BATCH_DISCOUNT:.2f} with the Batch API")


if __name__ == "__main__":
    main()
