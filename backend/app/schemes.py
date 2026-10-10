"""Structured scheme cards: data/schemes/*.json -> vector store.

Each JSON file looks like:
    {"source_url": "...", "vintage": "...", "records": [ {id, name, jurisdiction, ...}, ... ]}

Run from project root:
    python -m backend.app.schemes            # index (upsert) all in-scope records
    python -m backend.app.schemes --stats    # print counts only
"""
import argparse
import json
from urllib.parse import urlparse

from .config import INCLUDE_JURISDICTIONS, SCHEMES_DIR
from .vectorstore import add_chunks


def load_records(include_all: bool = False) -> list[dict]:
    """All records from data/schemes/*.json, each annotated with its file's source_url / vintage.
    By default only jurisdictions listed in INCLUDE_JURISDICTIONS are returned."""
    out = []
    for path in sorted(SCHEMES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for rec in data.get("records", []):
            if include_all or rec.get("jurisdiction") in INCLUDE_JURISDICTIONS:
                out.append({**rec, "source_url": data.get("source_url", ""),
                            "vintage": data.get("vintage", "")})
    return out


def record_text(rec: dict) -> str:
    """Plain-text rendering used for embedding and as the stored document."""
    lines = [f"Scheme: {rec['name']}",
             f"Jurisdiction: {rec['jurisdiction']}. Category: {rec['category']}."]
    for label, key in (("Part of", "parent_programme"), ("About", "summary"), ("Sponsor", "sponsor"),
                       ("Funding", "funding_pattern"), ("Implemented by", "implementing_agency"),
                       ("Area", "project_area"), ("Benefits", "benefits"),
                       ("Eligibility", "eligibility"), ("How to apply", "how_to_apply"),
                       ("Officers", "contact_officers")):
        if rec.get(key):
            lines.append(f"{label}: {rec[key]}")
    for c in rec.get("components") or []:
        parts = [c["name"]] + [x for x in (c.get("benefit"), c.get("eligibility")) if x]
        lines.append("Component: " + " - ".join(parts))
    return "\n".join(lines)


def index_schemes() -> int:
    recs = load_records()
    chunks = []
    for rec in recs:
        card = {k: v for k, v in rec.items() if k != "evidence"}
        chunks.append({
            "id": "scheme:" + rec["id"],
            "text": record_text(rec),
            "source": rec["source_url"] or "data/schemes",
            "title": rec["name"],
            "kind": "scheme",
            "domain": urlparse(rec["source_url"]).netloc or "local",
            "jurisdiction": rec["jurisdiction"],
            "category": rec["category"],
            "card": json.dumps(card, ensure_ascii=False),
        })
    add_chunks(chunks)
    print(f"Indexed {len(chunks)} scheme cards ({', '.join(sorted(INCLUDE_JURISDICTIONS))})", flush=True)
    return len(chunks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="print counts without touching the store")
    args = ap.parse_args()
    if args.stats:
        everything = load_records(include_all=True)
        in_scope = load_records()
        print(f"{len(everything)} records in data/schemes, {len(in_scope)} in scope "
              f"({', '.join(sorted(INCLUDE_JURISDICTIONS))})")
    else:
        index_schemes()
