import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import pandas as pd

# Let's calculate manually to avoid extra dependencies for now if simple.

def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def render_chart(ticker):
    with st.spinner(f"Loading Chart for {ticker}..."):
        try:
            # Fetch Data
            df = yf.download(ticker, period="1y", interval="1d", progress=False)
            
            # Fix for yfinance returning MultiIndex columns (Price, Ticker)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty:
                st.error("No data found.")
                return

            # Indicators
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            df['RSI'] = calculate_rsi(df)

            # Create Figure with Secondary Y-Axis for Volume
            from plotly.subplots import make_subplots
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price'
            ), secondary_y=False)

            # SMA 50
            fig.add_trace(go.Scatter(
                x=df.index, 
                y=df['SMA_50'], 
                line=dict(color='orange', width=1), 
                name='SMA 50'
            ), secondary_y=False)

            # SMA 200
            fig.add_trace(go.Scatter(
                x=df.index, 
                y=df['SMA_200'], 
                line=dict(color='white', width=1), 
                name='SMA 200'
            ), secondary_y=False)

            # Volume Bar Chart (Lower opacity)
            fig.add_trace(go.Bar(
                x=df.index,
                y=df['Volume'],
                marker_color='rgba(100, 100, 100, 0.3)',
                name='Volume'
            ), secondary_y=True)

            # Layout
            fig.update_layout(
                template="plotly_dark",
                height=600,
                xaxis_rangeslider_visible=False,
                title=f"{ticker} - Daily Chart",
                yaxis_title="Price",
                xaxis_title="Date",
                margin=dict(l=0, r=0, t=30, b=0)
            )

            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error rendering chart: {e}")

