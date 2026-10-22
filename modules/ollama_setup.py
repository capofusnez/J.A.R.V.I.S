import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import collections
import requests

OLLAMA_URL = "http://localhost:11434/"
INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Opzioni standard degli installer Inno Setup (quello di Ollama): nessuna finestra, nessun riavvio
SILENT_ARGS = ["/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]


# ---------------- formattazione ----------------
def fmt_size(n: float) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB".replace(".", ",")
    return f"{n / 1e6:.0f} MB"


def fmt_speed(bps: float) -> str:
    return f"{bps / 1e6:.1f} MB/s".replace(".", ",")


def fmt_eta(seconds: float) -> str:
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600} h {(s % 3600) // 60:02d} min"
    if s >= 60:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s} s"


def approx_model_size(name: str) -> str:
    """Stima del peso del download dal numero di parametri nel nome (es. 14b ≈ 9 GB a 4 bit)."""
    m = re.search(r"(\d+(?:\.\d+)?)b\b", name.lower())
    if m:
        return f"circa {max(1, round(float(m.group(1)) * 0.65))} GB"
    return "alcuni GB"


class _Rate:
    """Velocità media sugli ultimi secondi (più stabile di quella istantanea)."""

    def __init__(self, window: float = 6.0):
        self.window = window
        self.samples = collections.deque()

    def update(self, done: float):
        now = time.time()
        self.samples.append((now, done))
        while len(self.samples) > 1 and now - self.samples[0][0] > self.window:
            self.samples.popleft()

    def speed(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        (t0, d0), (t1, d1) = self.samples[0], self.samples[-1]
        return (d1 - d0) / (t1 - t0) if t1 > t0 else 0.0


class OllamaSetup:
    """Controlla Ollama all'avvio: se manca lo scarica dal sito ufficiale e lo installa (chiedendo il permesso),
    avvia il servizio e scarica il modello se non presente.

    status(testo)      -> testo della splash (può avere più righe)
    ask(titolo, testo) -> True/False: chiede conferma all'utente (mostrata sul thread della GUI)
    progress(v)        -> barra di avanzamento: float 0..1 = percentuale, None = attività senza percentuale
                          (barra animata), False = nascondi la barra
    """

    def __init__(self, model_name, status, ask, progress=None, base_url=OLLAMA_URL, installer_url=INSTALLER_URL):
        self.model_name = model_name
        self.status = status
        self.ask = ask
        self.progress = progress
        self.base_url = base_url
        self.installer_url = installer_url
        self._last_report = 0.0
        self.last_error = None          # ultimo errore reale (non il semplice rifiuto dell'utente)

    # ---------------- progresso ----------------
    def _prog(self, v):
        if self.progress:
            try:
                self.progress(v)
            except Exception:
                pass

    def _report(self, label: str, done: float, total: float, rate: _Rate, force: bool = False):
        now = time.time()
        if not force and now - self._last_report < 0.3:
            return
        self._last_report = now
        speed = rate.speed()
        speed_txt = f" · {fmt_speed(speed)}" if speed > 0 else " · in attesa di dati..."
        if total:
            frac = min(done / total, 1.0)
            eta = f" · mancano {fmt_eta((total - done) / speed)}" if speed > 0 and done < total else ""
            self.status(f"{label} — {frac * 100:.0f}%\n{fmt_size(done)} / {fmt_size(total)}{speed_txt}{eta}")
            self._prog(frac)
        else:
            self.status(f"{label} — scaricamento in corso\n{fmt_size(done)} scaricati{speed_txt}")
            self._prog(None)                      # dimensione totale sconosciuta: barra animata

    # ---------------- server ----------------
    def server_up(self) -> bool:
        try:
            return requests.get(self.base_url, timeout=1.5).status_code == 200
        except Exception:
            return False

    def wait_for_server(self, timeout: float, label: str = "In attesa del servizio Ollama") -> bool:
        t0 = time.time()
        self._prog(None)
        while True:
            if self.server_up():
                return True
            elapsed = time.time() - t0
            if elapsed >= timeout:
                return False
            self.status(f"[WAIT] {label}...\nTempo trascorso: {int(elapsed)} s")
            time.sleep(0.5)

    @staticmethod
    def find_binary():
        path = shutil.which("ollama")
        if path:
            return path
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def _wait_binary(self, timeout: float, label: str):
        t0 = time.time()
        self._prog(None)
        while True:
            b = self.find_binary()
            if b:
                return b
            elapsed = time.time() - t0
            if elapsed >= timeout:
                return None
            self.status(f"{label}\nTempo trascorso: {int(elapsed)} s")
            time.sleep(1.0)

    def start_server(self, binary: str):
        self.status("[EXEC] Avvio del demone Ollama in background...")
        try:
            subprocess.Popen([binary, "serve"], creationflags=NO_WINDOW)
        except Exception as e:
            self.status(f"[ERROR] Impossibile avviare Ollama: {e}")

    # ---------------- installazione ----------------
    def _download(self):
        dest = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        part = dest + ".part"
        self.status("[DOWNLOAD] Connessione a ollama.com...")
        self._prog(None)
        try:
            rate = _Rate()
            with requests.get(self.installer_url, stream=True, timeout=(10, 60), allow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                with open(part, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            rate.update(done)
                            self._report("[DOWNLOAD] Installer Ollama", done, total, rate)
                self._report("[DOWNLOAD] Installer Ollama", done, total, rate, force=True)
            if total and os.path.getsize(part) != total:
                raise IOError("download incompleto")
            with open(part, "rb") as f:
                if f.read(2) != b"MZ":                        # deve essere un eseguibile, non una pagina di errore
                    raise IOError("il file scaricato non è un eseguibile valido")
            os.replace(part, dest)
            return dest
        except Exception as e:
            self.last_error = f"Download dell'installer non riuscito: {e}"
            self.status(f"[ERROR] {self.last_error}")
            try:
                os.remove(part)
            except OSError:
                pass
            return None

    def _run_installer_silent(self, path: str) -> bool:
        t0 = time.time()
        self._prog(None)
        try:
            proc = subprocess.Popen([path] + SILENT_ARGS, creationflags=NO_WINDOW)
            while proc.poll() is None:
                elapsed = time.time() - t0
                if elapsed > 900:
                    proc.kill()
                    return False
                self.status(f"[INSTALL] Installazione di Ollama in corso...\nTempo trascorso: {int(elapsed)} s")
                time.sleep(0.5)
            return proc.returncode == 0
        except Exception as e:
            self.status(f"[WARN] Installazione silenziosa fallita: {e}")
            return False

    def _install(self):
        """Ritorna il percorso di ollama.exe dopo l'installazione, oppure None."""
        if not self.ask(
            "Ollama non trovato",
            "Jarvis ha bisogno di Ollama per ragionare, ma non è installato.\n\n"
            "Vuoi scaricarlo da ollama.com (sito ufficiale) e installarlo ora?\n"
            "Serve internet e circa 4 GB liberi. Non richiede permessi di amministratore.",
        ):
            self.status("[INFO] Installazione rifiutata: Jarvis si avvia senza cervello neurale.")
            return None

        path = self._download()
        if not path:
            return None

        self._run_installer_silent(path)
        binary = self._wait_binary(20, "[INSTALL] Verifica dell'installazione...")
        if not binary:                                          # ripiego: installer normale con procedura guidata
            opener = getattr(os, "startfile", None)
            if opener:
                try:
                    opener(path)
                    binary = self._wait_binary(300, "[INSTALL] Completa la procedura guidata di Ollama...")
                except Exception as e:
                    self.status(f"[ERROR] Impossibile aprire l'installer: {e}")
        try:
            os.remove(path)
        except OSError:
            pass
        if binary:
            self.status("[OK] Ollama installato.")
        else:
            self.last_error = "L'installazione di Ollama non è stata completata."
            self.status(f"[ERROR] {self.last_error}")
        return binary

    # ---------------- modello ----------------
    def model_installed(self) -> bool:
        r = requests.get(self.base_url + "api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return any(n == self.model_name or n.startswith(self.model_name + ":") for n in names)

    def _wait_model_installed(self, timeout: float) -> bool:
        """Controlla più volte per qualche secondo: il registro dei modelli può aggiornarsi con un attimo di ritardo."""
        t0 = time.time()
        while True:
            try:
                if self.model_installed():
                    return True
            except Exception:
                pass
            if time.time() - t0 >= timeout:
                return False
            time.sleep(0.5)

    def _pull_model(self) -> bool:
        label = f"[MODEL] Scarico {self.model_name}"
        self.status(f"{label}...\nPreparazione del download")
        self._prog(None)
        layers = {}                                             # digest -> (totale, scaricato)
        main_key, rate = None, _Rate(window=8.0)
        got_success = False
        try:
            with requests.post(self.base_url + "api/pull",
                               json={"model": self.model_name, "name": self.model_name, "stream": True},
                               stream=True, timeout=(10, 120)) as r:
                r.raise_for_status()
                for line in r.iter_lines(chunk_size=1):                  # riga per riga: niente aggiornamenti a scatti
                    if not line:
                        continue
                    d = json.loads(line)
                    if d.get("error"):
                        raise RuntimeError(d["error"])
                    if d.get("total") and d.get("completed") is not None:
                        layers[d.get("digest") or d.get("status", "")] = (d["total"], d["completed"])
                        # progresso = livello più grande (i pesi del modello): i file piccoli non contano
                        key = max(layers, key=lambda k: layers[k][0])
                        total, done = layers[key]
                        if key != main_key:
                            main_key, rate = key, _Rate(window=8.0)
                        if total >= 50_000_000:
                            rate.update(done)
                            self._report(label, done, total, rate, force=done >= total)
                        else:
                            self._prog(None)
                    elif d.get("status") and d["status"] != "success":
                        self.status(f"[MODEL] {d['status']}...")
                        self._prog(None)
                    if d.get("status") == "success":
                        got_success = True
                        break
            # controllo finale: il modello deve davvero risultare installato
            if not self._wait_model_installed(4):
                raise RuntimeError("il download si è interrotto prima della fine" if not got_success
                                   else "il modello non risulta installato")
            self.status(f"[OK] Modello {self.model_name} pronto.")
            return True
        except Exception as e:
            self.last_error = f"Download del modello non riuscito: {e}"
            self.status(f"[ERROR] {self.last_error}")
            return False

    def _ensure_model(self) -> bool:
        try:
            if self.model_installed():
                self.status(f"[OK] Modello {self.model_name} presente.")
                return True
        except Exception as e:
            self.status(f"[WARN] Impossibile verificare i modelli: {e}")
            return True
        if not self.ask(
            "Modello mancante",
            f"Il modello '{self.model_name}' non è ancora scaricato ({approx_model_size(self.model_name)}).\n\n"
            "Vuoi scaricarlo ora?\n"
            "Il download può richiedere diversi minuti: Jarvis si aprirà quando ha finito e puoi "
            "seguire l'avanzamento nella schermata di avvio. Senza il modello Jarvis non può rispondere.",
        ):
            self.status("[INFO] Modello non scaricato: Jarvis non potrà rispondere.")
            return False
        self.status(f"[MODEL] Confermato. Avvio il download di {self.model_name}...")
        return self._pull_model()

    # ---------------- sequenza completa ----------------
    def ensure(self) -> bool:
        """Porta Ollama e il modello in stato pronto. True se tutto è a posto."""
        self.last_error = None
        try:
            self.status("[NETWORK] Interrogazione demone Ollama (Porta 11434)...")
            if self.server_up():
                self.status("[OK] Canale neurale Ollama stabilito con successo.")
            else:
                binary = self.find_binary()
                if not binary:
                    self.status("[WARN] Ollama non è installato su questo computer.")
                    binary = self._install()
                    if not binary:
                        return False
                    self.wait_for_server(15)                    # l'installer di solito avvia già il servizio
                if not self.server_up():
                    self.start_server(binary)
                    self.wait_for_server(25)
                if not self.server_up():
                    self.last_error = "Il servizio Ollama non risponde."
                    self.status(f"[ERROR] {self.last_error}")
                    return False
                self.status("[OK] Servizio Ollama avviato e operativo.")
            return self._ensure_model()
        finally:
            self._prog(False)                                   # nasconde sempre la barra a fine sequenza
