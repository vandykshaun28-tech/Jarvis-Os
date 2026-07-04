"""
web_search.py
─────────────
JARVIS web search module.
Location: C:\jarvis_v18\brain\web_search.py
"""

from ddgs import DDGS


class WebSearch:

    def __init__(self):
        print("[Web] Search module ready.")

    def search(self, query: str, max_results: int = 3) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                return f"I found no results for that query, sir."

            parts = []
            for r in results[:2]:
                body = r.get("body", "")
                if body:
                    snippet = body[:150].strip()
                    if not snippet.endswith("."):
                        snippet = snippet.rsplit(" ", 1)[0] + "."
                    parts.append(snippet)

            return " ".join(parts) if parts else "I found results but could not summarise them, sir."

        except Exception as e:
            return f"Web search failed: {e}"

    def weather(self, location: str = "Benoni, South Africa") -> str:
        return self.search(f"current weather {location} today temperature")

    def news(self, topic: str = "") -> str:
        query = f"latest news {topic}" if topic else "top news today"
        return self.search(query)

    def quick_fact(self, query: str) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=1))
            if results:
                body = results[0].get("body", "")
                return body[:200].strip()
            return "I could not find that information, sir."
        except Exception as e:
            return f"Search error: {e}"