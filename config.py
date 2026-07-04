"""
config.py
─────────
Single source of truth for paths and settings.

Every path is derived from wherever this project folder actually lives,
so you can move/rename the folder (jarvis_v18, shuan, anywhere) and
nothing breaks. Override the Obsidian vault with the JARVIS_VAULT
environment variable if it lives somewhere unusual.
"""

import os
from pathlib import Path

# ── Project layout ──────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parent
MEMORY_DIR      = ROOT_DIR / "memory"
SCREENSHOTS_DIR = MEMORY_DIR / "screenshots"

MEMORY_FILE         = MEMORY_DIR / "jarvis_memory.json"
KNOWLEDGE_FILE      = MEMORY_DIR / "knowledge.json"
SESSION_FILE        = MEMORY_DIR / "last_session.json"
TASKS_FILE          = MEMORY_DIR / "tasks.json"
RESEARCH_QUEUE_FILE = MEMORY_DIR / "research_queue.json"

# ── Obsidian vault ──────────────────────────────
VAULT_PATH = Path(os.environ.get(
    "JARVIS_VAULT",
    str(Path.home() / "OneDrive" / "Documents" / "JARVIS_CORE"),
))

# ── AI ──────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Personal ────────────────────────────────────
OWNER_NAME = "Shaun"
HOME_CITY  = "Benoni, South Africa"

# ── Agents ──────────────────────────────────────
# Shopify: create a custom app in your store admin
# (Settings → Apps → Develop apps) and put the credentials in
# environment variables SHOPIFY_STORE and SHOPIFY_TOKEN, or paste
# them here directly.
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE", "")   # e.g. "yourstore.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN", "")   # shpat_...
SHOPIFY_CHECK_MINUTES  = 5      # how often to look for new orders
SHOPIFY_LOW_STOCK      = 5      # alert when inventory falls below this
SHOPIFY_SUMMARY_HOUR   = 18     # daily sales summary time (24h)

# Trading (Luno — public market data needs no keys)
TRADING_PAIRS          = ["XBTZAR", "ETHZAR"]   # BTC/ZAR, ETH/ZAR
TRADING_CHECK_SECONDS  = 60
TRADING_MODE           = "paper"     # paper trading only, by design
PAPER_STARTING_CASH    = 100_000.0   # ZAR of pretend money
TRADING_MOVE_ALERT_PCT = 2.0         # alert on moves bigger than this (15 min window)
PORTFOLIO_FILE         = MEMORY_DIR / "trading_portfolio.json"

# Autonomous mind — JARVIS thinks on a cycle and may speak up
MIND_ENABLED           = True
MIND_INTERVAL_MINUTES  = 30
MIND_QUIET_START       = 22    # don't speak between these hours
MIND_QUIET_END         = 6
