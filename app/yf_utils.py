import yfinance as yf

def get_ticker(symbol):
    """Wrapper for yf.Ticker letting YF manage its own curl_cffi session."""
    return yf.Ticker(symbol)

def download_data(tickers, *args, **kwargs):
    """Wrapper for yf.download letting YF manage its own curl_cffi session."""
    return yf.download(tickers, *args, **kwargs)
