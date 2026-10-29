import webbrowser
from urllib.parse import quote_plus


class WebTools:
    def web_search(self, query: str) -> str:
        if not query:
            return "Cosa desideri che cerchi?"
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
        return f"Ricerca completata per '{query}'."

    def open_shortcut(self, name: str) -> str:
        web_shortcuts = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "reddit": "https://www.reddit.com",
            "twitch": "https://www.twitch.tv",
            "meteo": "https://www.google.com/search?q=meteo",
        }
        url = web_shortcuts.get(name.lower())
        if url:
            webbrowser.open(url)
            return f"Fatto, apro {name}."
        return f"Scorciatoia non trovata per {name}."
