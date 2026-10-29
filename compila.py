"""Compila Jarvis in un unico Jarvis.exe.   Uso:  python compila.py   (o doppio clic su compila.bat)

Aggiunge a PyInstaller solo quello che esiste davvero sul tuo PC: un pacchetto non installato viene saltato
con un avviso, invece di far fallire tutta la compilazione.
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SEP = os.pathsep                       # ";" su Windows

HIDDEN = ["qtawesome", "PyQt6", "requests", "psutil", "pyttsx3", "speech_recognition", "sounddevice", "numpy",
          "dotenv", "ddgs", "win32com.client", "pythoncom", "win32gui", "win32con", "win32clipboard", "pycaw",
          "comtypes", "edge_tts", "miniaudio", "PIL", "send2trash",
          # librerie standard che i moduli creati da Jarvis possono usare
          "base64", "calendar", "decimal", "fractions", "hashlib", "secrets", "statistics", "textwrap",
          "unicodedata", "uuid"]
COLLECT_ALL = ["faster_whisper", "ctranslate2", "qtawesome", "kokoro_onnx", "espeakng_loader", "onnxruntime"]


def installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name.split(".")[0]) is not None
    except Exception:
        return False


def build_args():
    args = ["--noconsole", "--onefile", "--name", "Jarvis", "--clean", "--noconfirm"]
    if os.path.exists("icona.ico"):
        args += ["--icon=icona.ico"]
    else:
        print("[AVVISO] icona.ico non trovata: l'exe avra' l'icona predefinita.")
    for src, dst in (("icona.ico", "."), ("config.json", "."), ("env_example.txt", "."), ("modules", "modules")):
        if os.path.exists(src):
            args += ["--add-data", f"{src}{SEP}{dst}"]
        else:
            print(f"[AVVISO] {src} non trovato: salto.")
    args += ["--collect-submodules", "modules"]
    for name in HIDDEN:
        if installed(name):
            args += [f"--hidden-import={name}"]
        else:
            print(f"[AVVISO] {name} non installato: salto.")
    for name in COLLECT_ALL:
        if installed(name):
            args += ["--collect-all", name]
        else:
            print(f"[AVVISO] {name} non installato: salto.")
    return args + ["main.py"]


if __name__ == "__main__":
    if not os.path.exists("main.py"):
        sys.exit("ERRORE: main.py non e' in questa cartella: " + HERE)
    args = build_args()
    if "--dry" in sys.argv:
        print(" ".join(args))
        sys.exit(0)
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        sys.exit("ERRORE: PyInstaller non e' installato. Esegui:  python -m pip install -U pyinstaller")
    pyi.run(args)
    exe = os.path.join(HERE, "dist", "Jarvis.exe")
    print("\nFATTO: " + exe if os.path.exists(exe) else "\nNON RIUSCITA: guarda gli errori qui sopra (ultime righe).")
