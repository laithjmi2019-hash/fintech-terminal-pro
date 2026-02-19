import streamlit as st
import pandas as pd
import textwrap

# Page Configuration - Must be the first Streamlit command
st.set_page_config(
    page_title="Institutional Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load Custom CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

try:
    local_css("assets/style.css")
except FileNotFoundError:
    pass # Handle case where file is not yet created

# Inject Paywall & Global CSS
from app.ui import inject_paywall_css, inject_global_styles
inject_global_styles()
inject_paywall_css()


from app.ui import render_macro_header, render_search_bar
from app.auth import check_ip_status, render_login_form
from app.charts import render_chart
from app.scoring import calculate_scores

# --- Sidebar Polish ---
with st.sidebar:
    st.title("Quant Terminal Pro")
    
    # Auth Status
    if st.session_state.get('authenticated'):
        st.markdown("🟢 **Status: Pro Member**")
    else:
        st.markdown("🔴 **Status: Free Tier**")
        st.caption("3/3 Searches Used")
        if st.button("🚀 Upgrade to Pro", type="primary"):
            st.session_state.authenticated = True
            st.session_state.user_tier = 'Pro'
            st.rerun()
            
    st.divider()
    st.info("Market data provided by Yahoo Finance & FinBERT AI.")

# --- Layout ---

# 1. Macro Header
# 1. Macro Header & Market Regime
render_macro_header()

from app.insights import get_global_pulse, generate_tier_insight

# Global Market Pulse
pulse = get_global_pulse()

if pulse:
    # Use columns to create a horizontal layout
    # Streamlit columns are responsive, but for a long list, we might want a raw HTML flex container
    # Let's try raw HTML for a "ticker tape" style row
    
    pulse_html = '<div style="display: flex; gap: 15px; overflow-x: auto; padding: 10px 0; margin-bottom: 20px;">'
    
    for p in pulse:
        # Determine delta color for the small text
        d_color = "#00FF7F" if p['delta'] >= 0 else "#FF4560"
        delta_arrow = "↑" if p['delta'] >= 0 else "↓"
        
        # Main color comes from the Signal Logic
        main_color = p['color'] 
        
        # Add visual flair for STRONG signals
        border_width = "4px" # Restore border width
        
        if "STRONG" in p['signal']:
            # Signal text
            signal_text = f"<span style='color:{main_color}; font-size: 0.7rem; letter-spacing: 0.8px; text-transform: uppercase; display: block; margin-top: 3px;'>{p['signal']}</span>"
        else:
            signal_text = f"<span style='color:#888; font-size: 0.7rem; letter-spacing: 0.8px; text-transform: uppercase; display: block; margin-top: 3px;'>{p['signal']}</span>"

        pulse_html += f"""
<div style="background-color: #1E2129; padding: 10px 12px; border-radius: 6px; border-left: {border_width} solid {main_color}; min-width: 135px; text-align: center; margin-right: 0;">
    <div style="color: #fff; font-size: 0.85rem; font-weight: 600; margin-bottom: 2px;">{p['name']}</div>
    <div style="font-weight: bold; color: {main_color}; font-size: 1.25rem;">
        {p['price']:,.2f}
    </div>
    <div style="color: {d_color}; font-size: 0.8rem; margin-top: 2px; opacity: 0.9;">
        {delta_arrow} {abs(p['delta']):.2f} ({p['pct']:.2f}%)
    </div>
    {signal_text}
</div>
"""
    pulse_html += '</div>'
    
    st.markdown(pulse_html, unsafe_allow_html=True)
else:
    st.info("Market Pulse Unavailable")

# 2. Main Content
st.write("---")

# Session State for Search History/Auth
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Check Strike Count
# For now, we mock IP. In prod, use: st.context.headers.get("X-Forwarded-For")
user_ip = "127.0.0.1" 
strike_count = check_ip_status(user_ip)

if strike_count >= 3 and not st.session_state.authenticated:
    render_login_form()
    st.image("assets/blur_overlay.png") # Optional visual cue if we had one, or just stop rendering
    st.info("Paywall Active. Please Login.")
else:
    # 3. Search Bar
    ticker = render_search_bar()

    if ticker:
        # Smart Ticker Mapping for Crypto
        ticker_map = {
            'BTC': 'BTC-USD',
            'ETH': 'ETH-USD',
            'SOL': 'SOL-USD',
            'XRP': 'XRP-USD',
            'DOGE': 'DOGE-USD',
            'BTC-USDT': 'BTC-USD',
            'ETH-USDT': 'ETH-USD'
        }
        ticker = ticker_map.get(ticker.upper(), ticker)
        
        # 4. Display Dashboard
        # Fetch scores first to get Company Name
        with st.spinner('Analysing...'):
            scores = calculate_scores(ticker)
            company_name = scores.get('company_name', ticker)
        
        # --- Hero Section ---
        hero_c1, hero_c2, hero_c3 = st.columns([1, 1, 1])
        
        with hero_c1:
            st.markdown(f"## {ticker}")
            st.caption(company_name)
            
        with hero_c2:
            price = scores.get('current_price')
            if price:
                 st.markdown(f"## ${price:,.2f}")
            else:
                 st.markdown("## $--")
            st.caption("Current Price")
            
        with hero_c3:
            final_score = scores.get("final_score", 0)
            score_class = "score-high" if final_score >= 80 else "score-med" if final_score >= 50 else "score-low"
            st.markdown(f"## <span class='{score_class}'>{final_score}/100</span>", unsafe_allow_html=True)
            st.caption(f"Institutional Grade: {scores.get('final_grade')}")

        st.divider()
        
        # Create Tabs
        tab1, tab2 = st.tabs(["📊 Institutional Dashboard", "📈 Strategy Backtest (10Y)"])
        
        with tab1:
            col_left, col_right = st.columns([2, 1])
            
            with col_left:
                render_chart(ticker)
                
                # --- Peer Comparison & PDF Report ---
                st.write("---")
                st.subheader("🏆 Sector Peer Comparison")
                
                from app.peers import get_peer_comparison
                
                sector = scores.get('sector', 'Technology')
                with st.spinner(f"Analyzing {sector} Competitors..."):
                    try:
                        peer_df = get_peer_comparison(ticker, sector)
                        if not peer_df.empty:
                            # Highlight Target Ticker Row with Dark Green
                            def highlight_row(row):
                                return ['background-color: #003319'] * len(row) if row['Ticker'] == ticker else [''] * len(row)

                            st.dataframe(
                                peer_df.style.apply(highlight_row, axis=1),
                                column_config={
                                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                                    "P/E": st.column_config.NumberColumn(format="%.1f"),
                                    "EV/EBITDA": st.column_config.NumberColumn(format="%.1f"),
                                },
                                hide_index=True,
                                use_container_width=True
                            )
                            st.caption("ℹ️ Rankings calculated via Multi-Factor Composite Score (Valuation, Efficiency, and Growth Momentum). (*) denotes Industry Average proxy used for missing data.")
                        else:
                            st.info("No comparable peers found.")
                    except Exception as e:
                        st.warning(f"Could not fetch peer data: {e}")
                
                
                # PDF Report Button
                st.write("---")
                from app.report import generate_pdf_report
                
                pdf_data = None
                if st.button("📄 Generate Institutional PDF Report"):
                    with st.spinner("Generating PDF..."):
                        try:
                            # Defensive: Ensure peer_df exists
                            if 'peer_df' not in locals():
                                peer_df = pd.DataFrame() 
                            
                            pdf_data = generate_pdf_report(ticker, scores, peer_df)
                        except Exception as e:
                            st.error(f"Failed to generate PDF: {e}")
    
                if pdf_data:
                    st.download_button(
                        label="⬇️ Download Analysis PDF",
                        data=pdf_data,
                        file_name=f"{ticker}_Institutional_Report.pdf",
                        mime="application/pdf"
                    )
            
            with col_right:
                st.subheader("12-Tier Matrix")
                # scores already calculated
                
                if "error" in scores:
                    st.error(scores["error"])
                else:
                    # Grid for Tiers using Cards
                    breakdown = scores.get("breakdown", {})
                    metrics = scores.get("metrics", {})
                    
                    # Institutional Descriptions
                    TIER_BRIEFS = {
                        "Tier 1: Valuation": "Assesses the true enterprise cost, factoring in debt, cash, and free cash flow generation.",
                        "Tier 2: Intrinsic/Alpha": "Compares price to DCF models and tracks analyst revision momentum (Alpha).",
                        "Tier 3: Growth": "Evaluates top-line revenue trajectory and the expansion of the Total Addressable Market (TAM).",
                        "Tier 4: Efficiency": "Measures how effectively management turns capital and operational costs into pure profit.",
                        "Tier 5: Financial Health": "Stress-tests the balance sheet for survival risk, debt burdens, and short-term liquidity.",
                        "Tier 6: Forensics": "Audits the quality of earnings and checks for hidden accounting red flags.",
                        "Tier 7: Management": "Evaluates executive decision-making, capital allocation, and strategic business pivots.",
                        "Tier 8: Capital Flow": "Tracks the 'smart money'—monitoring what C-suite insiders and institutional hedge funds are buying.",
                        "Tier 9: Total Yield": "Measures direct shareholder returns through dividend payouts and the impact of share repurchases.",
                        "Tier 10: Timing": "Identifies asymmetric technical entry points using moving averages, RSI, and support/resistance floors.",
                        "Tier 11: Sentiment": "Analyzes short-term news cycles, upcoming earnings prints, and sector-wide macro narratives.",
                        "Tier 12: Derivatives": "Monitors options market pricing and Implied Volatility (IV) to gauge institutional fear or greed."
                    }
                    
                    # Iterate and create cards
                    # We want a vertical stack of cards in the right column
                    for category, score in breakdown.items():
                        score_int = int(score)
                        sN_class = "score-high" if score_int >= 80 else "score-med" if score_int >= 50 else "score-low"
                        brief = TIER_BRIEFS.get(category, "")
                        
                        # Build context string
                        context_str = ""
                        insight = generate_tier_insight(category, score_int, metrics)

                        if "Valuation" in category and metrics.get('PEG Ratio'):
                            context_str = f"PEG: {metrics['PEG Ratio']} | P/S: {metrics.get('P/S Ratio')}"
                        elif "Timing" in category and metrics.get('RSI (D/W)'):
                            context_str = f"RSI: {metrics['RSI (D/W)']}"
                        elif "Management" in category:
                            context_str = f"Insider Own: {metrics.get('Insider Own')}"
                        elif "Intrinsic" in category and metrics.get('Alpha (Revisions)'):
                            context_str = f"Alpha: {metrics['Alpha (Revisions)']}"
                        elif "Derivatives" in category:
                            context_str = f"Short: {metrics.get('Short Float')}"
                        
                        # Foolproof HTML generation - avoiding indentation issues
                        card_html = f"""
<div class="metric-card">
<div style="display: flex; justify-content: space-between; align-items: center;">
<span style="font-weight: bold; font-size: 1.1rem;">{category}</span>
<span class="{sN_class}">{score_int}</span>
</div>
<p class="tier-brief">{brief}</p>
<!-- AI Insight Box -->
<div style="background-color: #2D3139; border-left: 3px solid #00FF7F; padding: 8px; margin: 8px 0; border-radius: 4px;">
<small style="color: #CCCCCC; font-style: italic;">🤖 {insight}</small>
</div>
<div style="background-color: #333; border-radius: 4px; height: 6px; width: 100%; margin: 8px 0;">
<div style="background-color: {'#00FF7F' if score_int >= 80 else '#FFB020' if score_int >= 50 else '#FF4560'}; width: {score_int}%; height: 100%; border-radius: 4px;"></div>
</div>
<small style="color: #888;">{context_str}</small>
</div>
"""
                        st.markdown(card_html, unsafe_allow_html=True)
                    
                    # --- News Intelligence Feed ---
                    with st.expander("📰 News Intelligence (Catalysts)", expanded=False):
                        headlines = scores.get('news_headlines', [])
                        if headlines:
                            for h in headlines:
                                st.markdown(f"- {h}")
                        else:
                            st.info("No recent headlines found.")

                    # --- Data Export ---
                    st.divider()
                    st.subheader("💾 Export Data")
                    
                    # Prepare CSV
                    csv_data = pd.DataFrame([scores['metrics']]).to_csv(index=False)
                    st.download_button(
                        label="⬇️ Download Analysis (CSV)",
                        data=csv_data,
                        file_name=f"{ticker}_Analysis.csv",
                        mime="text/csv"
                    )

        with tab2:
            st.subheader("📜 Historical Backtest (The Truth)")
            st.caption("Proof of Concept: How this strategy would have performed over the last 10 years.")
            
            # Mock User Tier for Demo (Default to Free to show Paywall)
            user_tier = st.session_state.get('user_tier', 'Free')
            
            # Paywall Container Start
            if user_tier != 'Pro':
                 st.markdown('<div class="paywall-container">', unsafe_allow_html=True)

            from app.backtest import run_backtest
            
            with st.spinner("Running 10-Year Simulation..."):
                metrics, fig = run_backtest(ticker)
                
                if metrics:
                    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
                    b_col1.metric("Strategy CAGR", metrics['CAGR (Strategy)'], delta=metrics['Outperformance'])
                    b_col2.metric("Buy & Hold CAGR", metrics['CAGR (Buy & Hold)'])
                    b_col3.metric("Max Drawdown", metrics['Max Drawdown'])
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(fig) 

            # Paywall Overlay
            if user_tier != 'Pro':
                 st.markdown('''
                   <div class="frosted-glass-overlay">
                       <h2 style="color: white;">Unlock 10-Year Historical Proof</h2>
                       <p style="color: #CCCCCC;">See exactly how this stock would have performed over the last decade using our proprietary Matrix.</p>
                       <button class="paywall-button">Upgrade to Quant Pro</button>
                   </div>
                 </div>
                 ''', unsafe_allow_html=True)


