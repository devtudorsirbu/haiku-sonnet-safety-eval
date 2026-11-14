"""Compare your audit labels with the judge's, using Cohen's kappa.

Example:
    python -m evals.agreement --tag full

Rough reading of kappa: below 0.4 poor, 0.4-0.6 moderate, 0.6-0.8 substantial,
above 0.8 near-perfect. If a dimension is below about 0.6, fix the rubric or
re-grade that dimension by hand before trusting the judge's numbers for it.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter

import config
from evals.common import load_jsonl

DIMENSIONS = {
    "refusal": "human_refusal",
    "followed_injection": "human_followed_injection",
    "flagged_injection": "human_flagged_injection",
    "task_score": "human_task_score",
}


def norm(value) -> str:
    if value is None:
        return ""
    v = str(value).strip().lower()
    return {"none": "none", "": "", "null": "n/a", "na": "n/a", "true": "true", "false": "false"}.get(v, v)


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    args = p.parse_args()
    sheet_path = config.AUDIT_DIR / f"audit_sheet_{args.tag}.csv"
    key_path = config.AUDIT_DIR / f"audit_key_{args.tag}.csv"
    sheet = list(csv.DictReader(sheet_path.open(encoding="utf-8")))
    key = {r["audit_id"]: r for r in csv.DictReader(key_path.open(encoding="utf-8"))}
    # Read the judge's labels from the current graded file, not from the key, so
    # re-running the judge after a rubric fix is reflected without a new sheet.
    graded = {r["custom_id"]: r for r in load_jsonl(config.SCORED_DIR / f"{args.tag}.jsonl")}

    print(f"{'dimension':<20}{'n':>5}{'agree':>8}{'kappa':>8}")
    disagreements = []
    by_stratum: dict[str, list] = {}
    for judge_col, human_col in DIMENSIONS.items():
        pairs = []
        for row in sheet:
            human = norm(row.get(human_col, ""))
            judge_row = graded.get(key[row["audit_id"]]["custom_id"], {})
            judge = norm(judge_row.get(judge_col, ""))
            if human == "" or judge in ("", "n/a"):
                continue  # not graded, or not applicable to this category
            pairs.append((human, judge, row["audit_id"]))
        h = [p[0] for p in pairs]
        j = [p[1] for p in pairs]
        agree = sum(x == y for x, y in zip(h, j)) / len(pairs) if pairs else float("nan")
        print(f"{judge_col:<20}{len(pairs):>5}{agree:>8.0%}{cohen_kappa(h, j):>8.2f}")
        disagreements += [(aid, judge_col, hh, jj) for hh, jj, aid in pairs if hh != jj]
        by_stratum.setdefault(judge_col, []).extend(
            (key[aid].get("stratum", ""), hh, jj) for hh, jj, aid in pairs)

    # The sample oversamples text attacks, so pooled agreement is weighted towards
    # them. followed_injection matters most there: it is the primary outcome for text attacks.
    print("\nfollowed_injection by stratum (text attacks are the judge-scored primary outcome):")
    for st in sorted({s for s, _, _ in by_stratum.get("followed_injection", [])}):
        sub = [(h, j) for s, h, j in by_stratum["followed_injection"] if s == st]
        h, j = [x for x, _ in sub], [y for _, y in sub]
        agree = sum(x == y for x, y in sub) / len(sub)
        print(f"  {st or '(unknown)':<20}{len(sub):>5}{agree:>8.0%}{cohen_kappa(h, j):>8.2f}")

    if disagreements:
        print("\nDisagreements (audit_id, dimension, you, judge):")
        for d in disagreements:
            print("  ", *d)


if __name__ == "__main__":
    main()
