import requests
import yfinance as yf
import app.yf_utils as yfu
import pandas as pd
import numpy as np

def get_market_regime(ticker=None):
    """
    Determines the market regime based on the asset class of the provided ticker.
    Defaults to SPY (US Equities) if no ticker or non-crypto.
    """
    try:
        # 1. Determine Benchmark
        benchmark_symbol = "SPY"
        market_name = "US S&P 500"
        
        if ticker:
            # Simple Crypto Detection
            t = ticker.upper()
            if '-USD' in t or t in ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']:
                benchmark_symbol = "BTC-USD"
                market_name = "CRYPTO (BITCOIN)"
            elif t == 'GC=F':
                benchmark_symbol = "GC=F"
                market_name = "GOLD"
        
        # 2. Fetch History
        spy = yfu.get_ticker(benchmark_symbol).history(period="1y")
        if spy.empty:
            return {"status": "Unknown", "color": "gray", "summary": "Market data unavailable.", "market": market_name}
        
        current_price = spy['Close'].iloc[-1]
        sma50 = spy['Close'].rolling(50).mean().iloc[-1]
        sma200 = spy['Close'].rolling(200).mean().iloc[-1]
        
        # Calculate Volatility
        daily_vol = spy['Close'].pct_change().std() * 100 
        
        status = "Neutral"
        color = "gray"
        summary = f"{benchmark_symbol} is in equilibrium."
        
        # Regime Logic
        if current_price > sma200:
            if current_price > sma50:
                status = "Bull Market (Strong)"
                color = "#00FF7F" 
                summary = f"{benchmark_symbol} is trading above both 50 and 200 SMAs. Trend is strictly UP."
            else:
                status = "Bull Market (Pullback)"
                color = "#FFB020" 
                summary = f"Long-term trend is UP (>SMA200), but short-term momentum has weakened (<SMA50)."
        else:
            if current_price < sma50:
                status = "Bear Market (Weak)"
                color = "#FF4560" 
                summary = f"{benchmark_symbol} is trading below both moving averages. Trend is DOWN."
            else:
                status = "Bear Market (Reversal?)"
                color = "#FFB020" 
                summary = f"Long-term trend is DOWN (<SMA200), but short-term momentum is recovering (>SMA50)."
                
        if daily_vol > (3.0 if 'BTC' in benchmark_symbol else 1.5): # Higher vol threshold for Crypto
            status += " / High Volatility"
            
        return {"status": status, "color": color, "summary": summary, "market": market_name}
        
    except Exception as e:
        return {"status": "Error", "color": "red", "summary": f"Failed to detect regime: {e}", "market": "Unknown"}

def get_global_pulse():
    """
    Fetches simplified market regime for key global assets.
    Returns a list of dictionaries for horizontal display.
    """
    assets = [
        {"name": "S&P 500", "ticker": "^GSPC"},
        {"name": "EU 500", "ticker": "^STOXX50E"}, # Proxy for EU500 (Stoxx 50)
        {"name": "HK 50", "ticker": "^HSI"}, # Hang Seng Index
        {"name": "UK 100", "ticker": "^FTSE"},
        {"name": "BTC", "ticker": "BTC-USD"},
        {"name": "ETH", "ticker": "ETH-USD"},
        {"name": "Gold", "ticker": "GC=F"},
        {"name": "Silver", "ticker": "SI=F"},
        {"name": "Crude Oil", "ticker": "CL=F"},
        {"name": "10Y Yield", "ticker": "^TNX"},
        {"name": "VIX", "ticker": "^VIX"},
    ]
    
    pulse_data = []
    
    for asset in assets:
        try:
            name = asset['name']
            ticker = asset['ticker']
            
            # Fetch sufficient history for RSI (14) + SMA (200)
            t_obj = yfu.get_ticker(ticker)
            # We need at least 200 days for SMA200, plus buffer. 1y is safe.
            hist = t_obj.history(period="1y")
            
            if hist.empty or len(hist) < 50:
                continue

            # --- Technical Calculations ---
            series = hist['Close']
            current = series.iloc[-1]
            prev = series.iloc[-2]
            
            # 1. Price Change
            delta = current - prev
            pct_change = (delta / prev) * 100
            
            # 2. Moving Averages
            sma50 = series.rolling(50).mean().iloc[-1]
            sma200 = series.rolling(200).mean().iloc[-1]
            
            # Handle potential NaNs in recent IPOs/listings
            if pd.isna(sma200): sma200 = sma50 if not pd.isna(sma50) else current
            if pd.isna(sma50): sma50 = current
            
            # 3. RSI (14-day)
            delta_series = series.diff()
            gain = (delta_series.where(delta_series > 0, 0)).rolling(window=14).mean()
            loss = (-delta_series.where(delta_series < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]
            if pd.isna(rsi): rsi = 50 # Default neutral

            # --- Advanced Signal Logic ---
            # Score based approach (0-10) to determine Signal
            score = 0
            
            # Trend Score (0-6)
            if current > sma200: score += 3
            if current > sma50: score += 2
            if sma50 > sma200: score += 1 # Golden Cross alignment
            
            # Momentum Score (0-4)
            if rsi > 50: score += 1
            if rsi > 60: score += 1
            if rsi < 30: score += 2 # Oversold Bounce potential (Contrarian Bullish) - OR treat as weak. 
                                    # Actually, strictly for "Trend", RSI < 30 is weak, but for "Trading", it's a buy signal.
                                    # User wants "Professional Analysis". Let's stick to Trend Following for the "Pulse".
                                    # If RSI < 30, it's very weak momentum. 
            
            # Refined Logic based on Score
            if score >= 6:
                signal = "STRONG BUY"
                color = "#00FF7F" # Neon Green
                arrow = "▲"
            elif score >= 4:
                signal = "BUY" # Weak Bull
                color = "#00FF7F" # Green
                arrow = "▲"
            elif score <= 2:
                signal = "STRONG SELL"
                color = "#FF4560" # Red
                arrow = "▼"
            elif score <= 3:
                signal = "SELL"
                color = "#FF4560" # Red
                arrow = "▼"
            else:
                signal = "HOLD"
                color = "#FFB020" # Yellow
                arrow = "−" 
                
            # Override for RSI Extremes?
            # if rsi > 80: signal = "OVERBOUGHT" (maybe keep as Strong Buy but warn?)
            
            pulse_data.append({
                "name": name,
                "price": current,
                "delta": delta,
                "pct": pct_change,
                "arrow": arrow,
                "color": color,
                "signal": signal,
                "rsi": rsi # Pass RSI for potential display
            })

        except Exception as e:
            # print(f"Error fetching {name}: {e}")
            continue
        
    return pulse_data

def generate_tier_insight(tier, score, metrics):
    """
    Generates a 1-2 sentence explanation for a specific Tier Score based on provided metrics.
    """
    insight = "Score reflects balanced metrics relative to the sector."
    
    # --- Tier 1: Valuation ---
    if "Valuation" in tier:
        peg = metrics.get("PEG Ratio")
        pe = metrics.get("P/E Ratio")
        
        if score < 40:
            insight = "Stock appears overvalued vs peers."
            if peg and isinstance(peg, (int, float)) and peg > 2.0:
                insight += f" High PEG ({peg:.2f}) suggests growth does not justify the premium."
        elif score > 70:
            insight = "Stock appears undervalued or fairly priced."
            if peg and isinstance(peg, (int, float)) and peg < 1.0:
                insight += f" Low PEG ({peg:.2f}) indicates potential value trap or strong growth-at-a-discount."
                
    # --- Tier 2: Intrinsic/Alpha ---
    elif "Intrinsic" in tier:
        alpha = metrics.get("Alpha (Revisions)")
        if score > 70:
            insight = "Analysts are becoming increasingly bullish."
            if alpha and "100" in str(alpha):
                 insight += " Earnings expectations are being revised UP aggressively."
        elif score < 40:
             insight = "Analysts are downgrading earnings forecasts."

    # --- Tier 3: Growth ---
    elif "Growth" in tier:
        if score > 80:
             insight = "Top-tier revenue and earnings expansion trajectory."
        elif score < 40:
             insight = "Growth has stalled or is decelerating compared to historical adoption."

    # --- Tier 4: Efficiency ---
    elif "Efficiency" in tier:
        if score > 70:
            insight = "Management is highly efficient at generating profit from capital."
        elif score < 40:
            insight = "Margins are compressed. Cost structure may be bloated vs peers."

    # --- Tier 10: Timing ---
    elif "Timing" in tier:
        rsi_str = metrics.get("RSI (D/W)", "50/50")
        try:
            rsi_d = float(rsi_str.split('/')[0])
        except:
            rsi_d = 50
            
        if score > 80:
            insight = "Technical structure is bullish. Trend alignment is positive."
        elif score < 30:
            insight = "Technical structure is broken or heavily bearish."
            if rsi_d < 30: insight += " However, stock is oversold (RSI < 30) and due for a bounce."

    # --- Tier 12: Derivatives ---
    elif "Derivatives" in tier:
         short = metrics.get("Short Float")
         if score < 40:
             insight = "Implies high institutional hedging or betting against the stock."
             if short and "N/A" not in short and float(short.strip('%')) > 10:
                 insight += f" Short interest is elevated ({short}), suggesting precise bearish intent."
         elif score > 70:
             insight = "Options market and short interest suggest low fear."

    return insight
