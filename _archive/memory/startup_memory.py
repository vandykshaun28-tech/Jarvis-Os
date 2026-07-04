from pathlib import Path


class StartupMemory:

    def __init__(self, vault_path):

        self.vault_path = Path(vault_path)

    def get_recent_memories(self, limit=10):

        memories_folder = self.vault_path / "Memories"

        if not memories_folder.exists():
            return []

        files = sorted(
            memories_folder.glob("*.md"),
            reverse=True
        )

        results = []

        for file in files[:limit]:

            try:

                content = file.read_text(
                    encoding="utf-8"
                )

                results.append(
                    {
                        "file": file.name,
                        "content": content
                    }
                )

            except Exception:
                pass

        return results

    def build_context(self, limit=5):

        memories = self.get_recent_memories(limit)

        if not memories:
            return ""

        context = []

        for memory in memories:

            context.append(
                f"Memory File: {memory['file']}\n"
                f"{memory['content']}"
            )

        return "\n\n".join(context)