"""
Sentinel-BIST Mobile Dashboard.
Streamlit web interface: balance, positions, Start/Stop engine toggle.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
import yfinance as yf

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
STATE_FILE = DATA_DIR / "simulator_state.json"
ENGINE_STATUS_FILE = DATA_DIR / "engine_status.json"


def load_state() -> dict:
    """Load simulator state from JSON."""
    if not STATE_FILE.exists():
        return {
            "virtual_balance": 100_000.0,
            "initial_balance": 100_000.0,
            "positions": {},
            "trade_history": [],
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"virtual_balance": 100_000.0, "initial_balance": 100_000.0, "positions": {}, "trade_history": []}


def load_engine_status() -> bool:
    """Return True if engine is set to running."""
    if not ENGINE_STATUS_FILE.exists():
        return False
    try:
        with open(ENGINE_STATUS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("running", False)
    except Exception:
        return False


def save_engine_status(running: bool) -> None:
    """Persist engine running state."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ENGINE_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"running": running}, f, indent=2)


def get_current_price(ticker: str) -> float:
    """Fetch current price for ticker."""
    try:
        t = ticker if ticker.endswith(".IS") else f"{ticker}.IS"
        hist = yf.Ticker(t).history(period="5d")
        if hist.empty:
            return 0.0
        return float(hist["Close"].iloc[-1])
    except Exception:
        return 0.0


def main() -> None:
    st.set_page_config(
        page_title="Sentinel-BIST",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.title("📊 Sentinel-BIST")
    st.caption("Silent Autonomous Mode | Local Stop switch | Monitor via Midas")

    state = load_state()
    balance = state.get("virtual_balance", 0.0)
    initial = state.get("initial_balance", 100_000.0)
    positions = state.get("positions", {})

    # Position value (mark-to-market)
    position_value = 0.0
    for ticker, pos in positions.items():
        qty = pos.get("quantity", 0)
        price = get_current_price(ticker)
        position_value += qty * price

    total = balance + position_value
    pnl = total - initial
    pnl_pct = 100 * pnl / initial if initial > 0 else 0

    # --- Metrics Row ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Virtual Balance", f"{balance:,.2f} TL", delta=None)
    with col2:
        st.metric("Position Value", f"{position_value:,.2f} TL", delta=None)
    with col3:
        st.metric("Total Equity", f"{total:,.2f} TL", delta=None)
    with col4:
        st.metric("P&L", f"{pnl:+,.2f} TL ({pnl_pct:+.2f}%)", delta=f"{pnl_pct:+.1f}%")

    st.divider()

    # --- Active Positions ---
    st.subheader("Active Positions")
    if not positions:
        st.info("No active positions.")
    else:
        rows = []
        for ticker, pos in positions.items():
            qty = pos.get("quantity", 0)
            entry = pos.get("entry_price", 0)
            current = get_current_price(ticker)
            value = qty * current
            cost_basis = qty * entry
            pos_pnl = value - cost_basis
            pos_pnl_pct = 100 * pos_pnl / cost_basis if cost_basis > 0 else 0
            rows.append({
                "Ticker": ticker,
                "Quantity": f"{qty:,.0f}",
                "Entry": f"{entry:,.2f} TL",
                "Current": f"{current:,.2f} TL",
                "Value": f"{value:,.2f} TL",
                "P&L": f"{pos_pnl:+,.2f} ({pos_pnl_pct:+.1f}%)",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()

    # --- Stop Switch ---
    st.subheader("Engine Control (Stop Switch)")
    engine_running = load_engine_status()

    col_a, col_b, _ = st.columns([1, 1, 2])
    with col_a:
        if st.button("▶️ Start Engine", type="primary", use_container_width=True):
            save_engine_status(True)
            st.rerun()
    with col_b:
        if st.button("⏹️ Stop Engine", type="secondary", use_container_width=True):
            save_engine_status(False)
            st.rerun()

    status_color = "green" if engine_running else "red"
    status_text = "🟢 Running" if engine_running else "🔴 Stopped"
    st.markdown(f"**Status:** :{status_color}[{status_text}]")
    st.caption("Use Stop to halt the bot. Monitor positions via Midas brokerage UI.")

    st.divider()
    st.caption("Sentinel-BIST | Internal Use Only")


if __name__ == "__main__":
    main()
