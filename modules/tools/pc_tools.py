"""Controllo del computer a voce: finestre, tastiera, mouse, media, schermo, energia, file.

Solo Windows. Va in modules/tools/ (si aggancia da solo, chiave "pc").
Le azioni delicate (spegnere, riavviare, cancellare...) sono elencate in CONFIRM: il brain
chiede sempre una conferma a voce prima di eseguirle.
I file si cercano e si toccano SOLO dentro la cartella dell'utente (Desktop, Documenti, Download...).
"""
import os
import re
import sys
import time
import ctypes
import shutil
import functools
import datetime
import subprocess

IS_WIN = sys.platform == "win32"
NO_WIN = "Questa funzione è disponibile solo su Windows."

try:
    import psutil
except ImportError:
    psutil = None
if IS_WIN:
    try:
        import win32gui
        import win32con
        import win32clipboard
    except ImportError:
        win32gui = win32con = win32clipboard = None
else:
    win32gui = win32con = win32clipboard = None


# ----------------------------------------------------------------------------- tastiera / mouse (SendInput)
_VK = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "capslock": 0x14,
    "printscreen": 0x2C, "playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
}
for _i in range(1, 13):
    _VK[f"f{_i}"] = 0x6F + _i
_EXTENDED = {0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E, 0x5B}

_WORDS = {   # parole dette a voce -> nome del tasto
    "control": "ctrl", "controllo": "ctrl", "ctrl": "ctrl", "alt": "alt", "maiuscolo": "shift", "maiuscole": "shift",
    "shift": "shift", "windows": "win", "win": "win", "start": "win", "invio": "enter", "enter": "enter",
    "tab": "tab", "tabulazione": "tab", "escape": "esc", "esc": "esc", "spazio": "space", "backspace": "backspace",
    "cancella": "backspace", "canc": "delete", "elimina": "delete", "delete": "delete",
    "su": "up", "giù": "down", "sinistra": "left", "destra": "right", "freccia": None,
    "home": "home", "fine": "end", "end": "end", "pagina": None, "insert": "insert",
    "più": None, "piu": None, "e": None, "+": None, "il": None, "tasto": None, "tasti": None, "poi": None,
}


def _parse_combo(text: str):
    """'controllo c' | 'ctrl+shift+t' | 'alt tab' | 'freccia giù' -> ['ctrl','c'] ... oppure None se non capisco."""
    t = (text or "").lower().replace("+", " ").replace("-", " ")
    t = re.sub(r"[.,!?]", " ", t)
    words = t.split()
    keys, i = [], 0
    while i < len(words):
        w = words[i]
        if w == "freccia" and i + 1 < len(words):
            d = {"su": "up", "giù": "down", "giu": "down", "sinistra": "left", "destra": "right",
                 "alto": "up", "basso": "down"}.get(words[i + 1])
            if not d:
                return None
            keys.append(d)
            i += 2
            continue
        if w == "pagina" and i + 1 < len(words) and words[i + 1] in ("su", "giù", "giu"):
            keys.append("pageup" if words[i + 1] == "su" else "pagedown")
            i += 2
            continue
        if w in _WORDS:
            if _WORDS[w]:
                keys.append(_WORDS[w])
        elif re.fullmatch(r"f(?:[1-9]|1[0-2])", w):
            keys.append(w)
        elif len(w) == 1 and w.isalnum():
            keys.append(w)
        else:
            return None
        i += 1
    return keys or None


if IS_WIN:
    from ctypes import wintypes as _wt
    _user32 = ctypes.windll.user32
    _ULONG_PTR = ctypes.c_size_t

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", _wt.LONG), ("dy", _wt.LONG), ("mouseData", _wt.DWORD), ("dwFlags", _wt.DWORD),
                    ("time", _wt.DWORD), ("dwExtraInfo", _ULONG_PTR)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", _wt.WORD), ("wScan", _wt.WORD), ("dwFlags", _wt.DWORD), ("time", _wt.DWORD),
                    ("dwExtraInfo", _ULONG_PTR)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", _wt.DWORD), ("wParamL", _wt.WORD), ("wParamH", _wt.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", _wt.DWORD), ("u", _INPUTUNION)]

    def _send_key(vk=0, scan=0, flags=0):
        inp = _INPUT(type=1, u=_INPUTUNION(ki=_KEYBDINPUT(vk, scan, flags, 0, 0)))
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _vk_of(key: str) -> int:
        if key in _VK:
            return _VK[key]
        if len(key) == 1:
            return _user32.VkKeyScanW(ord(key)) & 0xFF
        raise ValueError(f"tasto sconosciuto: {key}")

    def _press(keys):
        vks = [_vk_of(k) for k in keys]
        for vk in vks:
            _send_key(vk, 0, 1 if vk in _EXTENDED else 0)
            time.sleep(0.02)
        for vk in reversed(vks):
            _send_key(vk, 0, (1 if vk in _EXTENDED else 0) | 2)
            time.sleep(0.02)

    def _type(text: str):
        for ch in text:
            if ch == "\n":
                _press(["enter"])
                continue
            data = ch.encode("utf-16-le")
            for j in range(0, len(data), 2):
                unit = int.from_bytes(data[j:j + 2], "little")
                _send_key(0, unit, 4)            # KEYEVENTF_UNICODE
                _send_key(0, unit, 4 | 2)
            time.sleep(0.008)

    def _mouse(flags: int, data: int = 0):
        _user32.mouse_event(flags, 0, 0, data, 0)
else:
    def _press(keys):
        raise OSError(NO_WIN)

    def _type(text):
        raise OSError(NO_WIN)

    def _mouse(flags, data=0):
        raise OSError(NO_WIN)


# ----------------------------------------------------------------------------- file: cartelle dell'utente
_HOME = os.path.expanduser("~")
_SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", "$recycle.bin", "venv", ".venv", "site-packages"}


def _known_dir(name: str):
    """'desktop' | 'documenti' | 'download' ... -> percorso reale (gestisce anche OneDrive)."""
    n = (name or "").lower().strip()
    table = {
        "desktop": ["Desktop"], "scrivania": ["Desktop"],
        "documenti": ["Documents", "Documenti"], "documents": ["Documents"],
        "download": ["Downloads", "Scaricati"], "scaricati": ["Downloads", "Scaricati"],
        "immagini": ["Pictures", "Immagini"], "foto": ["Pictures", "Immagini"],
        "musica": ["Music", "Musica"], "video": ["Videos", "Video"],
    }
    for sub in table.get(n, []):
        for base in (_HOME, os.path.join(_HOME, "OneDrive")):
            p = os.path.join(base, sub)
            if os.path.isdir(p):
                return p
    return None


def _search_roots():
    roots = []
    for n in ("desktop", "documenti", "download", "immagini", "musica", "video"):
        p = _known_dir(n)
        if p and p not in roots:
            roots.append(p)
    return roots


def _find(name: str, only_dirs=False, only_files=False, limit=6, seconds=5.0):
    """Cerca per nome (tutte le parole, senza estensione) nelle cartelle dell'utente. Migliori per primi."""
    words = [w for w in re.findall(r"\w+", (name or "").lower()) if len(w) > 1 or w.isdigit()]
    if not words:
        return []
    q = " ".join(words)
    hits, deadline = [], time.time() + seconds
    for root in _search_roots():
        base_depth = root.rstrip(os.sep).count(os.sep)
        for cur, dirs, files in os.walk(root):
            if time.time() > deadline:
                break
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            if cur.count(os.sep) - base_depth >= 4:
                dirs[:] = []
            entries = ([] if only_files else [(d, True) for d in dirs]) + ([] if only_dirs else [(f, False) for f in files])
            for entry, is_dir in entries:
                stem = os.path.splitext(entry)[0].lower() if not is_dir else entry.lower()
                stem_words = " ".join(re.findall(r"\w+", stem))
                if all(w in stem_words for w in words):
                    score = 0 if stem_words == q else (1 if stem_words.startswith(q) else 2)
                    hits.append((score, len(stem_words), os.path.join(cur, entry)))
    hits.sort()
    return [h[2] for h in hits[:limit]]


def _inside_home(path: str) -> bool:
    p = os.path.realpath(path)
    home = os.path.realpath(_HOME)
    return p.startswith(home + os.sep) and p != home


def _is_protected_dir(path: str) -> bool:
    p = os.path.realpath(path)
    return p in {os.path.realpath(d) for d in _search_roots()} or p == os.path.realpath(_HOME)


def _short(path: str) -> str:
    return os.path.basename(path.rstrip("\\/")) or path


def _win_only(fn):
    @functools.wraps(fn)                          # mantiene nome, docstring e firma (serve al catalogo degli strumenti)
    def wrapper(self, *a, **k):
        if not IS_WIN:
            return NO_WIN
        return fn(self, *a, **k)
    return wrapper


def _powershell(cmd: str, timeout=15) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                         capture_output=True, text=True, timeout=timeout,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout or "errore").strip().splitlines()[-1][:160])
    return out.stdout.strip()


# ----------------------------------------------------------------------------- il modulo
class PcTools:
    # azioni che il brain esegue SOLO dopo conferma a voce ({0} = primo argomento)
    CONFIRM = {
        "shutdown_pc": "spegnere il computer",
        "restart_pc": "riavviare il computer",
        "sleep_pc": "mettere il computer in sospensione",
        "sign_out": "chiudere la sessione",
        "empty_recycle_bin": "svuotare il cestino",
        "delete_path": "spostare nel cestino «{0}»",
    }

    # ---------------- media ----------------
    @_win_only
    def media_play_pause(self) -> str:
        """Play o pausa della musica o del video in riproduzione."""
        _press(["playpause"])
        return "Fatto."

    @_win_only
    def media_next(self) -> str:
        """Passa al brano successivo."""
        _press(["next"])
        return "Brano successivo."

    @_win_only
    def media_previous(self) -> str:
        """Torna al brano precedente."""
        _press(["prev"])
        return "Brano precedente."

    # ---------------- finestre ----------------
    def _windows(self):
        out = []

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                # GW_OWNER == 0: solo finestre principali, non le finestrelle di dialogo
                if title and title != "Program Manager" and win32gui.GetWindow(hwnd, 4) == 0:
                    out.append((hwnd, title))
        win32gui.EnumWindows(cb, None)
        return out

    @_win_only
    def list_windows(self) -> str:
        """Elenca le finestre aperte."""
        if win32gui is None:
            return "Mi manca pywin32 per vedere le finestre."
        titles = [t for _, t in self._windows()]
        if not titles:
            return "Non vedo finestre aperte."
        short = [t if len(t) < 40 else t[:37] + "..." for t in titles[:8]]
        return f"Hai {len(titles)} finestre aperte. Le principali: " + "; ".join(short) + "."

    @_win_only
    def get_active_window(self) -> str:
        """Dice quale finestra è in primo piano."""
        if win32gui is None:
            return "Mi manca pywin32 per vedere le finestre."
        title = win32gui.GetWindowText(win32gui.GetForegroundWindow()).strip()
        return f"In primo piano c'è: {title}." if title else "Non c'è nessuna finestra in primo piano."

    @_win_only
    def focus_window(self, name: str) -> str:
        """Porta in primo piano la finestra il cui titolo contiene il nome dato."""
        if win32gui is None:
            return "Mi manca pywin32 per gestire le finestre."
        q = (name or "").lower().strip()
        if not q:
            return "Quale finestra devo portare in primo piano?"
        for hwnd, title in self._windows():
            if q in title.lower():
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                _send_key(_VK["alt"], 0, 0)                  # trucco: permette a Windows di cambiare il primo piano
                _send_key(_VK["alt"], 0, 2)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    return f"Ho trovato {title} ma Windows non mi lascia metterla in primo piano."
                return f"Ecco {title if len(title) < 40 else name}."
        return f"Non trovo nessuna finestra chiamata {name}."

    @_win_only
    def minimize_window(self) -> str:
        """Minimizza la finestra attiva."""
        win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_MINIMIZE)
        return "Fatto."

    @_win_only
    def maximize_window(self) -> str:
        """Ingrandisce la finestra attiva a tutto schermo."""
        win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_MAXIMIZE)
        return "Fatto."

    @_win_only
    def restore_window(self) -> str:
        """Riporta la finestra attiva alle dimensioni normali."""
        win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_RESTORE)
        return "Fatto."

    @_win_only
    def close_window(self) -> str:
        """Chiude la finestra attiva (come la X in alto a destra)."""
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        if not title or title == "Program Manager":
            return "Non c'è una finestra da chiudere."
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return "Chiusa."

    @_win_only
    def switch_window(self) -> str:
        """Passa alla finestra successiva (Alt+Tab)."""
        _press(["alt", "tab"])
        return "Fatto."

    @_win_only
    def show_desktop(self) -> str:
        """Minimizza tutto e mostra il desktop."""
        _press(["win", "d"])
        return "Ecco il desktop."

    @_win_only
    def snap_window(self, side: str) -> str:
        """Aggancia la finestra attiva a sinistra o a destra dello schermo."""
        s = (side or "").lower()
        if s.startswith("sin"):
            _press(["win", "left"])
        elif s.startswith("des"):
            _press(["win", "right"])
        else:
            return "Dimmi se a sinistra o a destra."
        return "Fatto."

    # ---------------- tastiera ----------------
    @_win_only
    def type_text(self, text: str) -> str:
        """Scrive il testo dato nella finestra attiva, come se lo digitassi."""
        text = (text or "")[:1000]
        if not text.strip():
            return "Cosa devo scrivere?"
        time.sleep(0.3)
        _type(text)
        return "Scritto."

    @_win_only
    def press_keys(self, keys: str) -> str:
        """Preme un tasto o una combinazione, per esempio invio, escape, controllo c, alt tab."""
        parsed = _parse_combo(keys)
        if not parsed:
            return f"Non conosco il tasto {keys}."
        try:
            _press(parsed)
        except ValueError as e:
            return str(e)
        return "Fatto."

    @_win_only
    def shortcut(self, action: str) -> str:
        """Scorciatoie comuni: copia, incolla, taglia, seleziona tutto, salva, annulla, ripeti."""
        table = {"copia": ["ctrl", "c"], "incolla": ["ctrl", "v"], "taglia": ["ctrl", "x"],
                 "seleziona tutto": ["ctrl", "a"], "salva": ["ctrl", "s"], "annulla": ["ctrl", "z"],
                 "ripeti": ["ctrl", "y"], "trova": ["ctrl", "f"], "stampa": ["ctrl", "p"]}
        keys = table.get((action or "").lower().strip())
        if not keys:
            return f"Non conosco l'azione {action}."
        _press(keys)
        return "Fatto."

    # ---------------- mouse ----------------
    @_win_only
    def click(self) -> str:
        """Clic sinistro dove si trova il puntatore."""
        _mouse(0x0002)
        _mouse(0x0004)
        return "Clic."

    @_win_only
    def double_click(self) -> str:
        """Doppio clic dove si trova il puntatore."""
        for _ in range(2):
            _mouse(0x0002)
            _mouse(0x0004)
            time.sleep(0.05)
        return "Doppio clic."

    @_win_only
    def right_click(self) -> str:
        """Clic destro dove si trova il puntatore."""
        _mouse(0x0008)
        _mouse(0x0010)
        return "Clic destro."

    @_win_only
    def scroll(self, direction: str, amount: str = "") -> str:
        """Scorre la pagina verso l'alto o verso il basso."""
        d = (direction or "").lower()
        up = any(w in d for w in ("su", "alto"))
        a = str(amount or "").lower()
        notches = int(a) if a.isdigit() else {"poco": 2, "un po'": 3, "molto": 12, "tanto": 12}.get(a, 5)
        notches = max(1, min(notches, 40))
        _mouse(0x0800, (120 if up else -120) * notches & 0xFFFFFFFF)
        return "Fatto."

    @_win_only
    def move_mouse(self, where: str) -> str:
        """Sposta il puntatore: su, giù, sinistra, destra (con i pixel), oppure al centro o in un angolo."""
        w = (where or "").lower()
        sw, sh = _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
        pt = _wt.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        n = re.search(r"\d+", w)
        step = int(n.group()) if n else 200
        if "centro" in w:
            x, y = sw // 2, sh // 2
        elif "angolo" in w or (("alto" in w or "basso" in w) and ("sinistra" in w or "destra" in w)):
            x = 5 if "sinistra" in w else sw - 5
            y = 5 if "alto" in w else sh - 5
        elif "sinistra" in w:
            x, y = pt.x - step, pt.y
        elif "destra" in w:
            x, y = pt.x + step, pt.y
        elif re.search(r"\b(su|alto)\b", w):
            x, y = pt.x, pt.y - step
        elif re.search(r"\b(giù|giu|basso)\b", w):
            x, y = pt.x, pt.y + step
        else:
            return "Dimmi dove: su, giù, sinistra, destra o centro."
        _user32.SetCursorPos(max(0, min(sw - 1, x)), max(0, min(sh - 1, y)))
        return "Fatto."

    # ---------------- schermo, appunti ----------------
    @_win_only
    def take_screenshot(self) -> str:
        """Fa uno screenshot di tutto lo schermo e lo salva nella cartella Immagini."""
        folder = os.path.join(_known_dir("immagini") or _HOME, "Jarvis")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
        try:
            from PIL import ImageGrab
            ImageGrab.grab(all_screens=True).save(path)
        except ImportError:
            _press(["win", "printscreen"])
            return "Ho fatto lo screenshot: lo trovi in Immagini, Schermate. Per salvarlo nella cartella Jarvis installa pillow."
        return "Screenshot fatto: lo trovo nella cartella Immagini, sotto Jarvis."

    @_win_only
    def read_clipboard(self) -> str:
        """Legge ad alta voce il testo copiato negli appunti."""
        if win32clipboard is None:
            return "Mi manca pywin32 per leggere gli appunti."
        try:
            win32clipboard.OpenClipboard()
            try:
                text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            return "Negli appunti non c'è del testo."
        text = (text or "").strip()
        if not text:
            return "Gli appunti sono vuoti."
        return "Negli appunti c'è: " + (text if len(text) <= 300 else text[:300] + "...")

    @_win_only
    def copy_to_clipboard(self, text: str) -> str:
        """Mette il testo dato negli appunti."""
        if win32clipboard is None:
            return "Mi manca pywin32 per scrivere negli appunti."
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text))
        finally:
            win32clipboard.CloseClipboard()
        return "Copiato negli appunti."

    @_win_only
    def set_brightness(self, level: int) -> str:
        """Imposta la luminosità dello schermo da 0 a 100 (portatili e schermi integrati)."""
        level = max(0, min(100, int(level)))
        try:
            _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                        f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={level}}}")
        except Exception:
            return "Non riesco a regolare la luminosità: di solito funziona solo sugli schermi dei portatili."
        return f"Luminosità al {level} per cento."

    @_win_only
    def change_brightness(self, delta: int) -> str:
        """Alza o abbassa la luminosità dello schermo di una certa quantità."""
        try:
            cur = int(_powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"))
        except Exception:
            return "Non riesco a leggere la luminosità: di solito funziona solo sugli schermi dei portatili."
        return self.set_brightness(cur + int(delta))

    # ---------------- energia e sessione ----------------
    @_win_only
    def lock_pc(self) -> str:
        """Blocca il computer (schermata di accesso)."""
        _user32.LockWorkStation()
        return "Computer bloccato."

    @_win_only
    def sleep_pc(self) -> str:
        """Mette il computer in sospensione."""
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Vado in sospensione."

    @_win_only
    def shutdown_pc(self) -> str:
        """Spegne il computer tra 30 secondi (si può annullare)."""
        subprocess.run(["shutdown", "/s", "/t", "30"], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Spengo il computer tra trenta secondi. Dì annulla spegnimento per fermarmi."

    @_win_only
    def restart_pc(self) -> str:
        """Riavvia il computer tra 30 secondi (si può annullare)."""
        subprocess.run(["shutdown", "/r", "/t", "30"], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Riavvio tra trenta secondi. Dì annulla spegnimento per fermarmi."

    @_win_only
    def cancel_shutdown(self) -> str:
        """Annulla uno spegnimento o riavvio programmato."""
        r = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Spegnimento annullato." if r.returncode == 0 else "Non c'era nessuno spegnimento in programma."

    @_win_only
    def sign_out(self) -> str:
        """Chiude la sessione dell'utente."""
        subprocess.run(["shutdown", "/l"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Chiudo la sessione."

    @_win_only
    def empty_recycle_bin(self) -> str:
        """Svuota il cestino."""
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
        return "Cestino svuotato." if res in (0, -2147418113) else "Il cestino era già vuoto."

    # ---------------- sistema ----------------
    def battery_status(self) -> str:
        """Livello della batteria e se è in carica."""
        b = psutil.sensors_battery() if psutil and hasattr(psutil, "sensors_battery") else None
        if b is None:
            return "Non rilevo una batteria: forse è un computer fisso."
        return f"Batteria al {int(b.percent)} per cento, {'in carica' if b.power_plugged else 'a batteria'}."

    def disk_space(self, drive: str = "C") -> str:
        """Spazio libero e totale su un disco."""
        d = (drive or "C").strip(" :\\/").upper()[:1] or "C"
        path = f"{d}:\\" if IS_WIN else "/"
        try:
            u = shutil.disk_usage(path)
        except Exception:
            return f"Non riesco a leggere il disco {d}."
        gb = 1024 ** 3
        return f"Sul disco {d} hai {u.free // gb} giga liberi su {u.total // gb}."

    @_win_only
    def open_settings(self, page: str = "") -> str:
        """Apre le Impostazioni di Windows, anche su una pagina: wifi, bluetooth, schermo, audio, aggiornamenti, app, batteria."""
        pages = {"wifi": "network-wifi", "wi-fi": "network-wifi", "rete": "network", "internet": "network",
                 "bluetooth": "bluetooth", "schermo": "display", "display": "display", "audio": "sound",
                 "suono": "sound", "aggiornamenti": "windowsupdate", "windows update": "windowsupdate",
                 "app": "appsfeatures", "applicazioni": "appsfeatures", "batteria": "batterysaver",
                 "notifiche": "notifications", "privacy": "privacy", "account": "yourinfo",
                 "personalizzazione": "personalization", "sfondo": "personalization-background",
                 "stampanti": "printers", "mouse": "mousetouchpad", "tastiera": "easeofaccess-keyboard"}
        key = (page or "").lower().strip()
        uri = pages.get(key)
        os.startfile("ms-settings:" + uri if uri else "ms-settings:")
        return "Apro le impostazioni." if not uri else f"Apro le impostazioni di {page}."

    @_win_only
    def open_system_tool(self, name: str) -> str:
        """Apre strumenti di Windows: gestione attività, pannello di controllo, esplora file, calcolatrice, blocco note, terminale, cestino."""
        n = (name or "").lower().strip()
        cmds = {
            "gestione attività": ["taskmgr"], "gestione attivita": ["taskmgr"], "task manager": ["taskmgr"],
            "pannello di controllo": ["control"], "esplora risorse": ["explorer"], "esplora file": ["explorer"],
            "calcolatrice": ["calc"], "blocco note": ["notepad"], "prompt dei comandi": ["cmd"],
            "terminale": ["wt"], "powershell": ["powershell"], "cestino": ["explorer", "shell:RecycleBinFolder"],
        }
        cmd = cmds.get(n)
        if not cmd:
            return f"Non so aprire {name}."
        try:
            subprocess.Popen(["cmd", "/c", "start", "", *cmd], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            return f"Non riesco ad aprire {name}: {e}"
        return f"Apro {name}."

    # ---------------- file e cartelle (solo nella cartella dell'utente) ----------------
    def find_file(self, name: str) -> str:
        """Cerca un file o una cartella per nome in Desktop, Documenti, Download, Immagini, Musica e Video."""
        hits = _find(name, limit=4)
        if not hits:
            return f"Non trovo niente che si chiami {name}."
        if len(hits) == 1:
            return f"Ho trovato {_short(hits[0])}, nella cartella {_short(os.path.dirname(hits[0]))}."
        names = ", ".join(_short(h) for h in hits[:3])
        return f"Ne ho trovati {len(hits)}. I migliori: {names}."

    @_win_only
    def open_file(self, name: str) -> str:
        """Cerca un file per nome e lo apre con il programma predefinito."""
        hits = _find(name, only_files=True, limit=3)
        if not hits:
            return f"Non trovo nessun file che si chiami {name}."
        os.startfile(hits[0])
        return f"Apro {_short(hits[0])}."

    @_win_only
    def open_folder(self, name: str) -> str:
        """Apre una cartella: Desktop, Documenti, Download, Immagini, Musica, Video, oppure una cercata per nome."""
        path = _known_dir(name)
        if not path:
            hits = _find(name, only_dirs=True, limit=1)
            path = hits[0] if hits else None
        if not path:
            return f"Non trovo la cartella {name}."
        os.startfile(path)
        return f"Apro la cartella {_short(path)}."

    def list_folder(self, name: str = "desktop") -> str:
        """Elenca i primi elementi di una cartella (Desktop, Documenti, Download...)."""
        path = _known_dir(name) or (_find(name, only_dirs=True, limit=1) or [None])[0]
        if not path:
            return f"Non trovo la cartella {name}."
        items = sorted(os.listdir(path))
        items = [i for i in items if not i.startswith(".") and i.lower() != "desktop.ini"]
        if not items:
            return f"La cartella {_short(path)} è vuota."
        return f"In {_short(path)} ci sono {len(items)} elementi. Per esempio: " + ", ".join(items[:6]) + "."

    def create_folder(self, name: str, location: str = "desktop") -> str:
        """Crea una nuova cartella sul Desktop o in Documenti, Download, Immagini."""
        clean = re.sub(r'[<>:"/\\|?*]', "", str(name or "")).strip(" .")
        if not clean:
            return "Come devo chiamare la cartella?"
        base = _known_dir(location or "desktop") or _known_dir("desktop")
        if not base:
            return "Non trovo la cartella dove crearla."
        path = os.path.join(base, clean)
        if os.path.exists(path):
            return f"Esiste già una cartella {clean}."
        os.makedirs(path)
        return f"Creata la cartella {clean} in {_short(base)}."

    def delete_path(self, name: str) -> str:
        """Sposta nel cestino un file o una cartella cercata per nome (recuperabile)."""
        hits = _find(name, limit=4)
        if not hits:
            return f"Non trovo niente che si chiami {name}."
        exact = [h for h in hits if re.sub(r"\W+", " ", os.path.splitext(_short(h))[0].lower()).strip() ==
                 re.sub(r"\W+", " ", str(name).lower()).strip()]
        if len(exact) == 1:
            target = exact[0]
        elif len(hits) == 1:
            target = hits[0]
        else:
            return f"Ne ho trovati più di uno, tipo {', '.join(_short(h) for h in hits[:3])}. Dimmi il nome preciso."
        if not _inside_home(target) or _is_protected_dir(target):
            return "Questa cartella non la tocco."
        try:
            from send2trash import send2trash
        except ImportError:
            return "Per spostare nel cestino installa send2trash: pip install send2trash."
        send2trash(target)
        return f"Spostato nel cestino: {_short(target)}."
