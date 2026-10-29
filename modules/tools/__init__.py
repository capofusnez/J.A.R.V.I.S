import inspect
from .module_manager import ModuleManager


class LocalTools:
    """Facade dei moduli-strumento: li scopre, li carica a caldo e li espone al brain."""

    def __init__(self):
        self.manager = ModuleManager()
        self.manager.load_all_modules()

    # ---------------- gestione moduli ----------------
    def load_module(self, module_name: str) -> str:
        """Aggancia un modulo a caldo."""
        return self.manager.load_module(module_name.lower())

    def unload_module(self, module_name: str) -> str:
        """Sgancia un modulo a caldo."""
        return self.manager.unload_module(module_name.lower())

    def reload_module(self, module_name: str) -> str:
        """Ricarica a caldo un modulo."""
        return self.manager.load_module(module_name.lower())

    def get_modules_status(self) -> str:
        """Stato di tutti i moduli presenti nella cartella."""
        return self.manager.get_status()

    # ---------------- catalogo reale degli strumenti ----------------
    def catalog(self, exclude=()) -> list:
        """Elenco dei metodi pubblici dei moduli caricati: [{module, name, params, doc}]."""
        items = []
        for key, inst in list(self.manager.loaded_modules.items()):
            for name in dir(inst):
                if name.startswith("_") or name in exclude:
                    continue
                fn = getattr(inst, name, None)
                if not callable(fn):
                    continue
                try:
                    sig = inspect.signature(fn)
                except (TypeError, ValueError):
                    continue
                params = []
                for p in sig.parameters.values():
                    tname = getattr(p.annotation, "__name__", "") if p.annotation is not inspect.Parameter.empty else ""
                    label = f"{p.name}: {tname}" if tname else p.name
                    params.append(label + ("?" if p.default is not inspect.Parameter.empty else ""))
                doc = (inspect.getdoc(fn) or "").strip().split("\n")[0]
                items.append({"module": key, "name": name, "params": params, "doc": doc})
        return items

    def find_method(self, ref: str):
        """'modulo.metodo' oppure 'metodo' -> (callable, None) oppure (None, messaggio d'errore)."""
        ref = (ref or "").strip().lower()
        if "." in ref:
            mod_key, meth = ref.split(".", 1)
            inst = self.manager.loaded_modules.get(mod_key)
            if inst is None:
                return None, f"Il modulo '{mod_key}' non è attivo."
            fn = getattr(inst, meth, None) if not meth.startswith("_") else None
            return (fn, None) if callable(fn) else (None, f"Il modulo '{mod_key}' non ha lo strumento '{meth}'.")
        found = []
        for key, inst in self.manager.loaded_modules.items():
            fn = getattr(inst, ref, None) if not ref.startswith("_") else None
            if callable(fn):
                found.append((key, fn))
        if len(found) == 1:
            return found[0][1], None
        if not found:
            return None, f"Non ho uno strumento chiamato '{ref}'."
        return None, f"'{ref}' esiste in più moduli ({', '.join(k for k, _ in found)}): specifica quale."

    # ---------------- accesso diretto ai metodi (es. tools.set_volume) ----------------
    def __getattr__(self, name):
        # Un metodo sconosciuto deve dare AttributeError: così hasattr()/getattr(..., None) funzionano.
        if name.startswith("_") or name == "manager":
            raise AttributeError(name)
        for mod in self.manager.loaded_modules.values():
            if hasattr(mod, name):
                return getattr(mod, name)
        raise AttributeError(f"Nessun modulo caricato espone '{name}'")
