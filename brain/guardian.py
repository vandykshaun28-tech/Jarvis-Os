"""
guardian.py
───────────
JARVIS's early-warning system. A quiet background watchdog that checks
for trouble EVERY 45 SECONDS and warns Shaun BEFORE it bites — spoken
and in the chat, marked [Guardian] ⚠.

What it watches:
  MONEY    · API credit balance getting low / about to run out today
           · unusually high spend today
  BRAIN    · Claude down → running on a backup (free) brain
           · repeated tool failures in a row (something is broken)
  MACHINE  · RAM nearly full (sustained), disk nearly full, CPU pegged
  PROJECTS · paper-trading portfolio down hard
           · Shopify agent in an error state
           · a self-edit waiting for approval (forgotten changes)

Every check is DETERMINISTIC — no API calls, zero cost, no false
"AI imagination". Each warning has a cooldown so JARVIS nags exactly
once per problem, not every 45 seconds.

All thresholds can be overridden in config.py (defaults in CHECKS).
"""

import threading
import time

import config

try:
    import psutil
    PSUTIL_OK = True
except Exception:
    PSUTIL_OK = False


def _cfg(name, default):
    return getattr(config, name, default)


class Guardian:

    INTERVAL = 45          # seconds between patrols

    def __init__(self, brain, chat_callback=None, voice_callback=None):
        self.brain = brain
        self.chat_callback = chat_callback
        self.voice_callback = voice_callback
        self.running = False
        self._last_warn = {}      # key -> time of last warning
        self._ram_high = 0        # consecutive high-RAM patrols
        self._cpu_high = 0
        self.warnings_issued = []  # (time_str, message) log
        print("[Guardian] Early-warning system online.")

    def start(self):
        self.running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    # ── plumbing ─────────────────────────────────────────────────────

    def _warn(self, key, message, cooldown_hours=6.0, speak=True):
        """Warn once; stay quiet about the same problem for cooldown."""
        now = time.time()
        if now - self._last_warn.get(key, 0) < cooldown_hours * 3600:
            return
        self._last_warn[key] = now
        stamp = time.strftime("%H:%M")
        self.warnings_issued.append((stamp, message))
        self.warnings_issued = self.warnings_issued[-50:]
        print(f"[Guardian] WARNING: {message}")
        if self.chat_callback:
            try:
                self.chat_callback(f"[Guardian] ⚠ {message}")
            except Exception:
                pass
        if speak and self.voice_callback:
            try:
                self.voice_callback(f"Warning, sir. {message}")
            except Exception:
                pass

    def report(self) -> str:
        if not self.warnings_issued:
            return ("GUARDIAN: all clear, sir. Watching money, brain "
                    "health, this machine, trading and Shopify.")
        lines = ["GUARDIAN — recent warnings:"]
        for t_, m in self.warnings_issued[-10:]:
            lines.append(f"  {t_}  ⚠ {m}")
        return "\n".join(lines)

    # ── the patrol ───────────────────────────────────────────────────

    def _loop(self):
        time.sleep(20)                # let the brain finish waking up
        while self.running:
            try:
                self._check_money()
                self._check_brain()
                self._check_machine()
                self._check_projects()
            except Exception as e:
                print(f"[Guardian] patrol error: {e}")
            time.sleep(self.INTERVAL)

    # MONEY ─────────────────────────────────────────────────────────

    def _check_money(self):
        ct = getattr(self.brain, "cost_tracker", None)
        if ct is None:
            return
        # balance countdown (only if Shaun set CREDIT_BALANCE_USD)
        left = None
        if hasattr(ct, "remaining_balance"):
            try:
                left = ct.remaining_balance()
            except Exception:
                left = None
        if left is not None:
            if left <= _cfg("GUARDIAN_BALANCE_URGENT", 1.0):
                self._warn("balance_urgent",
                           f"API credits nearly gone — ${left:.2f} left. "
                           f"I'll switch to the free backup brains when it "
                           f"runs dry, but they're weaker. Top up at "
                           f"console.anthropic.com.", cooldown_hours=3)
            elif left <= _cfg("GUARDIAN_BALANCE_LOW", 3.0):
                self._warn("balance_low",
                           f"API credits running low: ${left:.2f} remaining. "
                           f"At today's pace that won't last long.",
                           cooldown_hours=12)
            # runway: will today's burn rate empty the tank today?
            try:
                today = ct.today_cost()
                if today > 0.5 and left < today:
                    self._warn("balance_runway",
                               f"Heads-up: I've spent ${today:.2f} today and "
                               f"only ${left:.2f} remains — at this pace I "
                               f"run out before the day ends.",
                               cooldown_hours=6)
            except Exception:
                pass
        # spend spike, even with no balance configured
        try:
            today = ct.today_cost()
            limit = _cfg("GUARDIAN_DAILY_COST_ALERT", 5.0)
            if today >= limit:
                self._warn("cost_spike",
                           f"Today's API spend is ${today:.2f} — past your "
                           f"${limit:.2f} alert line. Say 'cost report' to "
                           f"see where it went.", cooldown_hours=24)
        except Exception:
            pass

    # BRAIN ─────────────────────────────────────────────────────────

    def _check_brain(self):
        # running on a fallback brain while a Claude key exists?
        llm = getattr(self.brain, "llm", None)
        if llm is not None:
            import os
            active = getattr(llm, "active_provider", None)
            if (active and active != "anthropic"
                    and os.environ.get("ANTHROPIC_API_KEY")):
                self._warn("fallback_brain",
                           f"I'm answering on the backup brain ({active}) — "
                           f"Claude isn't responding (credits or "
                           f"connection). Expect weaker answers until it's "
                           f"back.", cooldown_hours=6)
        # repeated tool failures = something is actually broken
        try:
            with self.brain._act_lock:
                recent = list(self.brain.activity)[:4]
            fails = [e for e in recent if e.get("status") != "ok"]
            if len(recent) >= 3 and len(fails) >= 3:
                what = fails[0].get("action", "?")
                self._warn("tool_failures",
                           f"My last {len(fails)} actions in a row failed "
                           f"(latest: {what}). Something's broken — check "
                           f"the AI Agents page before trusting results.",
                           cooldown_hours=1)
        except Exception:
            pass

    # MACHINE ───────────────────────────────────────────────────────

    def _check_machine(self):
        if not PSUTIL_OK:
            return
        try:
            ram = psutil.virtual_memory().percent
            if ram >= _cfg("GUARDIAN_RAM_ALERT", 93):
                self._ram_high += 1
            else:
                self._ram_high = 0
            if self._ram_high >= 3:        # ~2+ minutes sustained
                self._warn("ram",
                           f"RAM is at {ram:.0f}% and staying there — the "
                           f"PC may start freezing. Worth closing something "
                           f"heavy (say 'list processes' to see culprits).",
                           cooldown_hours=2)

            cpu = psutil.cpu_percent(interval=None)
            if cpu >= _cfg("GUARDIAN_CPU_ALERT", 95):
                self._cpu_high += 1
            else:
                self._cpu_high = 0
            if self._cpu_high >= 4:
                self._warn("cpu",
                           f"CPU has been pegged near {cpu:.0f}% for a few "
                           f"minutes straight.", cooldown_hours=2)

            disk = psutil.disk_usage("C:\\").percent
            if disk >= _cfg("GUARDIAN_DISK_ALERT", 92):
                self._warn("disk",
                           f"Drive C: is {disk:.0f}% full. Windows gets "
                           f"unstable past this — time to clear space.",
                           cooldown_hours=12)
        except Exception:
            pass

    # PROJECTS ──────────────────────────────────────────────────────

    def _check_projects(self):
        # paper trading down hard
        try:
            mgr = getattr(self.brain, "agent_manager", None)
            agent = mgr.get("trading") if mgr else None
            if agent is not None:
                pf = agent.portfolio
                total = pf.get("cash", 0.0)
                for pair, h in pf.get("holdings", {}).items():
                    total += h["units"] * agent.latest.get(pair,
                                                           h["avg_price"])
                start = _cfg("PAPER_STARTING_CASH", 100_000.0)
                loss_pct = (start - total) / start * 100 if start else 0
                if loss_pct >= _cfg("GUARDIAN_TRADING_LOSS_PCT", 5.0):
                    self._warn("trading_loss",
                               f"The paper portfolio is down "
                               f"{loss_pct:.1f}% (R{start - total:,.0f}). "
                               f"If this were real money that would hurt — "
                               f"review the strategy on the Trading page.",
                               cooldown_hours=24)
        except Exception:
            pass
        # shopify agent stuck in error
        try:
            mgr = getattr(self.brain, "agent_manager", None)
            agent = mgr.get("shopify") if mgr else None
            if agent is not None and getattr(agent, "configured", False):
                snap = agent.snapshot()
                if "error" in str(snap.get("status", "")).lower():
                    self._warn("shopify_error",
                               f"The Shopify agent hit an error: "
                               f"{snap.get('last_message', '?')[:80]} — "
                               f"orders may be going unwatched.",
                               cooldown_hours=6)
        except Exception:
            pass
        # a self-edit sitting unapproved = forgotten changes
        try:
            se = getattr(self.brain, "self_edit", None)
            if se is not None and getattr(se, "pending", None):
                self._warn("selfedit_pending",
                           "There's a code change of mine still waiting "
                           "for your approval — approve or reject it so it "
                           "doesn't go stale.", cooldown_hours=12,
                           speak=False)
        except Exception:
            pass
