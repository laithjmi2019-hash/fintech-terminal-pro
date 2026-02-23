import feedparser
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import app.yf_utils as yfu
import streamlit as st
# Load pipeline once (if possible) or load on demand
try:
    from transformers import pipeline
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert-tone")
except ImportError:
    print("Warning: Transformers not found. Sentiment analysis disabled.")
    sentiment_pipeline = None
except Exception as e:
    print(f"Warning: Could not load FinBERT: {e}")
    sentiment_pipeline = None

def get_google_news(ticker):
    """
    Fetches latest 5 headlines from Google News RSS.
    """
    rss_url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    return [entry.title for entry in feed.entries[:5]]

def analyze_headlines(headlines):
    if not sentiment_pipeline or not headlines:
        return 50
    
    results = sentiment_pipeline(headlines)
    total_score = 0
    for res in results:
        if res['label'] == 'positive': total_score += 100 * res['score']
        elif res['label'] == 'negative': total_score += 0
        else: total_score += 50
        
    return int(total_score / len(results))

@st.cache_data(ttl=3600, show_spinner=False)
def get_consensus_sentiment(ticker):
    """
    Returns weighted average of Yahoo Finance (Direct) and Google News (Aggregated).
    """
    # Initialize headlines to avoid UnboundLocalError
    y_headlines = []
    g_headlines = []
    
    # Source 1: Yahoo
    try:
        y_news = yfu.get_ticker(ticker).news
        y_headlines = [i['title'] for i in y_news[:5]] if y_news else []
        s_yahoo = analyze_headlines(y_headlines)
    except:
        s_yahoo = 50
        
    # Source 2: Google News RSS
    try:
        g_headlines = get_google_news(ticker)
        s_google = analyze_headlines(g_headlines)
    except:
        s_google = 50
        
    # Combined Score
    # If one source fails (returns 50 default and empty headlines logic needed), we should weight the other.
    # For now, simple average.
    consensus = int((s_yahoo + s_google) / 2)
    
    return {
        "score": consensus,
        "yahoo_score": s_yahoo,
        "google_score": s_google,
        "headline_count": len(y_headlines) + len(g_headlines),
        "headlines": y_headlines + g_headlines
    }
