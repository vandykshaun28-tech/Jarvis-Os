"""
tools/ — real tools that do real things and report what actually happened.

Every function in this package returns a ToolResult. None of them return
prose that the caller has to interpret. If it worked, ok is True and the
payload is real data pulled from a real system. If it didn't, ok is False
and the error is the actual error, not a summary of one.
"""
