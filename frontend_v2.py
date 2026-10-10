"""Tamil Nadu agriculture schemes: Streamlit frontend (government-portal layout).

Run:  python -m streamlit run frontend.py     (the API must be running on localhost:8000)
"""
import base64
import html
import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API = "http://localhost:8000"
UI = Path(__file__).parent / "ui"
PAGES = ["Home", "Schemes", "Documents", "About"]
ALL_CATS = "All categories"
MAX_RESULTS = 20  # the API rejects k above 20
EXAMPLES = [
    "Subsidy for tractor and power tiller",
    "Pump set replacement subsidy for SC/ST farmers",
    "Paddy seed subsidy per kg",
    "Rain water harvesting and farm pond grant",
    "Kisan credit card",
    "பயிர் காப்பீடு",
    "நெல் விதை மானியம்",
    "டிராக்டர் மானியம்",
]
SOURCES = [
    ("tnhorticulture.tn.gov.in", "https://tnhorticulture.tn.gov.in/"),
    ("agritech.tnau.ac.in", "https://agritech.tnau.ac.in/"),
    ("erode.nic.in", "https://erode.nic.in/"),
    ("coimbatore.nic.in", "https://coimbatore.nic.in/"),
]

st.set_page_config(page_title="Tamil Nadu agriculture schemes", page_icon=":material/agriculture:",
                   layout="wide", initial_sidebar_state="collapsed")


# ---------- helpers ----------

def esc(value) -> str:
    return html.escape(str(value), quote=True)


_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~$])")


def md_safe(value) -> str:
    """Escape text scraped from the web so it renders literally in st.markdown."""
    return _MD_SPECIAL.sub(r"\\\1", str(value))


def short(text, n: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def clean_passage(text: str) -> str:
    """Make a stored passage readable: join PDF line breaks, drop a cut-off first word, mark trimmed ends."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    lead = ""
    if text and text[0].islower() and " " in text[:25]:  # chunks can start in the middle of a word
        text, lead = text.split(" ", 1)[1], "… "
    tail = "" if text.endswith((".", "!", "?", ")", ":", ";")) else " …"
    return f"{lead}{text}{tail}"


def safe_url(url) -> str | None:
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None


@st.cache_data(show_spinner=False, max_entries=16)
def _read_file(path: str, mtime_ns: int) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_asset(name: str) -> str:
    """Read a file from ui/; the mtime argument makes edits show up without restarting the server."""
    path = UI / name
    return _read_file(str(path), path.stat().st_mtime_ns)


def inject_css():
    st.html(f"<style>{read_asset('styles.css')}</style>")


# ---------- API access (successful responses are cached; failures are not) ----------

@st.cache_data(ttl=30, show_spinner=False)
def api_health() -> dict:
    r = requests.get(f"{API}/health", timeout=4)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300, show_spinner=False)
def api_schemes() -> list[dict]:
    r = requests.get(f"{API}/schemes", timeout=30)
    r.raise_for_status()
    return r.json()["schemes"]


@st.cache_data(ttl=600, max_entries=256, show_spinner=False)
def api_search(q: str, k: int, kind: str) -> list[dict]:
    r = requests.get(f"{API}/search", params={"q": q, "k": k, "kind": kind}, timeout=300)
    r.raise_for_status()
    return r.json()["results"]


def safe(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:  # noqa: BLE001 - shown to the user as a friendly message
        return None, e


def api_down_message(err: Exception | None = None):
    st.error("The search service is not reachable. Start it in another terminal with: "
             "`python -m uvicorn backend.app.main:app --port 8000`", icon=":material/cloud_off:")
    if err is not None:
        st.caption(f"Details: {type(err).__name__}: {short(err, 200)}")


# ---------- navigation callbacks ----------

def go(page: str):
    st.session_state.nav = page


def on_search():
    if st.session_state.get("nav") not in ("Schemes", "Documents"):
        st.session_state.nav = "Schemes"


def pick_example():
    value = st.session_state.get("example")
    if value:
        st.session_state.q = value
        st.session_state.nav = "Schemes"
        st.session_state.example = None


def pick_category(cat: str):
    st.session_state.f_cat = cat
    st.session_state.nav = "Schemes"


# ---------- page chrome ----------

def chrome(n_cards: int, health: dict | None) -> str:
    online = health is not None
    n_docs = max(0, health["chunks"] - n_cards) if online else 0
    logo = base64.b64encode(read_asset("logo.svg").encode()).decode()
    with st.container(key="chrome", gap=None):
        st.html(
            '<div class="tn-util">'
            '<span><b lang="ta">இது அரசு இணையதளம் அல்ல</b> &nbsp;|&nbsp; '
            'Unofficial search tool over Tamil Nadu agriculture department sources</span>'
            f'<span><span class="tn-dot{"" if online else " off"}">●</span> '
            f'{"Search service online" if online else "Search service offline"}</span>'
            '</div>')
        left, mid, right = st.columns([4.6, 4.4, 3], vertical_alignment="center")
        left.html(
            '<div class="tn-brand">'
            f'<img src="data:image/svg+xml;base64,{logo}" alt="">'
            '<div><div class="tn-ta" lang="ta">தமிழ்நாடு வேளாண் திட்டங்கள்</div>'
            '<div class="tn-en">Tamil Nadu Agriculture Schemes</div></div></div>')
        mid.text_input("Search schemes and documents", key="q", bind="query-params", on_change=on_search,
                       placeholder="Search schemes, e.g. subsidy for drip irrigation", label_visibility="collapsed")
        right.html(f'<div class="tn-stats"><b>{n_cards}</b> scheme cards<br><b>{n_docs:,}</b> document passages</div>')
        with st.container(key="navbar"):
            page = st.segmented_control("Menu", PAGES, default="Home", required=True, key="nav",
                                        bind="query-params", label_visibility="collapsed")
    with st.container(key="banner"):
        st.image(read_asset("banner.svg"), width="stretch",
                 alt="Illustration of Tamil Nadu farmland: paddy fields, a temple tower, coconut palms, "
                     "a tractor, sugarcane and a dam")
    return page


def crumb(current: str):
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="crumb"):
        st.button("Home", type="tertiary", on_click=go, args=("Home",), key="crumb_home")
        st.markdown("›")
        st.markdown(current)


def title_bar(title: str, count_text: str):
    st.html(f'<div class="tn-bar"><span>{esc(title)}</span><span class="tn-count">{esc(count_text)}</span></div>')


def footer():
    links = " · ".join(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(name)}</a>'
                       for name, url in SOURCES)
    st.html('<div class="tn-footer"><b>Tamil Nadu Agriculture Schemes search</b><br>'
            f'Indexed sources: {links}<br>'
            'Unofficial tool built for a RAG buildathon. Always confirm amounts, eligibility and dates with the '
            'concerned department before applying.</div>')


# ---------- detail views ----------

def scheme_detail(card: dict):
    with st.container(border=True, key="detail"):
        st.subheader(card["name"])
        st.markdown(f":blue-badge[{md_safe(card['jurisdiction'])}] :gray-badge[{md_safe(card['category'])}]"
                    + (f" :gray-badge[Part of {md_safe(card['parent_programme'])}]" if card.get("parent_programme") else ""))
        if card.get("summary"):
            st.write(md_safe(card["summary"]))
        for label, key in (("Benefits", "benefits"), ("Eligibility", "eligibility"), ("Area", "project_area"),
                           ("Funding", "funding_pattern"), ("Implemented by", "implementing_agency"),
                           ("How to apply", "how_to_apply"), ("Officers to contact", "contact_officers")):
            if card.get(key):
                st.markdown(f"**{label}:** {md_safe(card[key])}")
        if card.get("components"):
            with st.expander(f"Components ({len(card['components'])})", icon=":material/list:"):
                for c in card["components"]:
                    line = f"- **{md_safe(c['name'])}**"
                    if c.get("benefit"):
                        line += f" — {md_safe(c['benefit'])}"
                    if c.get("eligibility"):
                        line += f"  \n  *Eligibility:* {md_safe(c['eligibility'])}"
                    if c.get("officer"):
                        line += f"  \n  *Officer:* {md_safe(c['officer'])}"
                    st.markdown(line)
        if card.get("vintage"):
            st.caption(f":material/warning: {card['vintage']}")
        if safe_url(card.get("source_url")):
            st.link_button("Open source page", card["source_url"], icon=":material/open_in_new:")


def document_detail(doc: dict):
    with st.container(border=True, key="detail"):
        st.subheader(doc["title"])
        st.markdown(f":gray-badge[{md_safe(doc['kind'].upper())}] :gray-badge[{md_safe(doc['domain'])}]")
        st.write(md_safe(clean_passage(doc["text"])))
        if safe_url(doc.get("source")):
            st.link_button("Open source", doc["source"], icon=":material/open_in_new:")


# ---------- pages ----------

def page_home(schemes: list[dict], health: dict | None):
    st.title("Find agriculture schemes in Tamil Nadu")
    st.write("Search subsidies, assistance programmes and policies from official Tamil Nadu agriculture "
             "sources in English or தமிழ். Type a question in the search box above, or start from an example.")
    n_cards = len(schemes)
    cats = sorted({s["category"] for s in schemes})
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.metric("Scheme cards", n_cards, help="Structured records with benefits, eligibility and contacts.")
    with c2.container(border=True):
        st.metric("Document passages", f"{max(0, health['chunks'] - n_cards):,}" if health else "-",
                  help="Passages from policy notes, citizen charters, budget speeches and web pages.")
    with c3.container(border=True):
        st.metric("Categories", len(cats))
    st.subheader("Try a search")
    st.pills("Example searches", EXAMPLES, key="example", on_change=pick_example, label_visibility="collapsed")
    if cats:
        st.subheader("Browse schemes by category")
        counts = pd.Series([s["category"] for s in schemes]).value_counts()
        with st.container(horizontal=True):
            for cat in cats:
                st.button(f"{cat} ({counts[cat]})", on_click=pick_category, args=(cat,), key=f"cat_{cat}")


def page_schemes(schemes: list[dict]):
    crumb("Schemes")
    st.title("Schemes")
    q = (st.session_state.get("q") or "").strip()
    cats = sorted({s["category"] for s in schemes})
    with st.container(border=True, key="filters"):
        with st.form("scheme_filters", border=False):
            with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
                st.html('<span class="tn-flabel">Filter schemes category wise</span>')
                st.selectbox("Category", [ALL_CATS, *cats], key="f_cat", width=270, label_visibility="collapsed")
                st.selectbox("Applies to", ["All", "Tamil Nadu", "Central"], key="f_who", width=170,
                             label_visibility="collapsed")
                st.form_submit_button("Filter", type="primary", icon=":material/search:")
    cat, who = st.session_state.get("f_cat", ALL_CATS), st.session_state.get("f_who", "All")

    if q:
        results, err = safe(api_search, q, MAX_RESULTS, "scheme")
        if err:
            api_down_message(err)
            return
        cards = [r["card"] for r in results if r.get("card")]
        heading = f"Schemes matching “{q}”"
    else:
        cards = sorted(schemes, key=lambda s: (s["jurisdiction"], s["category"], s["name"]))
        heading = "All schemes"
    cards = [c for c in cards if cat in (ALL_CATS, c["category"]) and who in ("All", c["jurisdiction"])]

    with st.container(key="results"):
        title_bar(heading, f"{len(cards)} found")
        if not cards:
            st.info("No schemes match these filters. Try another category, or search the Documents page.",
                    icon=":material/search_off:")
            return
        df = pd.DataFrame({
            "Scheme": [c["name"] for c in cards],
            "Category": [c["category"] for c in cards],
            "Applies to": [c["jurisdiction"] for c in cards],
            "Benefits": [short(c.get("benefits") or c.get("summary"), 150) for c in cards],
            "View": [safe_url(c.get("source_url")) for c in cards],
        }, index=range(1, len(cards) + 1))
        df.index.name = "S.No."
        event = st.dataframe(
            df, key="tbl_schemes", on_select="rerun", selection_mode="single-row",
            selection_default={"selection": {"rows": [0]}},
            column_config={
                "Scheme": st.column_config.TextColumn(width=370),
                "Category": st.column_config.TextColumn(width=150),
                "Applies to": st.column_config.TextColumn(width=100),
                "Benefits": st.column_config.TextColumn(width=360),
                "View": st.column_config.LinkColumn("View / source", display_text="Open", width=100),
            },
            height=min(38 + 35 * len(cards), 460),
            alt="Schemes matching the filters. Select a row to read its details below the table.")
    rows = event.selection.rows
    if rows and rows[0] < len(cards):
        scheme_detail(cards[rows[0]])
    else:
        st.caption("Select a row to see the full details.")


def page_documents():
    crumb("Documents")
    st.title("Documents")
    q = (st.session_state.get("q") or "").strip()
    if not q:
        st.info("Type a question in the search box above to search policy notes, citizen charters, budget "
                "speeches and web pages.", icon=":material/search:")
        st.pills("Example searches", EXAMPLES, key="example", on_change=pick_example, label_visibility="collapsed")
        return
    results, err = safe(api_search, q, MAX_RESULTS, "document")
    if err:
        api_down_message(err)
        return
    domains = sorted({r["domain"] for r in results})
    with st.container(border=True, key="filters"):
        with st.form("doc_filters", border=False):
            with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
                st.html('<span class="tn-flabel">Filter documents source wise</span>')
                st.selectbox("Source", ["All sources", *domains], key="f_dom", width=300, label_visibility="collapsed")
                st.selectbox("Type", ["All types", "pdf", "web"], key="f_kind", width=170, label_visibility="collapsed")
                st.form_submit_button("Filter", type="primary", icon=":material/search:")
    dom, kind = st.session_state.get("f_dom", "All sources"), st.session_state.get("f_kind", "All types")
    docs = [r for r in results if dom in ("All sources", r["domain"]) and kind in ("All types", r["kind"])]

    with st.container(key="results"):
        title_bar(f"Documents matching “{q}”", f"{len(docs)} found")
        if not docs:
            st.info("No documents match these filters.", icon=":material/search_off:")
            return
        df = pd.DataFrame({
            "Document": [d["title"] for d in docs],
            "Type": [d["kind"].upper() for d in docs],
            "Source": [d["domain"] for d in docs],
            "Excerpt": [short(clean_passage(d["text"]), 170) for d in docs],
            "View": [safe_url(d.get("source")) for d in docs],
        }, index=range(1, len(docs) + 1))
        df.index.name = "S.No."
        event = st.dataframe(
            df, key="tbl_docs", on_select="rerun", selection_mode="single-row",
            selection_default={"selection": {"rows": [0]}},
            column_config={
                "Document": st.column_config.TextColumn(width=290),
                "Type": st.column_config.TextColumn(width=70),
                "Source": st.column_config.TextColumn(width=190),
                "Excerpt": st.column_config.TextColumn(width=400),
                "View": st.column_config.LinkColumn("View / download", display_text="Open", width=110),
            },
            height=min(38 + 35 * len(docs), 460),
            alt="Documents matching the search. Select a row to read the matching passage below the table.")
    rows = event.selection.rows
    if rows and rows[0] < len(docs):
        document_detail(docs[rows[0]])
    else:
        st.caption("Select a row to read the matching passage.")


def page_about():
    crumb("About")
    st.title("About this site")
    st.markdown(
        "This is an unofficial search tool built for a RAG buildathon. It indexes public Tamil Nadu agriculture "
        "documents and pages, then finds the passages and scheme records closest in meaning to your question, "
        "in English or தமிழ்.\n\n"
        "**How it works**\n\n"
        "1. Pages and PDFs from the sources below are read and cut into short passages.\n"
        "2. Each passage is converted to a multilingual embedding and stored in a vector database.\n"
        "3. Your question is embedded the same way and the nearest passages and scheme cards are returned.\n\n"
        "**Please note**\n\n"
        "- Scheme cards come from the TNAU paddy schemes page, which was compiled around 2007-2011. "
        "Amounts, names and eligibility may have changed.\n"
        "- The 2025-26 policy note, citizen charters and budget speeches are searchable on the Documents page.\n"
        "- This is not a government website. Confirm details with the department before applying.")
    st.subheader("Indexed sources")
    with st.container(horizontal=True):
        for name, url in SOURCES:
            st.link_button(name, url, icon=":material/open_in_new:")


# ---------- app ----------

inject_css()
health, health_err = safe(api_health)
schemes, _ = safe(api_schemes)
schemes = schemes or []
page = chrome(len(schemes), health)

if health_err:
    api_down_message(health_err)
elif page == "Home":
    page_home(schemes, health)
elif page == "Schemes":
    page_schemes(schemes)
elif page == "Documents":
    page_documents()
else:
    page_about()
footer()
