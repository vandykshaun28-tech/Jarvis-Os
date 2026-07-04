"""
web_search.py
─────────────
JARVIS web search + real weather.
"""

from ddgs import DDGS

try:
    import httpx
    HTTPX_OK = True
except Exception:
    HTTPX_OK = False

# WMO weather codes → plain English
_WMO = {0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "icy fog", 51: "light drizzle", 53: "drizzle",
        55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
        71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
        81: "rain showers", 82: "violent rain showers", 95: "thunderstorms",
        96: "thunderstorms with hail", 99: "severe thunderstorms with hail"}


class WebSearch:

    def __init__(self):
        self._geo_cache = {}
        print("[Web] Search module ready.")

    def search(self, query: str, max_results: int = 3) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                return "I found no results for that query, sir."

            parts = []
            for r in results[:max_results]:
                title = r.get("title", "").strip()
                body  = r.get("body", "").strip()
                if body:
                    snippet = body[:220].strip()
                    if not snippet.endswith("."):
                        snippet = snippet.rsplit(" ", 1)[0] + "."
                    parts.append(f"{title}: {snippet}" if title else snippet)

            return "\n".join(parts) if parts else \
                "I found results but could not summarise them, sir."

        except Exception as e:
            return f"Web search failed: {e}"

    def weather(self, location: str = "Benoni, South Africa") -> str:
        """Real weather from Open-Meteo (free, no API key) instead of
        scraping search snippets."""
        if not HTTPX_OK:
            return self.search(f"current weather {location} today temperature")
        try:
            place = location.split(",")[0].strip()
            if place not in self._geo_cache:
                g = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                              params={"name": place, "count": 1},
                              timeout=15).json()
                hit = (g.get("results") or [{}])[0]
                if "latitude" not in hit:
                    return f"I could not locate '{place}', sir."
                self._geo_cache[place] = (hit["latitude"], hit["longitude"])
            lat, lon = self._geo_cache[place]
            w = httpx.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code,"
                           "wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max",
                "timezone": "auto", "forecast_days": 1,
            }, timeout=15).json()
            c = w.get("current", {})
            d = w.get("daily", {})
            desc = _WMO.get(c.get("weather_code"), "unremarkable conditions")
            out = (f"{round(c.get('temperature_2m', 0))}°C and {desc}, "
                   f"feels like {round(c.get('apparent_temperature', 0))}°C. ")
            if d.get("temperature_2m_max"):
                out += (f"Today: {round(d['temperature_2m_min'][0])} to "
                        f"{round(d['temperature_2m_max'][0])}°C")
                rain = (d.get("precipitation_probability_max") or [None])[0]
                if rain is not None:
                    out += f", {rain}% chance of rain"
                out += "."
            return out
        except Exception as e:
            return f"Weather lookup failed ({e}), sir."

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
