from .module_manager import ModuleManager

class LocalTools:
    """Facade dinamico con scoperte e instradamento automatico a qualsiasi sotto-modulo."""

    def __init__(self):
        self.manager = ModuleManager()
        self.manager.load_all_modules()

    def load_module(self, module_name: str) -> str:
        """Aggancia un modulo a caldo (rileva in automatico dal registro)."""
        return self.manager.load_module(module_name.lower())

    def unload_module(self, module_name: str) -> str:
        """Sgancia un modulo a caldo."""
        return self.manager.unload_module(module_name.lower())

    def reload_module(self, module_name: str) -> str:
        """Ricarica a caldo un modulo."""
        return self.manager.load_module(module_name.lower())

    def get_modules_status(self) -> str:
        """Restituisce lo stato di tutti i moduli presenti nella cartella."""
        return self.manager.get_status()

    def __getattr__(self, name):
        """Dispatcher universale: se chiami un metodo (es. set_volume, ping, ecc.) 
        lo cerca automaticamente in tutti i moduli attualmente caricati in memoria."""
        for mod in self.manager.loaded_modules.values():
            if hasattr(mod, name):
                return getattr(mod, name)
        
        def missing_method(*args, **kwargs):
            return f"La funzione '{name}' non è disponibile o il relativo modulo è sganciato."
        return missing_method