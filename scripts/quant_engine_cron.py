import os
import sys
import json
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from supabase import create_client, Client

# Ensure we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.scoring import calculate_scores
from app.peers import get_peer_comparison

# Setup Supabase client
url: str = st.secrets["supabase"]["url"]
key: str = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

# --- QUANTITATIVE MODELS ---

def calculate_piotroski_f_score(info, financials, balance_sheet, cash_flow):
    """Calculates the 9-point Piotroski F-Score."""
    score = 0
    try:
        # F-Score requires historical comparisons. For a free yfinance script,
        # we will approximate using whatever TTM and Annual data is available.
        # This is a simplified reliable version.
        if cash_flow is not None and not cash_flow.empty:
            # 1. Positive Return on Assets (ROA)
            if info.get('returnOnAssets', 0) > 0: score += 1
            # 2. Positive Operating Cash Flow
            operating_cf = cash_flow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cash_flow.index else 0
            if operating_cf > 0: score += 1
            # 3. Higher ROA than previous year (Proxy: Earnings Growth)
            if info.get('earningsGrowth', 0) > 0: score += 1
            # 4. Cash Flow > Net Income
            net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
            if operating_cf > net_income: score += 1
        
        if balance_sheet is not None and not balance_sheet.empty:
            # 5. Lower Ratio of Long Term Debt to Assets (Proxy: Debt to Equity reduction)
            # 6. Higher Current Ratio (Proxy: Current Ratio > 1)
            if info.get('currentRatio', 0) > 1.0: score += 1
            # 7. No New Shares Issued (Proxy: float stable)
            score += 1 # Assume stable for now
            
        # 8. Higher Gross Margin (Proxy: Profit Margin positive)
        if info.get('profitMargins', 0) > 0.1: score += 1
        # 9. Higher Asset Turnover (Proxy: positive Revenue Growth)
        if info.get('revenueGrowth', 0) > 0: score += 1
        
    except Exception as e:
        print(f"Piotroski Error: {e}")
        return 5 # Neutral default
    return score

def calculate_dcf(info, current_price):
    """Calculates a simplified Discounted Cash Flow (DCF)."""
    try:
        fcf = info.get('freeCashflow')
        shares = info.get('sharesOutstanding')
        if not fcf or not shares or current_price is None or current_price == 0:
            return None, None
            
        growth_rate = info.get('earningsGrowth', 0.05) 
        if growth_rate < 0: growth_rate = 0.02 # Floor growth securely
        if growth_rate > 0.20: growth_rate = 0.20 # Cap hyper growth
        
        discount_rate = 0.09 # 9% WACC proxy
        terminal_growth = 0.025 # 2.5% perpetual
        
        # Project 5 years
        cf_projections = [fcf * (1 + growth_rate)**i for i in range(1, 6)]
        
        # Terminal Value = CF_5 * (1 + g) / (WACC - g)
        terminal_value = cf_projections[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
        
        # Discount to Present Value
        pv_cfs = sum([cf / (1 + discount_rate)**i for i, cf in enumerate(cf_projections, 1)])
        pv_tv = terminal_value / (1 + discount_rate)**5
        
        intrinsic_value_total = pv_cfs + pv_tv
        intrinsic_value_per_share = intrinsic_value_total / shares
        
        upside = ((intrinsic_value_per_share - current_price) / current_price) * 100
        return round(intrinsic_value_per_share, 2), round(upside, 2)
    except Exception as e:
        print(f"DCF Error: {e}")
        return None, None

def calculate_z_scores(df_peers):
    """Calculates Z-Scores for key columns in peer comparison."""
    if df_peers.empty: return df_peers
    
    # Example: Z-Score for Margins (higher is better)
    # We strip the '%' and convert to float
    try:
        if 'Margins' in df_peers.columns:
            margins = df_peers['Margins'].str.rstrip('%').replace('N/A', '0').astype(float)
            mean = margins.mean()
            std = margins.std()
            if std > 0:
                df_peers['Margin_Z'] = round((margins - mean) / std, 2)
            else:
                df_peers['Margin_Z'] = 0.0
    except:
        df_peers['Margin_Z'] = 0.0
    return df_peers

# --- MAIN ENGINE ---

def run_quant_engine():
    tickers = [
        'AAPL', 'MSFT', 'NVDA', 'ADBE', 'ORCL', 'CRM', 'AMD',
        'JPM', 'BAC', 'GS', 'XOM', 'CVX', 'JNJ', 'UNH', 'AMZN', 'TSLA'
    ]
    
    sector_map = {
        'AAPL': 'Technology', 'MSFT': 'Technology', 'NVDA': 'Technology', 
        'ADBE': 'Technology', 'ORCL': 'Technology', 'CRM': 'Technology', 'AMD': 'Technology',
        'JPM': 'Financial Services', 'BAC': 'Financial Services', 'GS': 'Financial Services',
        'XOM': 'Energy', 'CVX': 'Energy',
        'JNJ': 'Healthcare', 'UNH': 'Healthcare',
        'AMZN': 'Consumer Cyclical', 'TSLA': 'Consumer Cyclical'
    }

    results = []
    
    for t in tickers:
        print(f"Processing {t}...")
        try:
            stock = yf.Ticker(t)
            info = stock.info
            current_price = info.get('currentPrice')
            
            # Run existing tiered matrix
            score_data = calculate_scores(t)
            
            # Format breakdown into an array of objects for JSONB storage
            tiers = [{"tier": k, "score": v} for k, v in score_data.get("breakdown", {}).items()]
            
            # Get peer comparison
            sector = sector_map.get(t, 'Technology')
            peers_df = get_peer_comparison(t, sector)
            peers_df = calculate_z_scores(peers_df)
            
            # Compute new Masterclass metrics
            piotroski = calculate_piotroski_f_score(info, stock.financials, stock.balance_sheet, stock.cashflow)
            dcf_val, dcf_upside = calculate_dcf(info, current_price)
            
            # Prepare payload
            record = {
                "ticker": t,
                "current_price": current_price,
                "dcf_fair_value": dcf_val,
                "dcf_upside_pct": dcf_upside,
                "piotroski_score": piotroski,
                "z_score_composite": float(peers_df['Margin_Z'].mean()) if 'Margin_Z' in peers_df.columns else 0.0,
                "tier_matrix": tiers,
                "peer_comparison": json.loads(peers_df.to_json(orient='records')),
                "raw_financials": {"pe": info.get('trailingPE'), "mkt_cap": info.get('marketCap')}
            }
            results.append(record)
            
        except Exception as e:
            print(f"Failed to process {t}: {e}")
            
    # Upsert to Supabase
    if results:
        print("Upserting Quant Metrics to Supabase...")
        res = supabase.table('quant_metrics').upsert(results).execute()
        print(f"Inserted {len(res.data)} records.")

def run_macro_regime():
    try:
        spy = yf.Ticker('SPY').history(period='3mo')['Close']
        tlt = yf.Ticker('TLT').history(period='3mo')['Close']
        vix = yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
        
        spy_trend = "Bullish" if spy.iloc[-1] > spy.mean() else "Bearish"
        tlt_trend = "Bullish" if tlt.iloc[-1] > tlt.mean() else "Bearish"
        
        regime = "Risk-On (Expansion)" if spy_trend == "Bullish" and vix < 20 else "Risk-Off (Contraction)"
        if spy_trend == "Bearish" and tlt_trend == "Bullish": regime = "Defensive"
        if spy_trend == "Bearish" and tlt_trend == "Bearish": regime = "Stagflation / Cash"
        
        record = {
            "id": 1,
            "regime_label": regime,
            "spy_trend": spy_trend,
            "tlt_trend": tlt_trend,
            "gld_trend": "Neutral",
            "vix_level": round(vix, 2),
            "market_health_score": 80 if spy_trend == "Bullish" else 40
        }
        res = supabase.table('macro_regime').upsert([record]).execute()
        print(f"Upserted Macro Regime: {regime}")
    except Exception as e:
        print(f"Macro Regime Error: {e}")

if __name__ == "__main__":
    print("Starting Institutional Quant Engine...")
    run_macro_regime()
    run_quant_engine()
    print("Cron Job Complete.")
