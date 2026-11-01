"""
Invoice Extractor - Streamlit user interface (pure Python, no HTML/CSS/JS).

Run with:  streamlit run app.py

This file only sets up the page and the navigation; every page lives in
its own script in the ui/ folder:
    Overview  : Home (insights, quick actions, recent invoices)
    Invoices  : Upload & Extract, Records
    Insights  : Dashboard, Budgets
    Tools     : Batch Scan, Settings
"""

import streamlit as st

from ui import components

PAGES = {
    "Overview": [
        st.Page("ui/home.py", title="Home", icon=":material/home:", default=True),
    ],
    "Invoices": [
        st.Page("ui/upload.py", title="Upload & Extract", icon=":material/upload_file:"),
        st.Page("ui/records.py", title="Records", icon=":material/table_view:"),
    ],
    "Insights": [
        st.Page("ui/dashboard.py", title="Dashboard", icon=":material/monitoring:"),
        st.Page("ui/budgets.py", title="Budgets", icon=":material/savings:"),
    ],
    "Tools": [
        st.Page("ui/batch.py", title="Batch Scan", icon=":material/folder_open:"),
        st.Page("ui/settings.py", title="Settings", icon=":material/settings:"),
    ],
}


def main():
    st.set_page_config(page_title="Invoice Extractor", page_icon="🧾", layout="wide")
    components.bootstrap()
    page = st.navigation(PAGES)
    st.logo("assets/logo.png", size="large")
    components.sidebar_status()
    components.show_flash()
    page.run()


if __name__ == "__main__":
    main()
