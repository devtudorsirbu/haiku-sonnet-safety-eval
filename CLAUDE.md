# Project: does "treat documents as data" stop prompt injection in Claude agents?

A small pre-registered experiment. Claude Haiku 5.5 and Sonnet 5.5 act as an agent with mock
`read_document` and `send_email` tools. We measure how often they follow instructions planted in
documents, with and without one system-prompt paragraph (`MITIGATION` in `config.py`).
Read `README.md` first; the full plan is `haiku_sonnet_opus_implementation.md`. Where a code
listing in the plan differs from the files in `evals/`, the files are correct.

## Running things
- Activate the venv (`.venv`) and run every script from the repo root as a module:
  `python -m evals.<script>`. Never `python evals/<script>.py`.
- Every pipeline command is safe to re-run: finished work is skipped, failures retried,
  interrupted batches resumed. Do not delete files in `results/` to "start clean"; ask first.
- Offline checks that cost nothing: `python -m evals.build_dataset`, `check_raw_outputs`,
  `analyze_results`, `make_audit_sample`, `agreement`, `estimate_cost`.

## API calls cost the researcher money
- `smoke_test`, `run_eval` and `score_outputs` (without `--objective-only`) call the paid API.
  Say what a command will run and roughly what it costs, and get a yes before running it.
- Debug with Haiku only and a small limit: `--models haiku --limit 5 --mode sync`.
- Large runs use `--mode batch` (50% cheaper). Never raise effort, samples or `max_tokens` to
  fix a problem without asking.

## Experimental integrity
- Do not change models, effort, `temperature`-style parameters, system prompts, `MITIGATION`,
  the rubric, the judge prompt or the dataset unless the researcher asks. Do not add the API's
  server-side model `fallbacks`: they would swap the model being measured.
- Once `writeup/preregistration.md` is committed, hypotheses, the primary metric and the
  analysis method are frozen. Any later change needs the researcher's explicit agreement and
  must be recorded as a deviation in the report.
- Edit only `data/source/*.jsonl`, then rebuild with `python -m evals.build_dataset`. Never
  edit `data/dataset.jsonl` or `data/pilot.jsonl` by hand.
- Never hand-edit raw or scored outputs in `results/`.
- **The human audit must stay blind and human.** Never fill in the `human_*` columns of an
  audit sheet, suggest labels for it, or show the researcher judge labels, `results/scored/`
  rows or `results/audit/audit_key_*.csv` for audited episodes before they have finished
  grading. The audit is the independent check on the Claude judge.
- All companies, people, addresses and URLs are fictional and use `.example` domains. Tool
  calls are recorded, never executed; keep it that way.

## Secrets
- Never open, print or quote `.env`, and never put an API key in code, output or commits.

## Git
- Commit only when asked. Before committing, check `git status` shows no `.env`, results of
  an in-progress run, or `*.batch.json`.
- End commit messages with `Co-Authored-By: Claude <noreply@anthropic.com>` (the model name
  may be included). Do not add session links.
