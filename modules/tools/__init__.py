import os
import json
from .audio_tools import AudioTools
from .system_tools import SystemTools
from .web_tools import WebTools

class LocalTools(AudioTools, SystemTools, WebTools):
    """Classe unificata che eredita i moduli e ne gestisce l'abilitazione selettiva tramite config.json."""
    
    def __init__(self):
        super().__init__()
        config = self._load_config()
        modules_conf = config.get("modules", {"audio": True, "system": True, "web": True})
        
        self.audio_enabled = modules_conf.get("audio", True)
        self.system_enabled = modules_conf.get("system", True)
        self.web_enabled = modules_conf.get("web", True)

    def _load_config(self) -> dict:
        """Legge il file config.json nella root o lo crea automaticamente con i default se manca."""
        try:
            # Risale di tre cartelle: da modules/tools/ a modules/, poi alla root del progetto
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            config_path = os.path.join(root_dir, "config.json")
            
            default_config = {
                "model_name": "qwen2.5-coder:14b",
                "ollama_url": "http://localhost:11434/",
                "keep_alive": "30m",
                "modules": {
                    "audio": True,
                    "system": True,
                    "web": True
                }
            }
            
            # Se il file config.json non esiste, viene generato con le impostazioni predefinite
            if not os.path.exists(config_path):
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                return default_config
            
            # Se esiste già, viene letto normalmente
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
        return {}

    def get_modules_status(self) -> str:
        """Restituisce lo stato dettagliato dei moduli e delle loro dipendenze."""
        status_lines = []
        
        if self.audio_enabled:
            try:
                from .audio_tools import PYCAW_AVAILABLE
                if PYCAW_AVAILABLE:
                    status_lines.append("🔊 Audio: Attivo e operativo (Pycaw disponibile)")
                else:
                    status_lines.append("🔊 Audio: Attivo in configurazione, ma libreria Pycaw non installata/disponibile")
            except ImportError:
                status_lines.append("🔊 Audio: Attivo in configurazione, ma modulo audio non trovato")
        else:
            status_lines.append("🔊 Audio: Disattivato nel file config.json")

        if self.system_enabled:
            status_lines.append("⚙️ Sistema: Attivo e operativo")
        else:
            status_lines.append("⚙️ Sistema: Disattivato nel file config.json")

        if self.web_enabled:
            status_lines.append("🌐 Web: Attivo e operativo")
        else:
            status_lines.append("🌐 Web: Disattivato nel file config.json")

        return "\n".join(status_lines)

    # --- Metodi Proxy Audio ---
    def set_volume(self, level: int) -> str:
        if not self.audio_enabled:
            return "Il modulo audio è disattivato nella configurazione."
        return super().set_volume(level)

    def set_volume_relative(self, delta: int) -> str:
        if not self.audio_enabled:
            return "Il modulo audio è disattivato nella configurazione."
        return super().set_volume_relative(delta)

    def set_mute(self, mute: bool) -> str:
        if not self.audio_enabled:
            return "Il modulo audio è disattivato nella configurazione."
        return super().set_mute(mute)

    # --- Metodi Proxy Sistema ---
    def smart_open(self, target: str) -> str:
        if not self.system_enabled:
            return "Il modulo di sistema è disattivato nella configurazione."
        return super().smart_open(target)

    def get_system_status(self) -> str:
        if not self.system_enabled:
            return "Il modulo di sistema è disattivato nella configurazione."
        return super().get_system_status()

    def close_process(self, process_name: str) -> str:
        if not self.system_enabled:
            return "Il modulo di sistema è disattivato nella configurazione."
        return super().close_process(process_name)

    # --- Metodi Proxy Web ---
    def web_search(self, query: str) -> str:
        if not self.web_enabled:
            return "Il modulo web è disattivato nella configurazione."
        return super().web_search(query)

    def open_shortcut(self, name: str) -> str:
        if not self.web_enabled:
            return "Il modulo web è disattivato nella configurazione."
        return super().open_shortcut(name)