"""Hybrid retrieval: SQLite FTS5 (BM25) + hashed-ngram vectors, fused with Reciprocal Rank Fusion.
embed() is a light local embedding; swap in a real model if evals (evaluation/run_evals.py --mode) show a gap."""
import re, hashlib
import numpy as np
from .db import conn

DIM = 512

def _toks(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())

def embed(text: str) -> np.ndarray:
    w = _toks(text)
    v = np.zeros(DIM, dtype=np.float32)
    for g in w + [a + "_" + b for a, b in zip(w, w[1:])]:
        v[int(hashlib.md5(g.encode()).hexdigest(), 16) % DIM] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v

def index_chunk(c, url, title, heading, text, images, kind="article") -> int:
    cur = c.execute("INSERT INTO chunks(url,title,heading,text,images,kind,vec) VALUES(?,?,?,?,?,?,?)",
                    (url, title, heading, text, images, kind, embed(f"{title} {heading} {text}").tobytes()))
    c.execute("INSERT INTO fts(text,title,heading,chunk_id) VALUES(?,?,?,?)", (text, title, heading, cur.lastrowid))
    return cur.lastrowid

def search(q: str, k: int = 6, mode: str = "hybrid") -> list[dict]:
    c = conn()
    terms = [t for t in _toks(q) if len(t) > 2]
    kw: list[int] = []
    if terms and mode in ("hybrid", "keyword"):
        fq = " OR ".join(f'"{t}"' for t in terms)
        kw = [r[0] for r in c.execute("SELECT chunk_id FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 20", (fq,))]
    sims: list[tuple[float, int]] = []
    if mode in ("hybrid", "vector"):
        qv = embed(q)
        rows = c.execute("SELECT id, vec FROM chunks WHERE vec IS NOT NULL").fetchall()
        sims = sorted(((float(np.frombuffer(r["vec"], dtype=np.float32) @ qv), r["id"]) for r in rows), reverse=True)[:20]
    score: dict[int, float] = {}
    cos: dict[int, float] = {}
    for rank, i in enumerate(kw):
        score[i] = score.get(i, 0) + 1 / (60 + rank)
    for rank, (s, i) in enumerate(sims):
        score[i] = score.get(i, 0) + 1 / (60 + rank)
        cos[i] = s
    out = []
    for i in sorted(score, key=score.get, reverse=True)[:k]:
        r = c.execute("SELECT * FROM chunks WHERE id=?", (i,)).fetchone()
        out.append({"id": i, "url": r["url"], "title": r["title"], "heading": r["heading"], "text": r["text"],
                    "images": r["images"], "kind": r["kind"], "rrf": round(score[i], 4),
                    "cosine": round(cos.get(i, 0.0), 3), "keyword_hit": i in kw})
    return out
