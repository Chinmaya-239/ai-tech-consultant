import json, os, time, uuid
DIR = os.getenv("SCOPE_DATA", "data"); os.makedirs(DIR, exist_ok=True)
def _p(pid): return os.path.join(DIR, f"{pid}.json")
def new_project(name: str) -> dict:
    p = {"id": uuid.uuid4().hex[:8], "name": name, "meetings": [], "versions": []}; save(p); return p
def load(pid: str) -> dict:
    with open(_p(pid)) as f: return json.load(f)
def save(p: dict) -> None:
    with open(_p(p["id"]), "w") as f: json.dump(p, f, indent=1)
def list_projects() -> list[dict]:
    return [{"id": f[:-5], "name": load(f[:-5])["name"]} for f in os.listdir(DIR) if f.endswith(".json")]
def baseline(p: dict) -> dict | None:
    """Latest APPROVED version. Unapproved AI drafts never become the baseline."""
    ap = [v for v in p["versions"] if v["status"] in ("approved", "sent")]
    return ap[-1] if ap else None
def approve(p: dict, version: int, reviewer: str) -> dict:
    v = p["versions"][version - 1]; v.update(status="approved", approved_by=reviewer, approved_at=time.strftime("%Y-%m-%dT%H:%M:%S")); save(p); return v
def send(p: dict, version: int) -> dict:
    v = p["versions"][version - 1]
    if v["status"] not in ("approved", "sent"):
        raise PermissionError("version not approved by a human; refusing to send")
    v["status"] = "sent"; save(p); return v
