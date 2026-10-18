"""Task 3 talks to Task 1 ONLY through its HTTP API."""
import os, httpx
KB_URL = os.getenv("KB_URL", "http://localhost:8001"); KB_KEY = os.getenv("KB_API_KEY", "dev-key")

def query(question: str, request_id: str | None = None) -> dict:
    """Returns the /query JSON, or {'status':'kb_unavailable'} - never raises, never fabricates."""
    try:
        r = httpx.post(f"{KB_URL}/query", json={"question": question, "request_id": request_id},
                       headers={"X-API-Key": KB_KEY}, timeout=45)
        r.raise_for_status(); return r.json()
    except Exception as e:
        return {"status": "kb_unavailable", "answer": None, "sources": [], "error": str(e)}
