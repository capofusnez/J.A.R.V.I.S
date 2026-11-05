"""Aggiornamenti OTA da GitHub (Releases).

- exe compilato: scarica il nuovo Jarvis.exe dall'ultima release, controlla l'integrità, poi uno script .bat
  attende la chiusura di Jarvis, sostituisce l'exe (tenendo Jarvis.exe.bak come copia di sicurezza) e lo riavvia.
- esecuzione da sorgenti: scarica lo zip della release e sovrascrive i file .py (config, .env e data/ restano intatti).

Il repository è scritto nel codice (modules/version.py, UPDATE_REPO), quindi finisce dentro l'exe.
Per un repository privato serve GITHUB_TOKEN nel file .env.
"""
import os
import re
import sys
import json
import shutil
import hashlib
import logging
import tempfile
import zipfile
import subprocess

import requests

from modules.paths import APP_DIR, DATA_DIR, BUNDLE_DIR, FROZEN
from modules.version import VERSION, UPDATE_REPO

log = logging.getLogger("jarvis.updater")
SETTINGS_PATH = os.path.join(DATA_DIR, "update.json")
UPDATE_DIR = os.path.join(APP_DIR, "update")
API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT = 15


# ---------------------------------------------------------------- impostazioni
def repo() -> str:
    """Repository degli aggiornamenti: quello scritto nel codice. Segnaposto o vuoto = aggiornamenti spenti."""
    r = normalize_repo(UPDATE_REPO)
    return "" if r.upper().startswith("TUO_UTENTE/") else r


def load_settings() -> dict:
    """Solo l'interruttore del controllo automatico (data/update.json); il repository non si cambia da qui."""
    cfg = {"auto_check": True}
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            cfg["auto_check"] = bool(json.load(f).get("auto_check", True))
    except (OSError, ValueError):
        pass
    cfg["repo"] = repo()
    return cfg


def save_settings(auto_check: bool):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump({"auto_check": bool(auto_check)}, f, indent=2)


def normalize_repo(text: str) -> str:
    """Accetta 'utente/repo' oppure un indirizzo https://github.com/utente/repo(.git)."""
    t = (text or "").strip()
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", t)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return t if re.fullmatch(r"[\w.-]+/[\w.-]+", t) else ""


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "Jarvis-Updater"}
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def parse_version(text: str) -> tuple:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


# ---------------------------------------------------------------- controllo
def check(repo_name: str = None) -> dict:
    """Ritorna {ok, available, current, latest, notes, asset, zip_url, error}. Non solleva eccezioni."""
    repo_ = normalize_repo(repo_name) if repo_name else repo()
    out = {"ok": False, "available": False, "current": VERSION, "latest": "", "notes": "",
           "asset": None, "zip_url": "", "error": "", "repo": repo_}
    if not repo_:
        out["error"] = "Aggiornamenti non configurati: scrivi il repository GitHub in modules/version.py (UPDATE_REPO) e ricompila."
        return out
    try:
        r = requests.get(API.format(repo=repo_), headers=_headers(), timeout=TIMEOUT)
        if r.status_code == 404:
            out["error"] = f"Nessuna release trovata su {repo_} (o repository privato senza GITHUB_TOKEN)."
            return out
        if r.status_code in (401, 403):
            out["error"] = "GitHub ha rifiutato la richiesta (token non valido o limite di richieste raggiunto)."
            return out
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        out["error"] = f"Non riesco a contattare GitHub: {e}"
        return out
    except ValueError:
        out["error"] = "Risposta di GitHub non valida."
        return out

    out["latest"] = str(data.get("tag_name", "")).lstrip("vV")
    out["notes"] = (data.get("body") or "").strip()
    out["zip_url"] = data.get("zipball_url", "")
    assets = data.get("assets") or []
    exes = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    exes.sort(key=lambda a: (not str(a["name"]).lower().startswith("jarvis"), len(a["name"])))
    if exes:
        a = exes[0]
        sha = ""
        digest = str(a.get("digest") or "")
        if digest.startswith("sha256:"):
            sha = digest[7:]
        else:
            for s in assets:
                if s.get("name") == a["name"] + ".sha256":
                    try:
                        sha = requests.get(s["browser_download_url"], headers=_headers(), timeout=TIMEOUT).text.split()[0]
                    except Exception:
                        pass
        out["asset"] = {"name": a["name"], "url": a.get("url") or a["browser_download_url"],
                        "size": int(a.get("size") or 0), "sha256": sha.lower()}
    out["ok"] = True
    out["available"] = parse_version(out["latest"]) > parse_version(VERSION)
    return out


# ---------------------------------------------------------------- scaricamento + installazione
def _download(url: str, dest: str, size: int, progress=None):
    h = _headers()
    h["Accept"] = "application/octet-stream"
    with requests.get(url, headers=h, stream=True, timeout=TIMEOUT, allow_redirects=True) as r:
        r.raise_for_status()
        total = size or int(r.headers.get("content-length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(info: dict, progress=None) -> str:
    """Scarica e prepara l'aggiornamento. Ritorna 'restart' (exe: l'app deve chiudersi, lo script fa il resto),
    'reload' (sorgenti sovrascritti: basta riavviare a mano). Solleva RuntimeError con un messaggio comprensibile."""
    try:
        if FROZEN:
            return _install_exe(info, progress)
        return _install_source(info, progress)
    except requests.RequestException as e:
        raise RuntimeError(f"Scaricamento non riuscito: {e}")
    except OSError as e:
        raise RuntimeError(f"Errore sui file: {e}")


def _install_exe(info: dict, progress):
    asset = info.get("asset")
    if not asset:
        raise RuntimeError("La release non contiene un file .exe: carica Jarvis.exe tra gli asset della release.")
    os.makedirs(UPDATE_DIR, exist_ok=True)
    new = os.path.join(UPDATE_DIR, "Jarvis_new.exe")
    _download(asset["url"], new, asset["size"], progress)
    if os.path.getsize(new) < 1_000_000:
        raise RuntimeError("Il file scaricato è troppo piccolo: aggiornamento annullato.")
    with open(new, "rb") as f:
        if f.read(2) != b"MZ":
            raise RuntimeError("Il file scaricato non è un programma Windows valido: aggiornamento annullato.")
    if asset.get("sha256") and _sha256(new).lower() != asset["sha256"]:
        os.remove(new)
        raise RuntimeError("Controllo di integrità fallito (SHA-256 diverso): aggiornamento annullato.")
    cur = sys.executable
    bat = os.path.join(UPDATE_DIR, "aggiorna.bat")
    script = (
        "@echo off\r\n"
        f'set "NEW={new}"\r\nset "CUR={cur}"\r\n'
        "for /l %%i in (1,1,90) do (\r\n"
        '  move /y "%CUR%" "%CUR%.bak" >nul 2>&1 && goto swap\r\n'
        "  timeout /t 1 /nobreak >nul\r\n)\r\n"
        "exit /b 1\r\n"
        ":swap\r\n"
        'move /y "%NEW%" "%CUR%" >nul 2>&1\r\n'
        'if errorlevel 1 (move /y "%CUR%.bak" "%CUR%" >nul 2>&1 & exit /b 1)\r\n'
        'start "" "%CUR%"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n')
    with open(bat, "w", encoding="utf-8", newline="") as f:
        f.write(script)
    flags = 0x00000008 | 0x00000200 | 0x08000000          # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True, cwd=UPDATE_DIR)
    return "restart"


KEEP = {"config.json", ".env", "data", "logs", "voices", "moduli", "update", ".git"}


def _install_source(info: dict, progress):
    url = info.get("zip_url")
    if not url:
        raise RuntimeError("La release non ha un archivio dei sorgenti.")
    tmp = tempfile.mkdtemp(prefix="jarvis_upd_")
    try:
        zpath = os.path.join(tmp, "src.zip")
        _download(url, zpath, 0, progress)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(os.path.join(tmp, "x"))
        root = os.path.join(tmp, "x")
        entries = os.listdir(root)
        if len(entries) == 1 and os.path.isdir(os.path.join(root, entries[0])):
            root = os.path.join(root, entries[0])
        if not os.path.exists(os.path.join(root, "main.py")):
            raise RuntimeError("L'archivio non contiene main.py: aggiornamento annullato.")
        n = 0
        for dp, dns, fns in os.walk(root):
            rel = os.path.relpath(dp, root)
            top = rel.split(os.sep)[0]
            if rel != "." and (top in KEEP or top.startswith(".")):
                dns[:] = []
                continue
            for fn in fns:
                if rel == "." and fn in KEEP:
                    continue
                dst = os.path.join(BUNDLE_DIR, "" if rel == "." else rel, fn)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(dp, fn), dst)
                n += 1
        log.info("Aggiornamento da sorgenti: %d file sovrascritti", n)
        return "reload"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
