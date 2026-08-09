"""
Supabase client construction for the auth layer. Every browser session
gets its own client instance here - never cached or shared - since once a
client's auth state carries a signed-in user's tokens, sharing it across
concurrent users would leak sessions between them.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client


def new_client() -> Client:
    """A fresh Supabase client, authenticated with the anon key only. Used
    both for login/signup attempts and, after a successful one, as the
    per-session client stored in st.session_state."""
    load_dotenv()  # no-op if there's no .env file

    try:
        if "supabase" in st.secrets:
            return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    except Exception:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not found. Set SUPABASE_URL/SUPABASE_KEY in a .env file "
            "for local dev, or add a [supabase] url/key block to Streamlit secrets in the cloud."
        )
    return create_client(url, key)
