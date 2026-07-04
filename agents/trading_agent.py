"""
trading_agent.py
────────────────
JARVIS market desk. Watches crypto pairs on Luno (public market data,
no API keys needed), alerts on significant moves, runs a simple
moving-average strategy, and manages a PAPER portfolio — real market
prices, pretend money — so the strategy can prove itself safely.

Live-money execution is deliberately not wired in. When the paper
record convinces you, connecting Luno API keys and an execution path
is a separate, explicit step — not something JARVIS slides into.
"""

import json
import threading
from collections import deque
from datetime import datetime

import httpx

import config
from agents.base_agent import BaseAgent

TICKER_URL = "https://api.luno.com/api/1/ticker"

# strategy windows, in samples (one sample per tick ≈ 1 min)
SMA_FAST, SMA_SLOW = 10, 30
MOVE_WINDOW        = 15          # minutes for the %-move alert


class TradingAgent(BaseAgent):

    name        = "Trading"
    description = "Luno price watch, signals, paper portfolio"

    def __init__(self, brain=None):
        super().__init__(brain=brain,
                         interval_seconds=config.TRADING_CHECK_SECONDS)
        self.prices   = {p: deque(maxlen=200) for p in config.TRADING_PAIRS}
        self.latest   = {}
        self._signal  = {p: None for p in config.TRADING_PAIRS}  # last cross state
        self._alerted = {}
        self._plock   = threading.Lock()
        self.portfolio = self._load_portfolio()

    # ── portfolio persistence ───────────────────
    def _load_portfolio(self):
        try:
            if config.PORTFOLIO_FILE.exists():
                return json.loads(config.PORTFOLIO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"cash": config.PAPER_STARTING_CASH,
                "holdings": {},          # pair -> {"units":…, "avg_price":…}
                "trades": []}

    def _save_portfolio(self):
        try:
            config.PORTFOLIO_FILE.parent.mkdir(exist_ok=True)
            config.PORTFOLIO_FILE.write_text(
                json.dumps(self.portfolio, indent=2), encoding="utf-8")
        except Exception as e:
            self.log(f"portfolio save failed: {e}")

    # ── market data ─────────────────────────────
    def _fetch(self, pair):
        r = httpx.get(TICKER_URL, params={"pair": pair}, timeout=15)
        r.raise_for_status()
        return float(r.json()["last_trade"])

    def tick(self):
        for pair in config.TRADING_PAIRS:
            price = self._fetch(pair)
            self.prices[pair].append(price)
            self.latest[pair] = price
            self._check_move_alert(pair)
            self._check_sma_signal(pair)
        self.last_message = "  ".join(
            f"{p}: R{v:,.0f}" for p, v in self.latest.items())

    # ── alerts & strategy ───────────────────────
    def _check_move_alert(self, pair):
        hist = self.prices[pair]
        if len(hist) < MOVE_WINDOW:
            return
        old, new = hist[-MOVE_WINDOW], hist[-1]
        pct = (new - old) / old * 100
        if abs(pct) >= config.TRADING_MOVE_ALERT_PCT:
            key = (pair, datetime.now().strftime("%Y%m%d%H"))
            if self._alerted.get(key):
                return
            self._alerted[key] = True
            arrow = "up" if pct > 0 else "down"
            self.say(f"{pair} is {arrow} {abs(pct):.1f}% in {MOVE_WINDOW} minutes "
                     f"— now R{new:,.0f}.", speak=True)

    def _sma(self, pair, n):
        hist = self.prices[pair]
        if len(hist) < n:
            return None
        vals = list(hist)[-n:]
        return sum(vals) / n

    def _check_sma_signal(self, pair):
        fast, slow = self._sma(pair, SMA_FAST), self._sma(pair, SMA_SLOW)
        if fast is None or slow is None:
            return
        state = "bull" if fast > slow else "bear"
        prev  = self._signal[pair]
        self._signal[pair] = state
        if prev is None or state == prev:
            return
        if state == "bull":
            self.say(f"Signal: {pair} golden cross (fast SMA over slow). "
                     f"Buying with 10% of paper cash.", speak=False)
            self.paper_trade("buy", pair,
                             amount_zar=self.portfolio["cash"] * 0.10,
                             reason="SMA golden cross")
        else:
            held = self.portfolio["holdings"].get(pair, {}).get("units", 0)
            if held > 0:
                self.say(f"Signal: {pair} death cross. Closing paper position.",
                         speak=False)
                self.paper_trade("sell", pair, units=held,
                                 reason="SMA death cross")

    # ── paper trading ───────────────────────────
    def paper_trade(self, action, pair, amount_zar=None, units=None, reason="manual"):
        pair = pair.upper()
        price = self.latest.get(pair)
        if price is None:
            try:
                price = self._fetch(pair)
                self.latest[pair] = price
            except Exception as e:
                return f"No price available for {pair}: {e}"
        with self._plock:
            pf = self.portfolio
            if action == "buy":
                if not amount_zar:
                    return "Specify an amount in rand to buy, sir."
                amount_zar = min(float(amount_zar), pf["cash"])
                if amount_zar <= 0:
                    return "No paper cash left, sir."
                bought = amount_zar / price
                h = pf["holdings"].setdefault(pair, {"units": 0.0, "avg_price": 0.0})
                total_cost = h["units"] * h["avg_price"] + amount_zar
                h["units"] += bought
                h["avg_price"] = total_cost / h["units"]
                pf["cash"] -= amount_zar
                result = (f"Paper BUY {bought:.6f} {pair[:3]} at R{price:,.0f} "
                          f"(R{amount_zar:,.2f}). Cash left R{pf['cash']:,.2f}.")
            elif action == "sell":
                h = pf["holdings"].get(pair)
                if not h or h["units"] <= 0:
                    return f"No {pair} paper position to sell, sir."
                units = float(units) if units else h["units"]
                units = min(units, h["units"])
                proceeds = units * price
                pnl = (price - h["avg_price"]) * units
                h["units"] -= units
                if h["units"] <= 1e-12:
                    del pf["holdings"][pair]
                pf["cash"] += proceeds
                result = (f"Paper SELL {units:.6f} {pair[:3]} at R{price:,.0f} "
                          f"→ R{proceeds:,.2f} ({'profit' if pnl >= 0 else 'loss'} "
                          f"R{abs(pnl):,.2f}). Cash R{pf['cash']:,.2f}.")
            else:
                return "Action must be buy or sell."
            pf["trades"].insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": action, "pair": pair, "price": price,
                "detail": result, "reason": reason})
            pf["trades"] = pf["trades"][:100]
            self._save_portfolio()
        self.log(result)
        return result

    # ── reports (Claude tools / UI) ─────────────
    def portfolio_report(self):
        with self._plock:
            pf = self.portfolio
            lines = [f"Paper cash: R{pf['cash']:,.2f}"]
            total = pf["cash"]
            for pair, h in pf["holdings"].items():
                price = self.latest.get(pair, h["avg_price"])
                value = h["units"] * price
                pnl   = (price - h["avg_price"]) * h["units"]
                total += value
                lines.append(f"{pair}: {h['units']:.6f} @ avg R{h['avg_price']:,.0f} "
                             f"→ R{value:,.2f} ({'+' if pnl>=0 else '−'}R{abs(pnl):,.2f})")
            start = config.PAPER_STARTING_CASH
            lines.append(f"Total value: R{total:,.2f} "
                         f"({'+' if total>=start else '−'}R{abs(total-start):,.2f} all-time)")
            recent = pf["trades"][:3]
        if recent:
            lines.append("Recent: " + " | ".join(t["detail"][:60] for t in recent))
        return "\n".join(lines)

    def price_report(self):
        if not self.latest:
            return "No prices fetched yet — give me a minute, sir."
        return "  ".join(f"{p}: R{v:,.0f}" for p, v in self.latest.items())
