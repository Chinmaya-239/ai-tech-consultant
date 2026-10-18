import os, sqlite3
DB = os.getenv("KB_DB", "kb.sqlite")

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init() -> sqlite3.Connection:
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, lastmod TEXT, hash TEXT,
        status TEXT DEFAULT 'new', attempts INT DEFAULT 0, active INT DEFAULT 1, error TEXT, title TEXT);
    CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, title TEXT,
        heading TEXT, text TEXT, images TEXT, kind TEXT DEFAULT 'article', vec BLOB);
    CREATE INDEX IF NOT EXISTS ix_chunks_url ON chunks(url);
    CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, title, heading, chunk_id UNINDEXED);
    CREATE TABLE IF NOT EXISTS escalations(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
        reason TEXT, evidence TEXT, status TEXT DEFAULT 'open', answer TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT DEFAULT CURRENT_TIMESTAMP,
        added INT, updated INT, removed INT, unchanged INT, failed INT, finished INT DEFAULT 0);
    """)
    c.commit()
    return c

def drop_page_chunks(c: sqlite3.Connection, url: str) -> None:
    """Idempotency: remove all chunks for a URL before re-inserting."""
    for (i,) in c.execute("SELECT id FROM chunks WHERE url=?", (url,)).fetchall():
        c.execute("DELETE FROM fts WHERE chunk_id=?", (i,))
    c.execute("DELETE FROM chunks WHERE url=?", (url,))
