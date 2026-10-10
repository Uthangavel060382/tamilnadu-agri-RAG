import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="TN Agri Schemes", page_icon="🌾", layout="wide")
st.title("🌾 Tamil Nadu Agriculture Schemes")
st.caption("Semantic search over official Tamil Nadu agriculture sources (English / தமிழ்)")


def show_card(card: dict, score: float | None = None):
    """Structured scheme card."""
    with st.container(border=True):
        rel = f"  ·  relevance {score:.2f}" if score is not None else ""
        st.markdown(f"### {card['name']}")
        st.caption(f"{card['jurisdiction']}  ·  {card['category']}"
                   + (f"  ·  part of {card['parent_programme']}" if card.get("parent_programme") else "") + rel)
        if card.get("summary"):
            st.write(card["summary"])
        for label, key in (("Benefits", "benefits"), ("Eligibility", "eligibility"),
                           ("Area", "project_area"), ("Funding", "funding_pattern"),
                           ("How to apply", "how_to_apply"), ("Officers to contact", "contact_officers")):
            if card.get(key):
                st.markdown(f"**{label}:** {card[key]}")
        if card.get("components"):
            with st.expander(f"Components ({len(card['components'])})"):
                for c in card["components"]:
                    line = f"- **{c['name']}**"
                    if c.get("benefit"):
                        line += f" — {c['benefit']}"
                    if c.get("eligibility"):
                        line += f"  \n  _Eligibility:_ {c['eligibility']}"
                    st.markdown(line)
        if card.get("vintage"):
            st.caption(f"⚠️ {card['vintage']}")
        if card.get("source_url"):
            st.markdown(f"[Open source page]({card['source_url']})")


with st.sidebar:
    k = st.slider("Results", 1, 15, 5)
    kind = st.radio("Search in", ["all", "scheme", "document"], format_func=lambda x: {
        "all": "Everything", "scheme": "Scheme cards only", "document": "Documents / pages only"}[x])
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
        st.metric("Indexed chunks", health["chunks"])
        if health.get("ingesting"):
            st.info("Ingestion is running...")
    except Exception:
        st.error("Backend not reachable. Start it with: uvicorn backend.app.main:app")
    if st.button("Re-run ingestion"):
        try:
            st.info(requests.post(f"{API}/ingest", timeout=10).json()["status"])
        except Exception:
            st.error("Backend not reachable")

tab_search, tab_browse = st.tabs(["🔎 Search", "📚 Browse schemes"])

with tab_search:
    q = st.text_input("Ask about a scheme", placeholder="e.g. subsidy for drip irrigation for small farmers")
    if q:
        try:
            with st.spinner("Searching..."):
                resp = requests.get(f"{API}/search", params={"q": q, "k": k, "kind": kind}, timeout=120)
                resp.raise_for_status()
                res = resp.json()["results"]
        except Exception as e:
            st.error(f"Search failed: {e}")
            res = None
        if res == []:
            st.warning("No results. Run ingestion first.")
        for r in res or []:
            if r.get("card"):
                show_card(r["card"], r["score"])
                continue
            with st.container(border=True):
                st.markdown(f"**{r['title']}**  ·  `{r['kind']}`  ·  {r['domain']}  ·  relevance {r['score']:.2f}")
                st.write(r["text"])
                src = r["source"]
                st.markdown(f"[Open source]({src})" if src.startswith("http") else f"File: {src}")

with tab_browse:
    try:
        data = requests.get(f"{API}/schemes", timeout=30).json()
        cats = sorted({s["category"] for s in data["schemes"]})
        juris = sorted({s["jurisdiction"] for s in data["schemes"]})
        c1, c2 = st.columns(2)
        pick_j = c1.multiselect("Jurisdiction", juris, default=juris)
        pick_c = c2.multiselect("Category", cats, default=cats)
        shown = [s for s in data["schemes"] if s["jurisdiction"] in pick_j and s["category"] in pick_c]
        st.caption(f"{len(shown)} of {data['count']} schemes")
        for s in shown:
            show_card(s)
    except Exception as e:
        st.error(f"Could not load schemes: {e}")
