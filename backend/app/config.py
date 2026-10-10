from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"          # drop your own PDFs here
PDF_CACHE = DATA_DIR / "cache_pdfs"  # PDFs downloaded by the crawler
CHROMA_DIR = DATA_DIR / "chroma"
SCHEMES_DIR = DATA_DIR / "schemes"   # structured scheme records (JSON)
SEEDS_FILE = ROOT / "seed_urls.json"

# Records from other states stay in the JSON files but are not searchable in this app.
INCLUDE_JURISDICTIONS = {"Tamil Nadu", "Central"}

# multilingual-e5 supports Tamil and has a 512-token window (MiniLM truncates at 128).
EMBED_MODEL = "intfloat/multilingual-e5-base"
COLLECTION = "tn_agri_schemes_e5_base"  # name tied to the model so embeddings never mix

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MIN_CHUNK_CHARS = 80
MIN_PAGE_CHARS = 300

# PDFs discovered while crawling are only downloaded from these hosts (PDFs listed in seed_urls.json are always allowed).
ALLOWED_PDF_HOST_SUFFIXES = (".gov.in", ".nic.in", "tnau.ac.in")

MAX_PDF_MB = 30
MAX_PDF_PAGES = 250
PAGE_TIMEOUT_MS = 20000
