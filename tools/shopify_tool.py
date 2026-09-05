"""
shopify_tool.py — real calls to the Shopify Admin API.

Every function here performs an actual HTTP request against Shaun's
store and returns a ToolResult carrying the real status code and the
real payload. There is no sample data, no cached fixture, and no
"looks about right" path. If the store is unreachable or the token is
wrong, that is what comes back.

Two design decisions worth stating:

1. FAILURES ARE LOUD. The old agent had `except Exception: return ""` in
   product_summary(), which made a 401 indistinguishable from an empty
   catalogue — the marketing tool then invented products for a real
   store. Here, an auth failure returns ok=False with the status code.

2. WRITES REQUIRE CONFIRMATION. Anything that changes the store returns
   needs_confirmation on first call and does nothing. It only executes
   when called again with the matching token, which the brain only
   supplies after Shaun says yes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

import config
from tool_result import ToolResult, Stopwatch

TOOL_TIMEOUT = 30
# 2024-01 was the old hardcoded default and is NO LONGER SUPPORTED —
# confirmed against the real store, which accepts 2025-10 / 2026-01 /
# 2026-04 / 2026-07. Shopify does not error on an unsupported version,
# it silently serves the oldest supported one, so the old default was
# quietly lying about which API was answering. 2025-10 is the floor that
# shopifyqlQuery also requires. The selftest's version probe warns when
# this goes stale again.
DEFAULT_API_VERSION = getattr(config, "SHOPIFY_API_VERSION", "2025-10")


# ── credentials ────────────────────────────────────────────────────

def _creds():
    """(store, token) from env first, then config. Env wins so the
    selftest can run against a scratch store without editing files."""
    store = (os.environ.get("SHOPIFY_STORE")
             or getattr(config, "SHOPIFY_STORE", "") or "").strip()
    token = (os.environ.get("SHOPIFY_TOKEN")
             or getattr(config, "SHOPIFY_TOKEN", "") or "").strip()
    store = store.replace("https://", "").replace("http://", "").strip("/")
    return store, token


def _missing_creds(tool) -> ToolResult | None:
    store, token = _creds()
    if not store or not token:
        missing = []
        if not store:
            missing.append("SHOPIFY_STORE (e.g. your-shop.myshopify.com)")
        if not token:
            missing.append("SHOPIFY_TOKEN (starts with shpat_)")
        return ToolResult.failure(
            tool,
            "Shopify is not configured — missing " + " and ".join(missing)
            + ". Set them as environment variables or in keys.py. "
              "I have NOT contacted any store.",
            data={"configured": False})
    return None


# ── transport ──────────────────────────────────────────────────────

def _request(tool, method, path, *, params=None, payload=None,
             api_version=None) -> ToolResult:
    """One real HTTP call. Returns a ToolResult either way — the status
    code is always reported, so a caller can never mistake a 401 for an
    empty result set."""
    bad = _missing_creds(tool)
    if bad:
        return bad
    store, token = _creds()
    ver = api_version or DEFAULT_API_VERSION
    url = f"https://{store}/admin/api/{ver}/{path.lstrip('/')}"
    headers = {"X-Shopify-Access-Token": token,
               "Content-Type": "application/json",
               "Accept": "application/json"}

    with Stopwatch() as sw:
        try:
            r = httpx.request(method, url, headers=headers, params=params,
                              json=payload, timeout=TOOL_TIMEOUT)
        except Exception as e:
            return ToolResult.from_exception(
                tool, e, duration_ms=sw.elapsed_ms,
                data={"url": url, "method": method})

    ms = sw.elapsed_ms
    # Shopify's own rate-limit header — surfaced so she can say "slow
    # down" with a number instead of guessing
    call_limit = r.headers.get("X-Shopify-Shop-Api-Call-Limit", "")

    if r.status_code == 401:
        return ToolResult.failure(
            tool, "401 Unauthorised — the Shopify token was rejected. It is "
                  "wrong, revoked, or belongs to a different store.",
            http_status=401, duration_ms=ms, data={"url": url})
    if r.status_code == 403:
        return ToolResult.failure(
            tool, f"403 Forbidden — the token is valid but lacks the scope "
                  f"for {path}. Add the scope in the custom app's API "
                  f"access settings and reinstall it.",
            http_status=403, duration_ms=ms, data={"url": url})
    if r.status_code == 404:
        return ToolResult.failure(
            tool, f"404 Not Found — {url}. Either the store domain is wrong "
                  f"or API version {ver} no longer exists (Shopify retires "
                  f"versions after about a year). Run the selftest to see "
                  f"which versions this store accepts.",
            http_status=404, duration_ms=ms, data={"url": url})
    if r.status_code == 429:
        return ToolResult.failure(
            tool, f"429 Rate limited by Shopify (call limit {call_limit}). "
                  f"Wait a few seconds and retry.",
            http_status=429, duration_ms=ms)
    if r.status_code >= 400:
        return ToolResult.failure(
            tool, f"HTTP {r.status_code} from Shopify: {r.text[:300]}",
            http_status=r.status_code, duration_ms=ms)

    try:
        body = r.json()
    except Exception as e:
        return ToolResult.failure(
            tool, f"Shopify returned HTTP {r.status_code} but the body was "
                  f"not JSON ({e}): {r.text[:200]}",
            http_status=r.status_code, duration_ms=ms)

    return ToolResult.success(
        tool, f"HTTP {r.status_code} from {path} in {ms} ms",
        http_status=r.status_code, duration_ms=ms, data=body)


def _paginate(tool, path, params, max_pages=10, api_version=None):
    """Follow Shopify's Link-header cursor pagination.

    The old agent passed limit=50 and reported "Stock: healthy" after
    seeing only the first 50 products. Partial data presented as total
    data is its own kind of lie, so we page properly and report how many
    pages we actually read.
    """
    bad = _missing_creds(tool)
    if bad:
        return bad, []
    store, token = _creds()
    ver = api_version or DEFAULT_API_VERSION
    url = f"https://{store}/admin/api/{ver}/{path.lstrip('/')}"
    headers = {"X-Shopify-Access-Token": token, "Accept": "application/json"}
    items, pages, key = [], 0, path.split(".")[0].split("/")[-1]
    last_status = None

    with Stopwatch() as sw:
        try:
            while url and pages < max_pages:
                r = httpx.get(url, headers=headers,
                              params=params if pages == 0 else None,
                              timeout=TOOL_TIMEOUT)
                if r.status_code >= 400:
                    return ToolResult.failure(
                        tool, f"HTTP {r.status_code} on page {pages + 1} of "
                              f"{path}: {r.text[:200]}",
                        http_status=r.status_code,
                        duration_ms=sw.elapsed_ms), []
                last_status = r.status_code
                body = r.json()
                items.extend(body.get(key, []))
                pages += 1
                url = None
                link = r.headers.get("Link", "")
                for part in link.split(","):
                    if 'rel="next"' in part and "<" in part:
                        url = part[part.find("<") + 1:part.find(">")]
                        break
        except Exception as e:
            return ToolResult.from_exception(
                tool, e, duration_ms=sw.elapsed_ms), []

    truncated = bool(url)   # stopped because we hit max_pages
    return ToolResult.success(
        tool, f"read {len(items)} {key} across {pages} page(s)"
              + (" — MORE REMAIN (page cap hit)" if truncated else ""),
        http_status=last_status, duration_ms=sw.elapsed_ms,
        data={"count": len(items), "pages": pages,
              "complete": not truncated}), items


def _api_versions() -> ToolResult:
    """Ask the store which API versions it actually supports.

    Uses the GraphQL `publicApiVersions` query. An earlier attempt used
    REST GET /admin/api/api_versions.json, which 404s — that endpoint
    does not exist. Rather than guess a third time this is built from
    Shopify's published schema: publicApiVersions returns ApiVersion
    objects with handle / displayName / supported, and needs no scope.

    This matters more than it looks: when you pin an unsupported version
    Shopify does not error, it silently serves the oldest supported one.
    So the version string in your config can be pure fiction and nothing
    tells you. This is how you find out.
    """
    tool = "shopify_api_versions"
    bad = _missing_creds(tool)
    if bad:
        return bad
    store, token = _creds()
    url = f"https://{store}/admin/api/{DEFAULT_API_VERSION}/graphql.json"
    q = "{ publicApiVersions { handle displayName supported } }"
    with Stopwatch() as sw:
        try:
            r = httpx.post(url,
                           headers={"X-Shopify-Access-Token": token,
                                    "Content-Type": "application/json"},
                           json={"query": q}, timeout=TOOL_TIMEOUT)
        except Exception as e:
            return ToolResult.from_exception(tool, e, duration_ms=sw.elapsed_ms)
    if r.status_code >= 400:
        return ToolResult.failure(tool, f"HTTP {r.status_code}: {r.text[:200]}",
                                  http_status=r.status_code,
                                  duration_ms=sw.elapsed_ms)
    try:
        body = r.json()
    except Exception as e:
        return ToolResult.failure(tool, f"non-JSON reply: {e}",
                                  http_status=r.status_code)
    if body.get("errors"):
        return ToolResult.failure(
            tool, "; ".join(str(e.get("message"))[:150]
                            for e in body["errors"][:2]),
            http_status=r.status_code, data=body)
    vers = ((body.get("data") or {}).get("publicApiVersions") or [])
    return ToolResult.success(tool, f"{len(vers)} API version(s) listed",
                              http_status=r.status_code,
                              duration_ms=sw.elapsed_ms,
                              data={"api_versions": vers})


# ── read tools ─────────────────────────────────────────────────────

def shopify_orders(days: int = 7, status: str = "any",
                   limit: int = 250) -> ToolResult:
    """Real orders from the Admin API for the last N days."""
    tool = "shopify_orders"
    try:
        days = max(1, min(int(days), 365))
    except Exception:
        days = 7
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res, orders = _paginate(tool, "orders.json",
                            {"status": status, "created_at_min": since,
                             "limit": min(int(limit), 250)})
    if not res.ok:
        return res

    currency = ""
    gross = 0.0
    for o in orders:
        try:
            gross += float(o.get("total_price") or 0)
        except Exception:
            pass
        currency = currency or (o.get("currency") or "")

    recent = [{"order": o.get("name"),
               "created_at": o.get("created_at"),
               "total": o.get("total_price"),
               "currency": o.get("currency"),
               "financial_status": o.get("financial_status"),
               "fulfillment_status": o.get("fulfillment_status") or "unfulfilled",
               "customer": ((o.get("customer") or {}).get("first_name") or "")
                           + " " + ((o.get("customer") or {}).get("last_name") or ""),
               "line_items": len(o.get("line_items") or [])}
              for o in orders[:15]]

    return ToolResult.success(
        tool,
        f"{len(orders)} order(s) in the last {days} day(s), gross "
        f"{gross:.2f} {currency or ''}".strip(),
        http_status=res.http_status, duration_ms=res.duration_ms,
        data={"window_days": days, "order_count": len(orders),
              "gross_revenue": round(gross, 2), "currency": currency,
              "complete": res.data.get("complete", True),
              "pages_read": res.data.get("pages"),
              "recent_orders": recent})


def shopify_products(low_stock_below: int = 5) -> ToolResult:
    """Real product + inventory read, fully paginated."""
    tool = "shopify_products"
    res, products = _paginate(tool, "products.json", {"limit": 250})
    if not res.ok:
        return res

    try:
        threshold = max(0, int(low_stock_below))
    except Exception:
        threshold = 5

    low, total_variants, tracked = [], 0, 0
    for p in products:
        for v in p.get("variants") or []:
            total_variants += 1
            qty = v.get("inventory_quantity")
            if v.get("inventory_management") is None or qty is None:
                continue
            tracked += 1
            if qty <= threshold:
                low.append({"product": p.get("title"),
                            "variant": v.get("title"),
                            "sku": v.get("sku"),
                            "qty": qty, "price": v.get("price")})
    low.sort(key=lambda x: x["qty"])

    # A store with inventory tracking switched off returns zero low-stock
    # variants no matter how empty the shelves are. Reporting "0 at or
    # below 5" there reads as "stock is fine" when the true answer is
    # "I cannot see stock at all" — a blind instrument presented as a
    # clean bill of health. Say which one it is.
    blind = tracked == 0 and total_variants > 0
    if blind:
        headline = (f"{len(products)} product(s), {total_variants} variant(s). "
                    f"STOCK IS NOT TRACKED on any variant, so I CANNOT see "
                    f"quantities and low-stock detection is blind — the zero "
                    f"below means 'no data', NOT 'well stocked'. Turn on "
                    f"'Track quantity' per variant in Shopify to enable it.")
    else:
        headline = (f"{len(products)} product(s), {total_variants} variant(s); "
                    f"{len(low)} at or below {threshold} in stock "
                    f"({tracked} of {total_variants} variants are tracked)")

    return ToolResult.success(
        tool,
        headline
        + ("" if res.data.get("complete", True)
           else " — WARNING: product list was truncated at the page cap, "
                "these totals are NOT the whole catalogue"),
        http_status=res.http_status, duration_ms=res.duration_ms,
        data={"product_count": len(products), "variant_count": total_variants,
              "tracked_variants": tracked,
              "inventory_visible": not blind,
              "threshold": threshold,
              "complete": res.data.get("complete", True),
              "low_stock": low[:40]})


def _traffic_via_shopifyql(days: int = 7) -> ToolResult:
    """Sales-over-time analytics via ShopifyQL on the GraphQL Admin API.

    IMPORTANT — what this can and cannot do:

    Shopify does NOT expose session/visitor counts through the Admin API
    at all. Sessions, add-to-cart and conversion rate exist only in the
    admin analytics UI; there is no GraphQL or REST endpoint for them.
    So "traffic" in the visits sense is unavailable, full stop, and this
    tool says so explicitly rather than quietly substituting order counts
    and letting them be read as visits.

    What it DOES return is real: a daily sales breakdown from the
    ShopifyQL `sales` dataset, which is genuinely queryable.

    An earlier version of this function guessed the GraphQL schema and
    got it wrong three ways — the response type is ShopifyqlQueryResponse
    (not a TableResponse union), parseErrors is [String!]! (not objects),
    the field is `rows` (not rowData) — and it then blamed the resulting
    schema error on a missing "read_analytics" scope, which is not even
    the right scope name. The correct scope is read_reports. That wrong
    hint is exactly the kind of confident-but-unverified claim this
    rebuild exists to stamp out, so it is named here rather than quietly
    corrected.
    """
    tool = "shopify_traffic"
    bad = _missing_creds(tool)
    if bad:
        return bad
    store, token = _creds()
    try:
        days = max(1, min(int(days), 90))
    except Exception:
        days = 7

    query = """
    query($q: String!) {
      shopifyqlQuery(query: $q) {
        tableData {
          columns { name dataType displayName }
          rows
        }
        parseErrors
      }
    }"""
    ql = (f"FROM sales SHOW total_sales, orders "
          f"GROUP BY day SINCE -{days}d UNTIL today ORDER BY day")
    url = f"https://{store}/admin/api/{DEFAULT_API_VERSION}/graphql.json"

    with Stopwatch() as sw:
        try:
            r = httpx.post(url,
                           headers={"X-Shopify-Access-Token": token,
                                    "Content-Type": "application/json"},
                           json={"query": query, "variables": {"q": ql}},
                           timeout=TOOL_TIMEOUT)
        except Exception as e:
            return ToolResult.from_exception(tool, e,
                                             duration_ms=sw.elapsed_ms)
    ms = sw.elapsed_ms

    # Sessions are never available. State it once, here, so every caller
    # carries the same accurate line instead of inventing one.
    NO_SESSIONS = ("Session/visitor counts are NOT available from Shopify's "
                   "Admin API at any scope — they exist only in the admin "
                   "analytics UI. For real traffic numbers use GA4 or the "
                   "Shopify admin dashboard.")

    if r.status_code >= 400:
        hint = ""
        if r.status_code in (401, 403):
            hint = (" ShopifyQL needs the read_reports scope — add it to the "
                    "custom app's API access settings and reinstall the app.")
        return ToolResult.failure(
            tool, f"HTTP {r.status_code} from GraphQL: {r.text[:250]}.{hint}",
            http_status=r.status_code, duration_ms=ms,
            data={"sessions_available": False, "note": NO_SESSIONS})
    try:
        body = r.json()
    except Exception as e:
        return ToolResult.failure(tool, f"non-JSON GraphQL reply: {e}",
                                  http_status=r.status_code, duration_ms=ms)

    if body.get("errors"):
        msgs = "; ".join(str(e.get("message"))[:200]
                         for e in body["errors"][:3])
        scope_hint = ""
        if "access denied" in msgs.lower() or "scope" in msgs.lower():
            scope_hint = (" Add the read_reports scope to the custom app and "
                          "reinstall it.")
        return ToolResult.failure(
            tool, f"GraphQL rejected the query: {msgs}.{scope_hint}",
            http_status=r.status_code, duration_ms=ms,
            data={"graphql_errors": body["errors"][:3],
                  "sessions_available": False, "note": NO_SESSIONS})

    node = ((body.get("data") or {}).get("shopifyqlQuery") or {})
    # parseErrors is [String!]! — a plain list of strings
    perrs = node.get("parseErrors") or []
    if perrs:
        return ToolResult.failure(
            tool, "ShopifyQL rejected the query: "
                  + "; ".join(str(e)[:160] for e in perrs[:3]),
            http_status=r.status_code, duration_ms=ms,
            data={"parse_errors": perrs, "query": ql})

    table = node.get("tableData") or {}
    cols = [c.get("name") for c in (table.get("columns") or [])]
    rows = table.get("rows") or []

    total_sales = 0.0
    orders = 0
    for row in rows:
        vals = row if isinstance(row, list) else list((row or {}).values())
        for name, v in zip(cols, vals):
            try:
                if name == "total_sales":
                    total_sales += float(v)
                elif name == "orders":
                    orders += int(float(v))
            except Exception:
                pass

    return ToolResult.success(
        tool,
        f"sales analytics for the last {days} day(s): {orders} order(s), "
        f"{total_sales:.2f} total sales across {len(rows)} day-row(s). "
        f"NOTE: visitor sessions are not available from Shopify's API.",
        http_status=r.status_code, duration_ms=ms,
        data={"window_days": days, "orders": orders,
              "total_sales": round(total_sales, 2),
              "columns": cols, "rows": rows[:40],
              "sessions_available": False, "note": NO_SESSIONS})


def _sales_by_day_from_orders(days: int, why: ToolResult) -> ToolResult:
    """Daily sales computed from the orders endpoint we CAN already read.

    This is a labelled fallback, not a silent substitution. The summary
    and the data both name the source, because quietly serving orders
    data where analytics data was asked for is precisely the kind of
    near-enough answer that made Allison untrustworthy. The caller is
    told which source it got and why the better one was unavailable.
    """
    tool = "shopify_traffic"
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res, orders = _paginate(tool, "orders.json",
                            {"status": "any", "created_at_min": since,
                             "limit": 250})
    if not res.ok:
        return ToolResult.failure(
            tool,
            f"ShopifyQL unavailable ({why.error[:120]}) AND the orders "
            f"fallback also failed: {res.error[:150]}",
            http_status=res.http_status, duration_ms=res.duration_ms)

    by_day, currency, gross = {}, "", 0.0
    for o in orders:
        day = str(o.get("created_at") or "")[:10]
        try:
            amt = float(o.get("total_price") or 0)
        except Exception:
            amt = 0.0
        gross += amt
        currency = currency or (o.get("currency") or "")
        d = by_day.setdefault(day, {"day": day, "orders": 0, "sales": 0.0})
        d["orders"] += 1
        d["sales"] = round(d["sales"] + amt, 2)
    rows = [by_day[k] for k in sorted(by_day)]

    return ToolResult.success(
        tool,
        f"SOURCE: orders endpoint (NOT Shopify analytics). Last {days} "
        f"day(s): {len(orders)} order(s), {gross:.2f} {currency} gross "
        f"across {len(rows)} day(s) with activity. Visitor sessions are "
        f"NOT available from Shopify's API at all, and ShopifyQL analytics "
        f"is unavailable here ({why.error[:110]}).",
        http_status=res.http_status, duration_ms=res.duration_ms,
        data={"source": "orders_rest_fallback",
              "shopifyql_available": False,
              "shopifyql_reason": why.error[:300],
              "sessions_available": False,
              "window_days": days, "order_count": len(orders),
              "gross_revenue": round(gross, 2), "currency": currency,
              "by_day": rows})


def shopify_traffic(days: int = 7) -> ToolResult:
    """Store performance over time.

    Tries real ShopifyQL analytics first. If that is not reachable on
    this store (it needs the read_reports scope, Level 2 protected
    customer data access AND API version 2025-10+), falls back to
    computing daily sales from the orders endpoint — and says so, in the
    summary and in the data, so the source is never ambiguous.
    """
    ql = _traffic_via_shopifyql(days)
    if ql.ok:
        return ql
    return _sales_by_day_from_orders(days, ql)


# ── write tool (confirmation-gated) ────────────────────────────────

def _token_for(action: str, detail: str) -> str:
    raw = f"{action}|{detail}|{int(time.time() // 600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def shopify_update_price(variant_id: str, price: str,
                         confirm: str = "") -> ToolResult:
    """Change a variant's price. WRITES to the live store.

    First call always returns needs_confirmation and touches nothing.
    """
    tool = "shopify_update_price"
    if not variant_id or not price:
        return ToolResult.failure(tool, "variant_id and price are both required")

    want = _token_for("price", f"{variant_id}:{price}")
    if confirm != want:
        cur = _request(tool, "GET", f"variants/{variant_id}.json")
        now_price = "unknown"
        title = f"variant {variant_id}"
        if cur.ok:
            v = (cur.data or {}).get("variant") or {}
            now_price = v.get("price", "unknown")
            title = f"{v.get('title', '')} (sku {v.get('sku') or '—'})".strip()
        return ToolResult.confirm(
            tool,
            f"Change the price of {title} from {now_price} to {price} on the "
            f"LIVE store? This is immediately visible to customers.",
            want, data={"variant_id": variant_id, "current_price": now_price,
                        "new_price": price})

    res = _request(tool, "PUT", f"variants/{variant_id}.json",
                   payload={"variant": {"id": variant_id, "price": str(price)}})
    if not res.ok:
        return res
    v = (res.data or {}).get("variant") or {}
    # verify from the response body, don't assume the write took
    actual = str(v.get("price", ""))
    if actual != str(price):
        return ToolResult.failure(
            tool, f"Shopify accepted the request but the price now reads "
                  f"{actual!r}, not {price!r}. Treat this as NOT applied.",
            http_status=res.http_status, data=v)
    return ToolResult.success(
        tool, f"price for variant {variant_id} is now {actual} (verified "
              f"from Shopify's response)",
        http_status=res.http_status, duration_ms=res.duration_ms,
        data={"variant_id": variant_id, "price": actual})


# ── selftest ───────────────────────────────────────────────────────

def selftest(verbose=True) -> ToolResult:
    """Run every read tool against the REAL store and report verbatim.

    Run on the machine that has the token:
        python -m tools.shopify_tool
    """
    store, token = _creds()
    out = []
    out.append("=" * 62)
    out.append("SHOPIFY TOOL SELFTEST — real calls, real results")
    out.append("=" * 62)
    out.append(f"store        : {store or '(not set)'}")
    out.append(f"token        : {(token[:9] + '…' + str(len(token)) + ' chars') if token else '(not set)'}")
    out.append(f"api version  : {DEFAULT_API_VERSION}")
    out.append(f"run at       : {datetime.now().isoformat(timespec='seconds')}")
    out.append("")

    if not store or not token:
        out.append("RESULT: not configured — no calls attempted.")
        out.append("Set SHOPIFY_STORE and SHOPIFY_TOKEN, then re-run.")
        return ToolResult.failure("shopify_selftest",
                                  "credentials not configured",
                                  stdout="\n".join(out))

    # which API versions does this store actually accept?
    # NOTE: this used to be printed only `if ver.ok`, so when the probe
    # failed it vanished silently and looked like it had never run — the
    # same silent-skip pattern this whole rebuild exists to remove.
    # It now always reports, pass or fail.
    ver = _api_versions()
    out.append("▶ API versions this store accepts")
    if ver.ok:
        vers = ver.data.get("api_versions") or []
        supported = [v["handle"] for v in vers if v.get("supported")]
        out.append(f"  supported : {', '.join(supported[-8:])}")
        if DEFAULT_API_VERSION not in supported:
            out.append(f"  WARNING   : {DEFAULT_API_VERSION} is NOT supported. "
                       f"Shopify silently serves the OLDEST supported version "
                       f"instead, so your config's version label is fiction. "
                       f"Set SHOPIFY_API_VERSION in config.py to one above.")
        else:
            out.append(f"  {DEFAULT_API_VERSION} is supported.")
        if not any(v >= "2025-10" for v in supported):
            out.append("  note      : no 2025-10+ version available, so "
                       "shopifyqlQuery cannot work on this store at all.")
    else:
        out.append("  ok        : False")
        out.append(f"  http      : {ver.http_status}")
        out.append(f"  error     : {(ver.error or ver.summary)[:220]}")
    out.append("")

    checks = [("orders (7 days)", lambda: shopify_orders(days=7)),
              ("products + stock", lambda: shopify_products()),
              ("traffic (7 days)", lambda: shopify_traffic(days=7))]

    results, passed = [], 0
    for label, fn in checks:
        out.append("-" * 62)
        out.append(f"▶ {label}")
        r = fn()
        results.append((label, r))
        out.append(f"  ok         : {r.ok}")
        out.append(f"  http       : {r.http_status}")
        out.append(f"  duration   : {r.duration_ms} ms")
        out.append(f"  summary    : {r.summary}")
        if r.error:
            out.append(f"  error      : {r.error[:400]}")
        if verbose and r.ok and r.data:
            blob = json.dumps(r.data, indent=2, default=str)
            out.append("  data       :")
            out.extend("    " + ln for ln in blob.splitlines()[:28])
            if len(blob.splitlines()) > 28:
                out.append("    …(truncated)")
        passed += 1 if r.ok else 0
    out.append("-" * 62)
    out.append(f"RESULT: {passed}/{len(checks)} read tools returned real data.")
    if passed < len(checks):
        out.append("The failures above are REAL failures with real status "
                   "codes — that is the point of this rebuild. Fix the scope "
                   "or version they name and re-run.")
    text = "\n".join(out)
    return ToolResult(tool="shopify_selftest", ok=passed == len(checks),
                      summary=f"{passed}/{len(checks)} read tools passed",
                      stdout=text,
                      error="" if passed == len(checks) else "one or more tools failed",
                      data={"passed": passed, "total": len(checks)})


if __name__ == "__main__":
    print(selftest().stdout)
