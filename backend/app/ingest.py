"""Step 1: scrape URLs (Playwright) + read PDFs -> chunk -> vector store.

Run from project root:
    python -m backend.app.ingest            # resume: skips sources already indexed
    python -m backend.app.ingest --force    # re-index everything
    python -m backend.app.ingest --pdfs-only
"""
import argparse
import hashlib
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import (ALLOWED_PDF_HOST_SUFFIXES, CHUNK_OVERLAP, CHUNK_SIZE,
                     MAX_PDF_MB, MAX_PDF_PAGES, MIN_CHUNK_CHARS, MIN_PAGE_CHARS,
                     PAGE_TIMEOUT_MS, PDF_CACHE, PDF_DIR, SEEDS_FILE)
from .vectorstore import add_chunks, count, delete_source, has_source

UA = {"User-Agent": "Mozilla/5.0 (compatible; TNAgriRAG/1.0)"}

# Links worth following / PDFs worth downloading (scheme-like), and things to never touch.
SCHEME_RE = re.compile(
    r"scheme|subsid|mission|yojana|thittam|programme|policy|guideline|charter|budget|"
    r"tanhoda|midh|nmsa|pmksy|insurance|credit|pn_", re.I)
SKIP_RE = re.compile(
    r"season|crop[-_ ]?report|census|/fms/|gallery|media-wall|screen-reader|contact|sitemap|"
    r"team|login|\.(jpe?g|png|gif|svg|zip|docx?|xlsx?|mp4|xml)$", re.I)
BAD_TITLE_RE = re.compile(r"\b404\b|not found|has been blocked|access denied", re.I)


# ---------- chunking / storing ----------

def chunk_text(text: str) -> list[str]:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    chunks, i = [], 0
    while i < len(text):
        end = min(i + CHUNK_SIZE, len(text))
        if end < len(text):  # prefer to cut at a line/sentence boundary
            cut = max(text.rfind("\n", i, end), text.rfind(". ", i, end))
            if cut > i + CHUNK_SIZE * 0.6:
                end = cut + 1
        piece = text[i:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(piece)
        if end >= len(text):
            break
        i = max(end - CHUNK_OVERLAP, i + 1)
    return chunks


def store(text: str, source: str, title: str, kind: str, force: bool) -> int:
    if has_source(source):
        if not force:
            print(f"  = already indexed: {source}", flush=True)
            return 0
        delete_source(source)
    domain = urlparse(source).netloc or "local"
    chunks = [
        {"id": hashlib.md5(f"{source}#{i}".encode()).hexdigest(), "text": t,
         "source": source, "title": (title or source)[:200], "kind": kind, "domain": domain}
        for i, t in enumerate(chunk_text(text))
    ]
    add_chunks(chunks)
    return len(chunks)


# ---------- PDFs ----------

def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def fetch_pdf(url: str) -> Path | None:
    """Download into the cache. Rejects non-PDFs (some sites return an HTML 404 with status 200)."""
    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    path = PDF_CACHE / (hashlib.md5(url.encode()).hexdigest() + ".pdf")
    if path.exists():
        return path
    cap = MAX_PDF_MB * 1024 * 1024
    tmp = path.with_suffix(".part")
    too_big = False
    try:
        with requests.get(url, stream=True, timeout=(8, 40), headers=UA) as r:
            r.raise_for_status()
            if int(r.headers.get("content-length") or 0) > cap:
                print(f"  ! skip (> {MAX_PDF_MB} MB): {url}", flush=True)
                return None
            blocks = r.iter_content(1 << 16)
            first = next(blocks, b"")
            if not first.startswith(b"%PDF"):
                print(f"  ! not a PDF (soft 404?): {url}", flush=True)
                return None
            got = len(first)
            with open(tmp, "wb") as f:
                f.write(first)
                for block in blocks:
                    got += len(block)
                    if got > cap:
                        too_big = True
                        break
                    f.write(block)
    except Exception as e:
        print(f"  ! download failed {url}: {type(e).__name__}", flush=True)
        tmp.unlink(missing_ok=True)
        return None
    if too_big:
        tmp.unlink(missing_ok=True)
        print(f"  ! skip (> {MAX_PDF_MB} MB): {url}", flush=True)
        return None
    tmp.replace(path)
    return path


def ingest_pdf_url(url: str, force: bool):
    if not force and has_source(url):
        print(f"  = already indexed: {url}", flush=True)
        return
    path = fetch_pdf(url)
    if not path:
        return
    try:
        n = store(read_pdf(path), url, url.rsplit("/", 1)[-1], "pdf", force)
        print(f"  PDF {url} -> {n} chunks", flush=True)
    except Exception as e:
        print(f"  ! PDF parse failed {url}: {type(e).__name__}: {e}", flush=True)


def ingest_local_pdfs(force: bool):
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(PDF_DIR.glob("*.pdf")):
        if p.stat().st_size > MAX_PDF_MB * 1024 * 1024:
            print(f"  ! skip (> {MAX_PDF_MB} MB): {p.name}", flush=True)
            continue
        try:
            n = store(read_pdf(p), p.name, p.name, "pdf", force)
            print(f"  local PDF {p.name} -> {n} chunks", flush=True)
        except Exception as e:
            print(f"  ! local PDF failed {p.name}: {type(e).__name__}: {e}", flush=True)


# ---------- web pages (Playwright) ----------

def fetch_html(page, url: str) -> str | None:
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        page.wait_for_timeout(1500)  # let client-side rendering finish
        if resp is None or resp.status >= 400:
            return None
        if "html" not in (resp.headers.get("content-type") or ""):
            return None
        return page.content()
    except Exception as e:
        print(f"  ! fetch failed {url}: {type(e).__name__}", flush=True)
        return None


def parse_html(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")
    links = [(urljoin(url, a["href"]).split("#")[0], a.get_text(" ", strip=True))
             for a in soup.find_all("a", href=True)]
    for t in soup(["script", "style", "nav", "footer", "noscript"]):
        t.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title, soup.get_text("\n"), links


def crawl(entry: dict, page, visited: set[str], force: bool) -> set[str]:
    """Fetch entry['url'] and follow scheme-like same-site links up to entry['depth'].
    Returns PDF links worth downloading."""
    seed = entry["url"]
    host = urlparse(seed).netloc
    max_pages = entry.get("max_pages", 20)
    queue, pdfs, fetched, first = deque([(seed, 0)]), set(), 0, True
    while queue and fetched < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        html = fetch_html(page, url)
        fetched += 1
        if html is None:
            if first:  # host unreachable/blocked: don't waste time on its other links
                print(f"  ! giving up on {seed}", flush=True)
                break
            continue
        first = False
        title, text, links = parse_html(html, url)
        if BAD_TITLE_RE.search(title) or len(text.strip()) < MIN_PAGE_CHARS:
            print(f"  - skip (error/thin page): {url}", flush=True)
        else:
            n = store(text, url, title or url, "web", force)
            print(f"  WEB {url} -> {n} chunks", flush=True)
        for link, label in links:
            if not link.startswith("http") or SKIP_RE.search(link):
                continue
            scheme_like = SCHEME_RE.search(link) or SCHEME_RE.search(label)
            if link.lower().split("?")[0].endswith(".pdf"):
                if scheme_like and urlparse(link).netloc.lower().endswith(ALLOWED_PDF_HOST_SUFFIXES):
                    pdfs.add(link)
            elif depth < entry.get("depth", 0) and urlparse(link).netloc == host and scheme_like:
                queue.append((link, depth + 1))
    return pdfs


# ---------- main ----------

def main(force: bool = False, pdfs_only: bool = False):
    cfg = json.loads(SEEDS_FILE.read_text(encoding="utf-8"))
    pdfs = set(cfg.get("pdfs", []))
    if not pdfs_only:
        from playwright.sync_api import sync_playwright
        entries = [{"url": u, "depth": 0} for u in cfg.get("pages", [])] + cfg.get("crawl", [])
        visited: set[str] = set()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            for entry in entries:
                print(f"Page/crawl: {entry['url']}", flush=True)
                pdfs |= crawl(entry, page, visited, force)
            browser.close()
    print(f"Downloading/reading {len(pdfs)} PDFs", flush=True)
    for u in sorted(pdfs):
        ingest_pdf_url(u, force)
    ingest_local_pdfs(force)
    from .schemes import index_schemes  # structured cards from data/schemes/*.json
    index_schemes()
    print(f"Done. Total chunks in store: {count()}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-index sources already in the store")
    ap.add_argument("--pdfs-only", action="store_true", help="skip web pages")
    args = ap.parse_args()
    main(force=args.force, pdfs_only=args.pdfs_only)
