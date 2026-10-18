# DESIGN.md  (fill in the [bracketed] parts from YOUR runs; target 3-5 pages)

## Problem (own words)
Code is cheap now; the slow, expensive parts are knowing the product, answering email, and turning meetings into scopes. Three workflows, one shared memory.

## Architecture
```
 Help center sitemap --> [Task1 Knowledge Brain  :8001]  <-- HTTP /query -- [Task2 Inbox Agent (TS) :8002] --> human review --> feedback + autonomy gate
   crawl>parse>vision>chunk>index  | RAG | escalations  <-- HTTP /query -- [Task3 Scope team (Py) :8003] --> human approval --> approved baseline
```
## Features chosen and why
- **Resumable incremental crawl** (pages table = manifest; lastmod + content-hash diff; removals deleted from the index) - first crawl must not hurt the source, daily run only touches changes.
- **Screenshot understanding** (vision caption stored as its own `image` chunk linked to the article) - screenshots carry answers.
- **Abstain + escalate** - wrong answers cost more than "I don't know". Expert answers become `expert` records (separate, labelled, appended to the eval set).
- **Inbox: policy guard after the LLM** - a regex layer blocks refund/price/date promises even if the model slips. Refunds, complaints, quotes, project requests are *never* auto-send eligible.
- **20-in-a-row rule defined**: same kind = same category + low risk + knowledge-backed; unchanged = normalized text equality (not a button click). Eligible != enabled: a human flips it on; any later edit/reject auto-disables.
- **Scope: approved-baseline diff** - changes compare against the last human-approved version, never a draft. Missing KB evidence => `needs_clarification`, never "custom work".
- **Estimates: ranges; sums computed in code**, price rate configurable, labelled "not a quote".
## Needs found without being told
Prompt-injection in emails and KB pages; duplicate sends on retry (idempotent send); expert answers expiring (`expires` field accepted); estimates must not be single numbers.
## Dropped / deferred (and why)
[Real email IMAP/SMTP (simulated outbox); reranker; knowledge graph; scheduled re-embedding on chunking changes; auth beyond a shared API key; Postgres/pgvector (SQLite FTS5 + local vectors used for zero-setup)]
## Model choices
[Fill from EVALS.md after running: Haiku vs Sonnet for classification (cost vs accuracy), Sonnet for answers/estimates.]
## What breaks / next
- Local hashed embeddings are weaker than a trained embedding model; swap `embed()` and compare with the eval runner.
- Keyword rules in scope evals are a coarse check; manual review required.
- [Add real failures you saw.]
