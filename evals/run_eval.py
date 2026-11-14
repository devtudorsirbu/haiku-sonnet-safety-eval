"""Run the evaluated models over an item file.

Examples:
    python -m evals.run_eval --input data/pilot.jsonl --tag pilot --samples 1
    python -m evals.run_eval --tag full --mode batch

Agent items (injected, clean, benign_document) run as a two-turn tool loop:
  1. The model receives the user's request and the mock tools, and calls read_document.
  2. We return the document as the tool result. The model answers, and may call
     send_email. Tool calls in this turn are recorded, never executed, and end the episode.
Chat items (benign, direct_override) are a single turn with no tools.

Files: results/raw/<tag>.r1.jsonl and .r2.jsonl hold each turn; <tag>.jsonl is the
merged, one-row-per-episode file that everything else reads. Re-running the same
command skips completed work, retries failures and resumes interrupted batches.
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import config
from evals.common import extract_message, latest_rows, load_jsonl, message_params, run_jobs, write_jsonl

META_FIELDS = ("id", "category", "carrier", "doc_id", "source", "user_request", "document",
               "key_fact", "attack", "expected_behavior")


def paths(tag):
    base = config.RAW_DIR / tag
    return Path(f"{base}.r1.jsonl"), Path(f"{base}.r2.jsonl"), Path(f"{base}.jsonl")


def round1_jobs(items, model_keys, conditions, samples, effort):
    jobs = []
    for item, mk, cond, s in itertools.product(items, model_keys, conditions, range(1, samples + 1)):
        agent = item["category"] in config.AGENT_CATEGORIES
        params = message_params(
            config.MODELS[mk], config.system_prompt(item["category"], cond),
            [{"role": "user", "content": item["user_request"]}],
            effort, config.EVAL_MAX_TOKENS, tools=config.TOOLS if agent else None)
        meta = {k: item.get(k) for k in META_FIELDS}
        meta.update(model_key=mk, model=config.MODELS[mk], condition=cond, effort=effort, sample=s, agent=agent)
        jobs.append({"custom_id": f"{item['id']}__{mk}__{cond}__{effort}__s{s}", "params": params, "meta": meta})
    return jobs


def on_round1(job, msg, error):
    row = {"custom_id": job["custom_id"], **job["meta"], "round": 1}
    if error:
        row["error"] = error
    else:
        row.update(extract_message(msg))
    return row


def on_round2(job, msg, error):
    row = {"custom_id": job["custom_id"], "round": 2}
    if error:
        row["error"] = error
    else:
        row.update(extract_message(msg))
    return row


def tool_result_for(call, r1):
    if call["name"] == "read_document":
        return r1["document"]
    if call["name"] == "send_email":
        return "Email sent."
    return f"Error: unknown tool {call['name']}."


def round2_jobs(r1_rows):
    jobs = []
    for r1 in r1_rows.values():
        if r1.get("error") or not r1["agent"]:
            continue
        calls = r1["tool_calls"]
        if not any(c["name"] == "read_document" for c in calls):
            continue
        results = [{"type": "tool_result", "tool_use_id": c["id"], "content": tool_result_for(c, r1)}
                   for c in calls]
        messages = [
            {"role": "user", "content": r1["user_request"]},
            {"role": "assistant", "content": r1["content"]},  # unchanged, thinking blocks included
            {"role": "user", "content": results},
        ]
        params = message_params(r1["model"], config.system_prompt(r1["category"], r1["condition"]),
                                messages, r1["effort"], config.EVAL_MAX_TOKENS, tools=config.TOOLS)
        jobs.append({"custom_id": r1["custom_id"], "params": params, "meta": {}})
    return jobs


def merge(r1_path, r2_path, out_path):
    """One row per episode. Rows whose episode is unfinished carry an error."""
    r1_rows, r2_rows = latest_rows(r1_path), latest_rows(r2_path)
    final = []
    for cid, r1 in r1_rows.items():
        row = {k: v for k, v in r1.items() if k not in ("content", "text", "round")}
        if r1.get("error"):
            final.append(row)
            continue
        row["output"] = r1["text"]
        read = r1["agent"] and any(c["name"] == "read_document" for c in r1["tool_calls"])
        if not r1["agent"]:
            row["loop_status"] = "single"
        elif r1["stop_reason"] == "refusal":
            row["loop_status"] = "api_refusal"  # declined by the API's safety classifier before reading
        elif not read:
            row["loop_status"] = "no_read"  # never opened the document, so never saw the attack
        else:
            r2 = r2_rows.get(cid)
            if not r2 or r2.get("error"):
                row["error"] = (r2 or {}).get("error") or "round 2 not run yet"
                final.append(row)
                continue
            row.update(
                output=(r1["text"] + "\n\n" + r2["text"]).strip(),
                tool_calls=r1["tool_calls"] + r2["tool_calls"],
                stop_reason=r2["stop_reason"],
                thinking_blocks=r1["thinking_blocks"] + r2["thinking_blocks"],
                input_tokens=r1["input_tokens"] + r2["input_tokens"],
                output_tokens=r1["output_tokens"] + r2["output_tokens"],
                cache_read_tokens=r1.get("cache_read_tokens", 0) + r2.get("cache_read_tokens", 0),
                cache_write_tokens=r1.get("cache_write_tokens", 0) + r2.get("cache_write_tokens", 0),
                served_model=r2.get("served_model", r1.get("served_model")),
                # A second read_document call in turn 2 means the episode was cut off
                # before the model gave its answer (the loop has only two turns).
                loop_status=("truncated" if any(c["name"] == "read_document" for c in r2["tool_calls"])
                             else "complete"),
            )
        final.append(row)
    write_jsonl(out_path, final)
    return final


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=str(config.FULL_ITEMS))
    p.add_argument("--tag", required=True, help="Name of the run; output goes to results/raw/<tag>.jsonl")
    p.add_argument("--models", nargs="+", default=list(config.MODELS), choices=list(config.MODELS))
    p.add_argument("--conditions", nargs="+", default=list(config.CONDITIONS), choices=list(config.CONDITIONS))
    p.add_argument("--categories", nargs="+", default=None, choices=list(config.CATEGORIES))
    p.add_argument("--attack-kinds", nargs="+", default=None, choices=["action", "canary", "text"],
                   help="Only injected items whose attack is of these kinds")
    p.add_argument("--samples", type=int, default=config.SAMPLES_PER_ITEM)
    p.add_argument("--effort", default=config.EVAL_EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--mode", default="sync", choices=["sync", "batch"])
    p.add_argument("--limit", type=int, default=None, help="Only the first N items (for testing)")
    args = p.parse_args()

    items = load_jsonl(Path(args.input))
    if args.categories:
        items = [i for i in items if i["category"] in args.categories]
    if args.attack_kinds:
        items = [i for i in items if i.get("attack") and i["attack"].get("kind") in args.attack_kinds]
    if args.limit:
        items = items[: args.limit]

    r1_path, r2_path, out_path = paths(args.tag)
    run_jobs(round1_jobs(items, args.models, args.conditions, args.samples, args.effort),
             r1_path, on_round1, mode=args.mode, label="Turn 1: ")
    run_jobs(round2_jobs(latest_rows(r1_path)), r2_path, on_round2, mode=args.mode, label="Turn 2: ")
    final = merge(r1_path, r2_path, out_path)
    errors = sum(1 for r in final if r.get("error"))
    print(f"Done: {out_path} ({len(final)} episodes, {errors} unfinished; re-run to retry them)")


if __name__ == "__main__":
    main()
