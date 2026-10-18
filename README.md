# AI Tech Consultant
One shared **Knowledge Brain** (Python/FastAPI, port 8001) feeding an **Inbox Agent** (TypeScript, 8002) and a **Meeting-to-Scope** team (Python, 8003). Tasks 2 and 3 use Task 1 only over HTTP.

## Run
```
cp .env.example .env        # set ANTHROPIC_API_KEY
./run.sh                    # starts all 3 services
```
1. Open http://localhost:8001 -> "Run ingestion (20 pages)" (first, small crawl; for the full site `curl -XPOST :8001/ingestion/run -H 'X-API-Key: dev-key' -H 'Content-Type: application/json' -d '{}'`).
2. Inbox: http://localhost:8002. Scope Builder: http://localhost:8003. API docs: http://localhost:8001/docs

## Tests & evals
```
cd task1-knowledge-brain && python -m pytest && python evaluation/run_evals.py
cd task2-inbox-agent && npm test && npm run eval            # add -- --holdout-only for the 10 held-out emails
cd task3-meeting-to-scope && python -m pytest && python evaluation/run_evals.py
```
Config: `.env` (never commit it). Models: `CLAUDE_FAST` (classify / feasibility labels / image captions), `CLAUDE_SMART` (answers, drafts, scope, estimates).
Status and honest limits: see DESIGN.md and EVALS.md.
