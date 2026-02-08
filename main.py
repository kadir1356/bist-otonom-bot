"""
Sentinel-BIST: Hybrid Algorithmic Trading Bot for Borsa Istanbul.
Live loop: runs every 15 min during BIST hours (09:55–18:10 Istanbul).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from engine import HybridDecisionEngine
from broker.simulator import VirtualBroker
from analyzers.technical import BIST30_TICKERS

load_dotenv()

ISTANBUL = ZoneInfo("Europe/Istanbul")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
STATE_FILE = DATA_DIR / "simulator_state.json"
ENGINE_STATUS_FILE = DATA_DIR / "engine_status.json"

BIST_START = (9, 55)   # 09:55
BIST_END = (18, 10)    # 18:10
INTERVAL_MINUTES = 15


def is_engine_running() -> bool:
    """Check if dashboard has enabled the engine."""
    if not ENGINE_STATUS_FILE.exists():
        return False
    try:
        with open(ENGINE_STATUS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("running", False)
    except Exception:
        return False


def is_bist_trading_hours() -> bool:
    """Return True if current time is within BIST hours (Istanbul)."""
    now = datetime.now(ISTANBUL)
    h, m = now.hour, now.minute
    current_minutes = h * 60 + m
    start_minutes = BIST_START[0] * 60 + BIST_START[1]
    end_minutes = BIST_END[0] * 60 + BIST_END[1]
    return start_minutes <= current_minutes < end_minutes


def run_one_cycle() -> None:
    """Run one evaluation cycle. Silent autonomous mode — no external alerts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    broker = VirtualBroker(
        initial_balance=100_000.0,
        data_path=STATE_FILE,
    )
    engine = HybridDecisionEngine(broker=broker, data_path=DATA_DIR)

    tickers = list(BIST30_TICKERS)
    current_holding = list(broker.positions.keys())[0] if broker.positions else None

    engine.run_cycle(tickers, current_holding=current_holding)


def main() -> None:
    """Live loop: run every 15 min during BIST hours when engine is enabled."""
    print("Sentinel-BIST | Silent Autonomous Mode")
    print("BIST hours: 09:55 - 18:10 Istanbul | Max 3 trades/day")
    print("Stop switch: streamlit run app.py")
    print("-" * 50)

    while True:
        now = datetime.now(ISTANBUL)
        if is_engine_running() and is_bist_trading_hours():
            print(f"[{now.strftime('%H:%M:%S')}] Running cycle...")
            try:
                run_one_cycle()
            except Exception as e:
                print(f"  Error: {e}")
        else:
            if not is_engine_running():
                status = "Engine stopped (dashboard)"
            else:
                status = "Outside BIST hours"
            print(f"[{now.strftime('%H:%M:%S')}] Idle - {status}")

        # Sleep until next 15-min mark
        sleep_seconds = INTERVAL_MINUTES * 60
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
