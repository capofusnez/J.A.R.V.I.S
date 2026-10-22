import os
import json
import importlib
import pkgutil
import inspect
import sys

class ModuleManager:
    """Engine per la scoperta automatica (Auto-Discovery) e la gestione a caldo dei moduli."""

    def __init__(self):
        self.loaded_modules = {}  # Nome modulo -> Istanza della classe
        self.module_registry = {} # Nome modulo -> (import_path, class_name)
        self.config = self._load_config()
        self.discover_available_modules()

    def _load_config(self) -> dict:
        """Legge il file config.json nella root o lo genera con i default se manca."""
        try:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            config_path = os.path.join(root_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def discover_available_modules(self):
        """Scansiona automaticamente la cartella corrente per scoprire tutti i file e classi *_tools."""
        current_dir = os.path.dirname(__file__)
        package_prefix = "modules.tools."

        for _, module_name, is_pkg in pkgutil.iter_modules([current_dir]):
            # Ignora file speciali o di gestione interna
            if is_pkg or module_name.startswith("_") or module_name == "module_manager":
                continue

            import_path = package_prefix + module_name
            try:
                mod = importlib.import_module(import_path)
                # Cerca le classi definite all'interno del file (es. NetworkTools in network_tools.py)
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if obj.__module__ == import_path and not name.startswith("_"):
                        # Ricava la chiave breve (es. "network_tools" o "network" -> "network")
                        short_key = module_name.replace("_tools", "").lower()
                        self.module_registry[short_key] = (import_path, name)
            except Exception as e:
                print(f"[Auto-Discovery Error] Impossibile caricare {module_name}: {e}")

    def load_all_modules(self):
        """Carica a caldo tutti i moduli scoperti che sono abilitati in config.json."""
        self.discover_available_modules()
        modules_conf = self.config.get("modules", {})

        for mod_key, (import_path, class_name) in self.module_registry.items():
            # Se è presente nel config.json ed è True, oppure se è un nuovo modulo non ancora a config (default: True)
            is_enabled = modules_conf.get(mod_key, True)
            if is_enabled:
                self.load_module(mod_key)

    def load_module(self, mod_key: str) -> str:
        """Carica o ricarica un singolo modulo in memoria."""
        if mod_key not in self.module_registry:
            self.discover_available_modules()  # Riprova a scansionare se è stato aggiunto un file nuovo da poco
            if mod_key not in self.module_registry:
                return f"Modulo '{mod_key}' non trovato nella cartella."

        import_path, class_name = self.module_registry[mod_key]
        try:
            if import_path in sys.modules:
                mod = importlib.reload(sys.modules[import_path])
            else:
                mod = importlib.import_module(import_path)

            cls = getattr(mod, class_name)
            self.loaded_modules[mod_key] = cls()
            return f"Modulo '{mod_key}' agganciato con successo."
        except Exception as e:
            return f"Errore nell'aggancio del modulo '{mod_key}': {e}"

    def unload_module(self, mod_key: str) -> str:
        """Sgancia un modulo dalla memoria."""
        if mod_key in self.loaded_modules:
            del self.loaded_modules[mod_key]
            return f"Modulo '{mod_key}' sganciato."
        return f"Modulo '{mod_key}' non era caricato."

    def get_status(self) -> str:
        """Restituisce lo stato dinamico di tutti i moduli rilevati sul disco."""
        self.discover_available_modules()
        status = []
        for key in self.module_registry:
            if key in self.loaded_modules:
                status.append(f"🟢 [{key.upper()}] Modulo AGGANCIATO e operativo.")
            else:
                status.append(f"🔴 [{key.upper()}] Modulo SGANCIATO / Disattivato.")
        return "\n".join(status) if status else "Nessun modulo rilevato nella cartella."