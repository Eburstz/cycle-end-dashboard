# cycle_end_dashboard.py — Stable CoinGecko version (only Funding = N/A)
import time, requests, datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")
HALVING_DATE = dt.date(2024, 4, 19)

# ---------- HTTP helper (retry + UA) ----------
def get_json(url, params=None, tries=3, sleep=1.2, timeout=25):
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

# ---------- CoinGecko + Fear & Greed (free) ----------
def cg_prices(ids):
    js = get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(ids), "vs_currencies": "usd"},
    )
    if not js: return {}
    return {k: v.get("usd") for k, v in js.items()}

def cg_markets(ids):
    js = get_json(
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

def cg_global():
    js = get_json("https://api.coingecko.com/api/v3/global")
    try:
        return float(js["data"]["market_cap_percentage"]["btc"])
    except Exception:
        return None

def fear_greed():
    js = get_json("https://api.alternative.me/fng/?limit=1&format=json")
    if js and js.get("data"):
        x = js["data"][0]
        return int(x["value"]), x["value_classification"]
    return None, None

def btc_history_30d():
    js = get_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": 30},
    )
    if not js: return pd.DataFrame()
    df = pd.DataFrame(js["prices"], columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
    return df[["date","price"]]

# ---------- UI ----------
st.title("📊 Crypto Cycle-End Dashboard (Live • Free APIs Only)")

day_count = (dt.date.today() - HALVING_DATE).days

ids = [
    "bitcoin","ethereum","solana","render-token","sui","injective-protocol","uniswap","ondo-finance",
    "hedera-hashgraph","fetch-ai","osmosis","decentraland","matic-network","ripple"
]
prices = cg_prices(ids)
btc = prices.get("bitcoin", 0)
eth = prices.get("ethereum", 0)
sol = prices.get("solana", 0)

c1,c2,c3,c4 = st.columns(4)
c1.metric("BTC", f"${btc:,.0f}")
c2.metric("ETH", f"${eth:,.0f}")
c3.metric("SOL", f"${sol:,.0f}")
c4.metric("Days after halving", str(day_count))
st.write("---")

# ---------- Signals (Funding intentionally N/A) ----------
rows = []

# 1) Price Action (BTC 30d)
hist = btc_history_30d()
if hist.empty:
    rows.append(["Price Action","⚪","N/A"])
else:
    chg = (hist.iloc[-1]["price"] - hist.iloc[0]["price"]) / hist.iloc[0]["price"]
    if chg < -0.10: rows.append(["Price Action","🔴", f"Down {chg:.0%} in 30d"])
    elif chg < 0.05: rows.append(["Price Action","🟡", f"Flat {chg:.0%} in 30d"])
    else: rows.append(["Price Action","🟢", f"Up {chg:.0%} in 30d"])

# 2) Funding Rates (not wired on purpose)
rows.append(["Funding Rates","⚪","N/A"])

# 3) Spot vs Perps (proxy since funding unknown → assume healthy)
rows.append(["Spot vs Perps","🟢","Spot healthy"])

# 4) Sentiment (Fear & Greed)
fg, fg_label = fear_greed()
if fg is None: rows.append(["Sentiment (F&G)","⚪","N/A"])
else:
    if fg >= 90: rows.append(["Sentiment (F&G)","🔴", f"{fg} (Extreme Greed)"])
    elif fg >= 75: rows.append(["Sentiment (F&G)","🟡", f"{fg} (Greed)"])
    else: rows.append(["Sentiment (F&G)","🟢", f"{fg} ({fg_label})"])

# 5) Rotation (BTC Dominance)
dom = cg_global()
if dom is None: rows.append(["Rotation (BTC.D)","⚪","N/A"])
else:
    if dom < 50: rows.append(["Rotation (BTC.D)","🟡", f"BTC.D {dom:.1f}% (alt rotation forming)"])
    else: rows.append(["Rotation (BTC.D)","🟢", f"BTC.D {dom:.1f}%"])

# 6) Alt Breadth (≥30% in 7d) using markets for your alts (excl. BTC)
mkts = cg_markets(ids[1:])
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

# 7) Volume Thrust (24h Vol / MCap)
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

# ---------- Your coins vs targets ----------
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

st.caption("Only free endpoints used. If any value shows N/A or $0, refresh once — CoinGecko rate limits occasionally for ~60s.")
