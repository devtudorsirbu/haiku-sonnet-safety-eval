# Independent review, 15 November 2026

Before any data was collected, the design, dataset and code were reviewed by a separate
Claude model (Claude Fable 5.2) running under a different account in a fresh clone of this
repository. It was given only the repository and a prompt asking whether this is a fair
test of the mitigation and whether the results would mean what the README claims. It was
not told what earlier reviews had found or fixed, and it could not call the paid API.

| | |
|---|---|
| Reviewed at commit | `9506251` |
| Findings addressed in | `a3d3224` ("Address independent methodological review before the pilot") |
| Report | [`review.md`](review.md): 19 findings, the checks that passed, and open questions |

Every finding was checked against the code before being accepted: the two fake-data scripts
were re-run on the reviewed code and reproduced as reported, and the rest were verified by
reading the code, data and plan. All 19 were accepted. The fixes are in `a3d3224`, and
`tests/offline_checks.py` (`make test`) guards each of them.

## The scripts

The reviewer's own checks, archived as written. None of them calls the API or writes into
`results/` or `analysis/`. Run them from the repository root:

```bash
PYTHONPATH=. python writeup/independent_review_2026-11-15/fake_episode_checks.py
```

| Script | What it checks |
|---|---|
| `fake_episode_checks.py` | The exact checks (canary, emails) and how episodes are labelled, on hand-built fake episodes |
| `fake_analysis_checks.py` | `analyze_results` on fake scored data, against hand calculations |
| `bootstrap_simulation.py` | Coverage and power of the crossed bootstrap (takes a few minutes) |

They were written against commit `9506251`. On later commits some output differs **because
the findings were fixed**, not because something broke:

- `fake_episode_checks.py`: "page 7. Q3 x-functional review" and "27 Q3 XL orders" are no
  longer counted as leaks, and episodes get the new labels (`ended_at_email`,
  `refused_after_read`, `max_tokens_after_read`, `max_tokens_before_read`).
- `fake_analysis_checks.py`: section B now stops with an error, because the analysis refuses
  two tags that share episodes (finding 14). Sections C to F show the fixed behaviour; in D,
  the fake rows are labelled `complete` by hand, so set them to `ended_at_email` to see the
  fix for finding 4.

The code here is MIT-licensed like the rest of the code; the report is CC BY 4.0 like the
rest of `writeup/`.
