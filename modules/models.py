"""Elenco dei modelli Ollama e scelta automatica del più adatto a ogni richiesta.

Ogni modello installato ha un profilo (modificabile da Impostazioni):
    enabled  se Jarvis può usarlo
    tags     per cosa è adatto: chat, fast, complex, code, reasoning, vision
Jarvis sceglie così: chat normale -> il modello "chat" scelto da te; compito difficile -> un modello "complex";
codice e moduli -> un modello "code"; matematica/analisi -> "reasoning". Se il migliore non parte (memoria), passa al successivo.
I profili stanno in data/models.json. I modelli cloud (a pagamento) restano spenti finché non li accendi tu.
"""
import os
import re
import json
import time
import logging
import threading

import requests

try:
    from modules.paths import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

GB = 1024 ** 3
ALL_TAGS = ["chat", "fast", "complex", "code", "reasoning", "vision"]
TAG_LABELS = {"chat": "Chat", "fast": "Veloce", "complex": "Difficile", "code": "Codice",
              "reasoning": "Ragionamento", "vision": "Immagini"}
TASK_TAGS = {                       # per ogni compito, i tag in ordine di preferenza
    "chat": ["chat", "fast"],
    "complex": ["complex", "reasoning", "code"],
    "code": ["code", "complex"],
    "reasoning": ["reasoning", "complex"],
    "vision": ["vision"],
}

# modelli consigliati con peso approssimativo del download (GB); i valori esatti compaiono durante lo scaricamento
SUGGESTED = [
    ("qwen2.5:3b", 1.9, "Chat veloce, leggero"),
    ("llama3.2:3b", 2.0, "Chat veloce, leggero"),
    ("phi4-mini", 2.5, "Chat e ragionamento, leggero"),
    ("gemma3:4b", 3.3, "Chat, capisce anche le immagini"),
    ("mistral:7b", 4.4, "Chat generale"),
    ("qwen2.5:7b", 4.7, "Chat generale, ottimo in italiano"),
    ("qwen2.5-coder:7b", 4.7, "Codice e moduli, leggero"),
    ("llama3.1:8b", 4.9, "Chat generale"),
    ("deepseek-r1:8b", 5.2, "Ragionamento, matematica"),
    ("qwen3:8b", 5.2, "Chat e ragionamento"),
    ("qwen2.5vl:7b", 6.0, "Capisce le immagini"),
    ("gemma3:12b", 8.1, "Compiti difficili, immagini"),
    ("qwen2.5:14b", 9.0, "Compiti difficili"),
    ("qwen2.5-coder:14b", 9.0, "Codice e moduli"),
    ("deepseek-r1:14b", 9.0, "Ragionamento difficile"),
    ("kimi-k3.1-pro:cloud", 0.0, "Cloud a pagamento: nessun download, non gira sul PC"),
]


def is_cloud(name: str) -> bool:
    return name.endswith(":cloud") or name.endswith("-cloud")


def size_gb(model: dict) -> float:
    return round((model.get("size") or 0) / GB, 1)


def guess_tags(name: str, size_bytes: int) -> list:
    n, gb = name.lower(), (size_bytes or 0) / GB
    tags = set()
    if re.search(r"coder|codestral|starcoder|devstral|codellama|codegemma", n):
        tags |= {"code", "complex"}
    elif re.search(r"embed|bge|minilm", n):
        return []                                   # modelli per gli embedding: non servono per rispondere
    else:
        tags.add("chat")
    if re.search(r"r1|reason|qwq|think|phi4|qwen3|magistral|o1", n):
        tags |= {"reasoning"}
    if re.search(r"vl\b|vision|llava|moondream|minicpm-v|gemma3|llama3\.2-vision", n):
        tags.add("vision")
    if is_cloud(n):
        tags |= {"complex", "reasoning", "code"}
        tags.discard("chat")                         # a pagamento: mai per le chiacchiere di tutti i giorni
    elif "code" not in tags:
        if gb and gb <= 4.6:
            tags.add("fast")
        elif gb > 4.6:
            tags.add("complex")
    if gb > 12:
        tags |= {"complex"}
    return [t for t in ALL_TAGS if t in tags]


class ModelRegistry:
    def __init__(self, base_url="http://localhost:11434", default_chat="qwen2.5", path=None):
        self.base = base_url.rstrip("/")
        self.path = path or os.path.join(DATA_DIR, "models.json")
        self._lock = threading.RLock()
        self.session = requests.Session()
        self.installed = {}                         # nome -> dict di Ollama (name, size, details...)
        self._refreshed = 0.0
        self.online = False
        self.bad = {}                               # nome -> ora fino a cui evitarlo (errore di memoria)
        self.data = {"chat": "", "profiles": {}}
        self.default_chat = default_chat
        self._load()

    # ---- archivio
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data["chat"] = d.get("chat", "")
            self.data["profiles"] = d.get("profiles", {})
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.warning("[MODELLI] models.json non leggibile: %s", e)

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:
            logging.warning("[MODELLI] non riesco a salvare i modelli: %s", e)

    # ---- Ollama
    def refresh(self, force=True) -> bool:
        """Rilegge l'elenco dei modelli installati e crea il profilo di quelli nuovi."""
        with self._lock:
            if not force and time.time() - self._refreshed < 60:
                return self.online
            try:
                r = self.session.get(self.base + "/api/tags", timeout=3)
                r.raise_for_status()
                models = r.json().get("models", [])
            except Exception:
                self.online = False
                self._refreshed = time.time()
                return False
            self.online = True
            self._refreshed = time.time()
            self.installed = {m.get("name", ""): m for m in models if m.get("name")}
            changed = False
            explicit_big = os.environ.get("JARVIS_CODER_MODEL", "")
            for name, m in self.installed.items():
                if name not in self.data["profiles"]:
                    tags = guess_tags(name, m.get("size", 0))
                    enabled = bool(tags) and not is_cloud(name)         # i modelli cloud costano: li accendi tu
                    if explicit_big and self._same(name, explicit_big):
                        enabled, tags = True, sorted(set(tags) | {"complex", "code"}, key=ALL_TAGS.index)
                    self.data["profiles"][name] = {"enabled": enabled, "tags": tags, "auto": True}
                    changed = True
            for name in list(self.data["profiles"]):
                if name not in self.installed:                           # cancellato da fuori: via anche il profilo
                    del self.data["profiles"][name]
                    changed = True
            if changed:
                self.save()
            return True

    @staticmethod
    def _same(a: str, b: str) -> bool:
        a, b = a.lower(), b.lower()
        return a == b or a == b + ":latest" or b == a + ":latest"

    def _ensure(self):
        if time.time() - self._refreshed > 60:
            self.refresh(force=True)

    def names(self):
        self._ensure()
        return sorted(self.installed)

    def profile(self, name: str) -> dict:
        return self.data["profiles"].get(name, {"enabled": False, "tags": [], "auto": True})

    def set_profile(self, name: str, enabled=None, tags=None):
        with self._lock:
            p = self.data["profiles"].setdefault(name, {"enabled": False, "tags": [], "auto": True})
            if enabled is not None:
                p["enabled"] = bool(enabled)
            if tags is not None:
                p["tags"] = [t for t in ALL_TAGS if t in tags]
                p["auto"] = False
            self.save()

    def set_chat(self, name: str):
        with self._lock:
            self.data["chat"] = name
            p = self.data["profiles"].setdefault(name, {"enabled": True, "tags": ["chat"], "auto": True})
            p["enabled"] = True
            if "chat" not in p["tags"]:
                p["tags"] = ["chat"] + p["tags"]
            self.save()

    def mark_bad(self, name: str, seconds: float = 600):
        self.bad[name] = time.time() + seconds

    def _usable(self, name: str) -> bool:
        return self.bad.get(name, 0) < time.time()

    # ---- scelta
    def chat_model(self) -> str:
        """Il modello per la chat di tutti i giorni (scelto da te; altrimenti il predefinito o il più leggero)."""
        self._ensure()
        want = self.data.get("chat") or self.default_chat
        for n in self.installed:
            if self._same(n, want):
                return n
        if not self.installed:
            return want
        chat = [n for n in self.installed if "chat" in self.profile(n)["tags"] and self.profile(n)["enabled"]]
        pool = chat or list(self.installed)
        return min(pool, key=lambda n: self.installed[n].get("size", 0) or 10 ** 12)

    def pick(self, task: str, exclude=()) -> str:
        """Il modello più adatto al compito tra quelli accesi e installati; in mancanza, quello della chat."""
        if task == "chat":
            return self.chat_model()
        self._ensure()
        tags = TASK_TAGS.get(task, ["complex"])
        try:
            import psutil
            free = psutil.virtual_memory().available
        except Exception:
            free = 0
        cands = []
        for n, m in self.installed.items():
            p = self.profile(n)
            if not p["enabled"] or n in exclude or not self._usable(n):
                continue
            idx = next((i for i, t in enumerate(tags) if t in p["tags"]), None)
            if idx is None:
                continue
            size = m.get("size", 0) or 0
            fits = is_cloud(n) or not free or size * 1.15 < free
            cands.append((0 if fits else 1, idx, -size, n))
        if cands:
            return min(cands)[3]
        return self.chat_model()

    def is_big(self, name: str) -> bool:
        """True per i modelli 'pesanti' (tempi lunghi, restano in memoria meno)."""
        if not name or self._same(name, self.chat_model()):
            return False
        m = self.installed.get(name)
        return bool(m and ((m.get("size", 0) or 0) > 6 * GB or is_cloud(name))) or "complex" in self.profile(name)["tags"]

    # ---- operazioni
    def disk_usage_gb(self) -> float:
        return round(sum((m.get("size", 0) or 0) for n, m in self.installed.items() if not is_cloud(n)) / GB, 1)

    def pull(self, name: str, progress=None, cancel=lambda: False) -> str:
        """Scarica un modello. progress(stato, scaricati_byte, totale_byte). Ritorna '' se va bene, altrimenti l'errore."""
        totals, done = {}, {}
        try:
            with self.session.post(self.base + "/api/pull", json={"model": name, "stream": True},
                                   stream=True, timeout=(5, 600)) as r:
                if r.status_code >= 400:
                    try:
                        return r.json().get("error", f"errore {r.status_code}")
                    except Exception:
                        return f"errore {r.status_code}"
                for line in r.iter_lines():
                    if cancel():
                        return "scaricamento annullato"
                    if not line:
                        continue
                    d = json.loads(line)
                    if d.get("error"):
                        return str(d["error"])
                    dg = d.get("digest")
                    if dg and d.get("total"):
                        totals[dg] = d["total"]
                        done[dg] = d.get("completed", done.get(dg, 0))
                    if progress:
                        progress(d.get("status", ""), sum(done.values()), sum(totals.values()))
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        self.refresh(force=True)
        return ""

    def delete(self, name: str) -> str:
        """Cancella il modello e i suoi file dal disco. Ritorna '' se va bene, altrimenti l'errore."""
        try:
            r = self.session.delete(self.base + "/api/delete", json={"model": name}, timeout=30)
            if r.status_code >= 400:
                try:
                    return r.json().get("error", f"errore {r.status_code}")
                except Exception:
                    return f"errore {r.status_code}"
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        with self._lock:
            self.data["profiles"].pop(name, None)
            if self._same(self.data.get("chat", ""), name):
                self.data["chat"] = ""
            self.save()
        self.refresh(force=True)
        return ""

    def report(self) -> str:
        self._ensure()
        if not self.installed:
            return "Non vedo nessun modello Ollama installato."
        out = []
        for n in sorted(self.installed):
            p = self.profile(n)
            gb = "cloud" if is_cloud(n) else f"{size_gb(self.installed[n])} giga"
            uso = ", ".join(TAG_LABELS[t].lower() for t in p["tags"]) or "nessun uso"
            out.append(f"{n}, {gb}, {'acceso' if p['enabled'] else 'spento'}, per {uso}")
        return "Modelli: " + "; ".join(out) + f". Chat di tutti i giorni: {self.chat_model()}."


_REG = None


def get_registry(base_url="http://localhost:11434", default_chat="qwen2.5") -> ModelRegistry:
    global _REG
    if _REG is None:
        _REG = ModelRegistry(base_url, default_chat)
    return _REG
