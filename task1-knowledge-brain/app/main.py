import os, json, asyncio, contextlib
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import ingest, llm
from .db import init, conn
from .prompts import ANSWER_SYSTEM, PROMPT_VERSION
from .retrieval import search, index_chunk

API_KEY = os.getenv("KB_API_KEY", "dev-key")
MIN_COSINE = 0.12   # below this AND no keyword hit => abstain without spending an LLM call

def auth(x_api_key: str | None = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid or missing X-API-Key")

@contextlib.asynccontextmanager
async def lifespan(app):
    init()
    task = None
    if os.getenv("KB_DAILY") == "1":
        async def daily():
            while True:
                await asyncio.sleep(24 * 3600); await ingest.run()
        task = asyncio.create_task(daily())
    yield
    if task: task.cancel()

app = FastAPI(title="Knowledge Brain", version="1.0", lifespan=lifespan)

class QueryReq(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    context: str | None = Field(default=None, max_length=2000, description="Optional caller context (e.g. customer plan)")
    top_k: int = Field(default=6, ge=1, le=12)
    request_id: str | None = None

class Source(BaseModel):
    title: str; url: str; heading: str | None = None; kind: str; images: list[str] = []; relevance: float

class QueryResp(BaseModel):
    status: str   # "answered" | "insufficient_evidence"
    answer: str | None
    sources: list[Source]
    uncertainty: str | None = None
    evidence_score: float = Field(description="Top retrieval cosine similarity. NOT a calibrated probability.")
    needs_human: bool
    escalation_id: int | None = None
    prompt_version: str = PROMPT_VERSION
    request_id: str | None = None

def _escalate(q: str, reason: str, ev: list[dict]) -> int:
    c = conn()
    i = c.execute("INSERT INTO escalations(question,reason,evidence) VALUES(?,?,?)",
                  (q, reason, json.dumps([e["url"] for e in ev]))).lastrowid
    c.commit(); return i

@app.post("/query", response_model=QueryResp, dependencies=[Depends(auth)])
def query(req: QueryReq):
    ev = search(req.question, req.top_k)
    top = max((e["cosine"] for e in ev), default=0.0)
    if not ev or (top < MIN_COSINE and not any(e["keyword_hit"] for e in ev)):
        eid = _escalate(req.question, "no relevant evidence retrieved", ev)
        return QueryResp(status="insufficient_evidence", answer=None, sources=[], evidence_score=top,
                         needs_human=True, escalation_id=eid, request_id=req.request_id)
    blocks = "\n\n".join(f"<evidence id={e['id']} kind={e['kind']} url={e['url']}>\n{e['title']} / {e['heading']}\n{e['text']}\n</evidence>" for e in ev)
    try:
        r = llm.ask_json(ANSWER_SYSTEM, f"Question: {req.question}\nContext: {req.context or 'none'}\n\n{blocks}")
    except Exception as e:
        raise HTTPException(502, f"LLM failure: {e}")
    used = {int(i) for i in r.get("used_ids", []) if str(i).lstrip('-').isdigit()} & {e["id"] for e in ev}
    if not r.get("answerable") or not used:                 # citation required, else abstain
        eid = _escalate(req.question, "evidence retrieved but insufficient", ev)
        return QueryResp(status="insufficient_evidence", answer=None, sources=[], evidence_score=top,
                         uncertainty=r.get("uncertainty"), needs_human=True, escalation_id=eid, request_id=req.request_id)
    srcs = [Source(title=e["title"], url=e["url"], heading=e["heading"], kind=e["kind"],
                   images=json.loads(e["images"] or "[]"), relevance=e["cosine"]) for e in ev if e["id"] in used]
    return QueryResp(status="answered", answer=r["answer"], sources=srcs, uncertainty=r.get("uncertainty"),
                     evidence_score=top, needs_human=False, request_id=req.request_id)

class IngestReq(BaseModel):
    limit: int | None = Field(default=None, ge=1, description="Crawl only the first N URLs (for testing)")
    vision: bool = True

@app.post("/ingestion/run", dependencies=[Depends(auth)], status_code=202)
def ingestion_run(req: IngestReq, bg: BackgroundTasks):
    if ingest.STATE["running"]:
        raise HTTPException(409, "ingestion already running")
    bg.add_task(ingest.run, req.limit, req.vision)
    return {"started": True}

@app.get("/ingestion/status", dependencies=[Depends(auth)])
def ingestion_status():
    c = conn()
    by = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM pages GROUP BY status")}
    last = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"running": ingest.STATE["running"], "progress": ingest.STATE["progress"], "pages_by_status": by,
            "last_run": dict(last) if last else None, "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}

class EscReq(BaseModel):
    question: str = Field(min_length=3); reason: str = "manual"

@app.post("/escalations", dependencies=[Depends(auth)])
def esc_create(r: EscReq):
    return {"id": _escalate(r.question, r.reason, [])}

@app.get("/escalations", dependencies=[Depends(auth)])
def esc_list(status: str = "open"):
    return [dict(r) for r in conn().execute("SELECT * FROM escalations WHERE status=? ORDER BY id DESC", (status,))]

class ResolveReq(BaseModel):
    answer: str = Field(min_length=3); expires: str | None = None

@app.post("/escalations/{eid}/resolve", dependencies=[Depends(auth)])
def esc_resolve(eid: int, r: ResolveReq):
    c = conn()
    row = c.execute("SELECT * FROM escalations WHERE id=? AND status='open'", (eid,)).fetchone()
    if not row:
        raise HTTPException(404, "open escalation not found")
    # Expert answers are stored as separate, labelled knowledge records (kind='expert') - never mixed into articles.
    index_chunk(c, f"expert://{eid}", "Expert answer", row["question"], f"Q: {row['question']}\nA: {r.answer}", "[]", kind="expert")
    c.execute("UPDATE escalations SET status='resolved', answer=? WHERE id=?", (r.answer, eid)); c.commit()
    with open(os.path.join(os.path.dirname(__file__), "..", "evaluation", "from_escalations.jsonl"), "a") as f:
        f.write(json.dumps({"question": row["question"], "expect": "answerable", "source": f"expert://{eid}"}) + "\n")
    return {"resolved": eid}

@app.get("/health")
def health():
    return {"ok": True, "chunks": conn().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}

@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"))
