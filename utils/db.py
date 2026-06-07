import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

def fetch_all(table: str, order_col: str = None):
    sb = get_supabase()
    q = sb.table(table).select("*")
    if order_col:
        q = q.order(order_col, desc=True)
    res = q.execute()
    return res.data or []

def fetch_where(table: str, col: str, val):
    sb = get_supabase()
    res = sb.table(table).select("*").eq(col, val).execute()
    return res.data or []

def insert_row(table: str, data: dict):
    sb = get_supabase()
    res = sb.table(table).insert(data).execute()
    return res.data

def update_row(table: str, match_col: str, match_val, data: dict):
    sb = get_supabase()
    res = sb.table(table).update(data).eq(match_col, match_val).execute()
    return res.data

def delete_row(table: str, match_col: str, match_val):
    sb = get_supabase()
    res = sb.table(table).delete().eq(match_col, match_val).execute()
    return res.data
