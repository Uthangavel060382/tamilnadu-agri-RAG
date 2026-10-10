import threading
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Query

from . import ingest, schemes, vectorstore

app = FastAPI(title="TN Agriculture Schemes Search")
_ingest_lock = threading.Lock()


@app.get("/health")
def health():
    return {"status": "ok", "chunks": vectorstore.count(), "ingesting": _ingest_lock.locked()}


@app.get("/search")
def search(q: str = Query(..., min_length=2), k: int = Query(5, ge=1, le=20),
           kind: Literal["all", "scheme", "document"] = "all"):
    return {"query": q, "results": vectorstore.search(q, k, None if kind == "all" else kind)}


@app.get("/schemes")
def list_schemes(jurisdiction: str | None = None, category: str | None = None):
    """Browse the structured scheme cards (no embedding needed)."""
    recs = schemes.load_records()
    if jurisdiction:
        recs = [r for r in recs if r["jurisdiction"] == jurisdiction]
    if category:
        recs = [r for r in recs if r["category"] == category]
    return {"count": len(recs), "schemes": [{k: v for k, v in r.items() if k != "evidence"} for r in recs]}


def _ingest_job():
    with _ingest_lock:
        ingest.main()


@app.post("/ingest")
def run_ingest(bg: BackgroundTasks):
    if _ingest_lock.locked():
        return {"status": "ingestion already running"}
    bg.add_task(_ingest_job)
    return {"status": "ingestion started"}
