# cycle_end_dashboard.py
import os, time, math, datetime as dt, requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")

# -----------------------------
# Config / Secrets
# -----------------------------
GLASSNODE_KEY = st.secrets.get("GLASSNODE_API_KEY", os.getenv("GLASSNODE_API_KEY", ""))
COINGLASS_KEY = st.secrets.get("COINGLASS_API_KEY", os.getenv("COINGLASS_API_KEY", ""))
CRYPTOQUANT_KEY = st.secrets.get("CRYPTOQUANT_API_KEY", os.getenv("CRYPTOQUANT_API_KEY", ""))

HALVING_DATE = dt.date(2024, 4, 19)  # BTC halving

# -----------------------------
# Helpers
# -----------------------------
def get_json(url, headers=None, params=None, timeout=20):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def badge(color, text):
    return f"<span style='background:{color};padding:2px 8px;border-radius:12px;color:white;font-weight:600'>{text}</span>"

# -----------------------------
# Free Data (no key)
# -----------------------------
def coingecko_simple_price(ids, vs="usd"):
    url = "https://api.coingecko.com/api/v3/simple/price"
    data = get_json(url, params={"ids": ",".join(ids), "vs_currencies": vs})
    return {k: v.get(vs) for k, v in (data or {}).items()}

def coingecko_global():
    # btc dominance + market info
    url = "https://api.coingecko.com/api/v3/global"
    return get_json(url) or {}

def fear_greed():
    # Alternative.me Fear & Greed Index (free)
    data = get_json("https://api.alternative.me/fng/?limit=1&format=json")
    if data and data.get("data"):
        x = data["data"][0]
        return int(x["value"]), x["value_classification"], x["timestamp"]
    return None, None, None

def price_history_coin(coin_id, days=30):
    # daily prices for simple momentum check
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    js = get_json(url, params={"vs_currency": "usd", "days": days})
    if not js:
        return pd.DataFrame()
    prices = js.get("prices", [])
    df = pd.DataFrame(prices, columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
    return df[["date", "price"]]

# -----------------------------
# Optional Data (API keys)
# -----------------------------
def coinglass_funding(symbol="BTC", exchange="Binance"):
    if not COINGLASS_KEY:
        return None
    url = "https://open-api-v3.coinglass.com/api/futures/funding_rates"
    headers = {"coinglassSecret": COINGLASS_KEY}
    js = get_json(url, headers=headers, params={"symbol": symbol, "exchange": exchange})
    # Response structure varies; we’ll try to find last funding rate %
    try:
        items = js.get("data", [])
        if items:
            fr = items[0].get("uMarginList", [{}])[-1].get("rate", None)
            return float(fr) if fr is not None else None
    except Exception:
        pass
    return None

def glassnode_metric(path, params):
    if not GLASSNODE_KEY:
        return None
    base = "https://api.glassnode.com"
    q = {"api_key": GLASSNODE_KEY}
    q.update(params)
    js = get_json(f"{base}{path}", params=q)
    return js

def glassnode_mvrv_z():
    # MVRV Z-Score endpoint (requires key). Some plans gate this metric.
    js = glassnode_metric("/v1/metrics/market/mvrv_z_score", {"a":"BTC","i":"24h"})
    if not js: 
        return None
    try:
        return float(js[-1]["v"])
    except Exception:
        return None

def glassnode_lth_sopr():
    # Long-term holder SOPR; sometimes paywalled
    js = glassnode_metric("/v1/metrics/transactions/sopr_long_term_holders", {"a":"BTC","i":"24h"})
    if not js:
        return None
    try:
        return float(js[-1]["v"])
    except Exception:
        return None

def cryptoquant_exchange_netflow():
    # Daily BTC exchange netflow (needs key; free plans can be limited)
    if not CRYPTOQUANT_KEY:
        return None
    url = "https://api.cryptoquant.com/v1/btc/exchange-flows/netflow"
    js = get_json(url, params={"api_key": CRYPTOQUANT_KEY, "window":"day"})
    try:
        # latest value
        rows = js.get("result", {}).get("data", [])
        if rows:
            return float(rows[-1]["value"])  # positive = net inflow
    except Exception:
        pass
    return None

# -----------------------------
# Compute & Render
# -----------------------------
st.title("📊 Crypto Cycle-End Dashboard (Live)")

# Top summary
today = dt.date.today()
day_count = (today - HALVING_DATE).days
cg_prices = coingecko_simple_price(
    ["bitcoin","ethereum","solana","render-token","sui","injective-protocol","uniswap","ondo-finance",
     "hedera-hashgraph","fetch-ai","osmosis","decentraland","matic-network"]
)

btc = cg_prices.get("bitcoin")
eth = cg_prices.get("ethereum")
sol = cg_prices.get("solana")

col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC Price", f"${btc:,.0f}" if btc else "—")
col2.metric("ETH Price", f"${eth:,.0f}" if eth else "—")
col3.metric("SOL Price", f"${sol:,.0f}" if sol else "—")
col4.metric("Days after halving", f"{day_count}")

# Global / dominance
glob = coingecko_global()
btc_dom = None
try:
    btc_dom = glob["data"]["market_cap_percentage"]["btc"]
except Exception:
    pass

fg_value, fg_label, fg_ts = fear_greed()

st.write("---")

# -----------------------------
# Signals Logic
# -----------------------------
# 1) Price Action (simple momentum using 30d slope)
hist = price_history_coin("bitcoin", days=30)
pa_status, pa_detail = "🟢", "Uptrend"
if not hist.empty:
    change = (hist.iloc[-1]["price"] - hist.iloc[0]["price"]) / hist.iloc[0]["price"]
    if change < -0.10:
        pa_status, pa_detail = "🔴", f"Down {change:.0%} in 30d"
    elif change < 0.05:
        pa_status, pa_detail = "🟡", f"Flat {change:.0%} in 30d"
    else:
        pa_detail = f"Up {change:.0%} in 30d"

# 2) Funding (optional via CoinGlass)
funding_btc = coinglass_funding("BTC") if COINGLASS_KEY else None
funding_sol = coinglass_funding("SOL") if COINGLASS_KEY else None
fund_status, fund_detail = ("⚪", "N/A (no key)")
if funding_btc is not None:
    # thresholds: BTC > 0.10% / 8h red; 0.05–0.10 yellow
    if funding_btc >= 0.10:
        fund_status = "🔴"
    elif funding_btc >= 0.05:
        fund_status = "🟡"
    else:
        fund_status = "🟢"
    fund_detail = f"BTC {funding_btc:.3%}" + (f", SOL {funding_sol:.3%}" if funding_sol is not None else "")

# 3) Spot vs Perp Divergence (proxy: use funding sign + price drift)
sv_status, sv_detail = ("🟡" if fund_status=="🔴" else "🟢"), "Spot healthy" if fund_status!="🔴" else "Perps frothy"

# 4) LTH-SOPR (Glassnode)
lth = glassnode_lth_sopr() if GLASSNODE_KEY else None
lth_status, lth_detail = ("⚪", "N/A (no key)")
if lth is not None:
    if lth >= 4.0:
        lth_status, lth_detail = "🔴", f"{lth:.2f} (distribution)"
    elif lth >= 2.0:
        lth_status, lth_detail = "🟡", f"{lth:.2f} (profit taking)"
    else:
        lth_status, lth_detail = "🟢", f"{lth:.2f} (calm)"

# 5) MVRV Z-Score (Glassnode)
mvrv = glassnode_mvrv_z() if GLASSNODE_KEY else None
mvrv_status, mvrv_detail = ("⚪", "N/A (no key)")
if mvrv is not None:
    if mvrv >= 5.0:
        mvrv_status, mvrv_detail = "🔴", f"{mvrv:.2f} (overheated)"
    elif mvrv >= 3.0:
        mvrv_status, mvrv_detail = "🟡", f"{mvrv:.2f} (hot)"
    else:
        mvrv_status, mvrv_detail = "🟢", f"{mvrv:.2f} (normal)"

# 6) Sentiment (Fear & Greed)
sent_status, sent_detail = "⚪", "N/A"
if fg_value is not None:
    if fg_value >= 90:
        sent_status, sent_detail = "🔴", f"{fg_value} (Extreme Greed)"
    elif fg_value >= 75:
        sent_status, sent_detail = "🟡", f"{fg_value} (Greed)"
    else:
        sent_status, sent_detail = "🟢", f"{fg_value} ({fg_label})"

# 7) Rotation Climax (use dominance direction)
rot_status, rot_detail = "⚪", "N/A"
if btc_dom is not None:
    # If BTC dominance is falling fast while alts run, that’s late-cycle rotation.
    rot_status = "🟢"
    rot_detail = f"BTC.D {btc_dom:.1f}%"
    # We can’t judge "fast drop" without history; mark yellow if dominance < 50%
    if btc_dom < 50:
        rot_status = "🟡"
        rot_detail += " (alt rotation forming)"

signals = pd.DataFrame([
    ["Price Action", pa_status, pa_detail],
    ["Funding Rates", fund_status, fund_detail],
    ["Spot vs Perps", sv_status, sv_detail],
    ["LTH-SOPR", lth_status, lth_detail],
    ["MVRV Z-Score", mvrv_status, mvrv_detail],
    ["Sentiment (F&G)", sent_status, sent_detail],
    ["Rotation (BTC.D)", rot_status, rot_detail],
], columns=["Signal", "Status", "Details"])

st.subheader("Cycle-End Signals")
st.dataframe(signals, use_container_width=True)

# -----------------------------
# Your Coins – live prices + % to target ranges
# (Targets from our “realistic late-top” plan; tweak as you like)
# -----------------------------
targets = {
    "bitcoin":      (180_000, 220_000),
    "ethereum":     (12_500, 14_600),
    "solana":       (350, 450),
    "render-token": (29.2, 32.85),
    "sui":          (13.7, 15.7),
    "injective-protocol": (92.8, 106.0),
    "uniswap":      (39.2, 44.8),
    "ondo-finance": (4.31, 4.92),
    "hedera-hashgraph": (0.356, 0.401),
    "fetch-ai":     (9.52, 10.71),
    "osmosis":      (4.60, 5.18),
    "decentraland": (1.24, 1.40),
    "matic-network":(2.76, 3.11),
}

rows = []
for cid, price in cg_prices.items():
    if cid in targets and price:
        lo, hi = targets[cid]
        pct_to_lo = (lo/price - 1)*100
        pct_to_hi = (hi/price - 1)*100
        rows.append([cid, price, f"{lo} – {hi}", f"{pct_to_lo:.0f}% to {pct_to_hi:.0f}%"])

coins_df = pd.DataFrame(rows, columns=["Coin (CoinGecko id)","Price (USD)","Target range","Upside to range"])
st.subheader("Your Coins – live price vs target range")
st.dataframe(coins_df, use_container_width=True)

st.caption("🟢 healthy · 🟡 heating up · 🔴 high top risk · ⚪ requires API key")
