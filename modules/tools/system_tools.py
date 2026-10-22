import os
import psutil

class SystemTools:
    def smart_open(self, target: str) -> str:
        if not target:
            return "Specifica cosa devo aprire, Signore."
        target_lower = target.lower().strip()
        user_home = os.path.expanduser("~")
        
        common_folders = {
            "documenti": os.path.join(user_home, "Documents"),
            "download": os.path.join(user_home, "Downloads"),
            "desktop": os.path.join(user_home, "Desktop"),
            "immagini": os.path.join(user_home, "Pictures"),
            "musica": os.path.join(user_home, "Music")
        }
        for name, path in common_folders.items():
            if name in target_lower and os.path.exists(path):
                os.startfile(path)
                return f"Fatto, cartella {name} aperta."
        
        try:
            os.startfile(target)
            return f"Applicazione '{target}' avviata."
        except Exception:
            return f"Non sono riuscito a trovare '{target}'."

    def get_system_status(self) -> str:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('C:\\').percent
        return f"CPU al {cpu}%, RAM al {ram}%, Disco C al {disk}%. Sistemi stabili."

    def close_process(self, process_name: str) -> str:
        if not process_name:
            return "Specifica il nome del processo da terminare."
        closed = False
        for proc in psutil.process_iter(['name']):
            try:
                if process_name.lower() in proc.info['name'].lower():
                    proc.kill()
                    closed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return f"Processo {process_name} terminato." if closed else f"Nessun processo trovato per {process_name}."