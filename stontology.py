"""
Streamlit UI for the LLM-Driven Ontology Generator
==================================================

Material Design 3 inspired styling with a light, pleasant palette.
Single-page layout: header / metrics / tabs (graph + artifacts) on top,
chat input pinned at the bottom via ``st.chat_input``.

Run:
    streamlit run stontology.py
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import streamlit as st

from llm_ontology_generator import (
    MOCK_SPEC,
    SYSTEM_PROMPT,
    build_user_prompt,
    call_azure_openai,
    sample_csv,
    slugify,
    spec_to_ontology,
)
from ontology_builder import Ontology
from ontology_intake_processor import (
    build_intake_context,
    build_uploaded_context,
    scan_intake_folder,
    INTAKE_SYSTEM_PROMPT_ADDENDUM,
)


# ---------------------------------------------------------------------------
# Page config + Material Design 3 (light) styling
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Ontology Studio",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# M3 light tokens (approximate): primary #6750A4, secondary #625B71,
# tertiary #7D5260, surface #FEF7FF, surface-container #F3EDF7.
M3_CSS = """
<style>
    :root {
        --md-primary: #6750A4;
        --md-on-primary: #FFFFFF;
        --md-primary-container: #EADDFF;
        --md-on-primary-container: #21005D;
        --md-secondary: #625B71;
        --md-secondary-container: #E8DEF8;
        --md-tertiary: #7D5260;
        --md-tertiary-container: #FFD8E4;
        --md-surface: #FEF7FF;
        --md-surface-container: #F3EDF7;
        --md-surface-container-high: #ECE6F0;
        --md-outline: #79747E;
        --md-on-surface: #1D1B20;
        --md-on-surface-variant: #49454F;
    }

    /* App background + tighter top padding so everything fits one page */
    .stApp {
        background: linear-gradient(180deg, #FEF7FF 0%, #F3EDF7 100%);
        color: var(--md-on-surface);
    }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 6.5rem;  /* leave room for st.chat_input */
        max-width: 1400px;
    }

    /* Hide default Streamlit chrome to maximize page real-estate */
    #MainMenu, footer, header {visibility: hidden;}

    /* Headline */
    .m3-headline {
        font-family: 'Segoe UI', Roboto, system-ui, sans-serif;
        font-size: 1.75rem;
        font-weight: 500;
        color: var(--md-on-primary-container);
        margin: 0 0 0.15rem 0;
    }
    .m3-subhead {
        font-size: 0.92rem;
        color: var(--md-on-surface-variant);
        margin-bottom: 0.6rem;
    }

    /* M3 surface card */
    .m3-card {
        background: var(--md-surface-container);
        border: 1px solid var(--md-surface-container-high);
        border-radius: 16px;
        padding: 14px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06);
    }
    .m3-card-tonal {
        background: var(--md-primary-container);
        color: var(--md-on-primary-container);
        border-radius: 16px;
        padding: 12px 16px;
    }

    /* Metric chips row */
    .m3-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: var(--md-secondary-container);
        color: var(--md-on-surface);
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 6px;
    }
    .m3-chip .v {
        background: var(--md-surface);
        padding: 1px 8px;
        border-radius: 999px;
        font-weight: 600;
        color: var(--md-primary);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: var(--md-on-surface-variant);
        border-radius: 999px;
        padding: 6px 16px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: var(--md-primary-container) !important;
        color: var(--md-on-primary-container) !important;
    }

    /* Chat input – elevated, rounded, pinned at bottom */
    [data-testid="stChatInput"] {
        background: var(--md-surface-container);
        border-top: 1px solid var(--md-surface-container-high);
        box-shadow: 0 -2px 8px rgba(0,0,0,0.04);
    }
    [data-testid="stChatInput"] textarea {
        border-radius: 28px !important;
        background: var(--md-surface) !important;
    }

    /* Buttons */
    .stButton > button, .stDownloadButton > button {
        background: var(--md-primary);
        color: var(--md-on-primary);
        border: none;
        border-radius: 999px;
        padding: 6px 18px;
        font-weight: 500;
        box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background: #543B95;
        color: #fff;
    }

    /* Code blocks (artifacts) */
    pre, code {
        background: var(--md-surface) !important;
        border-radius: 12px !important;
    }

    /* Compact expander */
    .streamlit-expanderHeader {
        background: var(--md-surface-container);
        border-radius: 12px;
    }

    /* Status / messages */
    .m3-status-ok   { color: #146C2E; font-weight: 600; }
    .m3-status-warn { color: #8C4A00; font-weight: 600; }
</style>
"""
st.markdown(M3_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "spec" not in st.session_state:
    st.session_state.spec = None        # raw LLM spec (dict)
if "ont" not in st.session_state:
    st.session_state.ont = None         # built Ontology object
if "name" not in st.session_state:
    st.session_state.name = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "dry_run" not in st.session_state:
    st.session_state.dry_run = False
if "dataset_text" not in st.session_state:
    st.session_state.dataset_text = None
if "dataset_label" not in st.session_state:
    st.session_state.dataset_label = None
if "intake_context" not in st.session_state:
    st.session_state.intake_context = None   # combined text from intake files
if "intake_label" not in st.session_state:
    st.session_state.intake_label = None     # summary label for loaded intake
if "intake_files_summary" not in st.session_state:
    st.session_state.intake_files_summary = None  # list of loaded file names


# ---------------------------------------------------------------------------
# Header + control bar
# ---------------------------------------------------------------------------

hdr_l, hdr_r = st.columns([0.62, 0.38])
with hdr_l:
    st.markdown('<div class="m3-headline">🧬 Ontology Studio</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="m3-subhead">Upload CSVs, PDFs (data model), and DOCX '
        '(data dictionary) — or load the OntologyIntake folder — then chat '
        'to generate an OWL ontology powered by Azure OpenAI.</div>',
        unsafe_allow_html=True,
    )

with hdr_r:
    c1, c2 = st.columns([0.5, 0.5])
    with c1:
        st.toggle("Dry run", key="dry_run",
                  help="Skip Azure call; use a built-in mock spec.")
    with c2:
        if st.button("Reset", use_container_width=True):
            for k in ("spec", "ont", "name", "messages",
                      "dataset_text", "dataset_label",
                      "intake_context", "intake_label",
                      "intake_files_summary"):
                st.session_state[k] = [] if k == "messages" else None
            st.rerun()

# ---------------------------------------------------------------------------
# Data intake panel — file upload + OntologyIntake folder loader
# ---------------------------------------------------------------------------

INTAKE_FOLDER = Path("OntologyIntake")

with st.expander("📂 **Data Intake** — Upload files or load OntologyIntake folder",
                 expanded=st.session_state.intake_context is None):
    intake_c1, intake_c2 = st.columns([0.55, 0.45])

    with intake_c1:
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=["csv", "pdf", "docx", "doc"],
            accept_multiple_files=True,
            help="Upload CSV (data), PDF (data model/ERD), "
                 "DOCX (data dictionary) files.",
        )
        if uploaded_files:
            ctx = build_uploaded_context(uploaded_files)
            if ctx.strip():
                st.session_state.intake_context = ctx
                names = [f.name for f in uploaded_files]
                st.session_state.intake_label = f"{len(names)} uploaded file(s)"
                st.session_state.intake_files_summary = names
                # Also set legacy dataset_text for backward compat
                st.session_state.dataset_text = ctx
                st.session_state.dataset_label = ", ".join(names)

    with intake_c2:
        if INTAKE_FOLDER.is_dir():
            files_info = scan_intake_folder(INTAKE_FOLDER)
            csv_count = len(files_info["csv"])
            pdf_count = len(files_info["pdf"])
            docx_count = len(files_info["docx"])
            st.markdown(
                f"**OntologyIntake folder** detected:  \n"
                f"📊 {csv_count} CSV · 📄 {pdf_count} PDF · "
                f"📝 {docx_count} DOCX"
            )
            if st.button("📥 Load OntologyIntake folder",
                         use_container_width=True):
                ctx = build_intake_context(INTAKE_FOLDER)
                if ctx.strip():
                    st.session_state.intake_context = ctx
                    all_names = (
                        [f.name for f in files_info["csv"]]
                        + [f.name for f in files_info["pdf"]]
                        + [f.name for f in files_info["docx"]]
                    )
                    st.session_state.intake_label = (
                        f"OntologyIntake ({len(all_names)} files)"
                    )
                    st.session_state.intake_files_summary = all_names
                    st.session_state.dataset_text = ctx
                    st.session_state.dataset_label = "OntologyIntake folder"
                    st.success(
                        f"Loaded {len(all_names)} files from OntologyIntake."
                    )
                    st.rerun()
                else:
                    st.warning("No extractable content found in folder.")
        else:
            st.info("No OntologyIntake folder found in the project root.")

    # Show loaded files summary
    if st.session_state.intake_files_summary:
        file_chips = " ".join(
            f'<span class="m3-chip">{n}</span>'
            for n in st.session_state.intake_files_summary
        )
        st.markdown(
            f'<div style="margin-top:6px;">✅ <b>Loaded:</b> {file_chips}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Metric chips
# ---------------------------------------------------------------------------

ont = st.session_state.ont
intake_lbl = st.session_state.intake_label or st.session_state.dataset_label or "—"
chips_html = (
    f'<div class="m3-card" style="margin:6px 0 10px 0;">'
    f'<span class="m3-chip">Classes <span class="v">{len(ont.classes) if ont else 0}</span></span>'
    f'<span class="m3-chip">Object props <span class="v">{len(ont.object_properties) if ont else 0}</span></span>'
    f'<span class="m3-chip">Data props <span class="v">{len(ont.data_properties) if ont else 0}</span></span>'
    f'<span class="m3-chip">Individuals <span class="v">{len(ont.individuals) if ont else 0}</span></span>'
    f'<span class="m3-chip">Mode <span class="v">{"Dry run" if st.session_state.dry_run else "Live"}</span></span>'
    f'<span class="m3-chip">Intake <span class="v">{intake_lbl}</span></span>'
    f'</div>'
)
st.markdown(chips_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tree builders
# ---------------------------------------------------------------------------

def _class_tree_markdown(o) -> str:
    """Return a markdown tree of the class hierarchy (roots → children)."""
    children: dict[str, list[str]] = {n: [] for n in o.classes}
    roots: list[str] = []
    for name, cls in o.classes.items():
        parents = list(cls.parents) if cls.parents else []
        if not parents:
            roots.append(name)
        else:
            for p in parents:
                if p in children:
                    children[p].append(name)
                else:
                    roots.append(name)

    for k in children:
        children[k].sort()
    roots = sorted(set(roots))

    lines: list[str] = []
    visited: set[str] = set()

    def walk(node: str, depth: int) -> None:
        if node in visited:
            lines.append("  " * depth + f"- 🔁 `{node}` (cycle)")
            return
        visited.add(node)
        cls = o.classes[node]
        extras = []
        if cls.disjoint_with:
            extras.append("⊥ " + ", ".join(sorted(cls.disjoint_with)))
        suffix = f"  _( {' · '.join(extras)} )_" if extras else ""
        icon = "🌳" if depth == 0 else "🍃"
        lines.append("  " * depth + f"- {icon} **`{node}`**{suffix}")
        if cls.comment:
            lines.append("  " * (depth + 1) + f"- 📝 _{cls.comment}_")
        for ch in children.get(node, []):
            walk(ch, depth + 1)

    for r in roots:
        walk(r, 0)
    return "\n".join(lines) if lines else "_(no classes)_"


def _properties_tree_markdown(o) -> str:
    """Group object + data properties by their domain class."""
    by_domain: dict[str, dict[str, list]] = {}
    for n, p in o.object_properties.items():
        d = p.domain or "(no domain)"
        by_domain.setdefault(d, {"obj": [], "data": []})["obj"].append((n, p))
    for n, p in o.data_properties.items():
        d = p.domain or "(no domain)"
        by_domain.setdefault(d, {"obj": [], "data": []})["data"].append((n, p))

    lines: list[str] = []
    for domain in sorted(by_domain):
        bucket = by_domain[domain]
        lines.append(f"- 📦 **`{domain}`**")
        for n, p in sorted(bucket["obj"], key=lambda x: x[0]):
            flags = []
            if p.transitive:  flags.append("transitive")
            if p.symmetric:   flags.append("symmetric")
            if p.functional:  flags.append("functional")
            if p.inverse_of:  flags.append(f"inverse: `{p.inverse_of}`")
            extra = f"  _( {' · '.join(flags)} )_" if flags else ""
            lines.append(
                f"  - 🔗 `{n}` → `{p.range_ or '?'}`{extra}"
            )
        for n, p in sorted(bucket["data"], key=lambda x: x[0]):
            lines.append(f"  - 🏷️ `{n}` : `{p.datatype}`")
    return "\n".join(lines) if lines else "_(no properties)_"


def _individuals_tree_markdown(o) -> str:
    """Group individuals by their (first) type, with their assertions nested."""
    by_type: dict[str, list[str]] = {}
    for n, ind in o.individuals.items():
        types = sorted(ind.types) if ind.types else ["(untyped)"]
        by_type.setdefault(types[0], []).append(n)

    lines: list[str] = []
    for cls in sorted(by_type):
        lines.append(f"- 🧱 **`{cls}`**")
        for iname in sorted(by_type[cls]):
            ind = o.individuals[iname]
            all_types = ", ".join(sorted(ind.types))
            lines.append(f"  - 👤 **`{iname}`**  _types: {all_types}_")
            for prop, targets in sorted(ind.object_props.items()):
                for t in sorted(targets):
                    lines.append(f"    - 🔗 `{prop}` → `{t}`")
            for prop, values in sorted(ind.data_props.items()):
                for v in values:
                    lines.append(f"    - 🏷️ `{prop}` = `{v}`")
    return "\n".join(lines) if lines else "_(no individuals)_"


# ---------------------------------------------------------------------------
# Main content tabs (compact, fits one page)
# ---------------------------------------------------------------------------

tab_overview, tab_classes, tab_props, tab_individuals, tab_edit, tab_artifacts = st.tabs(
    ["Overview", "Classes 🌳", "Properties 🌳", "Individuals 🌳", "Edit ➕", "Artifacts"]
)

PANEL_HEIGHT = 340  # keeps the page within one viewport on most laptops

with tab_overview:
    if not ont:
        if st.session_state.intake_context:
            st.markdown(
                '<div class="m3-card-tonal">📂 Data loaded! Now use the chat '
                'below to generate your ontology — e.g. <i>"Create an ontology '
                'from the uploaded Order Management data model and data '
                'dictionary"</i>.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="m3-card-tonal">👋 Start by uploading files '
                '(CSV + PDF + DOCX) or loading the OntologyIntake folder above, '
                'then describe the domain in the chat below — e.g. <i>"Model a '
                'hospital with patients, doctors, appointments and '
                'prescriptions"</i>.</div>',
                unsafe_allow_html=True,
            )
    else:
        spec = st.session_state.spec or {}
        col1, col2 = st.columns([0.5, 0.5])
        with col1:
            st.markdown(f"**Ontology:** `{st.session_state.name}`")
            st.markdown(f"**IRI base:** `{spec.get('iri_base', '—')}`")
            st.markdown(f"**Prefix:** `{spec.get('prefix', '—')}`")
            st.markdown(f"**Description:** {spec.get('description', '—')}")
        with col2:
            issues = ont.check_consistency()
            if not issues:
                st.markdown('<span class="m3-status-ok">● Consistency OK</span>',
                            unsafe_allow_html=True)
            else:
                st.markdown(
                    f'<span class="m3-status-warn">● {len(issues)} issue(s)</span>',
                    unsafe_allow_html=True,
                )
                with st.container(height=PANEL_HEIGHT - 80):
                    for p in issues:
                        st.write(f"- {p}")

with tab_classes:
    if ont:
        with st.container(height=PANEL_HEIGHT, border=False):
            st.markdown(_class_tree_markdown(ont))
    else:
        st.info("No ontology yet — describe a domain in the chat below.")

with tab_props:
    if ont:
        with st.container(height=PANEL_HEIGHT, border=False):
            st.markdown(_properties_tree_markdown(ont))
        st.caption("🔗 = object property · 🏷️ = data property · grouped by domain class")
    else:
        st.info("No ontology yet — describe a domain in the chat below.")

with tab_individuals:
    if ont:
        with st.container(height=PANEL_HEIGHT, border=False):
            st.markdown(_individuals_tree_markdown(ont))
    else:
        st.info("No ontology yet — describe a domain in the chat below.")


# ---------------------------------------------------------------------------
# Edit tab — add classes / properties / individuals / assertions manually
# ---------------------------------------------------------------------------

def _persist_artifacts() -> Path | None:
    """Re-write the four ontology files for the current in-memory ontology."""
    o = st.session_state.ont
    if not o:
        return None
    name = st.session_state.name or "ontology"
    out = Path("ontology")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.ttl").write_text(o.to_turtle(), encoding="utf-8")
    (out / f"{name}.jsonld").write_text(
        json.dumps(o.to_jsonld(), indent=2), encoding="utf-8")
    (out / f"{name}.rdf").write_text(o.to_rdf_xml(), encoding="utf-8")
    (out / f"{name}.nt").write_text(o.to_ntriples(), encoding="utf-8")
    (out / f"{name}.json").write_text(
        json.dumps(o.to_dict(), indent=2), encoding="utf-8")
    if st.session_state.spec is not None:
        (out / f"{name}.raw.json").write_text(
            json.dumps(st.session_state.spec, indent=2), encoding="utf-8")
    return out


with tab_edit:
    with st.container(height=PANEL_HEIGHT, border=False):
        if not ont:
            st.markdown(
                '<div class="m3-card-tonal">No ontology loaded yet. '
                'Create an empty one to start editing, or generate one from '
                'the chat below.</div>',
                unsafe_allow_html=True,
            )
            cnew1, cnew2, cnew3 = st.columns([0.4, 0.3, 0.3])
            with cnew1:
                new_name = st.text_input("Name", value="ontology",
                                         key="new_ont_name")
            with cnew2:
                new_prefix = st.text_input("Prefix", value="ex",
                                           key="new_ont_prefix")
            with cnew3:
                new_iri = st.text_input("IRI base",
                                        value="https://example.org/ont/",
                                        key="new_ont_iri")
            if st.button("✨ Create empty ontology", use_container_width=True):
                st.session_state.ont = Ontology(iri=new_iri, prefix=new_prefix)
                st.session_state.spec = {
                    "ontology_name": new_name, "iri_base": new_iri,
                    "prefix": new_prefix, "description": "",
                    "classes": [], "object_properties": [],
                    "data_properties": [], "individuals": [],
                }
                st.session_state.name = slugify(new_name)
                _persist_artifacts()
                st.rerun()
        else:
            class_names = sorted(ont.classes.keys())
            obj_prop_names = sorted(ont.object_properties.keys())
            data_prop_names = sorted(ont.data_properties.keys())
            ind_names = sorted(ont.individuals.keys())
            xsd_types = ["xsd:string", "xsd:integer", "xsd:double",
                         "xsd:boolean", "xsd:dateTime"]

            ec1, ec2, ec3 = st.columns(3)

            # ---- Add Class (node) ----
            with ec1:
                st.markdown("**➕ Add class (node)**")
                with st.form("form_add_class", clear_on_submit=True):
                    c_name = st.text_input("Class name", key="c_name")
                    c_parent = st.selectbox("Parent (optional)",
                                            options=["(root)"] + class_names,
                                            key="c_parent")
                    c_disjoint = st.multiselect("Disjoint with",
                                                options=class_names,
                                                key="c_disjoint")
                    c_comment = st.text_input("Comment", key="c_comment")
                    if st.form_submit_button("Add class",
                                             use_container_width=True):
                        if not c_name.strip():
                            st.error("Class name is required.")
                        elif c_name in ont.classes:
                            st.error(f"Class '{c_name}' already exists.")
                        else:
                            parents = [] if c_parent == "(root)" else [c_parent]
                            ont.add_class(name=c_name.strip(),
                                          parents=parents,
                                          comment=c_comment,
                                          disjoint_with=c_disjoint)
                            _persist_artifacts()
                            st.success(f"Added class '{c_name}'.")
                            st.rerun()

            # ---- Add Object Property (relation) ----
            with ec2:
                st.markdown("**🔗 Add object property (relation)**")
                with st.form("form_add_obj_prop", clear_on_submit=True):
                    op_name = st.text_input("Property name", key="op_name")
                    op_domain = st.selectbox("Domain", options=class_names,
                                             key="op_domain")
                    op_range = st.selectbox("Range", options=class_names,
                                            key="op_range")
                    op_inverse = st.selectbox(
                        "Inverse of",
                        options=["(none)"] + obj_prop_names,
                        key="op_inverse")
                    fc1, fc2, fc3 = st.columns(3)
                    op_trans = fc1.checkbox("transitive", key="op_trans")
                    op_sym = fc2.checkbox("symmetric", key="op_sym")
                    op_func = fc3.checkbox("functional", key="op_func")
                    if st.form_submit_button("Add relation",
                                             use_container_width=True):
                        if not op_name.strip():
                            st.error("Property name is required.")
                        elif op_name in ont.object_properties:
                            st.error(f"Property '{op_name}' already exists.")
                        elif not class_names:
                            st.error("Add at least one class first.")
                        else:
                            ont.add_object_property(
                                name=op_name.strip(),
                                domain=op_domain,
                                range_=op_range,
                                inverse_of=None if op_inverse == "(none)" else op_inverse,
                                transitive=op_trans,
                                symmetric=op_sym,
                                functional=op_func,
                            )
                            _persist_artifacts()
                            st.success(f"Added relation '{op_name}'.")
                            st.rerun()

            # ---- Add Data Property ----
            with ec3:
                st.markdown("**🏷️ Add data property**")
                with st.form("form_add_data_prop", clear_on_submit=True):
                    dp_name = st.text_input("Property name", key="dp_name")
                    dp_domain = st.selectbox("Domain", options=class_names,
                                             key="dp_domain")
                    dp_type = st.selectbox("Datatype", options=xsd_types,
                                           key="dp_type")
                    dp_comment = st.text_input("Comment", key="dp_comment")
                    if st.form_submit_button("Add data property",
                                             use_container_width=True):
                        if not dp_name.strip():
                            st.error("Property name is required.")
                        elif dp_name in ont.data_properties:
                            st.error(f"Property '{dp_name}' already exists.")
                        elif not class_names:
                            st.error("Add at least one class first.")
                        else:
                            ont.add_data_property(name=dp_name.strip(),
                                                  domain=dp_domain,
                                                  datatype=dp_type,
                                                  comment=dp_comment)
                            _persist_artifacts()
                            st.success(f"Added data property '{dp_name}'.")
                            st.rerun()

            st.divider()
            ec4, ec5, ec6 = st.columns(3)

            # ---- Add Individual ----
            with ec4:
                st.markdown("**👤 Add individual**")
                with st.form("form_add_ind", clear_on_submit=True):
                    i_name = st.text_input("Individual name", key="i_name")
                    i_types = st.multiselect("Types", options=class_names,
                                             key="i_types")
                    if st.form_submit_button("Add individual",
                                             use_container_width=True):
                        if not i_name.strip():
                            st.error("Name is required.")
                        elif i_name in ont.individuals:
                            st.error(f"'{i_name}' already exists.")
                        elif not i_types:
                            st.error("Pick at least one type.")
                        else:
                            try:
                                ont.add_individual(name=i_name.strip(),
                                                   types=i_types)
                                _persist_artifacts()
                                st.success(f"Added '{i_name}'.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

            # ---- Assert object relation between two individuals ----
            with ec5:
                st.markdown("**🔗 Assert relation (triple)**")
                with st.form("form_assert_obj", clear_on_submit=True):
                    a_subj = st.selectbox("Subject", options=ind_names,
                                          key="a_subj")
                    a_pred = st.selectbox("Predicate", options=obj_prop_names,
                                          key="a_pred")
                    a_obj = st.selectbox("Object", options=ind_names,
                                         key="a_obj")
                    if st.form_submit_button("Assert", use_container_width=True):
                        if not (ind_names and obj_prop_names):
                            st.error("Need individuals and object properties.")
                        else:
                            try:
                                ont.assert_object(a_subj, a_pred, a_obj)
                                _persist_artifacts()
                                st.success(f"{a_subj} {a_pred} {a_obj}")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

            # ---- Assert data value on an individual ----
            with ec6:
                st.markdown("**🏷️ Assert data value**")
                with st.form("form_assert_data", clear_on_submit=True):
                    d_subj = st.selectbox("Individual", options=ind_names,
                                          key="d_subj")
                    d_pred = st.selectbox("Data property",
                                          options=data_prop_names,
                                          key="d_pred")
                    d_val = st.text_input("Value (literal)", key="d_val")
                    if st.form_submit_button("Set value",
                                             use_container_width=True):
                        if not (ind_names and data_prop_names):
                            st.error("Need individuals and data properties.")
                        elif d_val == "":
                            st.error("Value required.")
                        else:
                            # best-effort coerce by datatype
                            dt = ont.data_properties[d_pred].datatype
                            value: object = d_val
                            try:
                                if dt == "xsd:integer":
                                    value = int(d_val)
                                elif dt == "xsd:double":
                                    value = float(d_val)
                                elif dt == "xsd:boolean":
                                    value = d_val.strip().lower() in (
                                        "true", "1", "yes", "y")
                            except ValueError:
                                st.error(f"Could not parse '{d_val}' as {dt}.")
                                value = None
                            if value is not None:
                                try:
                                    ont.assert_data(d_subj, d_pred, value)
                                    _persist_artifacts()
                                    st.success(f"{d_subj} {d_pred} = {value}")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))

with tab_artifacts:
    if ont:
        name = st.session_state.name or "ontology"
        ttl = ont.to_turtle()
        jld = json.dumps(ont.to_jsonld(), indent=2)
        rdfxml = ont.to_rdf_xml()
        nt = ont.to_ntriples()
        nat = json.dumps(ont.to_dict(), indent=2)
        raw = json.dumps(st.session_state.spec or {}, indent=2)

        d1, d2, d3, d4, d5, d6 = st.columns(6)
        with d1:
            st.download_button("⬇ Turtle", ttl, file_name=f"{name}.ttl",
                               mime="text/turtle", use_container_width=True)
        with d2:
            st.download_button("⬇ RDF/XML", rdfxml, file_name=f"{name}.rdf",
                               mime="application/rdf+xml", use_container_width=True)
        with d3:
            st.download_button("⬇ N-Triples", nt, file_name=f"{name}.nt",
                               mime="application/n-triples", use_container_width=True)
        with d4:
            st.download_button("⬇ JSON-LD", jld, file_name=f"{name}.jsonld",
                               mime="application/ld+json", use_container_width=True)
        with d5:
            st.download_button("⬇ JSON", nat, file_name=f"{name}.json",
                               mime="application/json", use_container_width=True)
        with d6:
            st.download_button("⬇ Raw spec", raw, file_name=f"{name}.raw.json",
                               mime="application/json", use_container_width=True)

        st.caption(
            "All three of **Turtle**, **RDF/XML**, **N-Triples** and **JSON-LD** "
            "are W3C-standard RDF serializations — load any of them directly "
            "into GraphDB, Stardog, Apache Jena Fuseki, Blazegraph, AWS Neptune, "
            "Neo4j n10s, or any other RDF-compatible triplestore."
        )

        view = st.radio(
            "Preview",
            ["Turtle", "RDF/XML", "N-Triples", "JSON-LD", "JSON", "Raw"],
            horizontal=True, label_visibility="collapsed",
        )
        body = {"Turtle": ttl, "RDF/XML": rdfxml, "N-Triples": nt,
                "JSON-LD": jld, "JSON": nat, "Raw": raw}[view]
        lang = {"Turtle": "turtle", "RDF/XML": "xml", "N-Triples": "text",
                "JSON-LD": "json", "JSON": "json", "Raw": "json"}[view]
        with st.container(height=PANEL_HEIGHT - 60):
            st.code(body, language=lang)
    else:
        st.info("Generate an ontology to see exports.")


# ---------------------------------------------------------------------------
# Chat input (pinned at the bottom by Streamlit)
# ---------------------------------------------------------------------------

prompt = st.chat_input("Describe a domain or ask to create an ontology from uploaded data… "
                       "e.g. 'Create an ontology from the uploaded Order Management data'")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Use intake context (multi-file) if available, fallback to single CSV
    combined_context = (st.session_state.intake_context
                        or st.session_state.dataset_text)
    # Use enriched system prompt when intake data is loaded
    system_prompt = SYSTEM_PROMPT
    if st.session_state.intake_context:
        system_prompt = SYSTEM_PROMPT + INTAKE_SYSTEM_PROMPT_ADDENDUM

    user_prompt = build_user_prompt(prompt, combined_context)

    try:
        with st.spinner("Designing ontology…"):
            if st.session_state.dry_run:
                spec = MOCK_SPEC
            else:
                spec = call_azure_openai(system_prompt, user_prompt)

            ont_obj = spec_to_ontology(spec)
            name = slugify(spec.get("ontology_name") or prompt[:32])

            # Persist artifacts to ./ontology/
            out_dir = Path("ontology")
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{name}.raw.json").write_text(
                json.dumps(spec, indent=2), encoding="utf-8")
            (out_dir / f"{name}.ttl").write_text(
                ont_obj.to_turtle(), encoding="utf-8")
            (out_dir / f"{name}.jsonld").write_text(
                json.dumps(ont_obj.to_jsonld(), indent=2), encoding="utf-8")
            (out_dir / f"{name}.rdf").write_text(
                ont_obj.to_rdf_xml(), encoding="utf-8")
            (out_dir / f"{name}.nt").write_text(
                ont_obj.to_ntriples(), encoding="utf-8")
            (out_dir / f"{name}.json").write_text(
                json.dumps(ont_obj.to_dict(), indent=2), encoding="utf-8")

        st.session_state.spec = spec
        st.session_state.ont = ont_obj
        st.session_state.name = name
        st.session_state.last_out_dir = str(out_dir.resolve())

        issues = ont_obj.check_consistency()
        summary = (
            f"Built **{name}** — {len(ont_obj.classes)} classes, "
            f"{len(ont_obj.object_properties)} object props, "
            f"{len(ont_obj.data_properties)} data props, "
            f"{len(ont_obj.individuals)} individuals. "
            f"Consistency: {'OK ✅' if not issues else f'{len(issues)} issue(s) ⚠️'}  \n"
            f"Saved to `ontology/{name}.{{ttl,jsonld,rdf,nt,json,raw.json}}`"
        )
        st.session_state.messages.append({"role": "assistant", "content": summary})
        st.rerun()

    except SystemExit as e:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"⚠️ Configuration error: {e}"}
        )
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.session_state.messages.append(
            {"role": "assistant", "content": f"❌ Failed to generate: {e}"}
        )
        st.rerun()


# ---------------------------------------------------------------------------
# Chat history (shows last few messages for context)
# ---------------------------------------------------------------------------

if st.session_state.messages:
    with st.container():
        # Show up to 6 most recent messages
        recent = st.session_state.messages[-6:]
        for msg in recent:
            role = msg["role"]
            icon = "👤" if role == "user" else "🤖"
            bg = "var(--md-surface-container)" if role == "user" else "var(--md-primary-container)"
            st.markdown(
                f'<div class="m3-card" style="background:{bg};margin:4px 0;">'
                f'<b>{icon} {role.title()}:</b> {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
