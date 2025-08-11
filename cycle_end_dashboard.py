# cycle_end_dashboard.py  (no Glassnode required)
import requests, datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")

HALVING_DATE = dt.date(2024, 4, 19)

# -----------------------------
# HTTP helpers
# -----------------------------
def get_json(url, params=None, timeout=25):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

# -----------------------------
# Public data sources (free)
# -----------------------------
def coingecko_prices(ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    js = get_json(url, params={"ids": ",".join(ids), "vs_currencies": "usd"})
    return {k: v["usd"] for k, v in (js or {}).items()}

def coingecko_markets(ids):
    """Prices, 24h volume, market cap, 7d % change for many coins (free)."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    js = get_json(url, params={
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "price_change_percentage": "7d",
        "per_page": len(ids),
        "page": 1
    })
    return js or []

def btc_price_history_30d():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    js = get_json(url, params={"vs_currency": "usd", "days": 30})
    if not js:
        return pd.DataFrame()
    df = pd.DataFrame(js["prices"], columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
    return df[["date","price"]]

def coingecko_global():
    return get_json("https://api.coingecko.com/api/v3/global") or {}

def fear_greed():
    js = get_json("https://api.alternative.me/fng/?limit=1&format=json")
    if js and js.get("data"):
        x = js["data"][0]
        return int(x["value"]), x["value_classification"]
    return None, None

# Binance perpetual funding (no key)
def binance_funding(symbol="BTCUSDT", limit=1):
    js = get_json("https://fapi.binance.com/fapi/v1/fundingRate",
                  params={"symbol": symbol, "limit": limit})
    try:
        return float(js[-1]["fundingRate"]) * 100  # percent per 8h
    except Exception:
        return None

# -----------------------------
# Top summary
# -----------------------------
st.title("📊 Crypto Cycle-End Dashboard (Live • Free APIs Only)")

today = dt.date.today()
day_count = (today - HALVING_DATE).days

coin_ids = [
    "bitcoin","ethereum","solana","render-token","sui","injective-protocol","uniswap","ondo-finance",
    "hedera-hashgraph","fetch-ai","osmosis","decentraland","matic-network","ripple"
]
prices = coingecko_prices(coin_ids)
glob = coingecko_global()
btc_dom = None
try:
    btc_dom = glob["data"]["market_cap_percentage"]["btc"]
except Exception:
    pass

c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", f"${prices.get('bitcoin', 0):,.0f}")
c2.metric("ETH", f"${prices.get('ethereum', 0):,.0f}")
c3.metric("SOL", f"${prices.get('solana', 0):,.0f}")
c4.metric("Days after halving", str(day_count))

st.write("---")

# -----------------------------
# Signals (all free)
# -----------------------------
rows = []

# 1) Price Action (BTC 30d change)
hist = btc_price_history_30d()
pa_status, pa_detail = "⚪", "N/A"
if not hist.empty:
    chg = (hist.iloc[-1]["price"] - hist.iloc[0]["price"]) / hist.iloc[0]["price"]
    if chg < -0.10:  pa_status, pa_detail = "🔴", f"Down {chg:.0%} in 30d"
    elif chg < 0.05: pa_status, pa_detail = "🟡", f"Flat {chg:.0%} in 30d"
    else:            pa_status, pa_detail = "🟢", f"Up {chg:.0%} in 30d"
rows.append(["Price Action", pa_status, pa_detail])

# 2) Funding Rates (Binance)
f_btc = binance_funding("BTCUSDT")
f_sol = binance_funding("SOLUSDT")
if f_btc is None:
    fund_status, fund_detail = "⚪", "N/A"
else:
    if f_btc >= 0.10:   fund_status = "🔴"
    elif f_btc >= 0.05: fund_status = "🟡"
    else:               fund_status = "🟢"
    fund_detail = f"BTC {f_btc:.3f}% / SOL {f_sol:.3f}%" if f_sol is not None else f"BTC {f_btc:.3f}%"
rows.append(["Funding Rates", fund_status, fund_detail])

# 3) Spot vs Perps (proxy using funding froth)
sv_status = "🟡" if fund_status == "🔴" else "🟢"
rows.append(["Spot vs Perps", sv_status, "Perps frothy" if fund_status=="🔴" else "Spot healthy"])

# 4) Sentiment (Fear & Greed)
fg, fg_label = fear_greed()
if fg is None:
    sent_status, sent_detail = "⚪", "N/A"
else:
    if fg >= 90:   sent_status, sent_detail = "🔴", f"{fg} (Extreme Greed)"
    elif fg >= 75: sent_status, sent_detail = "🟡", f"{fg} (Greed)"
    else:          sent_status, sent_detail = "🟢", f"{fg} ({fg_label})"
rows.append(["Sentiment (F&G)", sent_status, sent_detail])

# 5) Rotation (BTC Dominance level)
if btc_dom is None:
    rot_status, rot_detail = "⚪", "N/A"
else:
    # <50% hints alt rotation; >55% = BTC led
    if btc_dom < 50:  rot_status, rot_detail = "🟡", f"BTC.D {btc_dom:.1f}% (alt rotation forming)"
    else:             rot_status, rot_detail = "🟢", f"BTC.D {btc_dom:.1f}%"
rows.append(["Rotation (BTC.D)", rot_status, rot_detail])

# 6) Alt Breadth (how many alts are ripping weekly)
mkts = coingecko_markets(coin_ids[1:])  # exclude BTC
up_30 = 0
valid = 0
for c in mkts:
    p7 = c.get("price_change_percentage_7d_in_currency")
    if p7 is None:
        continue
    valid += 1
    if p7 >= 30:
        up_30 += 1
if valid > 0:
    share = up_30 / valid
    if share >= 0.50: breadth_status = "🔴"   # classic late-stage alt mania
    elif share >= 0.30: breadth_status = "🟡"
    else: breadth_status = "🟢"
    rows.append(["Alt Breadth (≥30% in 7d)", breadth_status, f"{up_30}/{valid} alts ({share:.0%})"])
else:
    rows.append(["Alt Breadth (≥30% in 7d)", "⚪", "N/A"])

# 7) Volume Thrust (24h volume / market cap across tracked alts)
high_turnover = 0
valid2 = 0
for c in mkts:
    mc = c.get("market_cap") or 0
    vol = c.get("total_volume") or 0
    if mc > 0:
        valid2 += 1
        if (vol / mc) >= 0.15:   # 15%+ daily turnover is hot
            high_turnover += 1
if valid2 > 0:
    share2 = high_turnover / valid2
    if share2 >= 0.50: vt_status = "🔴"
    elif share2 >= 0.30: vt_status = "🟡"
    else: vt_status = "🟢"
    rows.append(["Volume Thrust (Vol/MCap ≥15%)", vt_status, f"{high_turnover}/{valid2} alts ({share2:.0%})"])
else:
    rows.append(["Volume Thrust (Vol/MCap ≥15%)", "⚪", "N/A"])

signals = pd.DataFrame(rows, columns=["Signal","Status","Details"])
st.subheader("Cycle-End Signals")
st.dataframe(signals, use_container_width=True)

# -----------------------------
# Your coins: live price vs targets
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
    "ripple":       (2.52, 2.84)
}

rows2 = []
for cid, (lo, hi) in targets.items():
    p = prices.get(cid)
    if p:
        rows2.append([cid, p, f"{lo} – {hi}", f"{(lo/p-1)*100:.0f}% to {(hi/p-1)*100:.0f}%"])
pf = pd.DataFrame(rows2, columns=["Coin (CoinGecko id)","Price (USD)","Target range","Upside to range"])

st.subheader("Your Coins – live price vs target range")
st.dataframe(pf, use_container_width=True)

st.caption
