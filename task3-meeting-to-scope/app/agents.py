"""One job per agent. Each has a versioned prompt, a JSON output contract, and a code-level validation step."""
import os, json
from . import llm, kb_client
PROMPT_VERSION = "scope-v1"
RATE = float(os.getenv("HOURLY_RATE", "60")); CUR = os.getenv("CURRENCY", "USD")

def number(text: str) -> str:
    return "\n".join(f"[L{i+1}] {l}" for i, l in enumerate(text.splitlines()) if l.strip())

def windows(numbered: str, size=6000, overlap=3) -> list[str]:
    lines = numbered.splitlines(); out, cur, n = [], [], 0
    for l in lines:
        cur.append(l); n += len(l)
        if n >= size: out.append("\n".join(cur)); cur = cur[-overlap:]; n = sum(len(x) for x in cur)
    return out + (["\n".join(cur)] if cur else [])

# 1. Transcript Analyst ------------------------------------------------------
ANALYST = """You are a senior software consultant reading part of a client meeting transcript (lines tagged [Lnn]).
Extract ONLY what is said. Separate explicit client requests from your inferences. Do not invent numbers, dates or prices.
Schema: {"requirements":[{"description":str,"origin":"explicit"|"inferred","status":"confirmed"|"unclear"|"disputed",
"priority":"must"|"should"|"optional","evidence_lines":[int],"open_questions":[str]}],
"decisions":[{"text":str,"lines":[int]}],"constraints":[{"type":"budget"|"deadline"|"other","text":str,"lines":[int]}],
"questions_to_ask_client":[str]}"""

def analyse(transcript: str) -> dict:
    parts = [llm.ask_json(ANALYST, w, llm.SMART, 3000) for w in windows(number(transcript))]
    if len(parts) == 1: return parts[0]
    merged = llm.ask_json("""Merge partial extractions from overlapping windows of ONE meeting. Deduplicate requirements (keep all evidence_lines),
resolve contradictions by preferring the LATER statement but mark status 'disputed' and add an open question. Same schema as the inputs.""",
                          json.dumps(parts), llm.SMART, 4000)
    return merged

# 2. Product Feasibility Agent (calls Task 1) ---------------------------------
def feasibility(reqs: list[dict]) -> list[dict]:
    for r in reqs:
        kb = kb_client.query(f"Does the product support or let users configure: {r['description']}? Which settings or limitations apply?", r["id"])
        if kb["status"] == "answered":
            c = llm.ask_json('Classify using ONLY this KB answer. JSON {"classification":"existing_configuration"|"existing_with_limitation"|"custom_development","note":str}.',
                             f"Requirement: {r['description']}\nKB answer: {kb['answer']}\nUncertainty: {kb.get('uncertainty')}", llm.FAST, 500)
            r["feasibility"] = {**c, "sources": [s["url"] for s in kb["sources"]]}
        else:
            # Missing evidence is NOT proof a feature is absent -> needs clarification, never 'custom'.
            r["feasibility"] = {"classification": "needs_clarification", "note": f"Knowledge Brain: {kb['status']}. Ask a human expert.", "sources": []}
    return reqs

# 3. Scope Agent ---------------------------------------------------------------
def scope(project: str, reqs: list[dict], constraints: list[dict]) -> str:
    return llm.ask("""Write a Scope of Work in Markdown with sections: Objective, Current problem, Agreed requirements, Proposed solution,
Deliverables (each with a testable acceptance criterion), Explicit exclusions, Assumptions & dependencies, Client responsibilities, Open questions & risks.
Rules: only requirements with status 'confirmed' go in Agreed requirements; 'unclear'/'disputed' go to Open questions. Requirements classified
existing_configuration are delivered as configuration, not custom code. Never present inferred items or needs_clarification items as commitments.""",
                   json.dumps({"project": project, "requirements": reqs, "constraints": constraints}), llm.SMART, 3500)

# 4. Estimation Agent -----------------------------------------------------------
def estimate(reqs: list[dict]) -> dict:
    items = [r for r in reqs if r.get("change") != "removed"]
    r = llm.ask_json("""Break each requirement into small engineering tasks with hours. existing_configuration => config/test tasks only.
needs_clarification => include a 'clarification' task and mark confidence 'low'. Never give a single precise number as certain.
Schema {"tasks":[{"req_id":str,"task":str,"low":num,"likely":num,"high":num,"assumptions":[str],"confidence":"low"|"medium"|"high","reasoning":str}]}""",
                     json.dumps([{k: x[k] for k in ("id", "description", "feasibility", "priority")} for x in items]), llm.SMART, 4000)
    for t in r["tasks"]:                                    # validation: ordering + numeric sanity
        t["low"], t["likely"], t["high"] = sorted(float(t[k]) for k in ("low", "likely", "high"))
    tot = {k: round(sum(t[k] for t in r["tasks"]), 1) for k in ("low", "likely", "high")}   # sums done in CODE, not by the LLM
    return {**r, "totals": tot, "rate": RATE, "currency": CUR,
            "price_range": {k: round(v * RATE, 2) for k, v in tot.items()}, "note": "Hours/price are estimates, not an approved quote."}

# 5. Proposal & Review Agent -----------------------------------------------------
def proposal(scope_md: str, est: dict, change_report: dict | None, constraints: list[dict]) -> dict:
    md = llm.ask("""Write a client-ready proposal in Markdown: Executive summary, Problem & solution, Scope & deliverables, Timeline & milestones,
Effort & pricing assumptions, Client responsibilities, Exclusions & dependencies, Risks & open questions, Approval & next steps.
Use ONLY the scope, estimate and constraints given. Quote the estimate as a range. Do not promise anything marked unclear or needs_clarification.
If a change report is given, add a 'Changes since the last approved version' section and list out-of-scope items as 'quoted separately'.""",
                 json.dumps({"scope": scope_md, "estimate": est, "changes": change_report, "constraints": constraints}), llm.SMART, 3500)
    chk = llm.ask_json('Review for consistency. JSON {"issues":[str]}: list any place the proposal promises something the scope marks unclear/unverified, or whose numbers disagree with the estimate. Empty list if none.',
                       json.dumps({"proposal": md, "scope": scope_md, "estimate": est["totals"]}), llm.FAST, 800)
    return {"markdown": md, "review_issues": chk.get("issues", [])}

# 6. Change detection vs APPROVED baseline ---------------------------------------
def compare(baseline_reqs: list[dict], new_reqs: list[dict]) -> list[dict]:
    """Assign stable IDs: matched new reqs inherit the baseline ID; others get fresh IDs."""
    m = llm.ask_json("""Match each NEW requirement to a BASELINE requirement id if it is the same need (even reworded). Detect explicit removals
("drop X", "no longer need X", "forget X") and modifications (same need, changed details). Schema:
{"matches":[{"new_index":int,"baseline_id":str|null,"modified":bool,"what_changed":str|null}],"removed_baseline_ids":[str]}""",
                     json.dumps({"baseline": [{"id": b["id"], "description": b["description"]} for b in baseline_reqs],
                                 "new": [{"index": i, "description": n["description"], "status": n.get("status")} for i, n in enumerate(new_reqs)]}), llm.SMART, 3000)
    by_new = {x["new_index"]: x for x in m["matches"]}
    nxt = max([int(b["id"].split("-")[1]) for b in baseline_reqs] + [0]) + 1
    for i, n in enumerate(new_reqs):
        x = by_new.get(i, {})
        if x.get("baseline_id") and any(b["id"] == x["baseline_id"] for b in baseline_reqs):
            n["id"] = x["baseline_id"]; n["change"] = "modified" if x.get("modified") else "unchanged"; n["what_changed"] = x.get("what_changed")
        else:
            n["id"] = f"REQ-{nxt:03d}"; nxt += 1; n["change"] = "added"
    removed = [b for b in baseline_reqs if b["id"] in set(m.get("removed_baseline_ids", []))]
    carried = [dict(b, change="unchanged") for b in baseline_reqs
               if b["id"] not in {n["id"] for n in new_reqs} and b["id"] not in {r["id"] for r in removed}]
    all_reqs = new_reqs + carried + [dict(b, change="removed") for b in removed]
    return all_reqs
def change_report(reqs: list[dict]) -> dict:
    g = lambda k: [{"id": r["id"], "description": r["description"], "detail": r.get("what_changed")} for r in reqs if r.get("change") == k]
    return {"added": g("added"), "modified": g("modified"), "removed": g("removed"),
            "potentially_out_of_scope": [dict(a, action="Not in approved baseline: clarify and quote separately") for a in g("added")]}
