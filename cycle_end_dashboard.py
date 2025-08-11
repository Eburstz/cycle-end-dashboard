# cycle_end_dashboard.py  — Live dashboard using ONLY free APIs
import time, requests, datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")
HALVING_DATE = dt.date(2024, 4, 19)

# -----------------------------
# Helpers
# -----------------------------
def _get_json(url, params=None, timeout=25, tries=3, sleep=1.2):
    """Robust GET with retry + UA header to avoid simple rate limits."""
    headers = {"User-Agent": "Mozilla/5.0 (Cycle-End-Dashboard)"}
    for _ in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=headers)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(sleep)
    return None

@st.cache_data(ttl=300)  # cache 5 min
def cg_prices(ids):
    js = _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(ids), "vs_currencies": "usd"},
    )
    if not js: return {}
    return {k: v.get("usd") for k, v in js.items()}

@st.cache_data(ttl=300)
def cg_markets(ids):
    js = _get_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": ",".join(ids),
            "price_change_percentage": "7d",
            "per_page": len(ids),
            "page": 1,
        },
    )
    return js or []

@st.cache_data(ttl=300)
def cg_global():
    return _get_json("https://api.coingecko.com/api/v3/global") or {}

@st.cache_data(ttl=300)
def fear_greed():
    js = _get_json("https://api.alternative.me/fng/?limit=1&format=json")
    if js and js.get("data"):
        x = js["data"][0]
        return int(x["value"]), x["value_classification"]
    return None, None

@st.cache_data(ttl=300)
def btc_history_30d():
    js = _get_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": 30},
    )
    if not js: return pd.DataFrame()
    df = pd.DataFrame(js["prices"], columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
    return df[["date", "price"]]

# --- Binance spot ticker (fallback if CoinGecko throttles) ---
BINANCE_SYMBOLS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
    "ripple": "XRPUSDT",
    "matic-network": "MATICUSDT",
}
@st.cache_data(ttl=120)
def binance_price(symbol):
    js = _get_json("https://api.binance.com/api/v3/ticker/price", params={"symbol": symbol})
    try: return float(js["price"])
    except Exception: return None

# --- Binance perpetual funding (live, no key) ---
@st.cache_data(ttl=300)
def binance_funding(symbol="BTCUSDT", limit=1):
    js = _get_json("https://fapi.binance.com/fapi/v1/fundingRate",
                   params={"symbol": symbol, "limit": limit})
    try:
        # fundingRate is decimal per 8h interval (e.g., 0.0001 = 0.01%)
        return float(js[-1]["fundingRate"]) * 100
    except Exception:
        return None

# -----------------------------
# Top summary
# -----------------------------
st.title("📊 Crypto Cycle-End Dashboard (Live • Free APIs Only)")

day_count = (dt.date.today() - HALVING_DATE).days
coin_ids = [
    "bitcoin","ethereum","solana","render-token","sui","injective-protocol","uniswap","ondo-finance",
    "hedera-hashgraph","fetch-ai","osmosis","decentraland","matic-network","ripple"
]
prices = cg_prices(coin_ids)

# fallback majors from Binance if CoinGecko returns nothing
for cid, sym in BINANCE_SYMBOLS.items():
    if not prices.get(cid):
        p = binance_price(sym)
        if p: prices[cid] = p

glob = cg_global()
btc_dom = None
try: btc_dom = glob["data"]["market_cap_percentage"]["btc"]
except Exception: pass

c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", f"${prices.get('bitcoin', 0):,.0f}")
c2.metric("ETH", f"${prices.get('ethereum', 0):,.0f}")
c3.metric("SOL", f"${prices.get('solana', 0):,.0f}")
c4.metric("Days after halving", str(day_count))

st.write("---")

# -----------------------------
# Signals
# -----------------------------
signals = []

# 1) Price Action (30d)
hist = btc_history_30d()
if hist.empty:
    signals.append(["Price Action", "⚪", "N/A"])
else:
    chg = (hist.iloc[-1]["price"] - hist.iloc[0]["price"]) / hist.iloc[0]["price"]
    if chg < -0.10: signals.append(["Price Action","🔴", f"Down {chg:.0%} in 30d"])
    elif chg < 0.05: signals.append(["Price Action","🟡", f"Flat {chg:.0%} in 30d"])
    else: signals.append(["Price Action","🟢", f"Up {chg:.0%} in 30d"])

# 2) Funding Rates (Binance)
f_btc = binance_funding("BTCUSDT"); f_sol = binance_funding("SOLUSDT")
if f_btc is None:
    signals.append(["Funding Rates","⚪","N/A"])
else:
    if f_btc >= 0.10: f_status = "🔴"
    elif f_btc >= 0.05: f_status = "🟡"
    else: f_status = "🟢"
    detail = f"BTC {f_btc:.3f}%"
    if f_sol is not None: detail += f" / SOL {f_sol:.3f}%"
    signals.append(["Funding Rates", f_status, detail])

# 3) Spot vs Perps (proxy via funding)
signals.append(["Spot vs Perps",
                "🟡" if (f_btc is not None and f_btc >= 0.10) else "🟢",
                "Perps frothy" if (f_btc is not None and f_btc >= 0.10) else "Spot healthy"])

# 4) Sentiment (Fear & Greed)
fg, fg_label = fear_greed()
if fg is None: signals.append(["Sentiment (F&G)","⚪","N/A"])
else:
    if fg >= 90: signals.append(["Sentiment (F&G)","🔴", f"{fg} (Extreme Greed)"])
    elif fg >= 75: signals.append(["Sentiment (F&G)","🟡", f"{fg} (Greed)"])
    else: signals.append(["Sentiment (F&G)","🟢", f"{fg} ({fg_label})"])

# 5) Rotation (BTC.D)
if btc_dom is None: signals.append(["Rotation (BTC.D)","⚪","N/A"])
else:
    if btc_dom < 50: signals.append(["Rotation (BTC.D)","🟡", f"BTC.D {btc_dom:.1f}% (alt rotation forming)"])
    else: signals.append(["Rotation (BTC.D)","🟢", f"BTC.D {btc_dom:.1f}%"])

# 6) Alt Breadth (how many alts up ≥30% in 7d)
mkts = cg_markets(coin_ids[1:])  # exclude BTC
up_30 = valid = 0
for c in mkts:
    p7 = c.get("price_change_percentage_7d_in_currency")
    if p7 is None: continue
    valid += 1
    if p7 >= 30: up_30 += 1
if valid:
    share = up_30/valid
    status = "🔴" if share >= 0.50 else ("🟡" if share >= 0.30 else "🟢")
    signals.append(["Alt Breadth (≥30% in 7d)", status, f"{up_30}/{valid} alts ({share:.0%})"])
else:
    signals.append(["Alt Breadth (≥30% in 7d)", "⚪", "N/A"])

# 7) Volume Thrust (24h Vol / Market Cap across tracked alts)
high_turn = valid2 = 0
for c in mkts:
    mc = c.get("market_cap") or 0
    vol = c.get("total_volume") or 0
    if mc > 0:
        valid2 += 1
        if (vol / mc) >= 0.15: high_turn += 1
if valid2:
    share2 = high_turn/valid2
    status2 = "🔴" if share2 >= 0.50 else ("🟡" if share2 >= 0.30 else "🟢")
    signals.append(["Volume Thrust (Vol/MCap ≥15%)", status2, f"{high_turn}/{valid2} alts ({share2:.0%})"])
else:
    signals.append(["Volume Thrust (Vol/MCap ≥15%)", "⚪", "N/A"])

st.subheader("Cycle-End Signals")
st.dataframe(pd.DataFrame(signals, columns=["Signal","Status","Details"]),
             use_container_width=True)

# -----------------------------
# Your coins vs targets
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
    "ripple":       (2.52, 2.84),
}
rows = []
for cid, (lo, hi) in targets.items():
    p = prices.get(cid)
    if p:
        rows.append([cid, p, f"{lo} – {hi}", f"{(lo/p-1)*100:.0f}% to {(hi/p-1)*100:.0f}%"])

st.subheader("Your Coins – live price vs target range")
st.dataframe(pd.DataFrame(rows,
             columns=["Coin (CoinGecko id)","Price (USD)","Target range","Upside to range"]),
             use_container_width=True)

st.caption("No API keys required. If majors show $0, pull-to-refresh — Binance fallbacks usually fill within a minute.")
