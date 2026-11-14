"""Cheap checks that the key, billing, model IDs, parameters and the tool loop work.

Run: python -m evals.smoke_test     (costs well under $0.05)
"""
import config
from evals.common import block_to_dict, extract_message, get_client, message_params

client = get_client()

print("1. One plain call per model")
for model in [*config.MODELS.values(), config.JUDGE_MODEL]:
    params = message_params(model, "You are a test harness.",
                            [{"role": "user", "content": "Reply with exactly: API smoke test successful"}],
                            "low", 1000)
    r = extract_message(client.messages.create(**params))
    print(f"   {model}: {r['text']!r} | in={r['input_tokens']} out={r['output_tokens']} stop={r['stop_reason']}")

print("2. The two-turn tool loop on each evaluated model")
doc = "Meeting moved to Thursday 10:00, room 4B."
for model in config.MODELS.values():
    system = config.system_prompt("clean", "baseline")
    messages = [{"role": "user", "content": "Read NOTE-1 and tell me when the meeting is."}]
    first = client.messages.create(**message_params(model, system, messages, "low", 2000, tools=config.TOOLS))
    calls = [b for b in first.content if b.type == "tool_use"]
    if not calls:
        print(f"   {model}: did not call a tool (stop={first.stop_reason}); check the output above")
        continue
    messages += [
        {"role": "assistant", "content": [block_to_dict(b) for b in first.content]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": c.id, "content": doc} for c in calls]},
    ]
    second = extract_message(client.messages.create(**message_params(model, system, messages, "low", 2000,
                                                                     tools=config.TOOLS)))
    print(f"   {model}: called {[c.name for c in calls]}, then replied {second['text'][:80]!r}")
print("If every line looks right, you are ready for Day 1.")
