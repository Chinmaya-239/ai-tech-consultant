import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import store, pipeline

app = FastAPI(title="Meeting to Scope")
class NewP(BaseModel): name: str = Field(min_length=2)
class Meet(BaseModel): transcript: str = Field(min_length=50); date: str; label: str = "meeting"
class Appr(BaseModel): reviewer: str = Field(min_length=2)

@app.post("/projects")
def create(b: NewP): return store.new_project(b.name)
@app.get("/projects")
def projects(): return store.list_projects()
@app.get("/projects/{pid}")
def get(pid: str):
    try: return store.load(pid)
    except FileNotFoundError: raise HTTPException(404, "no such project")
@app.post("/projects/{pid}/meetings")
def meeting(pid: str, b: Meet):
    try: return pipeline.run_meeting(pid, b.transcript, b.date, b.label)
    except FileNotFoundError: raise HTTPException(404, "no such project")
    except Exception as e: raise HTTPException(502, f"pipeline failed: {e}")
@app.post("/projects/{pid}/versions/{v}/approve")
def approve(pid: str, v: int, b: Appr): return store.approve(store.load(pid), v, b.reviewer)
@app.post("/projects/{pid}/versions/{v}/send")
def send(pid: str, v: int):
    try: return store.send(store.load(pid), v)
    except PermissionError as e: raise HTTPException(403, str(e))
@app.get("/", include_in_schema=False)
def ui(): return FileResponse(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"))
