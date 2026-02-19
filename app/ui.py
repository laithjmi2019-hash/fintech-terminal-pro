import streamlit as st
import yfinance as yf
import pandas as pd

def inject_paywall_css():
    st.markdown("""
    <style>
    .paywall-container {
        position: relative;
    }
    .frosted-glass-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(15, 15, 15, 0.4); /* Dark tint for dark mode */
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        z-index: 999;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        border-radius: 12px;
        text-align: center;
        padding: 20px;
    }
    .paywall-button {
        background-color: #00FF7F; /* Institutional green */
        color: #000000;
        font-weight: 800;
        padding: 12px 24px;
        border-radius: 6px;
        text-decoration: none;
        margin-top: 15px;
        font-size: 1.1rem;
        border: none;
        cursor: pointer;
    }
    </style>
    """, unsafe_allow_html=True)

def inject_global_styles():
    st.markdown("""
    <style>
    /* Hide Streamlit branding and top menus */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Style the main search bar to look massive and premium */
    .stTextInput>div>div>input {
        background-color: #1E2129;
        color: white;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 15px;
        font-size: 1.2rem;
    }
    .stTextInput>div>div>input:focus {
        border-color: #00FF7F;
        box-shadow: 0 0 5px rgba(0, 255, 127, 0.5);
    }
    
    /* Create a 'Card' look for the Matrix output */
    .metric-card {
        background-color: #1E2129;
        border: 1px solid #2D3139;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Neon glowing text for high scores */
    .score-high {
        color: #00FF7F;
        font-weight: 900;
        font-size: 1.5rem;
        text-shadow: 0 0 10px rgba(0, 255, 127, 0.3);
    }
    .score-med {
        color: #FFB020;
        font-weight: 800;
        font-size: 1.5rem;
    }
    .score-low {
        color: #FF4560;
        font-weight: 800;
        font-size: 1.5rem;
    }
    
    .tier-brief {
        color: #8B949E; /* Muted gray for dark mode */
        font-size: 0.85rem;
        font-weight: 400;
        margin-top: -5px;
        margin-bottom: 12px;
        font-style: italic;
        border-bottom: 1px solid #2D3139;
        padding-bottom: 8px;
    }

    /* Mobile-Specific Overrides */
    @media only screen and (max-width: 768px) {
        /* Force 12-Tier cards to stack vertically instead of side-by-side */
        .metric-card {
            width: 100% !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            display: block !important;
        }

        /* Adjust the Sector Comparison Table for small screens */
        .stDataFrame, .stTable {
            overflow-x: auto !important; /* Allow horizontal scrolling for the table */
            display: block !important;
        }

        /* Shrink massive hero headers so they don't wrap weirdly */
        .stTextInput>div>div>input {
            font-size: 1rem !important;
            padding: 10px !important;
        }

        /* Ensure the frosted glass paywall button is centered and clickable */
        .paywall-button {
            width: 90% !important;
            font-size: 1rem !important;
        }

        /* Adjust global market tickers to wrap into two rows */
        header div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

def render_macro_header():
    """
    Renders the top row with live macro data.
    """
    tickers = {
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "Dow Jones": "^DJI",
        "Gold": "GC=F",
        "Bitcoin": "BTC-USD"
    }

    cols = st.columns(len(tickers))
    
    # Fetch individually to avoid MultiIndex complexity and partial failures
    for i, (name, symbol) in enumerate(tickers.items()):
        try:
            ticker_obj = yf.Ticker(symbol)
            # Try history first (most reliable for Close)
            hist = ticker_obj.history(period="5d")
            
            if not hist.empty and len(hist) >= 2:
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                delta = current_price - prev_close
                delta_percent = (delta / prev_close) * 100
                
                cols[i].metric(
                    label=name,
                    value=f"{current_price:,.2f}",
                    delta=f"{delta:.2f} ({delta_percent:.2f}%)"
                )
            else:
                # Fallback to fast_info (sometimes better for Indices/Crypto real-time)
                price = ticker_obj.fast_info.get('last_price')
                prev = ticker_obj.fast_info.get('previous_close')
                
                if price and prev:
                    delta = price - prev
                    pct = (delta / prev) * 100
                    cols[i].metric(
                        label=name,
                        value=f"{price:,.2f}",
                        delta=f"{delta:.2f} ({pct:.2f}%)"
                    )
                else:
                    cols[i].metric(label=name, value="--", delta="No Data")
                    
        except Exception as e:
            cols[i].metric(label=name, value="Error", delta="Failed")

from app.utils import lookup_ticker

def render_search_bar():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        query = st.text_input("Search Ticker or Company (e.g., Microsoft, AAPL)", placeholder="Enter Company Name or Ticker...", key="search_input")
        
        if query:
            # Check if it looks like a ticker (short, no spaces)
            # US Tickers are usually 1-4 chars. Assume 4 or less is a ticker.
            # 5+ (e.g. "Apple", "Tesla") should use lookup unless user is specific.
            # While "GOOGL" is 5, lookup usually handles it fine.
            if query.isalpha() and len(query) <= 4:
                return query.upper()
            
            # Otherwise, try to resolve name
            resolved_ticker = lookup_ticker(query)
            if resolved_ticker:
                st.success(f"Resolved '{query}' to {resolved_ticker}")
                return resolved_ticker
            else:
                st.error(f"Could not find ticker for '{query}'")
                return None
        return None
