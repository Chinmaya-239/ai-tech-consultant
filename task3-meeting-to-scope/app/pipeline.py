from . import agents, store

def run_meeting(pid: str, transcript: str, date: str, label: str) -> dict:
    p = store.load(pid)
    p["meetings"].append({"date": date, "label": label, "transcript": transcript})   # original preserved
    a = agents.analyse(transcript)
    reqs = a["requirements"]
    base = store.baseline(p)
    if base:
        reqs = agents.compare(base["requirements"], reqs)
    else:
        for i, r in enumerate(reqs, 1):
            r["id"] = f"REQ-{i:03d}"; r["change"] = "new"
    active = [r for r in reqs if r.get("change") != "removed"]
    agents.feasibility(active)
    scope_md = agents.scope(p["name"], active, a.get("constraints", []))
    est = agents.estimate(reqs)
    rep = agents.change_report(reqs) if base else None
    cc = agents.compare_constraints(base.get('constraints', []), a.get('constraints', [])) if base else []
    if rep is not None: rep['constraint_changes'] = cc
    prop = agents.proposal(scope_md, est, rep, a.get("constraints", []))
    v = {"version": len(p["versions"]) + 1, "status": "draft", "meeting": label, "prompt_version": agents.PROMPT_VERSION,
         "requirements": reqs, "constraints": a.get("constraints", []), "decisions": a.get("decisions", []),
         "questions_to_ask_client": a.get("questions_to_ask_client", []), "scope_md": scope_md, "estimate": est,
         "proposal": prop, "change_report": rep, "constraint_changes": cc, "based_on_baseline": base["version"] if base else None}
    p["versions"].append(v); store.save(p)
    return v


