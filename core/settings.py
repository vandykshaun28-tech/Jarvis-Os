"""
core/settings.py — user settings that survive restarts.
One tiny JSON file (memory/settings.json), read by UI and brain alike.
"""

import json
import threading

import config

SETTINGS_FILE = config.MEMORY_DIR / "settings.json"

DEFAULTS = {
    "theme": "dark",           # dark | light
    "accent": "Arc",           # JARVIS cyan-blue (see theme_manager.ACCENTS)
    "voice_enabled": True,     # Allison speaks replies
    "wake_word_enabled": True, # mic listens for "allison"
    "brain_mode": "auto",      # auto (Haiku default, Sonnet for heavy) | smart (always Sonnet)
    "mini_tabs": False,        # auto pop-up info panels — OFF by default
                               # (they were popping on every answer); the
                               # study progress bar still shows regardless.
}

_lock = threading.Lock()
_cache = None


def load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            data = dict(DEFAULTS)
            try:
                if SETTINGS_FILE.exists():
                    data.update(json.loads(
                        SETTINGS_FILE.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"[Settings] load failed: {e}")
            # migrate older defaults to the JARVIS cyan-blue ("Arc") so her
            # look matches Huw's Jarvis (Shaun can still pick any accent in
            # Settings afterwards).
            if data.get("accent") in ("Cyan", "Violet"):
                data["accent"] = "Arc"
            _cache = data
        return dict(_cache)


def get(key, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def set(key, value):
    global _cache
    with _lock:
        data = dict(_cache) if _cache else dict(DEFAULTS)
        data[key] = value
        _cache = data
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(data, indent=2),
                                     encoding="utf-8")
        except Exception as e:
            print(f"[Settings] save failed: {e}")
    return value
