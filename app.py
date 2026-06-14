import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="LALALA Cloud Kitchen",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background-color: #1a1a2e; }
  [data-testid="stSidebar"] * { color: #eee !important; }
  .stButton > button { border-radius: 8px; font-weight: 500; }
  .stButton > button[kind="primary"] { background-color: #e65c00; border: none; color: white; }
  .stButton > button[kind="primary"]:hover { background-color: #cc5200; }
  div[data-testid="metric-container"] { background: #f8f9fa; padding: 12px 16px; border-radius: 10px; border: 1px solid #eee; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

from modules.billing   import billing_page
from modules.inventory import inventory_page
from modules.accounts  import accounts_page
from modules.wastage   import wastage_page
from modules.reports   import reports_page

# ── Sidebar Navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🍽️ LALALA Cloud Kitchen")
    st.markdown("**🍟🍔🥟 Good Food | 🌾 Sig-Nature Feel**")
    st.markdown("** 🌾 Sig-Nature Feel**")
    st.divider()

    page = st.radio("Navigation", [
        "🧾 Billing Counter",
        "🔐 Admin Panel"
    ], label_visibility="collapsed")

    st.divider()
    st.caption("LALALA Cloud Kitchen © 2026")

# ── Billing Counter (Public) ──────────────────────────────────────────────────
if page == "🧾 Billing Counter":
    billing_page()

# ── Admin Panel (Password Protected) ─────────────────────────────────────────
elif page == "🔐 Admin Panel":
    ADMIN_PASSWORD = st.secrets.get("app", {}).get("admin_password", "lalala2026")

    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if not st.session_state.admin_logged_in:
        st.markdown("## 🔐 Admin Login")
        st.markdown("Enter password to access Admin Panel")
        col1, col2 = st.columns([2, 1])
        with col1:
            pwd = st.text_input("Password", type="password", placeholder="Enter admin password")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Login", type="primary", use_container_width=True):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.error("❌ Wrong password")
        # Skip password option
        st.divider()
        if st.button("🚪 Enter without password (Dev mode)"):
            st.session_state.admin_logged_in = True
            st.rerun()
    else:
        # Admin sub-navigation
        with st.sidebar:
            admin_section = st.radio("Admin Sections", [
                "📦 Inventory Status",
                "💰 Accounts Entry",
                "🗑️ Wastage Entry",
                "📊 Report Analytics"
            ])
            st.divider()
            if st.button("🚪 Logout"):
                st.session_state.admin_logged_in = False
                st.rerun()

        if admin_section == "📦 Inventory Status":
            inventory_page()
        elif admin_section == "💰 Accounts Entry":
            accounts_page()
        elif admin_section == "🗑️ Wastage Entry":
            wastage_page()
        elif admin_section == "📊 Report Analytics":
            reports_page()
