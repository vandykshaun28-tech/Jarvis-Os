"""
theme_manager.py — one source of truth for both themes.
Components call pal() when styling; MainWindow.apply_theme() switches
the current palette and asks each themed component to retheme().
"""

# ALLISON's signature — JARVIS electric cyan-blue on near-black.
# Clean, minimal, "arc-reactor" holographic (Huw-Prosser / Iron-Man look).
DARK = {
    "name": "dark",
    "canvas": "#02060d",          # backdrop base (near-black blue)
    "grid": (46, 130, 190),       # backdrop gridline rgb (deep cyan-blue)
    "panel": "#08131f",           # cards / sidebar / header
    "panel2": "#0c1c2b",          # buttons, inputs
    "line": "#123048",            # borders
    "accent": "#3dd8ff",          # electric cyan-blue — arc-reactor
    "text": "#dff2ff",
    "text2": "#7fa6c2",
    "dim": "#4d6b82",
    "bubble_you_bg": "rgba(61,216,255,0.12)",
    "bubble_you_border": "rgba(61,216,255,0.34)",
    "bubble_ai_bg": "#0a1622",
    "code_bg": "#061019",
}

LIGHT = {
    "name": "light",
    "canvas": "#eef2f7",
    "grid": (40, 90, 130),
    "panel": "#ffffff",
    "panel2": "#eef4fa",
    "line": "#c3d3e2",
    "accent": "#0b7fa3",          # darker cyan — readable on white
    "text": "#12222f",
    "text2": "#41586c",
    "dim": "#5f7d95",
    "bubble_you_bg": "rgba(11,127,163,0.10)",
    "bubble_you_border": "rgba(11,127,163,0.35)",
    "bubble_ai_bg": "#ffffff",
    "code_bg": "#e7edf4",
}

_current = DARK

# user-selectable accent colours (label -> hex). Applied on top of the
# base dark/light palette so the whole UI + orb recolour together.
ACCENTS = {
    "Arc":     "#3dd8ff",   # JARVIS electric cyan-blue (default)
    "Cyan":    "#22d3ee",
    "Emerald": "#22e39a",
    "Violet":  "#a855f7",
    "Amber":   "#f5a623",
    "Rose":    "#fb5e8b",
    "Blue":    "#3b82f6",
    "Crimson": "#ef4444",
}
_accent_override = None   # hex string or None (use palette default)


def set_theme(name: str):
    global _current
    _current = LIGHT if name == "light" else DARK
    return _current


def set_accent(hex_or_none):
    """Override the accent colour app-wide, or None to reset to default."""
    global _accent_override
    _accent_override = hex_or_none


def pal() -> dict:
    if _accent_override:
        d = dict(_current)
        d["accent"] = _accent_override
        # keep the you-bubble tint in sync with the accent
        h = _accent_override.lstrip("#")
        try:
            r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
            d["bubble_you_bg"] = f"rgba({r},{g},{b},0.10)"
            d["bubble_you_border"] = f"rgba({r},{g},{b},0.35)"
        except Exception:
            pass
        return d
    return _current


def is_light() -> bool:
    return _current["name"] == "light"

