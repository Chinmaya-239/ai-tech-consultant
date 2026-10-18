"""Run cases against the live API. Usage: python evaluation/run_evals.py [--cases f.jsonl] [--out results.csv]
Records pass/fail, latency; cost is computed from app.llm.USAGE-like fields via /query timing only (server-side cost: see EVALS.md method).
Correctness of answerable cases needs a human spot-check column ('human_ok') - this script only checks mechanics:
answerable => status answered + >=1 source; abstain => insufficient_evidence."""
import sys, json, time, csv, os, httpx
URL = os.getenv("KB_URL", "http://localhost:8001"); KEY = os.getenv("KB_API_KEY", "dev-key")
args = sys.argv[1:]; cases_f = args[args.index("--cases") + 1] if "--cases" in args else os.path.join(os.path.dirname(__file__), "cases.jsonl")
out_f = args[args.index("--out") + 1] if "--out" in args else "kb_results.csv"
rows = []
for line in open(cases_f):
    c = json.loads(line); t = time.time()
    try:
        r = httpx.post(f"{URL}/query", json={"question": c["question"]}, headers={"X-API-Key": KEY}, timeout=60); d = r.json()
        ok = (d["status"] == "answered" and len(d["sources"]) > 0) if c["expect"] == "answerable" else d["status"] == "insufficient_evidence"
        rows.append({"task": "knowledge", "case_id": c.get("id", c["question"][:20]), "expected": c["expect"], "actual": d["status"],
                     "sources": ";".join(s["url"] for s in d["sources"]), "latency_ms": int((time.time() - t) * 1000),
                     "passed": ok, "human_ok": "", "failure_reason": "" if ok else "mismatch"})
    except Exception as e:
        rows.append({"task": "knowledge", "case_id": c.get("id"), "expected": c["expect"], "actual": "error", "sources": "", "latency_ms": 0, "passed": False, "human_ok": "", "failure_reason": str(e)})
w = csv.DictWriter(open(out_f, "w", newline=""), fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
p = sum(r["passed"] for r in rows); lat = sorted(r["latency_ms"] for r in rows)
print(f"{p}/{len(rows)} passed | p50={lat[len(lat)//2]}ms p95={lat[int(len(lat)*.95)-1]}ms -> {out_f}")
