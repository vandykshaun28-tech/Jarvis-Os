"""
brain/tool_gate.py — compatibility shim.
The real module now lives at the top level. See brain/tool_result.py for
why (package-vs-module import breakage under spec_from_file_location).
"""

from tool_gate import *            # noqa: F401,F403
from tool_gate import (            # noqa: F401
    gate, allowed_names, groups_for, explain, ALWAYS_ON, GROUPS, GENERAL,
)
