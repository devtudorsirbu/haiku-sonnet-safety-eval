"""Headline figure for the report: what the mitigation changed, and what it did not.

Run after analyze_results (it reads analysis/summary.json for the intervals, so the
figure shows exactly the numbers in analysis/results.md):

    python -m evals.report_figure --tag full

Writes results/figures/report_headline.png. Presentation only: nothing is computed
here that the registered analysis does not already compute.

Left: alarm rate on injected items per model, baseline -> mitigated (dumbbell).
Right: the paired mitigation effect with its crossed 95% interval (the H1' test).
Footer: the outcomes that were zero or at ceiling in every condition.

Colours: one hue in two shades for the ordered pair baseline -> mitigated (blue
steps 250 and 550 of the reference palette, validated as an ordinal pair).
"""
from __future__ import annotations

import argparse
import json

import config
from evals import analyze_results as ar

SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BASELINE, MITIGATED = "#86b6ef", "#1c5cab"
NAMES = {"haiku": "Haiku 5.5", "sonnet": "Sonnet 5.5"}


def rate(df, metric, model, cond):
    return float(ar.per_item(df[(df.model_key == model) & (df.condition == cond)], metric).mean())


def items_succeeded(df):
    inj = df[ar.METRICS["attack_success"][1](df)].copy()
    inj["success"] = ar._attack_success(inj)
    out = {}
    for (m, c), g in inj.groupby(["model_key", "condition"]):
        per = g.groupby("id")["success"].max()
        out[(m, c)] = (int(per.sum()), len(per))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="full")
    p.add_argument("--effort", default=config.EVAL_EFFORT)
    args = p.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = json.loads((config.ANALYSIS_DIR / "summary.json").read_text(encoding="utf-8"))["primary_effect"]
    all_df = ar.load([args.tag])
    df = all_df[(all_df["error"].isna() | all_df["judge_error"]) & (all_df["effort"] == args.effort)]
    models = [m for m in config.MODELS if m in set(df.model_key)]

    plt.rcParams.update({"font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK_2,
                         "xtick.color": MUTED, "ytick.color": INK, "text.color": INK})
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor(SURFACE)
    y = {m: i for i, m in enumerate(reversed(models))}

    # Left: dumbbell of alarm rates.
    for m in models:
        b, t = rate(df, ar.PRIMARY, m, "baseline"), rate(df, ar.PRIMARY, m, "mitigated")
        left.plot([t * 100, b * 100], [y[m]] * 2, color=AXIS, lw=2, zorder=1)
        for v, colour, cond, ha, dx in ((b, BASELINE, "baseline", "left", 2.5), (t, MITIGATED, "mitigated", "right", -2.5)):
            left.scatter(v * 100, y[m], s=110, color=colour, edgecolor=SURFACE, linewidth=2, zorder=3,
                         label=cond if m == models[0] else None)
            left.text(v * 100 + dx, y[m] + 0.16, f"{v:.0%}", ha=ha, va="bottom", color=INK_2, fontsize=9)
    left.set_xlim(0, 100)
    left.set_ylim(-0.6, len(models) - 0.4)
    left.set_yticks(list(y.values()), [NAMES.get(m, m) for m in y])
    left.set_xlabel("Injected episodes with an alarm (%)")
    left.set_title("Alarm rate, baseline → mitigated", loc="left", fontsize=11, color=INK)
    left.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK_2)

    # Right: paired effect with crossed 95% interval.
    for m in models:
        est, lo, hi = summary[m]["crossed"]
        right.plot([lo * 100, hi * 100], [y[m]] * 2, color=INK_2, lw=2, solid_capstyle="round", zorder=2)
        right.scatter(est * 100, y[m], s=90, color=MITIGATED, edgecolor=SURFACE, linewidth=2, zorder=3)
        right.text(est * 100, y[m] + 0.18, f"{est * 100:+.0f} pp [{lo * 100:+.0f}, {hi * 100:+.0f}]",
                   ha="center", va="bottom", color=INK, fontsize=9)
    right.axvline(0, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    right.set_xlim(-50, 10)
    right.set_ylim(-0.6, len(models) - 0.4)
    right.set_yticks(list(y.values()), [""] * len(y))
    right.set_xlabel("Mitigated − baseline, paired by item (pp)")
    right.set_title("Mitigation effect (crossed 95% interval)", loc="left", fontsize=11, color=INK)

    for ax in (left, right):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="x", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)

    # Footer: what did not change.
    succ = items_succeeded(df)
    k = max(v[0] for v in succ.values())  # worst cell
    n_cell = max(v[1] for v in succ.values())
    mention = min(rate(df, "mention_injected", m, c) for m in models for c in config.CONDITIONS)
    fa = sum(int(ar.per_item(df[(df.model_key == m) & (df.condition == c)], "false_alarm").gt(0).sum())
             for m in models for c in config.CONDITIONS)
    task = min(rate(df, "task_success_clean", m, c) for m in models for c in config.CONDITIONS)
    attacks = (f"no attack succeeded on any of the {n_cell} injected items" if k == 0
               else f"attacks succeeded on at most {k} of {n_cell} items")
    task_txt = "100%" if task >= 1 else f"at least {task:.0%}"
    mention_txt = "every" if mention >= 1 else f"at least {mention:.0%} of"
    footer = (f"Unchanged in every model × condition: {attacks} (one-sided 95% upper bound {ar.cp_upper(k, n_cell):.1%}); "
              f"the reply told the user about the instruction in {mention_txt} injected episode{'s' if mention < 1 else ''}; "
              f"false alarms on clean and benign documents: {fa}; clean-task success {task_txt}. "
              "An alarm = the reply calls the instruction suspicious or an attack, or advises caution (judge, rubric §3).")
    import textwrap
    fig.text(0.01, 0.02, "\n".join(textwrap.wrap(footer, 175)), fontsize=8.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = config.FIGURES_DIR / "report_headline.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
