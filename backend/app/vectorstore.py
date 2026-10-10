import json

import chromadb
from sentence_transformers import SentenceTransformer

from .config import CHROMA_DIR, COLLECTION, EMBED_MODEL

BATCH = 64
_E5 = "e5" in EMBED_MODEL.lower()  # e5 models need "query: " / "passage: " prefixes

_model = None
_collection = None


def _embed(texts: list[str], prefix: str) -> list[list[float]]:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    p = prefix if _E5 else ""
    vecs = _model.encode([p + t for t in texts], normalize_embeddings=True,
                         batch_size=16, show_progress_bar=False)
    return vecs.tolist()


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return _collection


def add_chunks(chunks: list[dict]):
    """chunks: [{id, text, source, title, kind, domain, ...extra scalar metadata}]"""
    col = get_collection()
    for i in range(0, len(chunks), BATCH):
        part = chunks[i:i + BATCH]
        texts = [c["text"] for c in part]
        col.upsert(
            ids=[c["id"] for c in part],
            documents=texts,
            embeddings=_embed(texts, "passage: "),
            metadatas=[{k: v for k, v in c.items() if k not in ("id", "text") and v is not None}
                       for c in part],
        )


def has_source(source: str) -> bool:
    return bool(get_collection().get(where={"source": source}, limit=1)["ids"])


def delete_source(source: str):
    get_collection().delete(where={"source": source})


def search(query: str, k: int = 5, kind: str | None = None) -> list[dict]:
    """kind: None (everything), 'scheme' (structured scheme cards) or 'document' (web/pdf chunks)."""
    col = get_collection()
    if col.count() == 0:
        return []
    where = None
    if kind == "scheme":
        where = {"kind": "scheme"}
    elif kind == "document":
        where = {"kind": {"$ne": "scheme"}}
    res = col.query(query_embeddings=_embed([query], "query: "), n_results=k, where=where)
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        item = {"text": doc, "score": round(1 - dist, 4), **meta}
        if "card" in item:
            item["card"] = json.loads(item["card"])
        out.append(item)
    return out


def count() -> int:
    return get_collection().count()
