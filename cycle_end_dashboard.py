import streamlit as st
import pandas as pd
import datetime as dt

st.set_page_config(page_title="Crypto Cycle-End Tracker", layout="wide")

st.title("📈 Crypto Cycle-End Tracker (Mock Data)")

# Mock cycle days
halving_date = dt.date(2024, 4, 20)
today = dt.date.today()
days_since_halving = (today - halving_date).days

st.subheader(f"Days since halving: {days_since_halving} days")

# Mock portfolio data
data = {
    "Coin": ["BTC", "ETH", "SOL", "SUI", "ONDO"],
    "Current Price": [71000, 3700, 181, 3.9, 1.05],
    "Cycle Target": [95000, 5200, 600, 6.5, 1.8],
    "Potential Upside (%)": [
        round((95000 / 71000 - 1) * 100, 1),
        round((5200 / 3700 - 1) * 100, 1),
        round((600 / 181 - 1) * 100, 1),
        round((6.5 / 3.9 - 1) * 100, 1),
        round((1.8 / 1.05 - 1) * 100, 1)
    ]
}

df = pd.DataFrame(data)

st.dataframe(df, use_container_width=True)

st.info("⚠️ This is mock data. Live price integration coming soon.")
