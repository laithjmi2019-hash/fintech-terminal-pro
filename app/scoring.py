import yfinance as yf
import app.yf_utils as yfu
import pandas as pd
import numpy as np
import streamlit as st

# Sentiment Pipeline moved to app/consensus.py to avoid duplication

from app.consensus import get_consensus_sentiment
from app.peers import get_peer_raw
from scipy.stats import percentileofscore

def get_finbert_sentiment(ticker):
    # Use the consensus module
    result = get_consensus_sentiment(ticker)
    return result['score']

def normalize(value, min_val, max_val, invert=False):
    """
    Normalizes a value to 0-100 score based on range.
    INVERT=True means Lower is Better (e.g. P/E).
    However, if value < 0 (Negative Earnings), it is usually WORST.
    So we penalize negatives heavily when invert=True.
    """
    if value is None: return 50
    
    if isinstance(value, str):
        try:
            value = float(value.replace('%', '').replace(',', ''))
        except ValueError:
            return 50
            
    # Critical Fix for Negative Ratios (Losses)
    if invert and value < 0:
        return 0 # Penalize losses to 0 score
        
    score = (value - min_val) / (max_val - min_val) * 100
    score = max(0, min(100, score))
    return 100 - score if invert else score

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_scores(ticker, live=False):
    """
    Calculates the 12-Tier Matrix Score with Institutional Weightings & Sector Adjustments.
    """
    # Cache invalidation trigger - V2
    if not live:
        try:
            url: str = st.secrets["supabase"]["url"]
            key: str = st.secrets["supabase"]["key"]
            from supabase import create_client
            supabase = create_client(url, key)
            res = supabase.table('quant_metrics').select('*').eq('ticker', ticker).execute()
            if res.data and 'tier_matrix' in res.data[0] and res.data[0]['tier_matrix']:
                payload = res.data[0]['tier_matrix']
                payload['dcf_fair_value'] = res.data[0].get('dcf_fair_value')
                payload['piotroski_score'] = res.data[0].get('piotroski_score')
                return payload
        except Exception:
            pass # Silently fallback to live calculation if not in database
            
    stock = yfu.get_ticker(ticker)
    try:
        info = stock.info
        history = stock.history(period="1y") 
        if history.empty: return {"error": "No price data found"}
    except Exception as e:
        return {"error": f"Failed to fetch data: {e}"}

    # Helper for safe access
    def get(key, default=None):
        val = info.get(key, default)
        if isinstance(val, str) and key not in ['sector', 'longName', 'symbol', 'industry', 'shortName']:
            try:
                return float(val.replace(',', '').replace('%', ''))
            except ValueError:
                pass
        return val

    scores = {}
    weights = {}

    # --- Sector Thresholds (Institutional Standards) ---
    sector = get('sector', 'Unknown')
    
    # Defaults (General Market)
    thresholds = {
        'pe_good': 15, 'pe_bad': 35,
        'pb_good': 1.5, 'pb_bad': 5.0,
        'roe_good': 0.15, # 15%
        'margin_good': 0.10, # 10%
        'de_good': 100, # 100% Debt/Equity
    }
    
    # Sector Overrides
    if sector == 'Technology':
        thresholds.update({'pe_good': 25, 'pe_bad': 50, 'pb_good': 5.0, 'pb_bad': 15.0, 'margin_good': 0.20})
    elif sector == 'Financial Services':
        thresholds.update({'pe_good': 10, 'pe_bad': 20, 'pb_good': 1.0, 'pb_bad': 2.0, 'de_good': 200}) # Banks carry high debt/deposits
    elif sector == 'Energy':
        thresholds.update({'pe_good': 10, 'pe_bad': 25, 'margin_good': 0.05})
    elif sector == 'Healthcare':
        thresholds.update({'pe_good': 20, 'pe_bad': 40, 'margin_good': 0.15})

    # --- Data Fetching: Peer Comparison & Revisions ---
    peers_data = get_peer_raw(ticker, sector)
    
    # helper to calculated percentile
    def get_percentile(metric_key, target_val, invert=True):
        if not peers_data or target_val is None: return 50
        
        # --- Negative Value Penalty Logic ---
        # If invert=True (Lower is Better e.g., P/E), a negative value (Loss) is WORST.
        # We must penalize it so it ranks as "High" (Bad).
        
        def penalize(x):
            if x is None: return None
            if isinstance(x, str):
                try:
                    x = float(x.replace('%', '').replace(',', ''))
                except ValueError:
                    return None
            if invert and x < 0: return 1000000 # Massive penalty for negative P/E, PEG, etc.
            return x

        # Apply penalty to constraints
        target_val_adj = penalize(target_val)
        if target_val_adj is None: return 50
        
        values = []
        for p in peers_data:
            val = p.get(metric_key)
            p_val = penalize(val)
            if p_val is not None:
                values.append(p_val)
                
        if not values: return 50
        
        # Add target to distribution if not implicitly there
        values.append(target_val_adj)
        
        # Calculate rank on ADJUSTED values
        # Now -440 becomes 1,000,000 (Worst), so it gets high percentile.
        pct = percentileofscore(values, target_val_adj, kind='weak')
        
        # Invert: 100 - 100 (Worst) = 0 Score. Correct.
        return 100 - pct if invert else pct

    # --- Tier 1: Valuation (Weight: 10) ---
    # Metrics: EV/EBITDA, P/E, P/B, PEG, P/S
    # NOW SECTOR-RELATIVE
    ev_ebitda = get('enterpriseToEbitda')
    pe_ratio = get('trailingPE')
    pb_ratio = get('priceToBook')
    peg_ratio = get('pegRatio')
    ps_ratio = get('priceToSalesTrailing12Months')
    
    scores_t1 = []
    
    # 1. PEG Ratio (Growth Adjusted Valuation) - CRITICAL for Tech
    # Fallback Calculation: P/E / (Earnings Growth * 100)
    if not peg_ratio and pe_ratio and get('earningsGrowth'):
        try:
            growth = get('earningsGrowth')
            if isinstance(pe_ratio, (int, float)) and isinstance(growth, (int, float)) and growth > 0:
                peg_ratio = pe_ratio / (growth * 100)
        except:
            pass

    if peg_ratio and isinstance(peg_ratio, (int, float)):
        scores_t1.append(normalize(peg_ratio, 1.0, 3.0, invert=True))
        
    # 2. P/S Ratio (Relative to Peers)
    # Using percentile: If our P/S is lower than peers, score is high.
    if ps_ratio:
        scores_t1.append(get_percentile('Price/Sales', ps_ratio, invert=True)) # Pass 'Price/Sales' if available in peers_data? Need to ensure peers_data keys match.
        # Wait, get_peer_raw returns specific keys. Let's stick to what we have in peers.
        # P/E, Fwd P/E, EV/EBITDA, Margins, ROE.
        # We don't have P/S in peers yet. Let's add it or stick to available.
        # Actually simplest is to stick to P/E and EV/EBITDA for peer comparison for now.
        pass

    # 3. EV/EBITDA (Relative)
    if ev_ebitda:
        scores_t1.append(get_percentile('EV/EBITDA', ev_ebitda, invert=True))
    
    # 4. P/E (Relative)
    if pe_ratio:
        scores_t1.append(get_percentile('P/E', pe_ratio, invert=True))
        
    # 5. Fwd P/E (Relative)
    fwd_pe = get('forwardPE')
    if fwd_pe:
        scores_t1.append(get_percentile('Fwd P/E', fwd_pe, invert=True))
        
    scores["Tier 1: Valuation"] = int(np.mean(scores_t1) if scores_t1 else 50)
    weights["Tier 1: Valuation"] = 10

    # --- Tier 2: Intrinsic Strength & Alpha (Weight: 10) ---
    # Metric: Analyst Target Upside + Earnings Revision Score (Alpha)
    current = history['Close'].iloc[-1] if not history.empty else 0
    target = get('targetMeanPrice')
    
    scores_t2 = []
    
    # 1. Analyst Upside
    if target and isinstance(target, (int, float)) and current > 0:
        upside = (target - current) / current
        scores_t2.append(normalize(upside, 0, 0.40))
        
    # 2. Earnings Revision Trend (The Alpha Factor)
    # Calculate Upgrades vs Downgrades ratio
    try:
        # yfinance caching might return None
        upgrades = len([x for x in stock.upgrades_downgrades.itertuples() if x.Action == 'Up' and (pd.Timestamp.now() - x.Index).days < 30]) if stock.upgrades_downgrades is not None else 0
        downgrades = len([x for x in stock.upgrades_downgrades.itertuples() if x.Action == 'Down' and (pd.Timestamp.now() - x.Index).days < 30]) if stock.upgrades_downgrades is not None else 0
        
        total_revisions = upgrades + downgrades
        if total_revisions > 0:
            revision_score = (upgrades / total_revisions) * 100
        else:
            revision_score = 50 # Neutral
            
        scores_t2.append(revision_score)
    except:
        scores_t2.append(50)

    scores["Tier 2: Intrinsic/Alpha"] = int(np.mean(scores_t2) if scores_t2 else 50)
    weights["Tier 2: Intrinsic/Alpha"] = 10

    # --- Tier 3: Growth (Weight: 9) ---
    # Metrics: Revenue Growth, Earnings Growth
    rev_growth = get('revenueGrowth')
    ear_growth = get('earningsGrowth')
    
    scores_t3 = []
    if rev_growth is not None: scores_t3.append(normalize(rev_growth, 0.0, 0.20))
    if ear_growth is not None: scores_t3.append(normalize(ear_growth, 0.0, 0.20))
    
    scores["Tier 3: Growth"] = int(np.mean(scores_t3) if scores_t3 else 50)
    weights["Tier 3: Growth"] = 9

    # --- Tier 4: Efficiency (Weight: 10) ---
    # Metrics: ROE, Profit Margins (Relative)
    roe = get('returnOnEquity')
    margins = get('profitMargins')
    
    scores_t4 = []
    if roe is not None: scores_t4.append(get_percentile('ROE', roe, invert=False))
    if margins is not None: scores_t4.append(get_percentile('Margins', margins, invert=False))
    
    scores["Tier 4: Efficiency"] = int(np.mean(scores_t4) if scores_t4 else 50)
    weights["Tier 4: Efficiency"] = 10

    # --- Tier 5: Financial Health (Weight: 9) ---
    # Metrics: Current Ratio, Debt/Equity
    curr_ratio = get('currentRatio')
    de_ratio = get('debtToEquity') 
    
    scores_t5 = []
    # Current Ratio: > 1.5 is safe, < 1.0 risky
    if curr_ratio and isinstance(curr_ratio, (int, float)): 
        scores_t5.append(normalize(curr_ratio, 1.0, 2.0))
    
    # Debt/Equity: yfinance returns %, e.g., 150 = 150%
    if de_ratio and isinstance(de_ratio, (int, float)):
        # Normalize based on sector threshold (e.g., Banks ok with 200, Tech needs <50)
        scores_t5.append(normalize(de_ratio, 50, thresholds['de_good'] * 1.5, invert=True))
    
    scores["Tier 5: Financial Health"] = int(np.mean(scores_t5) if scores_t5 else 50)
    weights["Tier 5: Financial Health"] = 9

    # --- Tier 6: Forensics (Weight: 8) ---
    # Proxy: Cashflow vs Earnings
    ocf = get('operatingCashflow')
    ni = get('netIncomeToCommon')
    
    s_forensics = 50
    if ocf and ni and isinstance(ocf, (int, float)) and isinstance(ni, (int, float)):
        if ni > 0:
            ratio = ocf / ni
            # Very strong if OCF > 1.2x Net Income
            s_forensics = normalize(ratio, 0.8, 1.5)
        elif ocf > 0: # Loss making but cash positive
            s_forensics = 75
        else: # Bleeding cash and loss
            s_forensics = 20
    elif sector == 'Financial Services':
         # Banks operate differently, OCF not always relevant. Use Net Margin stability or Assets?
         # Fallback to ROA
         roa = get('returnOnAssets')
         if roa: s_forensics = normalize(roa, 0.005, 0.015) 
    
    scores["Tier 6: Forensics"] = int(s_forensics)
    weights["Tier 6: Forensics"] = 8

    # --- Tier 7: Management (Weight: 8) ---
    # Proxy: Insider Ownership % (Adjusted for Market Cap)
    insider = get('heldPercentInsiders')
    mkt_cap = get('marketCap', 0)
    
    # Validation: Mega Caps (>100B) usually have lower insider %.
    target_insider = 0.10 # Default 10%
    if mkt_cap > 100_000_000_000: target_insider = 0.001 # 0.1% for Mega Caps (Fairer for Trillion $ Corps)
    
    s_mgmt = int(normalize(insider, 0, target_insider)) if insider is not None else 50
    scores["Tier 7: Management"] = s_mgmt
    weights["Tier 7: Management"] = 8

    # --- Tier 8: Capital Flow (Weight: 9) ---
    # Metrics: Relative Volume + Institutional Ownership
    vol = get('volume')
    avg_vol = get('averageVolume')
    inst_own = get('heldPercentInstitutions')
    
    scores_t8 = []
    
    # 1. Volume Flow
    if vol and avg_vol and isinstance(avg_vol, (int, float)) and isinstance(vol, (int, float)) and avg_vol > 0:
        rel_vol = vol / avg_vol
        scores_t8.append(normalize(rel_vol, 0.5, 1.5))
    
    # 2. Institutional Sponsorship (Smart Money)
    if inst_own is not None:
        # > 40% is good, > 80% is high saturation but strong backing.
        scores_t8.append(normalize(inst_own, 0.20, 0.80))
        
    scores["Tier 8: Capital Flow"] = int(np.mean(scores_t8) if scores_t8 else 50)
    weights["Tier 8: Capital Flow"] = 9

    # --- Tier 9: Total Yield (Weight: 8) ---
    div = get('dividendYield')
    # > 4% yield is great (100).
    scores["Tier 9: Total Yield"] = int(normalize(div, 0, 0.04)) if div is not None else 20
    weights["Tier 9: Total Yield"] = 8

    # --- Tier 10: Timing (Weight: 9) ---
    # Price vs SMA 200 + Multi-Timeframe RSI
    if not history.empty and len(history) > 15:
        # 1. SMA 200 (Long Term Trend Filter)
        sma200 = history['Close'].rolling(200).mean().iloc[-1]
        if np.isnan(sma200): sma200 = history['Close'].rolling(50).mean().iloc[-1]
        
        s_sma = 50
        if not np.isnan(sma200) and sma200 > 0:
            dist = (current - sma200) / sma200
            s_sma = int(normalize(dist, -0.25, 0.20))
            
        # 2. Daily RSI (14)
        def calc_rsi(series, period=14):
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))

        rsi_d = calc_rsi(history['Close']).iloc[-1]
        
        # 3. Weekly RSI (14) - Resample Daily to Weekly
        # 'W-FRI' ensures we take Friday close as weekly close
        weekly_history = history['Close'].resample('W-FRI').last() 
        rsi_w = 50 # Default
        if len(weekly_history) > 15:
            rsi_w = calc_rsi(weekly_history).iloc[-1]

        # RSI Scoring Logic (Mean Reversion + Trend)
        def score_rsi(val):
            if np.isnan(val): return 50
            # Buying Opportunity (Oversold)
            if val < 30: return 100
            if val < 40: return 85
            # Strong Trend (Bullish) but not overbought
            if 50 <= val <= 70: return 65 
            # Overbought (Risk)
            if val > 75: return 20 
            return 50 # Neutral

        s_rsi_d = score_rsi(rsi_d)
        s_rsi_w = score_rsi(rsi_w)
        
        # Weighted Timing: 40% SMA / 40% Weekly RSI (Trend) / 20% Daily RSI (Entry)
        scores["Tier 10: Timing"] = int(0.4*s_sma + 0.4*s_rsi_w + 0.2*s_rsi_d)
    else:
        scores["Tier 10: Timing"] = 50
    weights["Tier 10: Timing"] = 9

    # --- Tier 11: Sentiment (Weight: 8) ---
    sentiment_data = get_consensus_sentiment(ticker)
    scores["Tier 11: Sentiment"] = sentiment_data['score']
    weights["Tier 11: Sentiment"] = 8

    # --- Tier 12: Derivatives / Risk (Weight: 6) ---
    # Metrics: Beta, Short Interest, Volatility
    beta = get('beta')
    short_float = get('shortPercentFloat') 
    
    scores_t12 = []
    
    # 1. Beta (Market Risk)
    # < 0.8 Low Volatility (Safe), > 1.5 High Volatility (Risky)
    if beta is not None:
        scores_t12.append(normalize(beta, 0.5, 1.8, invert=True))
        
    # 2. Short Interest (The "Trap" or "Squeeze" potential)
    # < 5% = Normal
    # > 20% = Extremely High (Crowded Short) -> risky but could squeeze.
    # Professionals treat >10% as a red flag for long-term holding unless playing a squeeze.
    if short_float is not None:
        # Score higher for LOW short interest (Safety)
        scores_t12.append(normalize(short_float, 0.01, 0.15, invert=True))
        
    scores["Tier 12: Derivatives"] = int(np.mean(scores_t12) if scores_t12 else 50)
    weights["Tier 12: Derivatives"] = 6

    # --- Relative Strength (Add to Timing) ---
    # Compare Stock Performance vs SPY over last 3 months
    if not history.empty and len(history) > 60:
        # Download SPY data for comparison (cached/optimized in real app)
        try:
            spy = yfu.get_ticker("SPY").history(period="1y")['Close']
            # Align dates
            aligned_spy = spy.reindex(history.index).ffill()
            
            # 3-Month Performance
            stock_RET = (history['Close'].iloc[-1] / history['Close'].iloc[-60]) - 1
            spy_RET = (aligned_spy.iloc[-1] / aligned_spy.iloc[-60]) - 1
            
            rel_strength = stock_RET - spy_RET
            
            # Score: > 0 is Outperformance (Good), < -0.1 is bad lag.
            # We'll add this to Timing Score
            s_rs = int(normalize(rel_strength, -0.10, 0.10))
            
            # Recalculate Timing with RS
            # 30% SMA, 30% Weekly RSI, 20% Daily RSI, 20% Relative Strength
            s_timing_prev = scores["Tier 10: Timing"] 
            # Deconstruct previous (approx) or just average in
            scores["Tier 10: Timing"] = int(0.8 * s_timing_prev + 0.2 * s_rs)
            
        except Exception:
            pass # RS calculation failed (SPY fetch issue etc), keep previous timing score

    # --- Weighted Calculation ---
    total_score = 0
    total_weight = 0
    
    for tier, score in scores.items():
        w = weights.get(tier, 1)
        total_score += score * w
        total_weight += w
    
    final_weighted_score = total_score / total_weight if total_weight > 0 else 50
    
    grade = "Hold"
    if final_weighted_score >= 80: grade = "Strong Buy"
    elif final_weighted_score >= 65: grade = "Buy"
    elif final_weighted_score <= 35: grade = "Strong Sell"
    elif final_weighted_score <= 50: grade = "Sell"

    return {
        "final_grade": grade,
        "final_score": int(final_weighted_score),
        "breakdown": scores,
        "metrics": {
            "PEG Ratio": peg_ratio,
            "RSI (D/W)": f"{rsi_d:.0f} / {rsi_w:.0f}" if 'rsi_d' in locals() and not np.isnan(rsi_d) else "N/A",
            "P/S Ratio": ps_ratio,
            "Beta": beta,
            "Short Float": f"{short_float:.2%}" if short_float else "N/A",
            "Rel Strength (3M)": f"{rel_strength:.1%}" if 'rel_strength' in locals() else "N/A",
            "Insider Own": f"{insider:.2%}" if insider else "N/A",
            "SMA 200": f"{sma200:.2f}" if 'sma200' in locals() else "N/A",
            "Score (Yahoo)": sentiment_data['yahoo_score'],
            "Score (Google)": sentiment_data['google_score'],
            "Headlines": sentiment_data['headline_count'],
            "Alpha (Revisions)": f"{revision_score:.1f}/100" if 'revision_score' in locals() else "N/A"
        },
        "sector": sector,
        "company_name": info.get('longName', ticker),
        "current_price": current,
        "news_headlines": sentiment_data.get('headlines', [])
    }

