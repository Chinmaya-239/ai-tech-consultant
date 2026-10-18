import os, tempfile, pytest
os.environ["SCOPE_DATA"] = tempfile.mkdtemp()
from app import store, agents

def test_unapproved_cannot_be_sent_and_is_not_baseline():
    p = store.new_project("t"); p["versions"].append({"version": 1, "status": "draft", "requirements": []}); store.save(p)
    assert store.baseline(p) is None
    with pytest.raises(PermissionError): store.send(p, 1)
    store.approve(p, 1, "alice"); assert store.baseline(store.load(p["id"]))["version"] == 1
    assert store.send(store.load(p["id"]), 1)["status"] == "sent"

def test_change_report_buckets():
    r = agents.change_report([{"id": "REQ-001", "description": "a", "change": "added"}, {"id": "REQ-002", "description": "b", "change": "removed"}])
    assert r["added"][0]["id"] == "REQ-001" and r["removed"][0]["id"] == "REQ-002" and r["potentially_out_of_scope"]

def test_windows_overlap_and_numbering():
    t = agents.number("\n".join(f"line {i} " * 40 for i in range(60)))
    w = agents.windows(t, size=3000); assert len(w) > 1 and w[1].splitlines()[0] in w[0]
