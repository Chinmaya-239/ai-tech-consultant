import os, tempfile
os.environ["KB_DB"] = os.path.join(tempfile.mkdtemp(), "t.sqlite")
from app import db, retrieval, ingest

HTML = "<html><body><nav>MENU</nav><article><h1>Payments</h1><p>Intro.</p><h2>Refunds</h2><p>Open Billing > Refunds.</p><img src='/a.png'><h2>Gateways</h2><ul><li>Stripe</li></ul></article><footer>FOOT</footer></body></html>"

def test_parse_strips_chrome_and_splits_by_heading():
    p = ingest.parse(HTML, "https://x.com/p")
    text = " ".join(c["text"] for c in p["chunks"])
    assert "MENU" not in text and "FOOT" not in text
    assert [c["heading"] for c in p["chunks"]] == ["Payments", "Refunds", "Gateways"]
    assert p["chunks"][1]["images"][0]["url"] == "https://x.com/a.png"

def test_reindex_is_idempotent_and_removal_works():
    c = db.init()
    for _ in range(2):
        db.drop_page_chunks(c, "u1")
        retrieval.index_chunk(c, "u1", "Payments", "Refunds", "Open Billing then Refunds to refund a customer", "[]")
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM chunks WHERE url='u1'").fetchone()[0] == 1
    assert retrieval.search("how to refund a customer")[0]["url"] == "u1"
    db.drop_page_chunks(c, "u1"); c.commit()
    assert retrieval.search("how to refund a customer") == []
