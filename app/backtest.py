import yfinance as yf
import yfinance as yf
import pandas as pd
import numpy as np
import app.yf_utils as yfu
import plotly.graph_objects as go

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_backtest(ticker):
    """
    Simulates a "Buy the Dip in Bull Trend" strategy over 10 years.
    Returns:
        - metrics (dict): CAGR, Max Drawdown, Win Rate
        - chart (plotly figure): Equity Curve vs Buy & Hold
    """
    try:
        # 1. Fetch Data (10 Years)
        stock = yfu.get_ticker(ticker)
        df = stock.history(period="10y")
        
        if len(df) < 252: # Need at least 1 year
            return None, "Insufficient data for backtest (need > 1 year)"
            
        # 2. Calculate Indicators
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['RSI_14'] = calculate_rsi(df['Close'], 14)
        
        # 3. Define Strategy (Trend-Following Pullback)
        # BUY: Macro trend UP (50 > 200) AND Price > 200 AND RSI < 45 (Dip)
        buy_condition = (df['SMA_50'] > df['SMA_200']) & (df['Close'] > df['SMA_200']) & (df['RSI_14'] < 45)
        
        # SELL: Momentum breaks (Price < 50) OR Death Cross (50 < 200)
        sell_condition = (df['Close'] < df['SMA_50']) | (df['SMA_50'] < df['SMA_200'])
        
        df['Signal'] = 0
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1
        
        # Vectorized Position Management
        # Replace 0 with NaN to forward fill the last signal (Hold)
        # FillNa(0) for start of data
        # Clip at 0 because we don't short, we just go to cash (0)
        df['Position'] = df['Signal'].replace(0, np.nan).ffill().fillna(0)
        df['Position'] = df['Position'].clip(lower=0)
        
        # 4. Calculate Returns
        df['Daily_Ret'] = df['Close'].pct_change()
        df['Strategy_Ret'] = df['Position'].shift(1) * df['Daily_Ret'] # Shift 1 to trade NEXT day open/close approx
        
        df['Equity_BH'] = (1 + df['Daily_Ret']).cumprod() # Buy & Hold
        df['Equity_Strat'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() # Strategy
        
        # 5. Calculate Metrics
        total_days = len(df)
        years = total_days / 252
        
        # CAGR
        cagr_bh = (df['Equity_BH'].iloc[-1])**(1/years) - 1
        cagr_strat = (df['Equity_Strat'].iloc[-1])**(1/years) - 1
        
        # Max Drawdown
        rolling_max = df['Equity_Strat'].cummax()
        drawdown = (df['Equity_Strat'] - rolling_max) / rolling_max
        max_dd = drawdown.min()
        
        metrics = {
            "CAGR (Strategy)": f"{cagr_strat:.1%}",
            "CAGR (Buy & Hold)": f"{cagr_bh:.1%}",
            "Max Drawdown": f"{max_dd:.1%}",
            "Outperformance": f"{(cagr_strat - cagr_bh):.1%}"
        }
        
        # 6. Generate Plotly Chart
        fig = go.Figure()
        
        # Buy & Hold Line
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Equity_BH'],
            mode='lines', name='Buy & Hold',
            line=dict(color='gray', width=1, dash='dash')
        ))
        
        # Strategy Line
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Equity_Strat'],
            mode='lines', name='Institutional Strategy',
            line=dict(color='#00FFAA', width=2)
        ))
        
        fig.update_layout(
            title=f"10-Year Backtest: {ticker} (Trend + Dip Buying)",
            template="plotly_dark",
            yaxis_title="Growth of $1",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        return metrics, fig
        
    except Exception as e:
        return None, f"Backtest caught exception: {e}"
