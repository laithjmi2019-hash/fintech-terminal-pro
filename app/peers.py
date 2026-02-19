import yfinance as yf
import pandas as pd

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
            stock = yf.Ticker(t)
            info = stock.info 
            
            # --- Data Resiliency & Fallbacks ---
            
            # 1. P/E Fallback: Fwd -> Trailing
            pe = info.get('forwardPE')
            if pe is None: pe = info.get('trailingPE')
            
            # 2. Margins Fallback: Operating -> Profit
            margins = info.get('operatingMargins')
            if margins is None: margins = info.get('profitMargins')
            
            # 3. Growth / PEG Fallback
            # We need PEG for ranking.
            peg = info.get('pegRatio')
            
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

def get_peer_comparison(ticker, sector):
    """
    Fetches peer data, ranks them by Multi-Factor Composite Score, and returns formatted DF.
    Ranking Weights:
    - Value (40%): P/E + EV/EBITDA
    - Efficiency (40%): Margins + ROE
    - Growth (20%): PEG
    """
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
    # Rank 1 = Lowest P/E. 
    rank_pe = df['P/E'].rank(ascending=True)
    rank_ev = df['EV/EBITDA'].rank(ascending=True)
    # Average the ranks
    score_value = (rank_pe + rank_ev) / 2
    
    # 2. Efficiency Score (40%) - Higher is Better
    # Rank 1 = Highest Margins.
    rank_margins = df['Margins'].rank(ascending=False)
    rank_roe = df['ROE'].rank(ascending=False)
    score_efficiency = (rank_margins + rank_roe) / 2
    
    # 3. Growth Score (20%) - Lower PEG is "Better" value-growth? 
    # Usually PEG < 1 is good. Lower is better for valuation.
    rank_peg = df['PEG'].rank(ascending=True)
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
    return display_df[cols]

def format_market_cap(val):
    if not val: return "N/A"
    if val > 1e12: return f"${val/1e12:.1f}T"
    if val > 1e9: return f"${val/1e9:.1f}B"
    return f"${val/1e6:.1f}M"
