import yfinance as yf
import app.yf_utils as yfu
import pandas as pd
import streamlit as st

# Hardcoded Sector Leaders for Comparison
# Hardcoded Sector Leaders for Comparison (Expanded to 6+)
SECTOR_PEERS = {
    'Technology': ['MSFT', 'AAPL', 'NVDA', 'ORCL', 'ADBE', 'CRM', 'AMD'],
    'Financial Services': ['JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'BLK'],
    'Energy': ['XOM', 'CVX', 'SHEL', 'TTE', 'BP', 'COP', 'EOG'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'LLY', 'MRK', 'ABBV', 'TMO'],
    'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'LOW'],
    'Industrials': ['CAT', 'GE', 'HON', 'UPS', 'DE', 'LMT', 'BA'],
    'Consumer Defensive': ['WMT', 'PG', 'KO', 'PEP', 'COST', 'PM', 'MO'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'TMUS', 'VZ'],
    'Basic Materials': ['LIN', 'BHP', 'RIO', 'SHW', 'FCX', 'NEM', 'APD'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'VICI'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'PEG']
}

def get_peers(ticker, sector):
    """
    Returns a list of peer tickers based on sector, excluding the current ticker.
    """
    candidates = SECTOR_PEERS.get(sector, ['SPY', 'QQQ', 'DIA']) # Default to Indices if unknown
    peers = [p for p in candidates if p != ticker][:6] # Allow up to 6 peers
    return peers

@st.cache_data(ttl=3600, show_spinner=False)
def get_peer_raw(ticker, sector):
    """
    Fetches raw key metrics for the ticker and its peers.
    Implements Data Resiliency: Fallbacks for missing data.
    """
    peers = get_peers(ticker, sector)
    all_tickers = [ticker] + peers
    
    data = []
    
    for t in all_tickers:
        try:
            stock = yfu.get_ticker(t)
            info = stock.info 
            
            # --- Data Resiliency & Fallbacks ---
            
            # 1. P/E Fallback: Trailing -> Fwd (Trailing is more stable than forward estimates)
            pe = info.get('trailingPE')
            if pe is None: pe = info.get('forwardPE')
            
            # 2. Margins Fallback: Profit -> Operating
            margins = info.get('profitMargins')
            if margins is None: margins = info.get('operatingMargins')
            
            # 3. Growth / PEG Fallback
            # We need PEG for ranking.
            peg = info.get('pegRatio')
            
            # Robust Fallback Logic if PEG is missing
            if peg is None and pe is not None:
                # Priority 1: Market Standard (PEG = P/E / Earnings Growth)
                g_earn = info.get('earningsGrowth')
                if g_earn and g_earn > 0:
                    peg = pe / (g_earn * 100)
                else:
                    # Priority 2: Revenue Growth (Reliable for high growth / unprofitable tech)
                    g_rev = info.get('revenueGrowth')
                    if g_rev and g_rev > 0:
                        peg = pe / (g_rev * 100)
                    else:
                        # Priority 3: Ultimate Fallback (Sustainable Growth Rate)
                        # g = ROE * (1 - PayoutRatio)
                        roe = info.get('returnOnEquity')
                        payout = info.get('payoutRatio') or 0.0 # Assume 0 if missing
                        if roe and roe > 0:
                            g_sgr = roe * (1 - payout)
                            if g_sgr > 0.01: # Avoid division by zero
                                peg = pe / (g_sgr * 100)
            
            # 4. ROE (No fallback usually, maybe ROA? Stick to ROE)
            roe = info.get('returnOnEquity')
            
            ev_ebitda = info.get('enterpriseToEbitda')
            
            data.append({
                "Ticker": t,
                "Price": info.get('currentPrice'),
                "P/E": pe,
                "Fwd P/E": info.get('forwardPE'), # Keep original for display if needed
                "Trailing P/E": info.get('trailingPE'),
                "EV/EBITDA": ev_ebitda,
                "Margins": margins,
                "ROE": roe,
                "PEG": peg,
                "Mkt Cap": info.get('marketCap'),
                "Price/Sales": info.get('priceToSalesTrailing12Months')
            })
        except Exception:
            continue
            
    return data

def get_peer_comparison(ticker, sector, live=False):
    """
    Fetches peer data, ranks them by Multi-Factor Composite Score, and returns formatted DF.
    Ranking Weights:
    - Value (40%): P/E + EV/EBITDA
    - Efficiency (40%): Margins + ROE
    - Growth (20%): PEG
    """
    # Cache invalidation trigger - V2
    if not live:
        try:
            url: str = st.secrets["supabase"]["url"]
            key: str = st.secrets["supabase"]["key"]
            from supabase import create_client
            supabase = create_client(url, key)
            res = supabase.table('quant_metrics').select('peer_comparison').eq('ticker', ticker).execute()
            if res.data and 'peer_comparison' in res.data[0] and res.data[0]['peer_comparison']:
                return pd.DataFrame(res.data[0]['peer_comparison'])
        except Exception:
            pass # Silently fallback to live calculation if not in database
            
    raw_data = get_peer_raw(ticker, sector)
    if not raw_data: return pd.DataFrame()
    
    df = pd.DataFrame(raw_data)
    
    # --- Data Filling (Industry Average) ---
    # Convert columns to numeric, coercing errors
    cols_to_fill = ['P/E', 'EV/EBITDA', 'Margins', 'ROE', 'PEG']
    for col in cols_to_fill:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        # Fill NaN with mean of the group (Industry Average Proxy)
        if df[col].isnull().any():
            mean_val = df[col].mean()
            df[col] = df[col].fillna(mean_val) # Fill with average
            
    # --- Multi-Factor Ranking Logic ---
    
    # 1. Value Score (40%) - Lower is Better
    # Rank 1 = Lowest P/E (BUT negative P/E means loss, so it should be ranked worst)
    # Strategy: Replace negative values with a High Number (Penalty) before ranking
    
    # Create temp columns for ranking with robust penalty logic
    # Rule: Negative Valuation Ratios (P/E, EV/EBITDA, PEG) usually imply losses.
    # We want to rank these as "Worst" (High Rank Number).
    # Normal Positive Ratios: Lower is Better.
    
    def penalize_negatives(x):
        if pd.isnull(x): return 1000 # Treat missing as bad (or use mean if preferred, but penalty is safer for ranking)
        if x < 0: return 1000 # Penalize negative values (Losses)
        return x

    df['PE_RankValue'] = df['P/E'].apply(penalize_negatives)
    df['EV_RankValue'] = df['EV/EBITDA'].apply(penalize_negatives)
    
    rank_pe = df['PE_RankValue'].rank(ascending=True)
    rank_ev = df['EV_RankValue'].rank(ascending=True)
    
    # Average the ranks
    score_value = (rank_pe + rank_ev) / 2
    
    # 2. Efficiency Score (40%) - Higher is Better
    # Rank 1 = Highest Margins.
    rank_margins = df['Margins'].rank(ascending=False)
    rank_roe = df['ROE'].rank(ascending=False)
    score_efficiency = (rank_margins + rank_roe) / 2
    
    # 3. Growth Score (20%) - Lower PEG is "Better" value-growth? 
    # Usually PEG < 1 is good. Lower is better for valuation.
    # Penalize negative PEG (losses or negative growth)
    df['PEG_RankValue'] = df['PEG'].apply(penalize_negatives)
    
    rank_peg = df['PEG_RankValue'].rank(ascending=True)
    score_growth = rank_peg
    
    # Composite Score (Weighted Sum of Ranks)
    # Lower score is better (since Rank 1 is best)
    # Weights: 0.4, 0.4, 0.2
    df['composite_rank'] = (0.4 * score_value) + (0.4 * score_efficiency) + (0.2 * score_growth)
    
    # Sort by Best Fundamentals (Lowest Composite Rank)
    df = df.sort_values('composite_rank', ascending=True)
    
    # Assign Rank Column
    df.insert(0, "🏆 Rank", range(1, len(df) + 1))
    
    # --- Formatting for Display ---
    def format_pct(x): return f"{x:.1%}" if pd.notnull(x) else "N/A*"
    def format_num(x): return f"{x:.1f}" if pd.notnull(x) else "N/A*"
    
    display_df = df.copy()
    display_df['Margins'] = display_df['Margins'].apply(format_pct)
    display_df['ROE'] = display_df['ROE'].apply(format_pct)
    display_df['P/E'] = display_df['P/E'].apply(format_num)
    display_df['EV/EBITDA'] = display_df['EV/EBITDA'].apply(format_num)
    display_df['PEG'] = display_df['PEG'].apply(format_num)
    display_df['Mkt Cap'] = display_df['Mkt Cap'].apply(format_market_cap)
    
    # Select Columns for Display
    # Adding PEG and ROE to show the 'Why'
    cols = ["🏆 Rank", "Ticker", "Price", "P/E", "EV/EBITDA", "Margins", "ROE", "PEG", "Mkt Cap"]
    final_df = display_df[cols].rename(columns={"PEG": "PEG (v5)"})
    return final_df

def format_market_cap(val):
    if not val: return "N/A"
    if val > 1e12: return f"${val/1e12:.1f}T"
    if val > 1e9: return f"${val/1e9:.1f}B"
    return f"${val/1e6:.1f}M"
