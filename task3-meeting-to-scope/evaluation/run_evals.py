"""Runs meeting A -> approve -> meeting C through the real pipeline (needs Task 1 up for feasibility) and meeting B standalone.
Each rule in cases.json is one eval case (24 total). Keyword matching is a coarse first pass; READ the failures manually.
Usage: python evaluation/run_evals.py   (env: ANTHROPIC_API_KEY, KB_URL)"""
import os, re, csv, time, sys, json, tempfile
os.environ.setdefault("SCOPE_DATA", tempfile.mkdtemp()); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import store, pipeline, llm
T = lambda f: open(os.path.join(os.path.dirname(__file__), "..", "transcripts", f)).read()
cases = json.load(open(os.path.join(os.path.dirname(__file__), "cases.json")))
rows = []
def has(reqs, pat, pred=lambda r: True):
    return [r for r in reqs if re.search(pat, r["description"], re.I) and pred(r)]
def check(v, pat, kind):
    reqs = v["requirements"]; blob = json.dumps(v["constraints"]) + json.dumps(reqs)
    if kind == "present": return bool(has(reqs, pat))
    if kind in ("constraint", "constraint_or_req"): return bool(re.search(pat, blob, re.I))
    if kind == "needs_clarification": return bool(has(reqs, pat, lambda r: r.get("feasibility", {}).get("classification") == "needs_clarification"))
    if kind == "feasibility_not_custom_ok": return bool(has(reqs, pat))
    if kind == "removed": return bool(has(reqs, pat, lambda r: r.get("change") == "removed"))
    if kind == "added": return bool(has(reqs, pat, lambda r: r.get("change") == "added"))
    if kind == "unchanged": return bool(has(reqs, pat, lambda r: r.get("change") in ("unchanged", "modified")))
    if kind in ("added_or_modified", "modified_or_added"): return bool(has(reqs, pat, lambda r: r.get("change") in ("added", "modified")))
    return False
def run(label, fname, date, pid):
    n0 = len(llm.USAGE); t = time.time(); v = pipeline.run_meeting(pid, T(fname), date, label)
    return v, int((time.time() - t) * 1000), llm.USAGE[n0:]
pa = store.new_project("CityPros"); va, ms_a, u_a = run("A", "meeting_A_2026-10-05.txt", "2026-10-05", pa["id"])
store.approve(store.load(pa["id"]), 1, "eval-reviewer")
pb = store.new_project("Furniture"); vb, ms_b, u_b = run("B", "meeting_B_2026-10-07.txt", "2026-10-07", pb["id"])
vc, ms_c, u_c = run("C", "meeting_C_followup_2026-10-12.txt", "2026-10-12", pa["id"])
for key, v, ms, u in (("A", va, ms_a, u_a), ("B", vb, ms_b, u_b), ("C", vc, ms_c, u_c)):
    for i, (pat, kind) in enumerate(cases[key], 1):
        ok = check(v, pat, kind)
        rows.append({"task": "scope", "case_id": f"SC-{key}{i:02d}", "model": llm.SMART, "expected": f"{kind}:{pat}", "actual": "ok" if ok else "missing",
                     "latency_ms": ms, "tokens_in": sum(x["in"] for x in u), "tokens_out": sum(x["out"] for x in u), "passed": ok, "failure_reason": "" if ok else "see manual review"})
# approval compliance
try: store.send(store.load(pb["id"]), 1); sent = True
except PermissionError: sent = False
rows.append({"task": "scope", "case_id": "SC-APPROVAL", "model": "-", "expected": "blocked", "actual": "blocked" if not sent else "SENT", "latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "passed": not sent, "failure_reason": ""})
w = csv.DictWriter(open("scope_results.csv", "w", newline=""), fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
print(f"{sum(r['passed'] for r in rows)}/{len(rows)} passed -> scope_results.csv  (compute cost: tokens x your model prices)")
