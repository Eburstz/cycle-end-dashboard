import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")

# ======================
# CONFIG
# ======================
your_coins = ["BTC", "ETH", "SOL", "ADA", "RNDR", "DOGE"]  # adjust as needed
btc_group = ["BTC"]
large_caps = ["ETH", "SOL", "BNB", "ADA", "XRP"]  # adjust
small_caps = [c for c in your_coins if c not in btc_group + large_caps]

# Weights for BTC / Large Caps / Small Caps
weights_btc = {
    "Price Action": 0.30,
    "Funding Rates": 0.25,
    "Spot vs Perps": 0.20,
    "Sentiment (F&G)": 0.15,
    "Rotation (BTC.D)": 0.05,
    "Alt Breadth (≥30% in 7d)": 0.03,
    "Volume Thrust (Vol/MCap ≥15%)": 0.02,
}
weights_large = {
    "Price Action": 0.20,
    "Funding Rates": 0.20,
    "Spot vs Perps": 0.15,
    "Sentiment (F&G)": 0.10,
    "Rotation (BTC.D)": 0.10,
    "Alt Breadth (≥30% in 7d)": 0.15,
    "Volume Thrust (Vol/MCap ≥15%)": 0.10,
}
weights_small = {
    "Price Action": 0.05,
    "Funding Rates": 0.15,
    "Spot vs Perps": 0.10,
    "Sentiment (F&G)": 0.05,
    "Rotation (BTC.D)": 0.15,
    "Alt Breadth (≥30% in 7d)": 0.25,
    "Volume Thrust (Vol/MCap ≥15%)": 0.25,
}

# ======================
# API HELPERS
# ======================
@st.cache_data(ttl=300)
def coingecko_simple(ids, vs="usd"):
    url = "https://api.coingecko.com/api/v3/simple/price"
    r = requests.get(url, params={"ids": ids, "vs_currencies": vs, "include_24hr_vol": "true"})
    return r.json()

@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        return int(r.json()["data"][0]["value"])
    except:
        return None

@st.cache_data(ttl=300)
def binance_funding(symbol="BTCUSDT"):
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                         params={"symbol": symbol, "limit": 1}, timeout=10)
        if r.status_code == 200:
            return float(r.json()[0]["fundingRate"]) * 100
    except:
        return None
    return None

# ======================
# SIGNAL CALCULATION
# ======================
rows = []

# 1) Price Action BTC
try:
    mkt = requests.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                       params={"vs_currency": "usd", "days": 30}).json()
    if "prices" in mkt:
        start = mkt["prices"][0][1]
        end = mkt["prices"][-1][1]
        change = ((end - start) / start) * 100
        if change > 10:
            rows.append(["Price Action", "🟢", f"{change:.1f}%"])
        elif change > 0:
            rows.append(["Price Action", "🟡", f"{change:.1f}%"])
        else:
            rows.append(["Price Action", "🔴", f"{change:.1f}%"])
    else:
        rows.append(["Price Action", "⚪", "N/A"])
except:
    rows.append(["Price Action", "⚪", "N/A"])

# 2) Funding Rates BTC & SOL
f_btc = binance_funding("BTCUSDT")
f_sol = binance_funding("SOLUSDT")
if f_btc is None:
    rows.append(["Funding Rates", "⚪", "N/A"])
else:
    if f_btc >= 0.10:
        status = "🔴"
    elif f_btc >= 0.05:
        status = "🟡"
    else:
        status = "🟢"
    detail = f"BTC {f_btc:.3f}%"
    if f_sol is not None:
        detail += f" / SOL {f_sol:.3f}%"
    rows.append(["Funding Rates", status, detail])

# 3) Spot vs Perps
rows.append(["Spot vs Perps", "🟡", "Example value"])  # Replace with real data logic

# 4) Sentiment
fg = get_fear_greed()
if fg is None:
    rows.append(["Sentiment (F&G)", "⚪", "N/A"])
else:
    if fg >= 80:
        rows.append(["Sentiment (F&G)", "🔴", str(fg)])
    elif fg >= 60:
        rows.append(["Sentiment (F&G)", "🟡", str(fg)])
    else:
        rows.append(["Sentiment (F&G)", "🟢", str(fg)])

# 5) Rotation (BTC.D)
rows.append(["Rotation (BTC.D)", "🟡", "Example value"])  # Replace with BTC dominance logic

# 6) Alt Breadth
rows.append(["Alt Breadth (≥30% in 7d)", "🟡", "Example value"])

# 7) Volume Thrust
rows.append(["Volume Thrust (Vol/MCap ≥15%)", "🟡", "Example value"])

# ======================
# COMPOSITE LOGIC
# ======================
def composite_status(rows, weights):
    emoji_score = {"🟢": 1.0, "🟡": 0.5, "🔴": 0.0}
    total_score = 0.0
    total_weight = 0.0
    for sig, status, _ in rows:
        if sig in weights and status in emoji_score:
            total_score += emoji_score[status] * weights[sig]
            total_weight += weights[sig]
    if total_weight == 0:
        return "⚪"
    avg = total_score / total_weight
    if avg >= 0.75:
        return "🟢"
    elif avg >= 0.5:
        return "🟡"
    else:
        return "🔴"

def get_group(coin):
    if coin in btc_group:
        return "BTC"
    elif coin in large_caps:
        return "Large"
    else:
        return "Small"

def get_signal_colour(coin):
    g = get_group(coin)
    if g == "BTC":
        return composite_status(rows, weights_btc)
    elif g == "Large":
        return composite_status(rows, weights_large)
    else:
        return composite_status(rows, weights_small)

# ======================
# YOUR COINS TABLE
# ======================
data = []
for c in your_coins:
    data.append([get_signal_colour(c), c])
your_coins_df = pd.DataFrame(data, columns=["Signal", "Coin"])

# ======================
# DISPLAY
# ======================
st.title("Cycle-End Dashboard")
st.subheader("Cycle-End Signals")
st.table(pd.DataFrame(rows, columns=["Signal", "Status", "Detail"]))
st.subheader("Your Coins")
st.table(your_coins_df)
