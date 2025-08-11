# cycle_end_dashboard.py — Robust, no keys, with fallbacks + diagnostics
import time, requests, datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Cycle-End Dashboard", layout="wide")
HALVING_DATE = dt.date(2024, 4, 19)

# ----------------- HTTP helper -----------------
def get_json(url, params=None, tries=3, sleep=1.1, timeout=20):
    headers = {"User-Agent": "Mozilla/5.0 (Cycle-End-Dashboard)"}
    err = None
    for _ in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.json(), None
            err = f"{r.status_code} {r.text[:120]}"
        except Exception as e:
            err = str(e)
        time.sleep(sleep)
    return None, err

# ----------------- Primary sources (Binance) -----------------
@st.cache_data(ttl=300)
def binance_price(symbol):
    js, err = get_json("https://api.binance.com/api/v3/ticker/price", {"symbol": symbol})
    if js and "price" in js:
        try: return float(js["price"]), None
        except: pass
    return None, err or "no price"

@st.cache_data(ttl=300)
def binance_klines(symbol, interval="1d", limit=30):
    js, err = get_json("https://api.binance.com/api/v3/klines",
                       {"symbol": symbol, "interval": interval, "limit": limit})
    return js or [], err

@st.cache_data(ttl=300)
def binance_funding(symbol):
    js, err = get_json("https://fapi.binance.com/fapi/v1/fundingRate",
                       {"symbol": symbol, "limit": 1})
    try:
        rate = float(js[-1]["fundingRate"]) * 100
        return rate, None
    except Exception:
        return None, err or "no funding"

@st.cache_data(ttl=300)
def binance_24hr(symbol):
    js, err = get_json("https://api.binance.com/api/v3/ticker/24hr", {"symbol": symbol})
    return js or {}, err

# ----------------- Fallbacks -----------------
@st.cache_data(ttl=300)
def bybit_funding(symbol="BTCUSDT"):
    # Perp funding history; linear category for USDT contracts
    js, err = get_json(
        "https://api.bybit.com/v5/market/funding/history",
        {"category": "linear", "symbol": symbol, "limit": 1}
    )
    try:
        rate = float(js["result"]["list"][0]["fundingRate"]) * 100
        return rate, None
    except Exception:
        return None, err or "no bybit funding"

@st.cache_data(ttl=300)
def cg_btc_30d():
    js, err = get_json("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                       {"vs_currency": "usd", "days": 30})
    if js and "prices" in js:
        df = pd.DataFrame(js["prices"], columns=["ts", "price"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date
        return df[["date","price"]], None
    return pd.DataFrame(), err or "cg 30d failed"

@st.cache_data(ttl=300)
def cg_global():
    js, err = get_json("https://api.coingecko.com/api/v3/global")
    try:
        return float(js["data"]["market_cap_percentage"]["btc"]), None
    except Exception:
        return None, err or "cg global failed"

# ----------------- Config -----------------
MAJORS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
ALTS = [
    "ETHUSDT","SOLUSDT","RNDRUSDT","SUIUSDT","INJUSDT","UNIUSDT","ONDOUSDT",
    "HBARUSDT","FETUSDT","OSMOUSDT","MANAUSDT","MATICUSDT","XRPUSDT"
]
TARGETS = {
    "BTCUSDT": (180_000, 220_000),
    "ETHUSDT": (12_500, 14_600),
    "SOLUSDT": (350, 450),
    "RNDRUSDT": (29.2, 32.85),
    "SUIUSDT":  (13.7, 15.7),
    "INJUSDT":  (92.8, 106.0),
    "UNIUSDT":  (39.2, 44.8),
    "ONDOUSDT": (4.31, 4.92),
    "HBARUSDT": (0.356, 0.401),
    "FETUSDT":  (9.52, 10.71),
    "OSMOUSDT": (4.60, 5.18),
    "MANAUSDT": (1.24, 1.40),
    "MATICUSDT":(2.76, 3.11),
    "XRPUSDT":  (2.52, 2.84),
}

# ----------------- UI: Header -----------------
st.title("📊 Crypto Cycle-End Dashboard (No keys • Binance-first with fallbacks)")
day_count = (dt.date.today() - HALVING_DATE).days

p_btc, e_btc = binance_price(MAJORS["BTC"])
p_eth, e_eth = binance_price(MAJORS["ETH"])
p_sol, e_sol = binance_price(MAJORS["SOL"])

c1,c2,c3,c4 = st.columns(4)
c1.metric("BTC", f"${p_btc:,.0f}" if p_btc else "—")
c2.metric("ETH", f"${p_eth:,.0f}" if p_eth else "—")
c3.metric("SOL", f"${p_sol:,.0f}" if p_sol else "—")
c4.metric("Days after halving", str(day_count))
st.write("---")

# ----------------- Signals -----------------
signals = []
diag = {}  # diagnostics bucket

# 1) Price Action (BTC 30d)
kl, err_kl = binance_klines(MAJORS["BTC"], "1d", 30)
if not kl:
    diag["price_action"] = f"Binance klines failed: {err_kl}"
    df, err_cg = cg_btc_30d()
    if df.empty:
        signals.append(["Price Action", "⚪", "N/A"])
        diag["price_action_fallback"] = f"CoinGecko 30d failed: {err_cg}"
    else:
        chg = (df.iloc[-1]["price"] - df.iloc[0]["price"]) / df.iloc[0]["price"]
        status = "🔴" if chg < -0.10 else ("🟡" if chg < 0.05 else "🟢")
        signals.append(["Price Action", status, f"{'Down' if chg<0 else 'Up'} {abs(chg):.0%} in 30d (CG)"])
else:
    first, last = float(kl[0][4]), float(kl[-1][4])
    chg = (last - first) / first
    status = "🔴" if chg < -0.10 else ("🟡" if chg < 0.05 else "🟢")
    signals.append(["Price Action", status, f"{'Down' if chg<0 else 'Up'} {abs(chg):.0%} in 30d (Binance)"])

# 2) Funding Rates (Binance → Bybit fallback)
f_btc, f_err_b = binance_funding(MAJORS["BTC"])
f_sol, f_err_s = binance_funding(MAJORS["SOL"])
if f_btc is None:
    diag["funding_binance"] = f"BTC funding failed: {f_err_b}"
    f_btc, f_err_bb = bybit_funding("BTCUSDT")
    f_sol_alt, _ = bybit_funding("SOLUSDT")
    if f_btc is None:
        signals.append(["Funding Rates", "⚪", "N/A"])
        diag["funding_bybit"] = f"Bybit funding failed: {f_err_bb}"
    else:
        status = "🔴" if f_btc >= 0.10 else ("🟡" if f_btc >= 0.05 else "🟢")
        detail = f"BTC {f_btc:.3f}% (Bybit)"
        if f_sol_alt is not None: detail += f" / SOL {f_sol_alt:.3f}%"
        signals.append(["Funding Rates", status, detail])
else:
    status = "🔴" if f_btc >= 0.10 else ("🟡" if f_btc >= 0.05 else "🟢")
    detail = f"BTC {f_btc:.3f}% (Binance)"
    if f_sol is not None: detail += f" / SOL {f_sol:.3f}%"
    signals.append(["Funding Rates", status, detail])

# 3) Spot vs Perps (proxy via funding)
spot_status = "🟡" if (f_btc is not None and f_btc >= 0.10) else "🟢"
signals.append(["Spot vs Perps", spot_status,
                "Perps frothy" if spot_status=="🟡" else "Spot healthy"])

# 4) Sentiment (Fear & Greed)
fg_js, fg_err = get_json("https://api.alternative.me/fng/?limit=1&format=json")
if fg_js and fg_js.get("data"):
    fg = int(fg_js["data"][0]["value"])
    label = fg_js["data"][0]["value_classification"]
    status = "🔴" if fg >= 90 else ("🟡" if fg >= 75 else "🟢")
    signals.append(["Sentiment (F&G)", status, f"{fg} ({label})"])
else:
    signals.append(["Sentiment (F&G)", "⚪", "N/A"])
    diag["fear_greed"] = f"F&G failed: {fg_err}"

# 5) Rotation (BTC Dominance) — optional
dom, err_dom = cg_global()
if dom is None:
    signals.append(["Rotation (BTC.D)", "⚪", "N/A"])
    diag["dominance"] = f"CG global failed: {err_dom}"
else:
    status = "🟡" if dom < 50 else "🟢"
    detail = f"BTC.D {dom:.1f}%" + (" (alt rotation forming)" if status=="🟡" else "")
    signals.append(["Rotation (BTC.D)", status, detail])

# 6) Alt Breadth (≥30% in ~7d) via Binance klines
up_30, valid, errs = 0, 0, []
for sym in ALTS:
    ks, err = binance_klines(sym, "1d", 8)  # last 8 candles ≈ 7 days span
    if not ks:
        errs.append(f"{sym}:{err}")
        continue
    start, end = float(ks[0][4]), float(ks[-1][4])
    if start <= 0: 
        errs.append(f"{sym}:start<=0")
        continue
    valid += 1
    if (end - start) / start >= 0.30:
        up_30 += 1

if valid:
    share = up_30 / valid
    status = "🔴" if share >= 0.50 else ("🟡" if share >= 0.30 else "🟢")
    signals.append(["Alt Breadth (≥30% in 7d)", status, f"{up_30}/{valid} alts ({share:.0%})"])
else:
    signals.append(["Alt Breadth (≥30% in 7d)", "⚪", "N/A"])
    if errs: diag["breadth"] = "; ".join(errs[:3]) + (" ..." if len(errs)>3 else "")

# 7) Volume Thrust (heuristic) using 24h notional
high_turn, valid2, errs2 = 0, 0, []
for sym in ALTS:
    t, errt = binance_24hr(sym)
    try:
        price = float(t["lastPrice"])
        qvol  = float(t["quoteVolume"])  # USDT notional
        if price > 0:
            valid2 += 1
            # Heuristic: high activity if notional traded > fixed proxy of cap
            if (qvol / (price * 1e8)) >= 0.10:
                high_turn += 1
    except Exception:
        errs2.append(f"{sym}:{errt}")

if valid2:
    share2 = high_turn / valid2
    status2 = "🔴" if share2 >= 0.50 else ("🟡" if share2 >= 0.30 else "🟢")
    signals.append(["Volume Thrust (heuristic)", status2, f"{high_turn}/{valid2} alts ({share2:.0%})"])
else:
    signals.append(["Volume Thrust (heuristic)", "⚪", "N/A"])
    if errs2: diag["volume"] = "; ".join(errs2[:3]) + (" ..." if len(errs2)>3 else "")

st.subheader("Cycle-End Signals")
st.dataframe(pd.DataFrame(signals, columns=["Signal","Status","Details"]), use_container_width=True)

# ----------------- Portfolio vs targets (Binance spot) -----------------
rows = []
for sym, (lo, hi) in TARGETS.items():
    p, e = binance_price(sym)
    if p:
        rows.append([sym.replace("USDT",""), p, f"{lo} – {hi}",
                     f"{(lo/p-1)*100:.0f}% to {(hi/p-1)*100:.0f}%"])
st.subheader("Your Coins – live price vs target range")
st.dataframe(pd.DataFrame(rows, columns=["Coin","Price (USD)","Target range","Upside to range"]),
             use_container_width=True)

# ----------------- Diagnostics (toggle) -----------------
with st.expander("Diagnostics (why something might be N/A)"):
    if not diag:
        st.write("All primary calls succeeded recently.")
    else:
        for k, v in diag.items():
            st.write(f"**{k}** → {v}")
st.caption("Tip: If a row shows
