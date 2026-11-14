# Does "treat documents as data" stop prompt injection in Claude agents?

A small, pre-registered experiment. Claude Haiku 5.5 and Claude Sonnet 5.5 act as a workplace
assistant with mock `read_document` and `send_email` tools. Documents contain planted instructions
(10 attacks × 8 carrier documents). We measure how often the agent obeys, with and without a
one-paragraph system-prompt mitigation, and what the mitigation costs in false alarms and task
quality. Action and secret-leak attacks are scored exactly; text attacks by a blind Claude Opus 5.5
judge validated against a human audit. The full plan is in `haiku_sonnet_opus_implementation.md`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
python -m evals.smoke_test
```

Run every script from the repository root as a module: `python -m evals.<script>`.

## Pipeline

| Step | Command |
|---|---|
| Build and check the dataset | `python -m evals.build_dataset` |
| Run the agents | `python -m evals.run_eval --tag full --mode batch` |
| Check outputs | `python -m evals.check_raw_outputs --tag full` |
| Grade | `python -m evals.score_outputs --tag full --effort medium --mode batch` |
| Blind audit sheet | `python -m evals.make_audit_sample --tag full --per-cell 4` |
| Judge agreement | `python -m evals.agreement --tag full` |
| Analysis | `python -m evals.analyze_results --tags full` |
| Cost | `python -m evals.estimate_cost --tag full --batch` |

Every command can be re-run safely: completed work is skipped, failures are retried, and an
interrupted batch is resumed rather than resubmitted. See the `Makefile` for the pilot and the
effort ablation.

## Run record (fill in)

| Item | Value |
|---|---|
| Models | claude-haiku-5-5, claude-sonnet-5-5; judge claude-opus-5-5 |
| Access date | |
| SDK version | |
| Effort (subjects / judge) | medium / low |
| Samples per item | 2 |
| Dataset commit | |
| Rubric frozen at commit | |
| Pre-registration commit | |
| Total tokens (input / output) | |
| Total cost | |

## Limitations

80 injected items from 10 attacks and 8 documents, drafted with AI assistance and edited by one
researcher; a Claude judge grading Claude models (bounded by a human audit and by its accuracy on
exactly scored attacks); two-turn episodes with mock tools; one mitigation wording; one main
effort level. Results describe these snapshots, items and settings only.
