"""
brain/tool_result.py — compatibility shim.

The real module now lives at the TOP LEVEL (C:\jarvis\tool_result.py),
next to config.py.

Why it moved: core/worker.py loads brain/brain.py by file path via
spec_from_file_location, so `brain` in sys.modules can end up bound to
that MODULE rather than the package. Any other file doing
`from brain.tool_result import ...` then dies with

    No module named 'brain.tool_result'; 'brain' is not a package

which is exactly what killed website_build on Shaun's PC on 2026-08-08.
`import config` has always worked from every corner of this project, so
top level is the one location proven reachable no matter how a module
got loaded.

This shim stays so any straggler import keeps working.
"""

from tool_result import *          # noqa: F401,F403
from tool_result import (          # noqa: F401
    ToolResult, Stopwatch, coerce, unmigrated,
)
