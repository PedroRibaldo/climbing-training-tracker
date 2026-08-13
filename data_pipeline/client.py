"""
Supabase client construction, cached so the app authenticates once per
process rather than on every read/write call.
"""

import os
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

from .models import PipelineConfig


@st.cache_resource
def _create_supabase_client() -> Client:
    """Build the Supabase client once per process and reuse it. Cached with
    st.cache_resource since re-authenticating on every single read/write
    call is avoidable overhead"""
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


def _get_supabase_client(config: Optional['PipelineConfig'] = None) -> Client:
    """Return the shared, cached Supabase client. `config` is accepted (and
    ignored) so every call site can keep passing its PipelineConfig without
    it leaking into the cache key"""
    return _create_supabase_client()
