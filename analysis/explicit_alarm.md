# Exploratory: explicit versus soft alarms (not pre-registered)

Splits the judge's `alarm` label on injected episodes into **explicit** (the reply uses a word of suspicion itself) and **soft** (advice to verify or escalate, without such a word), then repeats the H1′ comparison for explicit alarms only. Heuristic word list; see `evals/explicit_alarm.py`. No interval here is a registered test.

## Composition of the judge's alarms

| Model / condition | Episodes | Alarm (judge) | Explicit | Soft |
|---|---|---|---|---|
| haiku / baseline | 160 | 55% | 28% | 28% |
| haiku / mitigated | 160 | 32% | 18% | 14% |
| sonnet / baseline | 160 | 61% | 32% | 29% |
| sonnet / mitigated | 160 | 41% | 23% | 18% |

## Mitigation effect (mitigated − baseline, paired by item, crossed 95% interval)

| Model | All alarms (H1′, registered) | Explicit alarms only (exploratory) |
|---|---|---|
| haiku | -23 pp [-35, -12] | -9 pp [-18, -2] |
| sonnet | -21 pp [-38, -7] | -9 pp [-24, +2] |

Intervals use a different random seed from the registered analysis, so the first column can differ from `results.md` by a point; `results.md` is authoritative for H1′.
