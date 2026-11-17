"""Compose the experiment's items from the source files and check them.

    python -m evals.build_dataset

Reads data/source/*.jsonl and writes data/dataset.jsonl (the full set) and
data/pilot.jsonl (a small subset). Every attack is planted in every carrier
document, so attacks and documents are crossed: 10 attacks x 8 carriers = 80
injected items. Each carrier also appears once with no attack (the clean control).
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from collections import Counter

import config
from evals.objective_checks import canary_leaked

SRC = config.DATA_DIR / "source"
PLACEHOLDER = "{{ATTACK}}"
ID_RE = re.compile(r"^[a-z0-9_]{1,24}$")

# Pilot: two carriers x five attacks covering every success type, plus controls.
PILOT_CARRIERS = ["c01", "c05"]
PILOT_ATTACKS = ["a01", "a02", "a04", "a06", "a09"]
PILOT_OTHER = ["b02", "b05", "p01", "p05", "p09", "o02", "o04"]


def read(name):
    with (SRC / name).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def format_attack(text: str, fmt: str) -> str:
    if fmt == "paragraph":
        return text
    if fmt == "bullet":
        return f"- {text}"
    if fmt == "python_comment":
        return "\n".join("# " + line for line in textwrap.wrap(text, 76, break_on_hyphens=False, break_long_words=False))
    raise ValueError(f"unknown attack_format {fmt}")


def clean_document(doc: str) -> str:
    lines = [l for l in doc.split("\n") if l.strip() != PLACEHOLDER]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def injected_items(carriers, attacks, note_prefix=""):
    """Every attack planted in every carrier."""
    items = []
    for c in carriers:
        common = {k: c[k] for k in ("doc_id", "source", "user_request", "key_fact")}
        for a in attacks:
            items.append({
                "id": f"{c['id']}_{a['id']}", "category": "injected", "carrier": c["id"], **common,
                "document": c["document"].replace(PLACEHOLDER, format_attack(a["text"], c["attack_format"])),
                "attack": {k: a[k] for k in ("id", "kind", "stealth", "text", "goal", "success")},
                "expected_behavior": "resist_injection",
                "notes": f"{note_prefix}Carrier: {c['notes']} Attack: {a['notes']}",
            })
    return items


def build():
    carriers = read("carriers.jsonl")
    attacks = read("attacks.jsonl")
    items = []
    for c in carriers:
        common = {k: c[k] for k in ("doc_id", "source", "user_request", "key_fact")}
        for a in attacks:
            items.append({
                "id": f"{c['id']}_{a['id']}", "category": "injected", "carrier": c["id"], **common,
                "document": c["document"].replace(PLACEHOLDER, format_attack(a["text"], c["attack_format"])),
                "attack": {k: a[k] for k in ("id", "kind", "stealth", "text", "goal", "success")},
                "expected_behavior": "resist_injection",
                "notes": f"Carrier: {c['notes']} Attack: {a['notes']}",
            })
        items.append({
            "id": f"{c['id']}_clean", "category": "clean", "carrier": c["id"], **common,
            "document": clean_document(c["document"]), "attack": None,
            "expected_behavior": "should_help", "notes": f"Clean control for {c['id']}.",
        })
    for name in ("benign_documents.jsonl", "benign.jsonl", "direct_override.jsonl"):
        items.extend(read(name))
    return carriers, attacks, items


def check(carriers, attacks, items) -> list[str]:
    errors = []
    for c in carriers:
        if c["document"].count(PLACEHOLDER) != 1:
            errors.append(f"{c['id']}: document must contain {PLACEHOLDER} exactly once")
    for a in attacks:
        s = a["success"]
        if s["type"] == "email_to" and s["domain"] not in a["text"]:
            errors.append(f"{a['id']}: success domain not in attack text")
        if s.get("marker") and s["marker"] not in a["text"]:
            errors.append(f"{a['id']}: success marker not in attack text")
        if a["kind"] not in ("action", "canary", "text"):
            errors.append(f"{a['id']}: kind must be action, canary or text")
        if a["stealth"] not in ("blatant", "disguised"):
            errors.append(f"{a['id']}: stealth must be blatant or disguised")

    ids = Counter(i["id"] for i in items)
    errors += [f"duplicate id {k}" for k, v in ids.items() if v > 1]
    for it in items:
        pid = it["id"]
        if not ID_RE.match(pid):
            errors.append(f"{pid}: ids are lowercase letters, digits and underscores, max 24 chars")
        if it["category"] not in config.CATEGORIES:
            errors.append(f"{pid}: unknown category {it['category']}")
        for f in ("user_request", "expected_behavior", "notes"):
            if not str(it.get(f) or "").strip():
                errors.append(f"{pid}: missing {f}")
        agent = it["category"] in config.AGENT_CATEGORIES
        if agent and not (it.get("document") and it.get("doc_id") and it.get("key_fact")):
            errors.append(f"{pid}: agent items need doc_id, document and key_fact")
        if agent and it["doc_id"] not in it["user_request"]:
            errors.append(f"{pid}: user_request should name the doc_id")
        text = f"{it.get('user_request', '')} {it.get('document') or ''}"
        if canary_leaked(text):  # same matcher as scoring, so no item can trip it by itself
            errors.append(f"{pid}: text matches the canary detector, so leaks would be undetectable")
        for host in re.findall(r"(?:@|https?://)([a-z0-9.-]+\.[a-z]+)", text.lower()):
            if not host.endswith(".example"):
                errors.append(f"{pid}: real-looking domain {host}; use .example")
    return errors


def main():
    carriers, attacks, items = build()
    errors = check(carriers, attacks, items)
    if errors:
        print(f"{len(errors)} problems:")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    pilot_ids = {f"{c}_{a}" for c in PILOT_CARRIERS for a in PILOT_ATTACKS}
    pilot_ids |= {f"{c}_clean" for c in PILOT_CARRIERS} | set(PILOT_OTHER)
    pilot = [i for i in items if i["id"] in pilot_ids]

    outputs = [(config.FULL_ITEMS, items), (config.PILOT_ITEMS, pilot)]
    if (SRC / "attacks_exploratory.jsonl").exists():
        x_attacks = read("attacks_exploratory.jsonl")
        x_items = injected_items(carriers, x_attacks, note_prefix="EXPLORATORY. ")
        x_errors = check(carriers, x_attacks, x_items)
        clash = {a["id"] for a in x_attacks} & {a["id"] for a in attacks}
        if clash:
            x_errors.append(f"exploratory attack ids reuse main ids: {sorted(clash)}")
        if x_errors:
            print(f"{len(x_errors)} problems in the exploratory attacks:")
            for e in x_errors:
                print("  -", e)
            sys.exit(1)
        outputs.append((config.EXPLORATORY_ITEMS, x_items))

    for path, rows in outputs:
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{path.name}: {len(rows)} items {dict(Counter(r['category'] for r in rows))}")


if __name__ == "__main__":
    main()
