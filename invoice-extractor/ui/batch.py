"""Batch Scan: process every file in the invoices/ folder (replaces the old Scanner.py run)."""

import pandas as pd
import streamlit as st

import config
from scripts.scan_folder import list_invoice_files, scan_folder
from ui import components

st.title(":material/folder_open: Batch Scan")
folder = config.INVOICE_FOLDER
folder.mkdir(parents=True, exist_ok=True)
st.caption(f"Drop PDFs and images into **{folder}** and scan them all at once. "
           "Files already saved are skipped automatically.")
components.ocr_warning()

files = list_invoice_files(folder)
with st.container(border=True):
    top = st.columns([3, 1])
    top[0].markdown(f"**{len(files)}** file(s) waiting in the folder")
    if top[1].button("Refresh", icon=":material/refresh:", width="stretch"):
        st.rerun()
    if files:
        st.dataframe(pd.DataFrame({"file": [f.name for f in files],
                                   "size (KB)": [round(f.stat().st_size / 1024, 1) for f in files]}),
                     hide_index=True, width="stretch", height=min(38 * len(files) + 38, 300))

if st.button("Scan invoices folder", type="primary", icon=":material/play_arrow:", disabled=not files):
    with st.status("Scanning...", expanded=True) as status:
        bar = st.progress(0.0)
        results = scan_folder(folder, on_progress=lambda done, total, name: bar.progress(
            done / total, text=f"Reading {name} ({done + 1}/{total})"))
        bar.progress(1.0, text="Done")
        status.update(label="Scan complete", state="complete", expanded=False)
    counts = pd.Series([r["status"] for r in results]).value_counts().to_dict()
    a, b, c = st.columns(3)
    a.metric("Added", counts.get("ADDED", 0))
    b.metric("Flagged for review", counts.get("REVIEW", 0))
    c.metric("Already saved", counts.get("EXISTS", 0))
    st.dataframe(pd.DataFrame(results), hide_index=True, width="stretch", column_config={
        "total_amount": st.column_config.NumberColumn("Total", format="₹ %.2f")})
    st.toast("Batch scan finished", icon="📂")
