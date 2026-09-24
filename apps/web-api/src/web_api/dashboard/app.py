"""Streamlit dashboard for the ERP Procurement Agent.

Run with:  streamlit run apps/web-api/src/web_api/dashboard/app.py
"""

import streamlit as st

st.set_page_config(page_title="Procurement Agent", layout="wide")

st.title("ERP Procurement Agent")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Overview", "Vendors", "Categories", "Savings", "Settings"]
)

with tab1:
    st.header("Spend Overview")
    st.info("Connect synthetic data or upload your chart of accounts to get started.")

with tab2:
    st.header("Vendors")

with tab3:
    st.header("Categories")

with tab4:
    st.header("Savings Opportunities")

with tab5:
    st.header("Settings")
