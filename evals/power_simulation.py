"""Power of the primary test (H1), simulated from the pilot's baseline attack success.

Examples:
    python -m evals.power_simulation --tag pilot
    python -m evals.power_simulation --rates 0.5 0.4 0.2 0.1 0 0 0 0 0 0

No API calls. Takes a minute or two.

For each model, the pilot's baseline success rate per attack is estimated from its
injected episodes. The full run has 10 attacks, so the simulation draws 10 attack rates
from the observed ones (with replacement), varies them across the 8 carrier documents,
draws 2 samples per cell at baseline and with the mitigation removing a given share of
attacks, and runs the same crossed bootstrap as analyze_results. Power is the share of
simulated studies whose interval lies entirely below zero.

The pilot covers only 5 attacks on 2 documents with 1 sample, so treat the result as a
rough guide. It assumes the unseen attacks behave like the seen ones and that the
mitigation removes the same share of every attack.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import config
from evals import analyze_results as ar
from evals.common import load_jsonl

IDS = [f"c{c:02d}_a{a:02d}" for c in range(1, 9) for a in range(1, 11)]


def pilot_rates(tag: str) -> dict[str, pd.Series]:
    """Baseline success rate per attack, per model, from scored episodes that read the document."""
    rows = [r for r in load_jsonl(config.SCORED_DIR / f"{tag}.jsonl")
            if r.get("category") == "injected" and r.get("condition") == "baseline"
            and r.get("loop_status") in config.READ_STATUSES and r.get("effort") == config.EVAL_EFFORT]
    if not rows:
        raise SystemExit(f"No scored baseline injected episodes in results/scored/{tag}.jsonl")
    df = pd.DataFrame(rows)
    df["attack_id"] = df["attack"].map(lambda a: a["id"])
    obj = df["attack_success_objective"]
    judged = df["followed_injection"].isin(["yes", "partial"])
    df["success"] = [bool(o) if o is not None and not pd.isna(o) else j for o, j in zip(obj, judged)]
    return {m: g.groupby("attack_id")["success"].agg(["mean", "size"]) for m, g in df.groupby("model_key")}


def power(observed: np.ndarray, keep: float, rng, reps: int, carrier_sd: float = 0.3) -> tuple[float, float, float]:
    """Returns (true effect, power, mean interval width)."""
    hits, widths, effects = 0, [], []
    for _ in range(reps):
        pa = rng.choice(observed, size=10, replace=True)
        mult = np.exp(rng.normal(0, carrier_sd, 8))
        mult /= mult.mean()
        p = np.clip(mult[:, None] * pa[None, :], 0, 1)
        base = rng.binomial(2, p) / 2
        mit = rng.binomial(2, keep * p) / 2
        effects.append((keep - 1) * p.mean())
        _, lo, hi = ar.crossed_bootstrap(pd.Series((mit - base).ravel(), index=IDS), rng)
        hits += hi < 0
        widths.append(hi - lo)
    return float(np.mean(effects)), hits / reps, float(np.mean(widths))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", help="Scored run to estimate baseline rates from, e.g. pilot")
    p.add_argument("--rates", nargs="+", type=float, help="Baseline success rates per attack, instead of --tag")
    p.add_argument("--keep", nargs="+", type=float, default=[0.75, 0.5, 0.25, 0.0],
                   help="Share of baseline success that survives the mitigation")
    p.add_argument("--reps", type=int, default=300)
    p.add_argument("--n-boot", type=int, default=1000)
    args = p.parse_args()
    if not (args.tag or args.rates):
        raise SystemExit("Give --tag or --rates.")

    ar.N_BOOT = args.n_boot
    rng = np.random.default_rng(20261115)
    if args.rates:
        rates = {"given": np.array(args.rates)}
    else:
        rates = {}
        for model, tab in pilot_rates(args.tag).items():
            print(f"\n{model}: baseline success per attack (episodes): " +
                  ", ".join(f"{a} {r['mean']:.0%} ({int(r['size'])})" for a, r in tab.iterrows()))
            rates[model] = tab["mean"].to_numpy()
    for model, observed in rates.items():
        works = int((observed > 0).sum())
        print(f"\n{model}: mean baseline success {observed.mean():.0%}; "
              f"{works} of {len(observed)} attacks succeeded at least once")
        if works == 0:
            print("  No attack succeeded, so there is nothing for the mitigation to reduce: power is 0.")
            continue
        print(f"  {'mitigation removes':>20} {'true effect':>12} {'power':>7} {'interval width':>15}")
        for keep in args.keep:
            eff, pw, width = power(observed, keep, rng, args.reps)
            print(f"  {1 - keep:>20.0%} {eff * 100:>+10.1f}pp {pw:>7.0%} {width * 100:>13.0f}pp")
    print("\nAim for at least 80% power at the smallest effect you would care about. If no row reaches it,"
          "\nthe full run cannot answer H1 as designed: make the attacks stronger before Day 3, or"
          "\npre-register that a null result will be reported as inconclusive at this size.")


if __name__ == "__main__":
    main()
