# cycle_end_dashboard.py — Stable (5-min cache) + Funding (Binance→Bybit→OKX) + Diagnostics
import time, requests, datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")
HALVING_DATE = dt.date(2024, 4, 19)

# ---------------- Robust GET with exponential backoff ----------------
def _get_json(url, params=None, timeout=25, tries=5, base_sleep=0.8, tag=None):
    headers = {"User-Agent": "Mozilla/5.0 (Cycle-End-Dashboard)"}
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=headers)
            if r.status_code == 200:
                return r.json()
            last_err = f"{r.status_code} {r.text[:120]}"
        except Exception as e:
            last_err = str(e)
        time.sleep(base_sleep * (2 ** i))
    if tag:
        st.session_state.setdefault("diag_errors", []).append(f"{tag}: {url} -> {last_err}")
    return None

# ---------------- CoinGecko + F&G (all cached 5 min) ----------------
@st.cache_data(ttl=300)
def cg_prices(ids):
    js = _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(ids), "vs_currencies": "usd"},
        tag="cg_prices",
    ) or {}
    return {k: v.get("usd") for k, v in js.items()}

@st.cache_data(ttl=300)
def cg_markets(ids):
    return _get_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": ",".join(ids),
            "price_change_percentage": "7d",
            "per_page": len(ids),
            "page": 1,
        },
        tag="cg_markets",
    ) or []

@st.cache_data(ttl=300)
def cg_global():
    js = _get_json("https://api.coingecko.com/api/v3/global", tag="cg_global") or {}
    try:
        return float(js["data"]["market_cap_percentage"]["btc"])
    except Exception:
        return None

@st.cache_data(ttl=300)
def btc_history_30d():
    js = _get_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": 30},
        tag="btc_history_30d",
    )
    if not js or "prices" not in js:
        return pd.DataFrame()
    df = pd.DataFrame(js["prices"], columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
    return df[["date", "price"]]

@st.cache_data(ttl=300)
def fear_greed():
    js = _get_json("https://api.alternative.me/fng/?limit=1&format=json", tag="fear_greed")
    if js and js.get("data"):
        x = js["data"][0]
        return int(x["value"]), x["value_classification"]
    return None, None

# ---------------- Funding helpers (no keys) ----------------
@st.cache_data(ttl=300)
def binance_funding(symbol="BTCUSDT", limit=1):
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": limit},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        if r.status_code == 200:
            js = r.json()
            return float(js[-1]["fundingRate"]) * 100
        else:
            st.session_state.setdefault("fund_diag", []).append(f"Binance {symbol}: {r.status_code}")
    except Exception as e:
        st.session_state.setdefault("fund_diag", []).append(f"Binance {symbol} err: {e}")
    return None

@st.cache_data(ttl=300)
def bybit_funding(symbol="BTCUSDT"):
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/funding/history",
            params={"category": "linear", "symbol": symbol, "limit": 1},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        if r.status_code == 200:
            js = r.json()
            return float(js["result"]["list"][0]["fundingRate"]) * 100
        else:
            st.session_state.setdefault("fund_diag", []).append(f"Bybit {symbol}: {r.status_code}")
    except Exception as e:
        st.session_state.setdefault("fund_diag", []).append(f"Bybit {symbol} err: {e}")
    return None

@st.cache_data(ttl=300)
def okx_funding(inst_id="BTC-USDT-SWAP"):
    try:
        r = requests.get(
            "https://www.okx.com/api/v5/public/funding-rate",
            params={"instId": inst_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        if r.status_code == 200:
            js = r.json()
            data = js.get("data", [])
            if data:
                return float(data[0]["fundingRate"]) * 100
        else:
            st.session_state.setdefault("fund_diag", []).append(f"OKX {inst_id}: {r.status_code}")
    except Exception as e:
        st.session_state.setdefault("fund_diag", []).append(f"OKX {inst_id} err: {e}")
    return None

# ---------------- UI Header ----------------
st.title("📊 Crypto Cycle-End Dashboard (5-min cache • Free APIs • Multi-source Funding)")

# Manual refresh button
left, _ = st.columns([1, 3])
with left:
    if st.button("🔄 Refresh now (clear 5-min cache)"):
        st.cache_data.clear()
        st.session_state.pop("diag_errors", None)
        st.session_state.pop("fund_diag", None)
        st.experimental_rerun()

day_count = (dt.date.today() - HALVING_DATE).days

ids = [
    "bitcoin","ethereum","solana","render-token","sui","injective-protocol","uniswap","ondo-finance",
    "hedera-hashgraph","fetch-ai","osmosis","decentraland","matic-network","ripple"
]
prices = cg_prices(ids)
btc = prices.get("bitcoin", 0)
eth = prices.get("ethereum", 0)
sol = prices.get("solana", 0)

c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", f"${btc:,.0f}")
c2.metric("ETH", f"${eth:,.0f}")
c3.metric("SOL", f"${sol:,.0f}")
c4.metric("Days after halving", str(day_count))
st.write("---")

# ---------------- Signals ----------------
rows = []

# 1) Price Action (BTC 30d)
hist = btc_history_30d()
if hist.empty:
    rows.append(["Price Action", "⚪", "N/A"])
else:
    chg = (hist.iloc[-1]["price"] - hist.iloc[0]["price"]) / hist.iloc[0]["price"]
    if chg < -0.10: rows.append(["Price Action","🔴", f"Down {chg:.0%} in 30d"])
    elif chg < 0.05: rows.append(["Price Action","🟡", f"Flat {chg:.0%} in 30d"])
    else: rows.append(["Price Action","🟢", f"Up {chg:.0%} in 30d"])

# 2) Funding Rates (Binance → Bybit → OKX)
f_btc = binance_funding("BTCUSDT")
f_sol = binance_funding("SOLUSDT")
if f_btc is None: f_btc = bybit_funding("BTCUSDT")
if f_sol is None: f_sol = bybit_funding("SOLUSDT")
if f_btc is None: f_btc = okx_funding("BTC-USDT-SWAP")
if f_sol is None: f_sol = okx_funding("SOL-USDT-SWAP")

if f_btc is None:
    rows.append(["Funding Rates", "⚪", "N/A"])
else:
    if f_btc >= 0.10: status = "🔴"
    elif f_btc >= 0.05: status = "🟡"
    else: status = "🟢"
    detail = f"BTC {f_btc:.3f}%"
    if f_sol is not None:
        detail += f" / SOL {f_sol:.3f}%"
    rows.append(["Funding Rates", status, detail])

# 3) Spot vs Perps (proxy via funding)
rows.append([
    "Spot vs Perps",
    "🟡" if (f_btc is not None and f_btc >= 0.10) else "🟢",
    "Perps frothy" if (f_btc is not None and f_btc >= 0.10) else "Spot healthy"
])

# 4) Sentiment (F&G)
fg, fg_label = fear_greed()
if fg is None:
    rows.append(["Sentiment (F&G)","⚪","N/A"])
else:
    if fg >= 90: rows.append(["Sentiment (F&G)","🔴", f"{fg} (Extreme Greed)"])
    elif fg >= 75: rows.append(["Sentiment (F&G)","🟡", f"{fg} (Greed)"])
    else: rows.append(["Sentiment (F&G)","🟢", f"{fg} ({fg_label})"])

# 5) Rotation (BTC.D)
dom = cg_global()
if dom is None:
    rows.append(["Rotation (BTC.D)","⚪","N/A"])
else:
    if dom < 50: rows.append(["Rotation (BTC.D)","🟡", f"BTC.D {dom:.1f}% (alt rotation forming)"])
    else: rows.append(["Rotation (BTC.D)","🟢", f"BTC.D {dom:.1f}%"])

# 6) Alt Breadth (≥30% in 7d)
mkts = cg_markets(ids[1:])  # exclude BTC
up_30, valid = 0, 0
for c in mkts:
    p7 = c.get("price_change_percentage_7d_in_currency")
    if p7 is None: continue
    valid += 1
    if p7 >= 30: up_30 += 1
if valid:
    share = up_30/valid
    rows.append(["Alt Breadth (≥30% in 7d)",
                 "🔴" if share>=0.50 else ("🟡" if share>=0.30 else "🟢"),
                 f"{up_30}/{valid} alts ({share:.0%})"])
else:
    rows.append(["Alt Breadth (≥30% in 7d)","⚪","N/A"])

# 7) Volume Thrust (Vol/MCap ≥15%)
high_turn, valid2 = 0, 0
for c in mkts:
    mc = c.get("market_cap") or 0
    vol = c.get("total_volume") or 0
    if mc > 0:
        valid2 += 1
        if (vol/mc) >= 0.15:
            high_turn += 1
if valid2:
    share2 = high_turn/valid2
    rows.append(["Volume Thrust (Vol/MCap ≥15%)",
                 "🔴" if share2>=0.50 else ("🟡" if share2>=0.30 else "🟢"),
                 f"{high_turn}/{valid2} alts ({share2:.0%})"])
else:
    rows.append(["Volume Thrust (Vol/MCap ≥15%)","⚪","N/A"])

st.subheader("Cycle-End Signals")
st.dataframe(pd.DataFrame(rows, columns=["Signal","Status","Details"]), use_container_width=True)

# ---------------- Your coins vs target range ----------------
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
rows2 = []
for cid,(lo,hi) in targets.items():
    p = prices.get(cid)
    if p:
        rows2.append([cid, p, f"{lo} – {hi}", f"{(lo/p-1)*100:.0f}% to {(hi/p-1)*100:.0f}%"])

st.subheader("Your Coins – live price vs target range")
st.dataframe(pd.DataFrame(rows2,
             columns=["Coin (CoinGecko id)","Price (USD)","Target range","Upside to range"]),
             use_container_width=True)

# ---------------- Diagnostics ----------------
with st.expander("Diagnostics"):
    errs = st.session_state.get("diag_errors", [])
    if errs:
        st.write("Recent fetch errors:")
        for e in errs[-8:]:
            st.write("•", e)
    else:
        st.write("No CoinGecko/F&G fetch errors recorded this run.")
    fd = st.session_state.get("fund_diag", [])
    if fd:
        st.write("Funding diagnostics:")
        for line in fd[-8:]:
            st.write("•", line)
