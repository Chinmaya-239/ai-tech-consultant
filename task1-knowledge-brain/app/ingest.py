"""Polite, resumable, incremental crawler: sitemap -> manifest (pages table) -> fetch -> parse -> images -> chunks."""
import os, re, json, base64, hashlib, asyncio, random
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from lxml import etree
from . import llm
from .db import init, drop_page_chunks
from .retrieval import index_chunk

SITEMAP = os.getenv("KB_SITEMAP", "https://support.brilliantdirectories.com/support/sitemap.xml")
CONC = int(os.getenv("KB_CRAWL_CONCURRENCY", "2"))
DELAY = float(os.getenv("KB_CRAWL_DELAY", "1.0"))
UA = "KnowledgeBrainBot/1.0 (capstone; polite crawler)"
MAX_IMG = 5
STATE = {"running": False, "last": None, "progress": {}}

async def read_sitemap(client: httpx.AsyncClient, url: str = SITEMAP, depth: int = 0) -> list[tuple[str, str | None]]:
    r = await client.get(url); r.raise_for_status()
    root = etree.fromstring(r.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    out: dict[str, str | None] = {}
    for sm in root.findall("s:sitemap", ns):          # sitemap index -> recurse (depth-limited)
        if depth < 2:
            for u, lm in await read_sitemap(client, sm.findtext("s:loc", namespaces=ns).strip(), depth + 1):
                out[u] = lm
    for u in root.findall("s:url", ns):
        loc = (u.findtext("s:loc", namespaces=ns) or "").strip()
        if loc.startswith("http"):
            out[loc] = u.findtext("s:lastmod", namespaces=ns)   # dict => de-duplicated
    return list(out.items())

def parse(html: str, url: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    for t in s(["nav", "footer", "script", "style", "header", "aside", "form", "noscript"]):
        t.decompose()
    root = s.find("article") or s.find("main") or s.body or s
    h1 = s.find("h1")
    title = (h1 or s.title).get_text(" ", strip=True) if (h1 or s.title) else url
    chunks: list[dict] = []
    cur = {"heading": title, "parts": [], "images": []}

    def flush():
        txt = "\n".join(cur["parts"]).strip()
        if txt or cur["images"]:
            for piece in split_long(txt):
                chunks.append({"heading": cur["heading"], "text": piece, "images": cur["images"]})
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "tr", "img"]):
        if el.name in ("h1", "h2", "h3", "h4"):
            flush(); cur = {"heading": el.get_text(" ", strip=True), "parts": [], "images": []}
        elif el.name == "img":
            src = el.get("src") or el.get("data-src")
            if src and not src.startswith("data:"):
                cur["images"].append({"url": urljoin(url, src), "alt": el.get("alt", ""),
                                      "context": " ".join(cur["parts"][-2:])[:300]})
        elif el.name == "p" and el.find_parent("li"):
            continue
        else:
            t = (" | ".join(td.get_text(" ", strip=True) for td in el.find_all(["td", "th"]))
                 if el.name == "tr" else el.get_text(" ", strip=True))
            if t:
                cur["parts"].append(("- " if el.name == "li" else "") + t)
    flush()
    return {"title": title, "chunks": chunks, "hash": hashlib.sha256(root.get_text().encode()).hexdigest()}

def split_long(text: str, limit: int = 1500) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, buf, last = [], "", ""
    for line in text.split("\n"):
        if len(buf) + len(line) > limit and buf:
            out.append(buf); buf = last + "\n"       # one-line overlap
        buf += line + "\n"; last = line
    return out + ([buf] if buf.strip() else [])

async def fetch(client: httpx.AsyncClient, url: str, retries: int = 4) -> tuple[str | None, str]:
    for a in range(retries):
        try:
            r = await client.get(url)
            if r.status_code in (404, 410):
                return None, "gone"                      # permanent: never retried
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.text, "ok"
        except httpx.HTTPError as e:
            if a == retries - 1:
                return None, f"error: {e}"
            await asyncio.sleep(2 ** a + random.random())  # exponential backoff + jitter
    return None, "error"

async def describe_images(client: httpx.AsyncClient, imgs: list[dict]) -> list[tuple[dict, str]]:
    res = []
    for im in imgs[:MAX_IMG]:
        try:
            r = await client.get(im["url"])
            ct = r.headers.get("content-type", "").split(";")[0]
            if r.status_code == 200 and ct in ("image/png", "image/jpeg", "image/gif", "image/webp") and len(r.content) < 4_500_000:
                d = await asyncio.to_thread(llm.describe_image, base64.b64encode(r.content).decode(), ct, im["context"] or im["alt"])
                res.append((im, d))
        except Exception:
            continue                                      # one bad image never fails the page
    return res

async def process_page(client, c, url, lastmod, vision: bool, existing) -> str:
    html, st = await fetch(client, url)
    if html is None:
        c.execute("INSERT INTO pages(url,lastmod,status,attempts,error) VALUES(?,?,?,1,?) ON CONFLICT(url) DO UPDATE SET "
                  "status=?, attempts=attempts+1, error=?", (url, lastmod, "gone" if st == "gone" else "failed", st,
                                                             "gone" if st == "gone" else "failed", st))
        if st == "gone":
            drop_page_chunks(c, url)
        c.commit(); return "failed"
    p = parse(html, url)
    if existing and existing["hash"] == p["hash"] and existing["status"] == "done":
        c.execute("UPDATE pages SET lastmod=?, active=1 WHERE url=?", (lastmod, url)); c.commit()
        return "unchanged"
    drop_page_chunks(c, url)
    for ch in p["chunks"]:
        index_chunk(c, url, p["title"], ch["heading"], ch["text"], json.dumps([i["url"] for i in ch["images"]]))
        if vision and ch["images"] and os.getenv("ANTHROPIC_API_KEY"):
            for im, desc in await describe_images(client, ch["images"]):
                index_chunk(c, url, p["title"], ch["heading"],
                            f"[Screenshot in section '{ch['heading']}'] {desc}", json.dumps([im["url"]]), kind="image")
    c.execute("INSERT INTO pages(url,lastmod,hash,status,attempts,active,title,error) VALUES(?,?,?,'done',0,1,?,NULL) "
              "ON CONFLICT(url) DO UPDATE SET lastmod=?, hash=?, status='done', attempts=0, active=1, title=?, error=NULL",
              (url, lastmod, p["hash"], p["title"], lastmod, p["hash"], p["title"]))
    c.commit()
    return "added" if existing is None else "updated"

async def run(limit: int | None = None, vision: bool = True) -> dict:
    if STATE["running"]:
        return {"error": "already running"}
    STATE["running"] = True
    c = init()
    counts = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "failed": 0}
    run_id = c.execute("INSERT INTO runs(added,updated,removed,unchanged,failed) VALUES(0,0,0,0,0)").lastrowid
    try:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
            urls = await read_sitemap(client)
            rp = RobotFileParser()
            try:
                rr = await client.get(urljoin(SITEMAP, "/robots.txt")); rp.parse(rr.text.splitlines())
            except Exception:
                rp = None
            if limit:
                urls = urls[:limit]
            seen = {u for u, _ in urls}
            existing = {r["url"]: r for r in c.execute("SELECT * FROM pages")}
            if not limit:                                   # removals only decided on a full sitemap read
                for u, r in existing.items():
                    if r["active"] and u not in seen:
                        drop_page_chunks(c, u); c.execute("UPDATE pages SET active=0,status='removed' WHERE url=?", (u,))
                        counts["removed"] += 1
                c.commit()
            todo = [(u, lm) for u, lm in urls if (u not in existing or existing[u]["status"] not in ("done", "gone")
                    or (lm and lm != existing[u]["lastmod"])) and (rp is None or rp.can_fetch(UA, u))]
            counts["unchanged"] = len(urls) - len(todo)
            sem = asyncio.Semaphore(CONC)
            STATE["progress"] = {"total": len(todo), "done": 0}

            async def one(u, lm):
                async with sem:
                    try:
                        res = await process_page(client, c, u, lm, vision, existing.get(u))
                    except Exception as e:                   # failure isolation
                        c.execute("INSERT INTO pages(url,status,error,attempts) VALUES(?,'failed',?,1) ON CONFLICT(url) DO UPDATE SET status='failed',error=?,attempts=attempts+1", (u, str(e), str(e)))
                        c.commit(); res = "failed"
                    counts[res] += 1; STATE["progress"]["done"] += 1
                    await asyncio.sleep(DELAY)
            await asyncio.gather(*(one(u, lm) for u, lm in todo))
        c.execute("UPDATE runs SET added=?,updated=?,removed=?,unchanged=?,failed=?,finished=1 WHERE id=?",
                  (*counts.values(), run_id))
        c.commit()
        STATE["last"] = counts
        return counts
    finally:
        STATE["running"] = False

if __name__ == "__main__":
    import sys
    print(asyncio.run(run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)))
