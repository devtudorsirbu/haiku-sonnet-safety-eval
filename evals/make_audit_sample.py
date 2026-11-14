"""Draw a stratified, blinded sample for human grading.

Example:
    python -m evals.make_audit_sample --tag full --per-cell 4

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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    p.add_argument("--per-cell", type=int, default=4,
                   help="Rows per category x model x condition cell (use a large number to take every row)")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    rows = {r["custom_id"]: r for r in load_jsonl(config.SCORED_DIR / f"{args.tag}.jsonl")}
    rows = [r for r in rows.values() if not r.get("error") and r.get("judged")]
    rng = random.Random(args.seed)

    cells: dict[tuple, list] = {}
    for r in rows:
        cells.setdefault((r["category"], r["model_key"], r["condition"]), []).append(r)
    sample = []
    for key in sorted(cells):
        group = cells[key]
        sample.extend(rng.sample(group, min(args.per_cell, len(group))))
    rng.shuffle(sample)

    config.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    sheet = config.AUDIT_DIR / f"audit_sheet_{args.tag}.csv"
    key = config.AUDIT_DIR / f"audit_key_{args.tag}.csv"
    with sheet.open("w", newline="", encoding="utf-8") as fs, key.open("w", newline="", encoding="utf-8") as fk:
        ws = csv.writer(fs)
        wk = csv.writer(fk)
        ws.writerow(["audit_id", "category", "user_request", "key_facts", "planted_instruction",
                     "document", "tool_calls_attempted", "assistant_reply"] + HUMAN_COLUMNS)
        wk.writerow(["audit_id", "custom_id", "model_key", "condition"])
        for i, r in enumerate(sample, 1):
            aid = f"A{i:03d}"
            doc = (r.get("document") or "") if r.get("loop_status") in config.READ_STATUSES else ""
            ws.writerow([aid, r["category"], r["user_request"], r.get("key_fact") or "",
                         (r.get("attack") or {}).get("goal", ""), doc, render_calls(r.get("tool_calls")),
                         r.get("output", "")] + [""] * len(HUMAN_COLUMNS))
            wk.writerow([aid, r["custom_id"], r["model_key"], r["condition"]])
    print(f"Wrote {len(sample)} rows to {sheet} (grade these) and {key} (keep closed).")


if __name__ == "__main__":
    main()
