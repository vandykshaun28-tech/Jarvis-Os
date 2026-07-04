from datetime import datetime
import traceback


class Executor:
    """
    Executes commands and returns a standardized result.
    """

    def __init__(self):
        self.commands = {}

    def register(self, name: str, func):
        """Register a command."""
        self.commands[name] = func

    def execute(self, command: str, *args, **kwargs):

        if command not in self.commands:
            return {
                "success": False,
                "command": command,
                "message": f"Unknown command: {command}",
                "data": None
            }

        try:
            result = self.commands[command](*args, **kwargs)

            return {
                "success": True,
                "command": command,
                "message": "Command executed successfully.",
                "data": result
            }

        except Exception as e:

            return {
                "success": False,
                "command": command,
                "message": str(e),
                "traceback": traceback.format_exc()
            }