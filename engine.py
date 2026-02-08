"""
Hybrid Decision Engine for Sentinel-BIST.
Academic basis: Fama-French (Value + Momentum), MIT Sloan Risk, Keynes' Animal Spirits.
Combines Technical (T) and Sentiment (S) scores. Executes trade only when aligned.
Enforces max 3 trades per day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import yfinance as yf

from analyzers.technical import TechnicalAnalyzer
from analyzers.sentiment import SentimentAnalyzer
from broker.simulator import VirtualBroker


@dataclass
class DecisionResult:
    """Result of hybrid decision evaluation."""

    action: str  # "BUY", "SELL", "HOLD"
    ticker: str
    T_score: float
    S_score: float
    confidence_score: float  # Adjusted for Animal Spirits risk
    aligned: bool
    daily_trades_left: int
    reason: str = ""


class HybridDecisionEngine:
    """
    Hybrid Decision Engine: T (Technical) + S (Sentiment).
    Rules:
      - MIT Sloan: SELL if position drops >3% from peak (uses 1 daily trade)
      - Keynes' Animal Spirits: Reduce confidence 30% if sentiment contains
        'enflasyon' or 'belirsizlik'
      - Execute trade ONLY if T and S align. Max 3 rebalancing actions per day.
    """

    MAX_DAILY_TRADES = 3
    ALIGNMENT_THRESHOLD = 0.2
    DRAWDOWN_THRESHOLD = 0.03  # MIT Sloan: 3% drop from peak triggers SELL
    ANIMAL_SPIRITS_PENALTY = 0.30  # Reduce confidence by 30% when risk keywords present

    def __init__(
        self,
        broker: Optional[VirtualBroker] = None,
        data_path: Optional[Path] = None,
    ):
        self.technical = TechnicalAnalyzer()
        self.sentiment = SentimentAnalyzer()
        self.broker = broker or VirtualBroker(data_path=data_path)
        self._trade_counter_date: Optional[date] = None
        self._trade_count_today: int = 0
        self._peak_prices: dict[str, float] = {}  # MIT Sloan: track peak per position

    def _refresh_daily_counter(self) -> None:
        """Reset trade count at start of new day."""
        today = date.today()
        if self._trade_counter_date != today:
            self._trade_counter_date = today
            self._trade_count_today = 0

    def _increment_trade_count(self) -> bool:
        """Increment trade count; return True if under limit."""
        self._refresh_daily_counter()
        if self._trade_count_today >= self.MAX_DAILY_TRADES:
            return False
        self._trade_count_today += 1
        return True

    def _trades_remaining(self) -> int:
        """Number of trades left today."""
        self._refresh_daily_counter()
        return max(0, self.MAX_DAILY_TRADES - self._trade_count_today)

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Fetch current (last close) price for ticker."""
        t = ticker.upper()
        if not t.endswith(".IS"):
            t = f"{t}.IS"
        try:
            hist = yf.Ticker(t).history(period="5d")
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception:
            return None

    def _check_drawdown_sell(self, ticker: str) -> bool:
        """
        MIT Sloan Standards: If position drops >3% from peak, trigger SELL.
        Returns True if SELL should be triggered.
        """
        pos = self.broker.get_position(ticker) if self.broker else None
        if not pos:
            return False

        current = self._get_current_price(ticker)
        if current is None:
            return False

        peak = self._peak_prices.get(ticker, pos.entry_price)
        peak = max(peak, current)
        self._peak_prices[ticker] = peak

        drawdown = (peak - current) / peak
        return drawdown >= self.DRAWDOWN_THRESHOLD

    def _aligned(self, T: float, S: float, confidence: float) -> tuple[bool, str]:
        """
        Check if T and S align for a trade.
        Confidence Score reduces effective alignment threshold when < 1.0.
        Returns (aligned, direction).
        """
        thresh = self.ALIGNMENT_THRESHOLD / confidence if confidence > 0 else self.ALIGNMENT_THRESHOLD
        if T > thresh and S > thresh:
            return True, "bullish"
        if T < -thresh and S < -thresh:
            return True, "bearish"
        return False, "neutral"

    def evaluate(
        self,
        ticker: str,
        current_holding: Optional[str] = None,
    ) -> DecisionResult:
        """
        Evaluate whether to BUY, SELL, or HOLD.
        MIT Sloan: SELL if position drops >3% from peak.
        Animal Spirits: Reduce confidence 30% if 'enflasyon' or 'belirsizlik' in sentiment.
        """
        remaining = self._trades_remaining()
        if remaining <= 0:
            return DecisionResult(
                action="HOLD",
                ticker=ticker,
                T_score=0.0,
                S_score=0.0,
                confidence_score=1.0,
                aligned=False,
                daily_trades_left=0,
                reason="Daily trade limit (3) reached.",
            )

        # --- MIT Sloan: Check drawdown for current holding first ---
        if current_holding and self._check_drawdown_sell(current_holding):
            if self._increment_trade_count():
                return DecisionResult(
                    action="SELL",
                    ticker=current_holding,
                    T_score=0.0,
                    S_score=0.0,
                    confidence_score=1.0,
                    aligned=True,
                    daily_trades_left=self._trades_remaining(),
                    reason="MIT Sloan: Position dropped >3% from peak. Sell triggered.",
                )
            return DecisionResult(
                action="HOLD",
                ticker=current_holding,
                T_score=0.0,
                S_score=0.0,
                confidence_score=1.0,
                aligned=True,
                daily_trades_left=0,
                reason="Drawdown SELL required but daily limit reached.",
            )

        # --- Sentiment with Animal Spirits risk check ---
        try:
            S, has_animal_spirits_risk = self.sentiment.score_for_ticker_with_risk(ticker)
        except Exception:
            S = 0.0
            has_animal_spirits_risk = False

        # Keynes' Animal Spirits: Reduce confidence 30% if risk keywords present
        confidence = 1.0 - self.ANIMAL_SPIRITS_PENALTY if has_animal_spirits_risk else 1.0

        # --- Downside risk: analyze current holding for bearish signals ---
        if current_holding:
            try:
                T_hold, _ = self.technical.analyze(current_holding)
            except Exception:
                T_hold = 0.0
            try:
                S_hold, risk_hold = self.sentiment.score_for_ticker_with_risk(current_holding)
                conf_hold = 1.0 - self.ANIMAL_SPIRITS_PENALTY if risk_hold else 1.0
            except Exception:
                S_hold = 0.0
                conf_hold = 1.0
            aligned_hold, dir_hold = self._aligned(T_hold, S_hold, conf_hold)
            if aligned_hold and dir_hold == "bearish":
                if self._increment_trade_count():
                    return DecisionResult(
                        action="SELL",
                        ticker=current_holding,
                        T_score=T_hold,
                        S_score=S_hold,
                        confidence_score=conf_hold,
                        aligned=True,
                        daily_trades_left=self._trades_remaining(),
                        reason="Downside risk detected; rebalancing.",
                    )
                return DecisionResult(
                    action="HOLD",
                    ticker=current_holding,
                    T_score=T_hold,
                    S_score=S_hold,
                    confidence_score=conf_hold,
                    aligned=True,
                    daily_trades_left=0,
                    reason="Downside risk but daily limit reached.",
                )

        # --- Bullish alignment for ticker: consider BUY ---
        try:
            T, _ = self.technical.analyze(ticker)
        except Exception as e:
            return DecisionResult(
                action="HOLD",
                ticker=ticker,
                T_score=0.0,
                S_score=S,
                confidence_score=confidence,
                aligned=False,
                daily_trades_left=remaining,
                reason=f"Technical analysis failed: {e}",
            )

        aligned, direction = self._aligned(T, S, confidence)
        if aligned and direction == "bullish":
            if self._increment_trade_count():
                return DecisionResult(
                    action="BUY",
                    ticker=ticker,
                    T_score=T,
                    S_score=S,
                    confidence_score=confidence,
                    aligned=True,
                    daily_trades_left=self._trades_remaining(),
                    reason="Technical and sentiment aligned bullish."
                    + (" (Confidence reduced: Animal Spirits risk)" if confidence < 1.0 else ""),
                )

        return DecisionResult(
            action="HOLD",
            ticker=ticker,
            T_score=T,
            S_score=S,
            confidence_score=confidence,
            aligned=aligned,
            daily_trades_left=remaining,
            reason="T and S not aligned for trade."
            + (" (Confidence reduced: enflasyon/belirsizlik in news)" if confidence < 1.0 else ""),
        )

    def run_cycle(
        self,
        tickers: list[str],
        current_holding: Optional[str] = None,
    ) -> list[DecisionResult]:
        """
        Run one evaluation cycle over tickers.
        Optionally execute via virtual broker (paper trade).
        """
        results = []
        holding = current_holding

        for ticker in tickers:
            res = self.evaluate(ticker, current_holding=holding)
            results.append(res)

            if res.action == "BUY" and self.broker:
                self.broker.execute_buy(ticker, 1)
                holding = ticker
                self._peak_prices[ticker] = self._get_current_price(ticker) or 0.0
            elif res.action == "SELL" and self.broker and res.ticker:
                self.broker.execute_sell(res.ticker, 1)
                self._peak_prices.pop(res.ticker, None)
                holding = None

        return results
