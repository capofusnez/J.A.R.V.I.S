import os
import subprocess
import glob
import webbrowser
import platform
import psutil

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

class LocalTools:
    def __init__(self):
        pass

    def set_volume(self, level: int) -> str:
        if not PYCAW_AVAILABLE:
            return "Controllo audio non disponibile."
        try:
            level = max(0, min(100, level))
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            scalar = level / 100.0
            volume.SetMasterVolumeLevelScalar(scalar, None)
            return f"Volume impostato al {level}%."
        except Exception as e:
            return f"Errore volume: {e}"

    def set_mute(self, mute: bool) -> str:
        if not PYCAW_AVAILABLE:
            return "Controllo audio non disponibile."
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            volume.SetMute(1 if mute else 0, None)
            return "Audio disattivato." if mute else "Audio riattivato."
        except Exception as e:
            return f"Errore muto: {e}"

    def smart_open(self, target: str) -> str:
        if not target:
            return "Specifica cosa devo aprire, Signore."
        
        target_lower = target.lower().strip()
        user_home = os.path.expanduser("~")
        
        # Scorciatoie per siti web noti (apertura diretta nel browser)
        web_shortcuts = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "reddit": "https://www.reddit.com",
            "twitch": "https://www.twitch.tv",
            "meteo": "https://www.google.com/search?q=meteo"
        }
        for name, url in web_shortcuts.items():
            if name in target_lower:
                webbrowser.open(url)
                return f"Fatto, apro {name}."

        # Cartelle comuni del sistema
        common_folders = {
            "documenti": os.path.join(user_home, "Documents"),
            "download": os.path.join(user_home, "Downloads"),
            "desktop": os.path.join(user_home, "Desktop"),
            "immagini": os.path.join(user_home, "Pictures"),
            "musica": os.path.join(user_home, "Music")
        }

        for name, path in common_folders.items():
            if name in target_lower:
                if os.path.exists(path):
                    os.startfile(path)
                    return f"Fatto, cartella {name} aperta."

        # Ricerca ricorsiva mirata a cartelle
        try:
            for root, dirs, _ in os.walk(user_home):
                for d in dirs:
                    if target_lower == d.lower() or target_lower in d.lower():
                        folder_path = os.path.join(root, d)
                        os.startfile(folder_path)
                        return f"Fatto, cartella {d} aperta."
        except Exception:
            pass

        # Tentativo come applicazione di sistema
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

    def web_search(self, query: str) -> str:
        if not query:
            return "Cosa desideri che cerchi?"
        url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return f"Ricerca completata per '{query}'."