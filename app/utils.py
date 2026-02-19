import pandas as pd
import requests

def format_number(num):
    if num > 1_000_000_000_000:
        if not num % 1_000_000_000_000:
            return f'{num // 1_000_000_000_000}T'
        return f'{round(num / 1_000_000_000_000, 1)}T'
    return f'{num // 1_000_000_000}B' if num > 1_000_000_000 else f'{num // 1_000_000}M'

def format_percentage(val):
    return f"{val:.2f}%"

def lookup_ticker(query):
    """
    Searches for a ticker symbol given a query string (company name or ticker)
    using Yahoo Finance's public search API.
    """
    url = f"https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": 1, "newsCount": 0}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        if "quotes" in data and len(data["quotes"]) > 0:
            return data["quotes"][0]["symbol"]
    except Exception as e:
        print(f"Error looking up ticker: {e}")
    
    return None
