#!/usr/bin/env bash
# One command: ./run.sh  (starts all 3 services; Ctrl-C stops them)
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "Copy .env.example to .env and set ANTHROPIC_API_KEY"; exit 1; }
set -a; . ./.env; set +a
python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip -q install -r task1-knowledge-brain/requirements.txt -r task3-meeting-to-scope/requirements.txt
(cd task2-inbox-agent && npm install --silent)
trap 'kill 0' EXIT
(cd task1-knowledge-brain && uvicorn app.main:app --port 8001) &
sleep 3
(cd task3-meeting-to-scope && uvicorn app.main:app --port 8003) &
(cd task2-inbox-agent && npm run start) &
echo "Task1 http://localhost:8001 | Inbox http://localhost:8002 | Scope http://localhost:8003"
wait
