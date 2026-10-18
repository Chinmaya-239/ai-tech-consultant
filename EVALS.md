# EVALS.md  (2-3 pages) - NO RESULTS HAVE BEEN RUN YET. Everything below is PENDING until you run it.

| Task | Cases | Runner | Output |
|---|---|---|---|
| Knowledge | 20 (`task1-knowledge-brain/evaluation/cases.jsonl`; edit KB-011/012 and tighten expectations after ingest) | `python evaluation/run_evals.py` | `kb_results.csv` |
| Inbox | 50 emails, 10 held out (`task2-inbox-agent/data/emails.jsonl`) | `npm run eval` | `inbox_results.csv` |
| Scope | 24 rule cases on 3 transcripts + approval check | `python evaluation/run_evals.py` | `scope_results.csv` |

## Model comparison (needs 20-30 cases per decision)
Run each runner twice with `CLAUDE_FAST`/`CLAUDE_SMART` swapped (e.g. haiku vs sonnet for classification; sonnet vs opus-tier for estimates). Record:
| Decision | Model | Quality % | p50 / p95 latency | Cost per task | Failure rate |
|---|---|---|---|---|---|
| classify | [pending] | | | | |
Cost = (tokens_in x price_in + tokens_out x price_out) from the CSV columns, using current published prices (not hardcoded here).

## Retrieval ablation
Add `mode` = vector / keyword / hybrid to `search()` calls in the eval runner; report recall@6 on the 15 answerable cases.

## Failures and fixes
[List real failed cases, why, and the prompt/code change; re-run same cases before/after, record both.]
