import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def init_supabase():
    try:
        if "supabase" not in st.secrets:
            # st.warning("Supabase secrets not found. Auth disabled.")
            return None
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        # st.error(f"Supabase connection error: {e}")
        return None

def check_ip_status(ip_address):
    """
    Returns the number of searches performed by this IP.
    """
    supabase: Client = init_supabase()
    if not supabase:
        return 0 # Fail open if DB is down/unconfigured check? Or fail closed? Fail open for dev.
    
    try:
        # Count records for this IP
        response = supabase.table('search_logs').select('*', count='exact').eq('ip_address', ip_address).execute()
        return response.count if response.count is not None else 0
    except Exception as e:
        # st.error(f"DB Error: {e}")
        return 0

def increment_strike(ip_address, ticker):
    """
    Log a search for this IP.
    """
    supabase: Client = init_supabase()
    if not supabase:
        return

    try:
        supabase.table('search_logs').insert({"ip_address": ip_address, "ticker": ticker}).execute()
    except Exception as e:
        st.error(f"Failed to log search: {e}")

def render_login_form():
    st.subheader("Professional Access Required")
    st.markdown("You have reached the free search limit. Enter your email to receive a secure login link.")
    
    email = st.text_input("Work Email", placeholder="trader@fund.com")
    
    if st.button("Send Magic Link"):
        supabase: Client = init_supabase()
        if supabase:
            try:
                # Magic Link Login
                # Redirect URL should point to local or deployed app
                data = supabase.auth.sign_in_with_otp({"email": email})
                st.success(f"Magic Link sent to {email}. Check your inbox.")
            except Exception as e:
                st.error(f"Login failed: {e}")

