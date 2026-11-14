"""Shared helpers: data loading, request building, response parsing, and a job
runner that works with either the synchronous Messages API or the Message Batches API."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

import config

CUSTOM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def latest_rows(path: Path) -> dict[str, dict]:
    """Rows keyed by custom_id; a later row (e.g. a successful retry) wins."""
    return {row["custom_id"]: row for row in load_jsonl(path)}


# ---------------------------------------------------------------------------
# Requests and responses
# ---------------------------------------------------------------------------
def message_params(model: str, system, messages: list, effort: str, max_tokens: int,
                   tools: list | None = None) -> dict:
    params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "output_config": {"effort": effort},
    }
    if tools:
        params["tools"] = tools
    return params


def get_client():
    from anthropic import Anthropic
    from dotenv import load_dotenv

    load_dotenv(config.ROOT / ".env")
    return Anthropic()


def block_to_dict(block) -> dict:
    """Serialise a response content block so it can be sent back unchanged.

    Thinking blocks must be returned exactly as received in a tool-use loop."""
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    return dict(block)


def extract_message(msg) -> dict:
    """Visible text, tool calls, raw content and usage from a Message object."""
    blocks = [block_to_dict(b) for b in msg.content]
    return {
        "text": "".join(b.get("text", "") for b in blocks if b.get("type") == "text"),
        "tool_calls": [{"name": b["name"], "input": b.get("input", {}), "id": b["id"]}
                       for b in blocks if b.get("type") == "tool_use"],
        "content": blocks,
        "stop_reason": msg.stop_reason,
        "thinking_blocks": sum(b.get("type") in ("thinking", "redacted_thinking") for b in blocks),
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,  # includes thinking tokens
        # Cached prompt tokens are billed separately and are not in input_tokens.
        "cache_read_tokens": getattr(msg.usage, "cache_read_input_tokens", None) or 0,
        "cache_write_tokens": getattr(msg.usage, "cache_creation_input_tokens", None) or 0,
        "served_model": msg.model,
    }


def cost_usd(model: str, input_tokens: float, output_tokens: float, batch: bool = False,
             cache_read_tokens: float = 0, cache_write_tokens: float = 0) -> float:
    price_in, price_out = config.PRICES[model]
    cost = (input_tokens * price_in + output_tokens * price_out
            + cache_read_tokens * price_in * config.CACHE_READ_MULTIPLIER.get(model, 0.1)
            + cache_write_tokens * price_in * config.CACHE_WRITE_MULTIPLIER) / 1_000_000
    return cost * (config.BATCH_DISCOUNT if batch else 1.0)


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------
# A job is {"custom_id": str, "params": dict, "meta": dict}.
# on_result(job, message_or_None, error_or_None) -> row dict to append.
ResultFn = Callable[[dict, object, "str | None"], dict]


def pending_jobs(jobs: list[dict], out_path: Path) -> list[dict]:
    done = {cid for cid, row in latest_rows(out_path).items() if not row.get("error")}
    todo = [j for j in jobs if j["custom_id"] not in done]
    for j in todo:
        if not CUSTOM_ID_RE.match(j["custom_id"]):
            raise ValueError(f"Invalid custom_id (max 64 chars, [A-Za-z0-9_-]): {j['custom_id']}")
    return todo


def run_jobs(jobs: list[dict], out_path: Path, on_result: ResultFn,
             mode: str = "sync", client=None, poll_seconds: int = 30, label: str = "") -> None:
    """Run every job not already completed in out_path. Safe to re-run."""
    todo = pending_jobs(jobs, out_path)
    print(f"{label}{len(jobs)} jobs, {len(jobs) - len(todo)} already done, {len(todo)} to run ({mode}).")
    if not todo:
        return
    client = client or get_client()
    if mode == "sync":
        _run_sync(todo, out_path, on_result, client)
    elif mode == "batch":
        _run_batch(todo, out_path, on_result, client, poll_seconds)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def _run_sync(todo, out_path, on_result, client, max_attempts: int = 5) -> None:
    import anthropic

    for i, job in enumerate(todo, 1):
        for attempt in range(max_attempts):
            try:
                msg = client.messages.create(**job["params"])
                append_jsonl(out_path, on_result(job, msg, None))
                break
            except (anthropic.BadRequestError, anthropic.AuthenticationError,
                    anthropic.PermissionDeniedError, anthropic.NotFoundError) as exc:
                # A configuration problem (wrong model ID, unsupported parameter,
                # bad key). Retrying will not fix it, so stop immediately.
                raise SystemExit(f"Request failed for {job['custom_id']}: {exc}") from exc
            except (anthropic.RateLimitError, anthropic.APIConnectionError,
                    anthropic.APIStatusError) as exc:
                wait = min(60, 2 ** attempt * 2)
                print(f"  {job['custom_id']}: {type(exc).__name__}, retrying in {wait}s")
                time.sleep(wait)
        else:
            append_jsonl(out_path, on_result(job, None, "failed_after_retries"))
        print(f"  [{i}/{len(todo)}] {job['custom_id']}")


def _batch_state_path(out_path: Path) -> Path:
    return Path(str(out_path) + ".batch.json")


def _run_batch(todo, out_path, on_result, client, poll_seconds) -> None:
    state_path = _batch_state_path(out_path)
    by_id = {j["custom_id"]: j for j in todo}

    if state_path.exists():
        state = json.loads(state_path.read_text())
        batch_id = state["batch_id"]
        # Requests already saved by an earlier, interrupted collection are done, not foreign.
        saved = {cid for cid, row in latest_rows(out_path).items() if not row.get("error")}
        unexpected = set(state["custom_ids"]) - set(by_id) - saved
        if unexpected:
            # Collecting now would discard results this command has no job for,
            # and they would have to be paid for again.
            raise SystemExit(
                f"{state_path} belongs to an unfinished batch ({batch_id}) with {len(unexpected)} requests "
                "this command does not include. Re-run the command that created it first.")
        print(f"Resuming batch {batch_id}")
    else:
        requests = [{"custom_id": j["custom_id"], "params": j["params"]} for j in todo]
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        state_path.write_text(json.dumps({"batch_id": batch_id, "custom_ids": list(by_id)}))
        print(f"Created batch {batch_id} with {len(requests)} requests")

    while True:
        b = client.messages.batches.retrieve(batch_id)
        counts = b.request_counts
        print(f"  status={b.processing_status} processing={counts.processing} "
              f"succeeded={counts.succeeded} errored={counts.errored}")
        if b.processing_status == "ended":
            break
        time.sleep(poll_seconds)

    collected = set()
    for entry in client.messages.batches.results(batch_id):
        job = by_id.get(entry.custom_id)
        if job is None:
            continue
        if entry.result.type == "succeeded":
            row = on_result(job, entry.result.message, None)
        else:
            detail = getattr(entry.result, "error", None)
            row = on_result(job, None, f"{entry.result.type}: {detail}")
        append_jsonl(out_path, row)
        collected.add(entry.custom_id)
    state_path.unlink()
    print(f"Batch {batch_id} collected into {out_path}")
    missing = set(by_id) - collected
    if missing:
        print(f"{len(missing)} jobs were not in that batch; run the same command again to send them.")
