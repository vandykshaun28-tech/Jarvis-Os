"""
cost_tracker.py
────────────────
Tracks real Anthropic API spend from actual token usage returned by
every call — never estimated, never guessed. Persists to disk so the
total survives restarts (Shaun should always be able to ask "what have
you cost me this month" and get a real answer).

Pricing lives in config.CLAUDE_PRICING (USD per million tokens, input
and output separately) — update it there if Anthropic changes rates.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

import config


class CostTracker:

    def __init__(self, log_file=None):
        try:
            self.log_file = Path(log_file or config.COST_LOG_FILE)
        except TypeError:
            # bad/missing path must NEVER kill the brain — track this
            # session in memory only and say so once
            print("[CostTracker] no valid log file — session-only tracking")
            self.log_file = None
        self._lock = threading.Lock()
        self.session_calls = 0
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cost = 0.0
        self._data = self._load()

    # ── persistence ──────────────────────────────
    def _load(self) -> dict:
        try:
            if self.log_file and self.log_file.exists():
                return json.loads(self.log_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[CostTracker] load failed: {e}")
        return {"total_cost": 0.0, "total_calls": 0,
                "by_model": {}, "by_day": {}}

    def _save(self):
        if self.log_file is None:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.write_text(json.dumps(self._data, indent=2),
                                     encoding="utf-8")
        except Exception as e:
            print(f"[CostTracker] save failed: {e}")

    # ── recording ────────────────────────────────
    def record(self, model: str, input_tokens: int, output_tokens: int):
        """Call this with the ACTUAL usage numbers from an Anthropic
        response (resp.usage.input_tokens / .output_tokens). Silently
        no-ops for unknown models rather than guessing a price."""
        rates = config.CLAUDE_PRICING.get(model)
        if rates is None:
            return
        in_rate, out_rate = rates
        cost = (input_tokens / 1_000_000) * in_rate \
             + (output_tokens / 1_000_000) * out_rate

        with self._lock:
            self.session_calls += 1
            self.session_input_tokens += input_tokens
            self.session_output_tokens += output_tokens
            self.session_cost += cost

            self._data["total_cost"] = round(
                self._data.get("total_cost", 0.0) + cost, 6)
            self._data["total_calls"] = self._data.get("total_calls", 0) + 1

            by_model = self._data.setdefault("by_model", {})
            m = by_model.setdefault(model, {"calls": 0, "cost": 0.0,
                                            "input_tokens": 0,
                                            "output_tokens": 0})
            m["calls"] += 1
            m["cost"] = round(m["cost"] + cost, 6)
            m["input_tokens"] += input_tokens
            m["output_tokens"] += output_tokens

            today = datetime.now().strftime("%Y-%m-%d")
            by_day = self._data.setdefault("by_day", {})
            by_day[today] = round(by_day.get(today, 0.0) + cost, 6)

            self._save()

    # ── reporting ────────────────────────────────
    def session_summary(self) -> dict:
        return {
            "calls": self.session_calls,
            "input_tokens": self.session_input_tokens,
            "output_tokens": self.session_output_tokens,
            "cost": round(self.session_cost, 4),
        }

    def today_cost(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        return round(self._data.get("by_day", {}).get(today, 0.0), 4)

    def month_cost(self) -> float:
        prefix = datetime.now().strftime("%Y-%m")
        total = sum(v for d, v in self._data.get("by_day", {}).items()
                   if d.startswith(prefix))
        return round(total, 4)

    def total_cost(self) -> float:
        return round(self._data.get("total_cost", 0.0), 4)

    def remaining_balance(self):
        """Credits left, counting DOWN from config.CREDIT_BALANCE_USD.
        The moment that config value changes (a top-up / re-sync), a
        reference point is stored so only spend AFTER the change counts
        against the new balance. Returns None if the feature is off."""
        cfg = float(getattr(config, "CREDIT_BALANCE_USD", 0) or 0)
        if cfg <= 0:
            return None
        with self._lock:
            ref = self._data.get("balance_ref")
            if not ref or ref.get("value") != cfg:
                ref = {"value": cfg,
                       "total_at_set": self._data.get("total_cost", 0.0)}
                self._data["balance_ref"] = ref
                self._save()
            spent_since = (self._data.get("total_cost", 0.0)
                           - ref.get("total_at_set", 0.0))
            return max(0.0, round(cfg - spent_since, 4))

    def report(self) -> str:
        s = self.session_summary()
        lines = [
            "COST REPORT (real Anthropic API spend, from actual token usage):",
            f"  This session: {s['calls']} calls, "
            f"{s['input_tokens']:,} in / {s['output_tokens']:,} out tokens "
            f"— ${s['cost']:.4f}",
            f"  Today:        ${self.today_cost():.4f}",
            f"  This month:   ${self.month_cost():.4f}",
            f"  All time:     ${self.total_cost():.4f}",
        ]
        by_model = self._data.get("by_model", {})
        if by_model:
            lines.append("  By model (all time):")
            for model, m in sorted(by_model.items(),
                                   key=lambda x: -x[1]["cost"]):
                lines.append(f"    {model}: {m['calls']} calls — "
                             f"${m['cost']:.4f}")
        return "\n".join(lines)
