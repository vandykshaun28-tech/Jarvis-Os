"""
shopify_agent.py
────────────────
Runs your Shopify store autonomously:

  • watches for new orders and announces them as they arrive
  • flags products running low on stock
  • gives a spoken daily sales summary at closing time

Setup (once): in Shopify admin → Settings → Apps and sales channels →
Develop apps → create an app with read_orders + read_products scopes,
then set environment variables SHOPIFY_STORE (yourstore.myshopify.com)
and SHOPIFY_TOKEN (shpat_...), or fill them into config.py.
Until then the agent idles politely as 'not configured'.
"""

import json
from datetime import datetime, date

import httpx

import config
from agents.base_agent import BaseAgent

API_VERSION = "2024-01"


class ShopifyAgent(BaseAgent):

    name        = "Shopify"
    description = "Order watch, stock alerts, daily sales summary"

    def __init__(self, brain=None):
        super().__init__(brain=brain,
                         interval_seconds=config.SHOPIFY_CHECK_MINUTES * 60)
        self._last_order_id   = None
        self._summary_done_on = None
        self._stock_check_on  = None

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
        low  = []
        for p in data.get("products", []):
            for v in p.get("variants", []):
                q = v.get("inventory_quantity")
                if q is not None and q <= config.SHOPIFY_LOW_STOCK:
                    title = p.get("title", "?")
                    vt    = v.get("title", "")
                    label = title if vt in ("Default Title", "") else f"{title} ({vt})"
                    low.append(f"{label}: {q} left")
        if low:
            self.say("Stock alert — " + "; ".join(low[:8]), speak=True)
        else:
            self.log("Stock levels healthy.")

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
