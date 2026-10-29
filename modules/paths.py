"""Dove Jarvis tiene i suoi file.

Tutto sta accanto a Jarvis.exe (oppure accanto a main.py quando lo avvii da Python), in cartelle ordinate:

    Jarvis.exe
    .env              password della posta (lo scrivi tu, vedi env_example.txt)
    config.json       moduli attivi / disattivi
    data/             memory.json, mail_state.json, voice.json
    logs/             jarvis.log, jarvis_crash.log
    voices/           voci offline scaricate (Kokoro, Piper)
    moduli/           moduli creati da Jarvis e installati; moduli/_pending = in attesa di "installa"

Se la cartella dell'exe non è scrivibile (es. C:\\Program Files) si usa %LOCALAPPDATA%\\Jarvis.
"""
import os
import sys
import shutil

FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))        # dove le vecchie versioni salvavano


def _default_app_dir() -> str:
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))          # la cartella dell'exe (anche con --onefile)
    return os.path.dirname(_LEGACY_MODULES_DIR)                          # la cartella con main.py


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".scrittura_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _choose_app_dir() -> str:
    d = os.environ.get("JARVIS_HOME") or _default_app_dir()              # JARVIS_HOME: per scegliere a mano un'altra cartella
    if _writable(d):
        return d
    alt = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Jarvis")
    os.makedirs(alt, exist_ok=True)
    return alt


APP_DIR = _choose_app_dir()
DATA_DIR = os.path.join(APP_DIR, "data")
LOGS_DIR = os.path.join(APP_DIR, "logs")
VOICES_DIR = os.path.join(APP_DIR, "voices")
TOOLS_DIR = os.path.join(APP_DIR, "moduli")
PENDING_DIR = os.path.join(TOOLS_DIR, "_pending")
ENV_PATH = os.path.join(APP_DIR, ".env")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")


def _copy_if_missing(src: str, dst: str):
    try:
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    except OSError:
        pass


def init_dirs():
    """Crea le cartelle, copia config.json di serie e porta con sé i file delle vecchie versioni (senza cancellarli)."""
    for d in (DATA_DIR, LOGS_DIR, VOICES_DIR, TOOLS_DIR, PENDING_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    _copy_if_missing(os.path.join(BUNDLE_DIR, "config.json"), CONFIG_PATH)
    _copy_if_missing(os.path.join(BUNDLE_DIR, "env_example.txt"), os.path.join(APP_DIR, "env_example.txt"))
    if FROZEN:
        return                                       # dentro l'exe non ci sono vecchi file personali da portare con sé
    # vecchi percorsi: memory.json e mail_state.json stavano in modules/, voice.json accanto a main.py
    _copy_if_missing(os.path.join(_LEGACY_MODULES_DIR, "memory.json"), os.path.join(DATA_DIR, "memory.json"))
    _copy_if_missing(os.path.join(_LEGACY_MODULES_DIR, "mail_state.json"), os.path.join(DATA_DIR, "mail_state.json"))
    _copy_if_missing(os.path.join(os.path.dirname(_LEGACY_MODULES_DIR), "voice.json"), os.path.join(DATA_DIR, "voice.json"))


init_dirs()
