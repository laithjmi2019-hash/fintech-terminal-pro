import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import app.yf_utils as yfu
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
            df = yfu.download_data(ticker, period="1y", interval="1d", progress=False)
            
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

            # Invisible trace for reliable unified hover tracking
            import numpy as np
            custom_data = np.stack((df['Open'], df['High'], df['Low'], df['Close']), axis=-1)
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df['Close'],
                mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                showlegend=False,
                name='Price',
                customdata=custom_data,
                hovertemplate="Open: %{customdata[0]:.2f}<br>High: %{customdata[1]:.2f}<br>Low: %{customdata[2]:.2f}<br>Close: %{customdata[3]:.2f}<extra></extra>"
            ), secondary_y=False)

            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price',
                hoverinfo='skip'
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
                margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
                hoverdistance=-1,
                spikedistance=-1
            )

            # Add crosshairs for exact cursor position
            fig.update_xaxes(
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                showline=True,
                spikedash="dash",
                spikecolor="gray",
                spikethickness=1
            )
            fig.update_yaxes(
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                showline=True,
                spikedash="dash",
                spikecolor="gray",
                spikethickness=1,
                secondary_y=False
            )

            config = {
                'displayModeBar': True,
                'scrollZoom': True,
                'modeBarButtonsToAdd': ['crosshair']
            }
            st.plotly_chart(fig, use_container_width=True, config=config)
            
        except Exception as e:
            st.error(f"Error rendering chart: {e}")

