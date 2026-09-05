"""
tool_gate.py — decide which tools exist for THIS turn.

Allison advertises 54 tools. Handing all 54 to a free 70B model on every
message is not just wasteful, it actively causes the bug we're fixing:
the more near-duplicate options in the schema list, the more often a
small model picks a plausible-sounding wrong one, fumbles the arguments,
and — before the llm.py fix — got its tools silently stripped and
narrated instead.

So we gate. Each turn, the user's message decides which GROUPS of tools
are visible. A question about the store sees the store tools; a request
to build a site sees the file tools. Nothing else is on the menu.

Design rules:
  • ALWAYS_ON is small and safe — the handful she needs to be herself.
  • Gating is by keyword, deliberately. This is routing, not execution:
    a wrong guess costs a slightly odd tool list, never a fake action.
    Execution correctness is enforced by ToolResult, not by this file.
  • Failing open beats failing closed. An unrecognised message gets the
    general set rather than nothing, so she is never mute.
"""

from __future__ import annotations

import re

# Always available — identity, memory, and the ability to answer at all.
ALWAYS_ON = {
    "web_search", "get_weather", "remember_fact", "recall_knowledge",
    "add_task", "list_tasks", "activity_report", "cost_report",
}

# name → (regex that turns the group on, tool names in the group)
GROUPS: dict[str, tuple[str, set[str]]] = {
    "shopify": (
        r"\b(shopify|store|shop|order|orders|product|products|inventory|"
        r"stock|sales|revenue|customer|refund|fulfil|fulfill|traffic|"
        r"sessions|checkout|sku)\b",
        {"shopify_report", "shopify_replies", "shopify_orders",
         "shopify_products", "shopify_traffic", "build_store_plan",
         "marketing_pack"},
    ),
    "web_build": (
        r"\b(website|web ?site|web ?page|landing|html|css|js|javascript|"
        r"site|blog|portfolio|build me a|make me a|scaffold)\b",
        {"build_website", "website_build", "code_project", "write_file",
         "read_file", "list_directory"},
    ),
    "code": (
        r"\b(code|script|python|program|app|function|bug|refactor|repo|"
        r"module|class|api|vs ?code|project)\b",
        {"code_write", "code_run", "code_project", "write_file",
         "read_file", "list_directory", "search_files",
         "run_command", "open_in_vscode"},
    ),
    "files": (
        r"\b(file|files|folder|directory|dir|path|save|read|open|write|"
        r"disk|desktop|download)\b",
        {"read_file", "write_file", "list_directory", "search_files",
         "open_app", "open_in_vscode"},
    ),
    "pc": (
        r"\b(open|launch|start|close|quit|volume|mute|shutdown|restart|"
        r"sleep|screenshot|screen|process|task manager|cpu|ram|system)\b",
        {"open_app", "open_url", "run_command", "pc_power", "set_volume",
         "take_screenshot", "list_processes", "get_system_info",
         "open_in_vscode"},
    ),
    "screen_hands": (
        r"\b(click|type|typing|keyboard|mouse|press|key|drag|scroll|"
        r"control (the )?screen|do it for me)\b",
        {"type_text", "mouse_control", "press_keys", "take_screenshot",
         "screen_look", "computer_use"},
    ),
    "vision": (
        r"\b(see|look|camera|webcam|photo|picture|image|identify|show you|"
        r"what am i holding|watch)\b",
        {"vision_search", "screen_look", "camera_look", "take_screenshot"},
    ),
    "draw": (
        r"\b(draw|sketch|render|design|illustrat|diagram|blueprint|3d|"
        r"model|picture of|image of|concept)\b",
        {"draw_image", "build_website"},
    ),
    "browser": (
        r"\b(browser|browse|navigate|url|http|google|search the web|"
        r"log ?in|sign ?in|sign ?up|fill in|form|scrape)\b",
        {"browser_goto", "browser_read", "browser_click", "browser_fill",
         "browser_press", "browser_screenshot", "open_url", "web_search"},
    ),
    "trading": (
        r"\b(trade|trading|crypto|btc|bitcoin|portfolio|market|price|"
        r"buy|sell|invest)\b",
        {"trading_portfolio", "market_prices", "paper_trade"},
    ),
    "agents": (
        r"\b(agent|agents|autopilot|background|mind|start the|stop the)\b",
        {"agents_status", "agent_control"},
    ),
}

# When nothing matches, this is the menu — enough to be useful, small
# enough to stay sharp.
GENERAL = {
    "open_app", "open_url", "take_screenshot", "read_file",
    "list_directory", "write_file", "code_project", "build_website",
    "draw_image", "shopify_report", "vision_search", "screen_look",
    "code_write",
}


def groups_for(text: str) -> list[str]:
    """Which groups this message switches on."""
    t = (text or "").lower()
    return [name for name, (pattern, _) in GROUPS.items()
            if re.search(pattern, t, re.I)]


def allowed_names(text: str, extra: set[str] | None = None) -> set[str]:
    """The exact set of tool names visible for this turn."""
    names = set(ALWAYS_ON)
    hits = groups_for(text)
    for name in hits:
        names |= GROUPS[name][1]
    if not hits:
        names |= GENERAL          # fail open, never mute
    if extra:
        names |= extra
    return names


def gate(tool_defs: list, text: str, extra: set[str] | None = None,
         warn=None) -> list:
    """Filter full tool definitions down to this turn's allowed set.

    Fail-open rule: we return the ungated list ONLY if gating produced
    nothing at all. An earlier version used an absolute floor ("keep at
    least 6"), which silently disabled gating whenever the catalogue was
    small — the guard fired constantly and nothing was ever filtered.
    A relative rule can misfire the same way, so the condition is now
    the single unambiguous one: empty means fall back, anything else
    means the gate did its job.
    """
    if not tool_defs:
        return tool_defs
    allow = allowed_names(text, extra)
    kept = [t for t in tool_defs if t.get("name") in allow]
    if not kept:
        if warn:
            warn(f"tool gate matched nothing for {text[:60]!r} — "
                 f"falling back to all {len(tool_defs)} tools")
        return tool_defs
    return kept


def explain(text: str) -> str:
    """Debug helper — why this turn got the tools it did."""
    hits = groups_for(text)
    allow = allowed_names(text)
    return (f"groups: {', '.join(hits) or '(none → GENERAL)'}\n"
            f"{len(allow)} tools: {', '.join(sorted(allow))}")
