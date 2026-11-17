# Usage: make test | smoke | dataset | pilot | judge-pilot | power | screen | explore-screen | explore | full | score | audit | agreement | analyze | ablation | cost
PY = python -m
MODE ?= batch

# Offline regression checks: no API calls.
test:
	$(PY) tests.offline_checks

smoke:
	$(PY) evals.smoke_test

dataset:
	$(PY) evals.build_dataset

# Pilot: synchronous so you can read results within minutes (about $0.50).
pilot: dataset
	$(PY) evals.run_eval --input data/pilot.jsonl --tag pilot --samples 1 --mode sync
	$(PY) evals.check_raw_outputs --tag pilot

judge-pilot:
	$(PY) evals.score_outputs --tag pilot --mode sync
	$(PY) evals.make_audit_sample --tag pilot --per-cell 100
	$(PY) evals.estimate_cost --tag pilot --project data/dataset.jsonl

# Full run: Batch API by default (50% cheaper).
full: dataset
	$(PY) evals.run_eval --input data/dataset.jsonl --tag full --mode $(MODE)
	$(PY) evals.check_raw_outputs --tag full

score:
	$(PY) evals.score_outputs --tag full --effort medium --mode $(MODE)

audit:
	$(PY) evals.make_audit_sample --tag full --per-cell 4

agreement:
	$(PY) evals.agreement --tag full

analyze:
	$(PY) evals.analyze_results --tags full

# Effort ablation: objective attacks only, baseline, 1 sample, no judge (about $0.60 with batch).
ablation:
	$(PY) evals.run_eval --input data/dataset.jsonl --tag full --conditions baseline \
		--attack-kinds action canary --samples 1 --effort low --mode $(MODE)
	$(PY) evals.run_eval --input data/dataset.jsonl --tag full --conditions baseline \
		--attack-kinds action canary --samples 1 --effort high --mode $(MODE)
	$(PY) evals.score_outputs --tag full --effort low --objective-only
	$(PY) evals.score_outputs --tag full --effort high --objective-only

# Difficulty screen: every injected item, baseline only, 1 sample, both models, judged.
# About $1 with the Batch API. Development data: report it, do not pool it with the full run.
screen: dataset
	$(PY) evals.run_eval --input data/dataset.jsonl --tag screen --categories injected \
		--conditions baseline --samples 1 --mode $(MODE)
	$(PY) evals.check_raw_outputs --tag screen
	$(PY) evals.score_outputs --tag screen --mode $(MODE)
	$(PY) evals.power_simulation --tag screen

# Exploratory arm (stronger attacks, designed after the screen). Labelled exploratory throughout.
# Mini-screen first: baseline only, 1 sample, both models, judged. About $0.35 with the Batch API.
explore-screen: dataset
	$(PY) evals.run_eval --input data/exploratory.jsonl --tag explore-screen --conditions baseline \
		--samples 1 --mode $(MODE)
	$(PY) evals.check_raw_outputs --tag explore-screen
	$(PY) evals.score_outputs --tag explore-screen --mode $(MODE)
	$(PY) evals.power_simulation --tag explore-screen

# Full exploratory arm: both conditions, 2 samples (about $1.40 with the Batch API).
explore: dataset
	$(PY) evals.run_eval --input data/exploratory.jsonl --tag explore --mode $(MODE)
	$(PY) evals.check_raw_outputs --tag explore
	$(PY) evals.score_outputs --tag explore --effort medium --mode $(MODE)
	$(PY) evals.analyze_results --tags explore --exploratory --out results_exploratory.md

# Power of the primary test from the pilot's baseline rates (difficulty gate): no API calls.
power:
	$(PY) evals.power_simulation --tag pilot --metric alarm

cost:
	$(PY) evals.estimate_cost --tag full --batch

.PHONY: test smoke dataset pilot judge-pilot power screen explore-screen explore full score audit agreement analyze ablation cost
