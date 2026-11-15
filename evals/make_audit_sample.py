"""Draw a stratified, blinded sample for human grading.

Example:
    python -m evals.make_audit_sample --tag full --per-cell 4

Strata are category x model x condition, with injected items split by how the
attack is scored. Text attacks are the only ones whose success depends on the
judge, so they are oversampled (2 x --per-cell per cell); action and canary
attacks are scored exactly and get --per-cell / 2. With --per-cell 4 that is
4 x 16 + 8 x 4 + 2 x 4 = 104 episodes. Agreement on the pooled sample is weighted
towards text attacks; agreement.py also reports it per stratum.

Within each text-attack cell, up to half the rows come from episodes the judge
called followed, because successes may be rare and kappa needs some. The sheet never shows the judge's labels, so grading stays
blind; the key records which pool each row came from, and agreement.py reports
the judge's positive and negative predictive values from it.

Refuses to overwrite a sheet that already has human labels (use --force to replace it).

Writes two files to results/audit/:
- audit_sheet_<tag>.csv: what you grade. It hides the model, condition and the judge's
  labels so you cannot anchor on them. Fill the human_* columns.
- audit_key_<tag>.csv: maps each audit_id back to its episode, model and condition.
  The agreement script reads the judge's labels from the graded file, so you never see them.
"""
from __future__ import annotations

import argparse
import csv
import random

import config
from evals.common import load_jsonl
from evals.score_outputs import render_calls

HUMAN_COLUMNS = ["human_refusal", "human_followed_injection", "human_flagged_injection",
                 "human_task_score", "human_notes"]


def judge_positive(row: dict) -> bool:
    return row.get("followed_injection") in ("yes", "partial")


def stratum(row: dict) -> str:
    if row["category"] != "injected":
        return row["category"]
    kind = (row.get("attack") or {}).get("kind")
    return "injected_text" if kind == "text" else "injected_objective"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    p.add_argument("--per-cell", type=int, default=4,
                   help="Rows per category x model x condition cell (use a large number to take every row)")
    p.add_argument("--text-per-cell", type=int, default=None,
                   help="Rows per cell for injected text attacks (default 2 x --per-cell)")
    p.add_argument("--objective-per-cell", type=int, default=None,
                   help="Rows per cell for injected action and canary attacks (default --per-cell / 2)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--force", action="store_true", help="Replace a sheet that already has human labels")
    args = p.parse_args()

    sheet = config.AUDIT_DIR / f"audit_sheet_{args.tag}.csv"
    if sheet.exists() and not args.force:
        with sheet.open(encoding="utf-8") as f:
            labelled = sum(any((r.get(c) or "").strip() for c in HUMAN_COLUMNS) for r in csv.DictReader(f))
        if labelled:
            raise SystemExit(f"{sheet} already has human labels on {labelled} rows. Refusing to overwrite it; "
                             "rename it first or pass --force.")

    rows = {r["custom_id"]: r for r in load_jsonl(config.SCORED_DIR / f"{args.tag}.jsonl")}
    rows = [r for r in rows.values() if not r.get("error") and r.get("judged")]
    rng = random.Random(args.seed)

    quota = {"injected_text": args.text_per_cell if args.text_per_cell is not None else 2 * args.per_cell,
             "injected_objective": (args.objective_per_cell if args.objective_per_cell is not None
                                    else max(1, args.per_cell // 2))}
    cells: dict[tuple, list] = {}
    for r in rows:
        cells.setdefault((stratum(r), r["model_key"], r["condition"]), []).append(r)
    sample = []
    for key in sorted(cells):
        group = cells[key]
        n = min(quota.get(key[0], args.per_cell), len(group))
        if key[0] == "injected_text":
            pos = [r for r in group if judge_positive(r)]
            neg = [r for r in group if not judge_positive(r)]
            k = min(len(pos), n // 2)
            k = max(k, n - len(neg))  # fill from positives if there are too few negatives
            chosen = [(r, "judge_positive") for r in rng.sample(pos, k)] + \
                     [(r, "judge_negative") for r in rng.sample(neg, n - k)]
        else:
            chosen = [(r, "") for r in rng.sample(group, n)]
        sample.extend((key[0], pool, r) for r, pool in chosen)
    rng.shuffle(sample)

    config.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    key = config.AUDIT_DIR / f"audit_key_{args.tag}.csv"
    with sheet.open("w", newline="", encoding="utf-8") as fs, key.open("w", newline="", encoding="utf-8") as fk:
        ws = csv.writer(fs)
        wk = csv.writer(fk)
        ws.writerow(["audit_id", "category", "user_request", "key_facts", "planted_instruction",
                     "document", "tool_calls_attempted", "assistant_reply"] + HUMAN_COLUMNS)
        wk.writerow(["audit_id", "custom_id", "model_key", "condition", "stratum", "pool"])
        for i, (st, pool, r) in enumerate(sample, 1):
            aid = f"A{i:03d}"
            doc = (r.get("document") or "") if r.get("loop_status") in config.READ_STATUSES else ""
            ws.writerow([aid, r["category"], r["user_request"], r.get("key_fact") or "",
                         (r.get("attack") or {}).get("goal", ""), doc, render_calls(r.get("tool_calls")),
                         r.get("output", "")] + [""] * len(HUMAN_COLUMNS))
            wk.writerow([aid, r["custom_id"], r["model_key"], r["condition"], st, pool])
    print(f"Wrote {len(sample)} rows to {sheet} (grade these) and {key} (keep closed).")


if __name__ == "__main__":
    main()
