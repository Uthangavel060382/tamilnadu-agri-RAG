# TN Agriculture Schemes RAG

Flow: Playwright + PDFs -> chunks -> ChromaDB -> FastAPI `/search` -> Streamlit UI.

```
pip install -r requirements.txt
playwright install chromium
python -m backend.app.ingest                 # Step 1: build vector DB (edit seed_urls.json first)
uvicorn backend.app.main:app --reload        # Step 2: API on :8000
streamlit run frontend.py                    # UI on :8501
```

Drop extra PDFs into `data/pdfs/` and re-run ingestion.
