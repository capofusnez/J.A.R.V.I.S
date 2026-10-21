import os
import re
import json
import threading


class MemoryStore:
    """Memoria a lungo termine di Jarvis (memory.json).

    Contiene: fatti sull'utente, mittenti VIP / silenziati, esempi del suo stile di scrittura.
    Legge anche il vecchio formato (semplice lista di frasi).
    """

    MAX_FACTS = 40
    MAX_STYLE = 6

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self.data = {"facts": [], "vip": [], "blocked": [], "style_samples": []}
        self._load()

    # ---------- persistenza ----------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return
        if isinstance(raw, list):                       # vecchio formato
            self.data["facts"] = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, dict):
            for key in self.data:
                if isinstance(raw.get(key), list):
                    self.data[key] = raw[key]

    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[MEMORY ERROR] salvataggio fallito: {e}")

    # ---------- fatti ----------
    def facts(self) -> list:
        with self._lock:
            return list(self.data["facts"])

    def add_fact(self, text: str) -> bool:
        text = (text or "").strip().strip("\"'")
        if len(text) < 4:
            return False
        with self._lock:
            if text.lower() in (f.lower() for f in self.data["facts"]):
                return False
            self.data["facts"].append(text)
            self.data["facts"] = self.data["facts"][-self.MAX_FACTS:]
            self._save()
            return True

    def forget(self, query: str, max_remove: int = 3):
        """Rimuove i fatti che corrispondono. Ritorna la lista rimossa,
        oppure None se le corrispondenze sono troppe (richiesta troppo vaga)."""
        q = (query or "").lower().strip(" .!?")
        if len(q) < 3:
            return []
        words = [w for w in re.findall(r"\w+", q) if len(w) > 2]
        with self._lock:
            hits = [f for f in self.data["facts"]
                    if q in f.lower() or (words and all(w in f.lower() for w in words))]
            if len(hits) > max_remove:
                return None
            self.data["facts"] = [f for f in self.data["facts"] if f not in hits]
            if hits:
                self._save()
            return hits

    # ---------- mittenti ----------
    @staticmethod
    def _match(ident: str, addr: str, name: str) -> bool:
        addr, name = (addr or "").lower(), (name or "").lower()
        return ident == addr or ("@" not in ident and ident != "" and ident in name)

    def add_vip(self, ident: str):
        ident = ident.lower().strip()
        with self._lock:
            self.data["blocked"] = [b for b in self.data["blocked"] if b != ident]
            if ident and ident not in self.data["vip"]:
                self.data["vip"].append(ident)
            self._save()

    def block(self, ident: str):
        ident = ident.lower().strip()
        with self._lock:
            self.data["vip"] = [v for v in self.data["vip"] if v != ident]
            if ident and ident not in self.data["blocked"]:
                self.data["blocked"].append(ident)
            self._save()

    def is_vip(self, addr: str, name: str = "") -> bool:
        with self._lock:
            return any(self._match(i, addr, name) for i in self.data["vip"])

    def is_blocked(self, addr: str, name: str = "") -> bool:
        with self._lock:
            return any(self._match(i, addr, name) for i in self.data["blocked"])

    # ---------- stile di scrittura ----------
    def add_style_sample(self, text: str) -> bool:
        text = (text or "").strip()
        if not 40 <= len(text) <= 1200:
            return False
        with self._lock:
            if text in self.data["style_samples"]:
                return False
            self.data["style_samples"].append(text)
            self.data["style_samples"] = self.data["style_samples"][-self.MAX_STYLE:]
            self._save()
            return True

    def style_samples(self) -> list:
        with self._lock:
            return list(self.data["style_samples"])
