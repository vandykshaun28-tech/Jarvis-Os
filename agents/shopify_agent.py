"""
shopify_agent.py
────────────────
Runs your Shopify store autonomously — the AUTOPILOT:

  • watches for new orders and announces them as they arrive
  • flags products running low on stock
  • gives a spoken daily sales summary at closing time
  • AUTO-FULFILS paid orders (optional — SHOPIFY_AUTO_FULFIL = True)
  • answers CUSTOMER EMAILS: reads the store inbox, drafts replies with
    the Claude brain, and either queues them for Shaun's approval
    (default) or sends simple ones automatically. Refunds/cancellations
    are ALWAYS queued for approval, never auto-sent.
  • one-question morning report: "how is Shopify doing" → sales,
    fulfilments, stock, customer emails, everything.

Setup (once):
  1. Shopify admin → Settings → Apps and sales channels → Develop apps
     → create an app with scopes: read_orders, read_products
     (+ write_fulfillments & read_fulfillments for auto-fulfil)
     → set SHOPIFY_STORE (yourstore.myshopify.com) and SHOPIFY_TOKEN.
  2. For customer email: a Gmail APP PASSWORD (myaccount.google.com →
     Security → 2-Step Verification → App passwords) →
     set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in keys.py or config.py.
Until then each part idles politely as 'not configured'.
"""

import imaplib
import json
import os
import re
import smtplib
import threading
from email import message_from_bytes
from email.mime.text import MIMEText
from email.utils import parseaddr
from datetime import datetime, date, timedelta

import httpx

import config
from agents.base_agent import BaseAgent

API_VERSION = "2024-01"

# senders that are never customers — bots, receipts, ourselves
_SKIP_SENDERS = ("no-reply", "noreply", "do-not-reply", "notifications@",
                 "mailer-daemon", "postmaster", "@shopify.com",
                 "@google.com", "@anthropic.com")
# these topics are NEVER auto-answered — always queued for Shaun
_ALWAYS_APPROVE = re.compile(
    r"refund|cancel|charge ?back|dispute|lawyer|legal|fraud|scam|police",
    re.IGNORECASE)


def _cfg(name, default):
    """config.py attr, overridable by an environment variable."""
    return os.environ.get(name) or getattr(config, name, default) or default


class ShopifyAgent(BaseAgent):

    name        = "Shopify"
    description = "Order watch, stock alerts, daily sales summary"

    def __init__(self, brain=None):
        super().__init__(brain=brain,
                         interval_seconds=config.SHOPIFY_CHECK_MINUTES * 60)
        self._last_order_id   = None
        self._summary_done_on = None
        self._stock_check_on  = None
        # ── autopilot state (survives restarts) ──
        self._ap_lock  = threading.Lock()
        self._ap_file  = config.MEMORY_DIR / "shopify_autopilot.json"
        self._ap = {"fulfilled": [], "seen_uids": [], "actions": [],
                    "pending": [], "auto_sent": {}}
        try:
            if self._ap_file.exists():
                self._ap.update(json.loads(
                    self._ap_file.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[Shopify] autopilot state load: {e}")

    # ── autopilot config ────────────────────────
    @property
    def email_configured(self):
        return bool(_cfg("GMAIL_ADDRESS", "") and
                    _cfg("GMAIL_APP_PASSWORD", ""))

    @property
    def auto_fulfil(self):
        return bool(getattr(config, "SHOPIFY_AUTO_FULFIL", False))

    @property
    def reply_mode(self):
        # "approve" (default: Shaun approves every reply) or "auto"
        return str(getattr(config, "AUTOPILOT_REPLY_MODE", "approve")).lower()

    def _ap_save(self):
        try:
            self._ap["fulfilled"] = self._ap["fulfilled"][-500:]
            self._ap["seen_uids"] = self._ap["seen_uids"][-800:]
            self._ap["actions"]   = self._ap["actions"][-200:]
            self._ap_file.parent.mkdir(parents=True, exist_ok=True)
            self._ap_file.write_text(json.dumps(self._ap, indent=2),
                                     encoding="utf-8")
        except Exception as e:
            print(f"[Shopify] autopilot state save: {e}")

    def _act(self, msg):
        """Record an autopilot action (shows in the morning report)."""
        with self._ap_lock:
            self._ap["actions"].insert(
                0, [datetime.now().strftime("%Y-%m-%d %H:%M"), str(msg)[:160]])
            self._ap_save()
        self.log(msg)

    # ── helpers ─────────────────────────────────
    @property
    def configured(self):
        return bool(config.SHOPIFY_STORE and config.SHOPIFY_TOKEN)

    def _get(self, path, params=None):
        url = f"https://{config.SHOPIFY_STORE}/admin/api/{API_VERSION}/{path}"
        r = httpx.get(url, params=params or {}, timeout=20, headers={
            "X-Shopify-Access-Token": config.SHOPIFY_TOKEN})
        r.raise_for_status()
        return r.json()

    # ── the autonomous loop ─────────────────────
    def tick(self):
        if not self.configured:
            self.status = "not_configured"
            self.last_message = "Waiting for store credentials (see config.py)."
            return

        self._check_new_orders()

        today = date.today()
        now   = datetime.now()

        # low-stock sweep once a day (morning)
        if self._stock_check_on != today and now.hour >= 8:
            self._stock_check_on = today
            self._check_low_stock()

        # daily summary at closing time
        if self._summary_done_on != today and now.hour >= config.SHOPIFY_SUMMARY_HOUR:
            self._summary_done_on = today
            self.say(self.sales_today(), speak=True)

        # ── AUTOPILOT ───────────────────────────
        if self.auto_fulfil:
            try:
                self._autopilot_fulfil()
            except Exception as e:
                self.log(f"auto-fulfil error: {e}")
        if self.email_configured:
            try:
                self._autopilot_inbox()
            except Exception as e:
                self.log(f"inbox error: {e}")

    # ════════════════════════════════════════════
    #  AUTOPILOT 1 — fulfil paid orders
    # ════════════════════════════════════════════

    def _post(self, path, payload):
        url = f"https://{config.SHOPIFY_STORE}/admin/api/{API_VERSION}/{path}"
        r = httpx.post(url, json=payload, timeout=20, headers={
            "X-Shopify-Access-Token": config.SHOPIFY_TOKEN})
        r.raise_for_status()
        return r.json()

    def _autopilot_fulfil(self):
        data = self._get("orders.json", {
            "financial_status": "paid",
            "fulfillment_status": "unfulfilled", "limit": 10})
        for o in data.get("orders", []):
            oid = o["id"]
            with self._ap_lock:
                if oid in self._ap["fulfilled"]:
                    continue
            try:
                fo = self._get(f"orders/{oid}/fulfillment_orders.json")
                fo_list = [f for f in fo.get("fulfillment_orders", [])
                           if f.get("status") == "open"]
                if not fo_list:
                    continue
                self._post("fulfillments.json", {"fulfillment": {
                    "notify_customer": True,
                    "line_items_by_fulfillment_order": [
                        {"fulfillment_order_id": f["id"]} for f in fo_list],
                }})
                with self._ap_lock:
                    self._ap["fulfilled"].append(oid)
                self._act(f"Auto-fulfilled order #{o.get('order_number')} "
                          f"({o.get('currency','')} {o.get('total_price','?')}) "
                          f"— customer notified.")
                self.say(f"Order #{o.get('order_number')} fulfilled "
                         f"automatically, sir.", speak=False)
            except Exception as e:
                self.log(f"fulfil #{o.get('order_number')}: {e}")

    # ════════════════════════════════════════════
    #  AUTOPILOT 2 — customer email service
    # ════════════════════════════════════════════

    def _gmail(self):
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(_cfg("GMAIL_ADDRESS", ""), _cfg("GMAIL_APP_PASSWORD", ""))
        return m

    @staticmethod
    def _email_text(msg):
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        return part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", "replace")
                    except Exception:
                        continue
            return ""
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "replace")
        except Exception:
            return ""

    def _autopilot_inbox(self):
        """Read UNSEEN inbox mail, draft replies for customer messages."""
        m = self._gmail()
        try:
            m.select("INBOX")
            _, data = m.search(None, "UNSEEN")
            uids = data[0].split()[-15:]          # newest batch only
            for uid in uids:
                uid_s = uid.decode()
                with self._ap_lock:
                    if uid_s in self._ap["seen_uids"]:
                        continue
                    self._ap["seen_uids"].append(uid_s)
                _, msg_data = m.fetch(uid, "(RFC822)")
                msg = message_from_bytes(msg_data[0][1])
                sender = parseaddr(msg.get("From", ""))[1].lower()
                subject = str(msg.get("Subject", ""))[:120]
                if (not sender
                        or any(s in sender for s in _SKIP_SENDERS)
                        or sender == _cfg("GMAIL_ADDRESS", "").lower()
                        or msg.get("List-Unsubscribe")):
                    continue                       # bot / newsletter / self
                body = self._email_text(msg)[:2500].strip()
                if not body:
                    continue
                self._handle_customer_email(sender, subject, body)
            self._ap_save()
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def _order_context(self, email_addr):
        """Recent orders for this customer, for grounded replies."""
        try:
            data = self._get("orders.json", {
                "email": email_addr, "status": "any", "limit": 3})
            lines = []
            for o in data.get("orders", []):
                lines.append(
                    f"Order #{o.get('order_number')}: "
                    f"{o.get('currency','')} {o.get('total_price','?')}, "
                    f"payment {o.get('financial_status','?')}, "
                    f"fulfilment {o.get('fulfillment_status') or 'unfulfilled'}, "
                    f"placed {str(o.get('created_at',''))[:10]}")
            return "\n".join(lines) or "No orders found for this email."
        except Exception as e:
            return f"(order lookup failed: {e})"

    def _draft_reply(self, sender, subject, body, orders_ctx):
        llm = getattr(self.brain, "llm", None)
        if llm is None:
            return None
        store = (config.SHOPIFY_STORE or "our store").split(".")[0]
        system = (
            f"You are the customer-service agent for the Shopify store "
            f"'{store}'. Write a short, warm, professional reply email "
            f"(plain text, no subject line, no markdown). Be honest — "
            f"only promise what the order data supports. Sign off as "
            f"'The {store} team'. If the customer asks about a refund, "
            f"cancellation or dispute, acknowledge kindly and say the "
            f"owner will confirm personally within 24 hours — do NOT "
            f"promise the refund itself.")
        user = (f"Customer email from {sender}:\nSubject: {subject}\n\n"
                f"{body}\n\n--- Their order history ---\n{orders_ctx}\n\n"
                f"Write the reply now.")
        try:
            return llm.simple(system, user, max_tokens=350).strip()
        except Exception as e:
            self.log(f"draft failed: {e}")
            return None

    def _send_email(self, to_addr, subject, body):
        addr = _cfg("GMAIL_ADDRESS", "")
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = addr
        msg["To"] = to_addr
        msg["Subject"] = subject if subject.lower().startswith("re:") \
            else f"Re: {subject}"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(addr, _cfg("GMAIL_APP_PASSWORD", ""))
            s.send_message(msg)

    def _handle_customer_email(self, sender, subject, body):
        orders_ctx = self._order_context(sender)
        draft = self._draft_reply(sender, subject, body, orders_ctx)
        if draft is None:
            self._queue_reply(sender, subject, body, "(drafting failed — "
                              "write this one yourself, sir)")
            return
        sensitive = bool(_ALWAYS_APPROVE.search(subject + " " + body))
        today = date.today().isoformat()
        sent_today = self._ap["auto_sent"].get(today, 0)
        if self.reply_mode == "auto" and not sensitive and sent_today < 10:
            try:
                self._send_email(sender, subject, draft)
                with self._ap_lock:
                    self._ap["auto_sent"] = {today: sent_today + 1}
                self._act(f"Replied automatically to {sender} "
                          f"(‘{subject[:50]}’).")
                self.say(f"Answered a customer email from {sender} — "
                         f"‘{subject[:60]}’.", speak=False)
                return
            except Exception as e:
                self.log(f"auto-send failed: {e}")
        self._queue_reply(sender, subject, body, draft, sensitive)

    def _queue_reply(self, sender, subject, body, draft, sensitive=False):
        with self._ap_lock:
            n = len(self._ap["pending"]) + 1
            self._ap["pending"].append({
                "n": n, "from": sender, "subject": subject,
                "body": body[:800], "draft": draft,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
            self._ap_save()
        tag = "SENSITIVE — " if sensitive else ""
        self.say(f"{tag}Customer email from {sender}: ‘{subject[:60]}’. "
                 f"Reply drafted — say 'show shopify replies' to review, "
                 f"'approve reply {n}' to send.", speak=True)

    # ── pending-reply management (Claude tools) ─
    def pending_replies(self):
        with self._ap_lock:
            pend = list(self._ap["pending"])
        if not pend:
            return "No customer replies waiting, sir."
        out = []
        for p in pend:
            out.append(f"REPLY {p['n']} — from {p['from']} "
                       f"({p['time']})\nSubject: {p['subject']}\n"
                       f"They wrote: {p['body'][:220]}\n"
                       f"--- My draft ---\n{p['draft']}\n")
        return "\n".join(out)

    def approve_reply(self, n):
        with self._ap_lock:
            match = [p for p in self._ap["pending"] if p["n"] == int(n)]
        if not match:
            return f"No pending reply #{n}, sir."
        p = match[0]
        try:
            self._send_email(p["from"], p["subject"], p["draft"])
        except Exception as e:
            return f"Sending failed, sir: {e}"
        with self._ap_lock:
            self._ap["pending"] = [x for x in self._ap["pending"]
                                   if x["n"] != int(n)]
            self._ap_save()
        self._act(f"Reply #{n} to {p['from']} approved and sent.")
        return f"Sent to {p['from']}, sir."

    def reject_reply(self, n):
        with self._ap_lock:
            before = len(self._ap["pending"])
            self._ap["pending"] = [x for x in self._ap["pending"]
                                   if x["n"] != int(n)]
            self._ap_save()
        if len(self._ap["pending"]) == before:
            return f"No pending reply #{n}, sir."
        self._act(f"Reply #{n} rejected (not sent).")
        return f"Discarded, sir. The customer has NOT been answered."

    # ════════════════════════════════════════════
    #  THE MORNING ANSWER — "how is Shopify doing"
    # ════════════════════════════════════════════

    def full_report(self):
        if not self.configured:
            return ("Shopify is not connected yet, sir. Create a custom app "
                    "in the store admin (read_orders, read_products) and put "
                    "SHOPIFY_STORE + SHOPIFY_TOKEN in keys.py or config.py.")
        lines = ["SHOPIFY — full status:"]
        # sales: today + yesterday
        try:
            today0 = datetime.now().strftime("%Y-%m-%dT00:00:00")
            data = self._get("orders.json", {"status": "any",
                                             "created_at_min": today0,
                                             "limit": 250})
            orders = data.get("orders", [])
            cur = orders[0].get("currency", "") if orders else ""
            total = sum(float(o.get("total_price", 0)) for o in orders)
            lines.append(f"  Today: {len(orders)} order(s), {cur} {total:,.2f}.")
            y0 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
            ydata = self._get("orders.json", {"status": "any",
                                              "created_at_min": y0,
                                              "created_at_max": today0,
                                              "limit": 250})
            yo = ydata.get("orders", [])
            yt = sum(float(o.get("total_price", 0)) for o in yo)
            lines.append(f"  Yesterday: {len(yo)} order(s), {cur} {yt:,.2f}.")
        except Exception as e:
            lines.append(f"  Sales lookup failed: {e}")
        # fulfilment backlog
        try:
            un = self._get("orders.json", {"financial_status": "paid",
                                           "fulfillment_status": "unfulfilled",
                                           "limit": 50}).get("orders", [])
            state = "auto-fulfil is ON" if self.auto_fulfil else \
                "auto-fulfil is OFF (set SHOPIFY_AUTO_FULFIL = True)"
            lines.append(f"  Awaiting fulfilment: {len(un)} paid order(s) — {state}.")
        except Exception as e:
            lines.append(f"  Fulfilment lookup failed: {e}")
        # customer service
        if self.email_configured:
            with self._ap_lock:
                pend = len(self._ap["pending"])
            lines.append(f"  Customer emails: {pend} repl"
                         f"{'y' if pend == 1 else 'ies'} waiting for your "
                         f"approval" + (" — say 'show shopify replies'."
                                        if pend else "."))
        else:
            lines.append("  Customer email: not connected (set GMAIL_ADDRESS "
                         "+ GMAIL_APP_PASSWORD for the autopilot inbox).")
        # low stock (quick)
        try:
            data = self._get("products.json", {"limit": 50})
            low = 0
            tracked = 0
            for p in data.get("products", []):
                for v in p.get("variants", []):
                    if not v.get("inventory_management"):
                        continue                  # not tracked → always sellable
                    tracked += 1
                    q = v.get("inventory_quantity")
                    if q is not None and q <= config.SHOPIFY_LOW_STOCK:
                        low += 1
            if not tracked:
                lines.append("  Stock: not tracked — products are always "
                             "available to buy.")
            else:
                lines.append(f"  Stock: {low} variant(s) at or below "
                             f"{config.SHOPIFY_LOW_STOCK}."
                             if low else "  Stock: healthy.")
        except Exception as e:
            lines.append(f"  Stock lookup failed: {e}")
        # autopilot action log (last 24h)
        with self._ap_lock:
            cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
            recent = [a for a in self._ap["actions"] if a[0] >= cutoff][:8]
        if recent:
            lines.append("  Autopilot actions (24h):")
            for t, msg in recent:
                lines.append(f"    {t[-5:]}  {msg}")
        else:
            lines.append("  Autopilot actions (24h): none.")
        return "\n".join(lines)

    def _check_new_orders(self):
        data   = self._get("orders.json",
                           {"status": "any", "limit": 10, "order": "id desc"})
        orders = data.get("orders", [])
        if not orders:
            self.last_message = "No orders yet."
            return
        newest = orders[0]["id"]
        if self._last_order_id is None:
            self._last_order_id = newest      # first run: baseline, no spam
            self.last_message = f"Watching orders (latest #{orders[0].get('order_number')})."
            return
        fresh = [o for o in orders if o["id"] > self._last_order_id]
        self._last_order_id = newest
        for o in reversed(fresh):
            total = o.get("total_price", "?")
            cur   = o.get("currency", "")
            items = sum(li.get("quantity", 0) for li in o.get("line_items", []))
            name  = (o.get("customer") or {}).get("first_name", "a customer")
            self.say(f"New order #{o.get('order_number')} from {name} — "
                     f"{cur} {total}, {items} item(s).", speak=True)

    def _check_low_stock(self):
        data = self._get("products.json", {"limit": 50})
        low   = []
        zero  = 0
        total = 0
        for p in data.get("products", []):
            for v in p.get("variants", []):
                # inventory_management is None/"" when "Track quantity" is OFF.
                # Untracked products are ALWAYS sellable in Shopify, so they
                # are never "sold out" — skip them (this was the false alarm).
                if not v.get("inventory_management"):
                    continue
                q = v.get("inventory_quantity")
                if q is None:
                    continue
                total += 1
                if q <= 0:
                    zero += 1
                if q <= config.SHOPIFY_LOW_STOCK:
                    title = p.get("title", "?")
                    vt    = v.get("title", "")
                    label = title if vt in ("Default Title", "") else f"{title} ({vt})"
                    low.append(f"{label}: {q} left")

        # Build the message. The ALL-SOLD-OUT case is a business blocker,
        # not a routine low-stock nudge — say it clearly and actionably.
        if total and zero == total:
            msg = ("Heads up, sir — every product shows 0 stock, so customers "
                   "see 'Sold out' and cannot buy. In Shopify open each product "
                   "and either set an inventory quantity, or tick 'Continue "
                   "selling when out of stock' (or turn off 'Track quantity'). "
                   "No point driving traffic until this is fixed.")
        elif low:
            msg = "Stock alert — " + "; ".join(low[:8])
        else:
            self.log("Stock levels healthy.")
            self._last_stock_msg = ""
            return

        # don't repeat the same alert every cycle — only speak when it changes
        if getattr(self, "_last_stock_msg", "") == msg:
            self.log("Stock unchanged since last alert.")
            return
        self._last_stock_msg = msg
        self.say(msg, speak=True)

    # ── on-demand reports (used as Claude tools) ─
    def sales_today(self):
        if not self.configured:
            return "Shopify is not connected yet, sir. Add the store credentials in config.py."
        start = datetime.now().strftime("%Y-%m-%dT00:00:00")
        data  = self._get("orders.json",
                          {"status": "any", "created_at_min": start, "limit": 250})
        orders = data.get("orders", [])
        if not orders:
            return "No orders today, sir."
        total = sum(float(o.get("total_price", 0)) for o in orders)
        cur   = orders[0].get("currency", "")
        return (f"Today: {len(orders)} order(s) totalling {cur} {total:,.2f}.")

    def recent_orders(self, n=5):
        if not self.configured:
            return "Shopify is not connected yet, sir."
        data = self._get("orders.json", {"status": "any", "limit": n, "order": "id desc"})
        lines = []
        for o in data.get("orders", []):
            lines.append(f"#{o.get('order_number')} — {o.get('currency','')} "
                         f"{o.get('total_price','?')} ({o.get('financial_status','?')})")
        return "\n".join(lines) or "No orders found."

    def low_stock_report(self):
        if not self.configured:
            return "Shopify is not connected yet, sir."
        self._check_low_stock()
        return self.last_message

    def product_summary(self, limit=12):
        """Compact list of the store's real products for marketing copy —
        name, price (ZAR) and a short description. Returns '' if the store
        isn't connected or has no products, so callers can fall back."""
        if not self.configured:
            return ""
        try:
            data = self._get("products.json", {"limit": limit})
        except Exception:
            return ""
        lines = []
        for p in data.get("products", []):
            title = p.get("title", "").strip()
            if not title:
                continue
            variants = p.get("variants", []) or [{}]
            price = variants[0].get("price", "")
            body = re.sub(r"<[^>]+>", " ", p.get("body_html", "") or "")
            body = re.sub(r"\s+", " ", body).strip()[:160]
            price_txt = f" — R{price}" if price else ""
            lines.append(f"- {title}{price_txt}" +
                         (f": {body}" if body else ""))
        return "\n".join(lines)
