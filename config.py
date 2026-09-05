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
import sys
from pathlib import Path

# ── keys.py: paste-your-keys-in-a-file (beats setx headaches) ──
# If C:\jarvis\keys.py exists, any keys in it are injected into the
# environment so every module (Anthropic SDK, llm.py) just works.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import keys as _keys
    for _name in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
                  "OPENROUTER_API_KEY"):
        _val = (getattr(_keys, _name, "") or "").strip()
        # keys.py ALWAYS wins — stale setx leftovers in the Windows
        # environment must never shadow the file you actually edit
        if _val:
            os.environ[_name] = _val
except ImportError:
    pass

# ── Project layout ──────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parent
MEMORY_DIR      = ROOT_DIR / "memory"
SCREENSHOTS_DIR = MEMORY_DIR / "screenshots"

MEMORY_FILE         = MEMORY_DIR / "jarvis_memory.json"
KNOWLEDGE_FILE      = MEMORY_DIR / "knowledge.json"
SESSION_FILE        = MEMORY_DIR / "last_session.json"
TASKS_FILE          = MEMORY_DIR / "tasks.json"
RESEARCH_QUEUE_FILE = MEMORY_DIR / "research_queue.json"
COST_LOG_FILE        = MEMORY_DIR / "cost_log.json"

# ── Obsidian vault ──────────────────────────────
VAULT_PATH = Path(os.environ.get(
    "JARVIS_VAULT",
    str(Path.home() / "OneDrive" / "Documents" / "JARVIS_CORE"),
))

# ── AI ──────────────────────────────────────────
# Two Claude tiers, both paid Anthropic API (console.anthropic.com):
#   FAST  — Haiku:  cheap, quick, handles all normal chat + tool use.
#   SMART — Sonnet: coding, self-edits, research synthesis, browser work.
# The brain picks per-message; normal chatter never burns Sonnet money.
# Set a monthly spend limit in the Anthropic console so it can't run away.
CLAUDE_MODEL      = "claude-sonnet-4-6"            # SMART tier
CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"    # FAST tier (default)

# ── Credit balance countdown ────────────────────
# Anthropic's API has no "check my balance" endpoint, so JARVIS counts
# DOWN from the credits you last loaded. Whenever you top up (or want
# to re-sync), look at console.anthropic.com → Billing, and set this
# to the credits showing there. JARVIS subtracts every real token cost
# from that moment on and shows what's left in the header.
# 0 = feature off (no balance pill).
CREDIT_BALANCE_USD = 0.0

# Pricing in USD per million tokens (input, output) — as of July 2026.
# Anthropic occasionally changes these; check console.anthropic.com/
# settings/billing or docs.claude.com/en/docs/about-claude/pricing if
# the cost dashboard ever looks off, and update the numbers below.
CLAUDE_PRICING = {
    CLAUDE_MODEL_FAST: (1.00, 5.00),
    CLAUDE_MODEL:       (3.00, 15.00),
}

# Brain providers, tried in order. Anthropic (Claude) is the smartest;
# when it's out of credits JARVIS automatically falls back to the FREE
# ones below. Get free keys (no card needed):
#   Groq:   console.groq.com  → set env var GROQ_API_KEY
#   Gemini: aistudio.google.com/apikey → set env var GEMINI_API_KEY
# Ollama = fully local & free forever (install from ollama.com), used
# last if it's running.
# Allison's brains, tried in this order. FREE brains lead now — Groq
# (fast, smart 70B) and Gemini (free vision) carry her at zero cost and
# zero RAM. Anthropic sits LAST so she never wastes a call on it while
# credits are $0; the moment Shopify funds it, move "anthropic" to the
# front and she gains the heavy reasoning + real screen vision back.
LLM_PROVIDER_ORDER = ["groq", "gemini", "openrouter", "ollama", "anthropic"]
GROQ_MODEL           = "llama-3.3-70b-versatile"
GROQ_MODEL_FALLBACKS = ["llama-3.1-8b-instant"]   # higher free limits
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
# free lanes get crowded — if one model is saturated, hop to the next
OPENROUTER_MODEL_FALLBACKS = [
    "deepseek/deepseek-chat-v3-0324:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "google/gemma-3-27b-it:free",
]
# Gemini free tier (verified July 2026). Old gemini-2.0-flash / 1.5 were
# SHUT DOWN and return 404 — using them was the reason Gemini "didn't
# work". gemini-2.5-flash-lite has the most generous free quota
# (15 req/min, 1000/day); flash-latest currently points to 3.5 Flash.
GEMINI_MODEL = "gemini-2.5-flash-lite"
# free image generation model — used for "draw me..." requests
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
# tried in order if the first model name is rejected (Google renames often)
GEMINI_MODEL_FALLBACKS = ["gemini-2.5-flash", "gemini-flash-latest",
                          "gemini-3.5-flash", "gemini-3.1-flash-lite"]
OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_URL   = "http://localhost:11434/v1"

# ── Identity ────────────────────────────────────
# She is ALLISON now — a woman, Shaun's command-centre AI. Her name is
# also her wake word (just say "Allison", no "hey"). The folder, files
# and modules keep the 'jarvis' names on purpose — only the persona,
# voice and displayed name change.
ASSISTANT_NAME = "Allison"

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

# ── Voice ───────────────────────────────────────
# "neural": Microsoft Edge neural TTS (needs internet, sounds like the
#           film JARVIS). "sapi": offline Windows voice. Neural falls
#           back to SAPI automatically if the internet is down.
VOICE_ENGINE = "neural"
# Allison's voice — a warm British female neural voice. Alternatives:
# en-GB-LibbyNeural, en-US-AriaNeural, en-US-JennyNeural, en-AU-NatashaNeural
VOICE_NAME   = "en-GB-SoniaNeural"
VOICE_RATE   = "+4%"                # speaking speed tweak

# Webcam for JARVIS's eyes (camera.py) — 0 = default camera
CAMERA_INDEX = 0

# Every file JARVIS overwrites gets backed up here first
FILE_BACKUP_DIR = MEMORY_DIR / "file_backups"

# Microphone. Windows reshuffles device NUMBERS whenever Bluetooth
# reconnects, so prefer picking by NAME — any part of the device name,
# case-insensitive. Examples: "FUNKI" for the headset, "Microphone Array"
# for the laptop's built-in mics. Leave "" to use the system default.
MIC_DEVICE_NAME  = ""
# (legacy fallback — only used if MIC_DEVICE_NAME is empty)
MIC_DEVICE_INDEX = None

SITES_DIR       = ROOT_DIR / "sites"
DEBUG_TOOL_GATE = False

SHOPIFY_API_VERSION = "2025-10"
