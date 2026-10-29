"""Voce di Jarvis: più motori intercambiabili, con la voce di Windows come ripiego sicuro.

Voci disponibili (nome breve -> motore):
  elsa, windows   SAPI di Windows      offline, già installata
  diego, giuseppe, isabella
                  Microsoft Edge       neurali, molto naturali, richiedono internet
                                       (pip install edge-tts miniaudio)
  nicola, sara    Kokoro               neurali, OFFLINE, le più naturali (pip install kokoro-onnx);
                                       la prima volta scarica ~90 MB in voices/, poi non serve più internet
  nicola-hd, sara-hd                   come sopra ma qualità massima (~310 MB)
  paola, riccardo Piper                neurali, offline  (pip install piper-tts; la voce si scarica da sola)

Si sceglie con:  la variabile JARVIS_VOICE, il file voice.json, il comando "cambia voce" / "usa la voce di Diego",
oppure con lo script provavoce.py. Se un motore fallisce (es. niente internet) la frase viene letta
comunque con la voce di Windows.
"""
import os
import re
import sys
import json
import time
import queue
import asyncio
import logging
import threading
import subprocess

import numpy as np

try:
    import requests
except ImportError:
    requests = None

try:
    import pythoncom
except ImportError:
    pythoncom = None
try:
    import win32com.client
    SAPI_OK = True
except ImportError:
    SAPI_OK = False
try:
    import sounddevice as sd
except Exception:                       # PortAudio mancante ecc.
    sd = None

from modules.paths import APP_DIR as ROOT, DATA_DIR, VOICES_DIR      # tutto accanto a Jarvis.exe

CONFIG_PATH = os.path.join(DATA_DIR, "voice.json")
DEFAULT_VOICE = "elsa"

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_MODELS = {"int8": "kokoro-v1.0.int8.onnx", "f32": "kokoro-v1.0.onnx"}
KOKORO_VOICES = "voices-v1.0.bin"

PRESETS = {
    "elsa": {"engine": "sapi", "name": "Elsa", "desc": "voce di Windows, offline"},
    "diego": {"engine": "edge", "name": "it-IT-DiegoNeural", "desc": "neurale maschile, online"},
    "giuseppe": {"engine": "edge", "name": "it-IT-GiuseppeMultilingualNeural", "desc": "neurale maschile, online"},
    "isabella": {"engine": "edge", "name": "it-IT-IsabellaNeural", "desc": "neurale femminile, online"},
    "nicola": {"engine": "kokoro", "name": "im_nicola@int8", "desc": "neurale maschile, offline dopo il primo download"},
    "sara": {"engine": "kokoro", "name": "if_sara@int8", "desc": "neurale femminile, offline dopo il primo download"},
    "nicola-hd": {"engine": "kokoro", "name": "im_nicola@f32", "desc": "neurale maschile, offline, qualità massima"},
    "sara-hd": {"engine": "kokoro", "name": "if_sara@f32", "desc": "neurale femminile, offline, qualità massima"},
    "paola": {"engine": "piper", "name": "it_IT-paola-medium", "desc": "neurale femminile, offline"},
    "riccardo": {"engine": "piper", "name": "it_IT-riccardo-x_low", "desc": "neurale maschile, offline, qualità bassa"},
}
ALIASES = {"windows": {"engine": "sapi", "name": "", "desc": "voce predefinita di Windows"}}


class EngineUnavailable(Exception):
    """Il motore non è utilizzabile (libreria mancante, ecc.): il messaggio è pensato per l'utente."""


class NeedsDownload(Exception):
    """I file della voce (Piper o Kokoro) non sono ancora stati scaricati."""


def resolve_voice(spec: str):
    """'diego' | 'edge:it-IT-DiegoNeural' | 'piper:nome' | 'sapi:Cosimo' -> (chiave, motore, nome) oppure None."""
    s = (spec or "").strip()
    low = s.lower()
    if low in PRESETS:
        return low, PRESETS[low]["engine"], PRESETS[low]["name"]
    if low in ALIASES:
        return low, ALIASES[low]["engine"], ALIASES[low]["name"]
    if ":" in s:
        eng, name = s.split(":", 1)
        if eng.strip().lower() in ("sapi", "edge", "piper", "kokoro") and name.strip():
            return s, eng.strip().lower(), name.strip()
    return None


def _split_kokoro(name: str):
    """'im_nicola@int8' -> ('im_nicola', 'int8')."""
    voice, _, prec = name.partition("@")
    return voice, (prec if prec in KOKORO_MODELS else "int8")


def voice_files(engine: str, name: str):
    """File necessari a una voce offline: [(percorso, url o None)]."""
    if engine == "piper":
        return [(os.path.join(VOICES_DIR, name + ".onnx"), None)]
    if engine == "kokoro":
        _, prec = _split_kokoro(name)
        return [(os.path.join(VOICES_DIR, KOKORO_MODELS[prec]), KOKORO_BASE + KOKORO_MODELS[prec]),
                (os.path.join(VOICES_DIR, KOKORO_VOICES), KOKORO_BASE + KOKORO_VOICES)]
    return []


def download_file(url: str, dest: str, progress=None, timeout=30):
    """Scarica in dest.part e rinomina solo a download completo (niente file a metà)."""
    if requests is None:
        raise EngineUnavailable("Per scaricare le voci installa: pip install requests")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                if chunk:
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, total)
    if total and os.path.getsize(part) != total:
        os.remove(part)
        raise IOError("download incompleto")
    os.replace(part, dest)


def clean_for_speech(text: str) -> str:
    """Rende il testo adatto alla lettura: niente link, simboli o emoji letti male."""
    t = re.sub(r"https?://\S+", "link", text or "")
    t = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]", "", t)
    t = t.replace("%", " per cento").replace("€", " euro").replace("&", " e ").replace("°C", " gradi")
    t = re.sub(r"[*_#`>~|]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


# ----------------------------------------------------------------------------- motori
class SapiEngine:
    """Voce di Windows (SAPI). Va usata solo dal thread di riproduzione (COM ha affinità di thread)."""
    kind = "direct"

    def __init__(self, hint: str = "", rate: int = 1, volume: int = 100):
        self.hint, self.rate, self.volume = (hint or "").lower(), rate, volume
        self._voice = None

    def _create(self):
        if not SAPI_OK:
            raise EngineUnavailable("La voce di Windows non è disponibile su questo sistema.")
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate, voice.Volume = self.rate, self.volume
        try:
            tokens, best, best_score = voice.GetVoices(), None, 0
            for i in range(tokens.Count):
                tok = tokens.Item(i)
                score = 0
                try:
                    if tok.GetAttribute("Language").split(";")[0].strip() == "410":      # it-IT
                        score += 1
                except Exception:
                    pass
                if self.hint and self.hint in (tok.GetDescription() or "").lower():
                    score += 2
                if score > best_score:
                    best, best_score = tok, score
            if best is not None:
                voice.Voice = best
        except Exception:
            pass
        return voice

    def say(self, text: str):
        if self._voice is None:
            self._voice = self._create()
        v = self._voice
        v.Speak(text, 1)                                       # 1 = asincrono
        limit, t0 = 10 + len(text) / 8, time.time()
        while not v.WaitUntilDone(200):
            if time.time() - t0 > limit:
                v.Speak("", 3)                                 # svuota e riparti
                self._voice = None
                raise TimeoutError("SAPI bloccato, riavvio il motore vocale")

    def purge(self):
        try:
            if self._voice is not None:
                self._voice.Speak("", 3)
        except Exception:
            pass


class EdgeEngine:
    """Voci neurali di Microsoft Edge (servizio online). Sintetizza in mp3 e lo decodifica in memoria."""
    kind = "pcm"

    def __init__(self, voice: str, rate: int = 1):
        try:
            import edge_tts
            import miniaudio
        except ImportError as e:
            raise EngineUnavailable("Per le voci neurali online installa: pip install edge-tts miniaudio") from e
        self._edge, self._mini = edge_tts, miniaudio
        self.voice = voice
        self.rate = f"{int(rate) * 5:+d}%"                     # rate 1 -> +5%

    def synth(self, text: str):
        async def run():
            buf = bytearray()
            async for chunk in self._edge.Communicate(text, self.voice, rate=self.rate).stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        mp3 = asyncio.run(asyncio.wait_for(run(), timeout=20))
        if not mp3:
            raise RuntimeError("il servizio non ha restituito audio")
        snd = self._mini.decode(mp3, output_format=self._mini.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
        return np.frombuffer(snd.samples, dtype=np.int16), int(snd.sample_rate)


class PiperEngine:
    """Voci neurali Piper, tutto in locale."""
    kind = "pcm"

    def __init__(self, name: str, rate: int = 1):
        try:
            from piper import PiperVoice
        except ImportError as e:
            raise EngineUnavailable("Per le voci offline installa: pip install piper-tts") from e
        path = os.path.join(VOICES_DIR, name + ".onnx")
        if not os.path.exists(path):
            raise NeedsDownload(name)
        self.voice = PiperVoice.load(path)
        self.length_scale = max(0.6, 1.0 - 0.04 * int(rate))   # rate più alto = voce più veloce
        try:
            from piper import SynthesisConfig
            self.cfg = SynthesisConfig(length_scale=self.length_scale)
        except Exception:
            self.cfg = None

    def synth(self, text: str):
        pcm, sr = bytearray(), 22050
        try:
            chunks = self.voice.synthesize(text, syn_config=self.cfg) if self.cfg else self.voice.synthesize(text)
        except TypeError:
            chunks = self.voice.synthesize(text)
        for chunk in chunks:
            sr = int(chunk.sample_rate)
            pcm.extend(chunk.audio_int16_bytes)
        if not pcm:
            raise RuntimeError("nessun audio prodotto")
        return np.frombuffer(bytes(pcm), dtype=np.int16), sr


class KokoroEngine:
    """Voci neurali Kokoro-82M (nicola, sara), tutto in locale una volta scaricati i file."""
    kind = "pcm"

    def __init__(self, name: str, rate: int = 1):
        try:
            from kokoro_onnx import Kokoro
        except ImportError as e:
            raise EngineUnavailable("Per le voci offline Kokoro installa: pip install kokoro-onnx") from e
        self.voice, prec = _split_kokoro(name)
        model, voices = [p for p, _ in voice_files("kokoro", name)]
        if not (os.path.exists(model) and os.path.exists(voices)):
            raise NeedsDownload(name)
        self.kokoro = Kokoro(model, voices)
        self.speed = min(1.4, 1.0 + 0.05 * int(rate))

    def synth(self, text: str):
        samples, sr = self.kokoro.create(text, voice=self.voice, speed=self.speed, lang="it")
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            raise RuntimeError("nessun audio prodotto")
        return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16), int(sr)


# ----------------------------------------------------------------------------- speaker
class Speaker:
    """Coda di frasi con due stadi: uno sintetizza la frase successiva mentre l'altro riproduce quella corrente,
    così le voci neurali parlano senza pause tra una frase e l'altra."""

    def __init__(self, voice=None, rate: int = 1, volume: int = 100):
        self.rate, self.volume = rate, volume
        self._text_q, self._play_q = queue.Queue(), queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._epoch = 0                                        # stop(): scarta tutto ciò che è in coda
        self._stream = None
        self.last_error = ""
        self._fallback = SapiEngine("", rate, volume)          # sempre disponibile, usata se un motore fallisce
        self._engine = SapiEngine("elsa", rate, volume)
        self.voice_key = DEFAULT_VOICE
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

        spec = voice or os.environ.get("JARVIS_VOICE") or self._load_saved() or DEFAULT_VOICE
        msg = self.set_voice(spec, persist=False)
        if not msg.startswith("Ok"):                           # voce non disponibile: resta quella di Windows
            logging.info("[VOCE] %s", msg)

    # ---------------- stato ----------------
    @property
    def is_speaking(self) -> bool:
        return self._pending > 0

    def wait_until_done(self, poll=0.05, timeout=90.0):
        t0 = time.time()
        while self.is_speaking and time.time() - t0 < timeout:
            time.sleep(poll)

    def _note_error(self, msg: str):
        self.last_error = msg
        logging.warning("[VOCE] %s", msg)
        print(f"[SPEAKER] {msg}")

    def _finish(self, done):
        with self._lock:
            self._pending -= 1
        if done:
            done.set()

    # ---------------- thread ----------------
    def _synth_loop(self):
        while True:
            text, done, epoch = self._text_q.get()
            if epoch != self._epoch:
                self._finish(done)
                continue
            engine = self._engine
            if engine.kind == "direct":
                self._play_q.put(("direct", engine, text, done, epoch))
                continue
            try:
                pcm, sr = engine.synth(text)
                self._play_q.put(("pcm", pcm, sr, text, done, epoch))
            except Exception as e:                              # rete assente, motore rotto...: ripiego su Windows
                self._note_error(f"{type(e).__name__}: {e} — uso la voce di Windows per questa frase")
                self._play_q.put(("direct", self._fallback, text, done, epoch))

    def _play_pcm(self, pcm: np.ndarray, sr: int):
        if sd is None:
            raise RuntimeError("sounddevice non disponibile")
        data = pcm if self.volume >= 100 else (pcm.astype(np.float32) * (self.volume / 100.0)).astype(np.int16)
        data = np.ascontiguousarray(data.reshape(-1, 1))
        stream = sd.OutputStream(samplerate=sr, channels=1, dtype="int16")
        self._stream = stream
        try:
            stream.start()
            stream.write(data)
            stream.stop()                                       # aspetta la fine della riproduzione
        finally:
            self._stream = None
            stream.close()

    def _play_loop(self):
        if pythoncom is not None:
            pythoncom.CoInitialize()
        while True:
            item = self._play_q.get()
            kind = item[0]
            done, epoch = item[-2], item[-1]
            try:
                if epoch != self._epoch:
                    pass                                         # interrotta da stop()
                elif kind == "pcm":
                    try:
                        self._play_pcm(item[1], item[2])
                    except Exception as e:
                        self._note_error(f"{type(e).__name__}: {e} — uso la voce di Windows per questa frase")
                        self._fallback.say(item[3])
                else:
                    item[1].say(item[2])
            except Exception as e:
                self._note_error(f"Errore sintesi vocale: {e}")
            finally:
                self._finish(done)

    # ---------------- API di base ----------------
    def speak(self, text: str, block: bool = True):
        """block=True: ritorna a fine frase. block=False: accoda e ritorna subito."""
        text = clean_for_speech(text)
        if not text:
            return
        done = threading.Event() if block else None
        with self._lock:
            self._pending += 1
        self._text_q.put((text, done, self._epoch))
        if done:
            done.wait()

    def stop(self):
        """Interrompe subito la voce e svuota la coda."""
        self._epoch += 1
        for fn in (getattr(self._stream, "abort", None), getattr(self._engine, "purge", None),
                   getattr(self._fallback, "purge", None)):
            try:
                if fn:
                    fn()
            except Exception:
                pass

    # ---------------- scelta della voce ----------------
    @staticmethod
    def _load_saved():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return str(json.load(f).get("voice", "")) or None
        except Exception:
            return None

    @staticmethod
    def _save(key: str):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"voice": key}, f, ensure_ascii=False)
        except Exception as e:
            logging.warning("[VOCE] impossibile salvare voice.json: %s", e)

    def _build_engine(self, engine: str, name: str):
        if engine == "sapi":
            if not SAPI_OK:
                raise EngineUnavailable("La voce di Windows non è disponibile su questo sistema.")
            return SapiEngine(name, self.rate, self.volume)
        if engine == "edge":
            return EdgeEngine(name, self.rate)
        if engine == "kokoro":
            return KokoroEngine(name, self.rate)
        return PiperEngine(name, self.rate)

    @staticmethod
    def is_ready(key: str) -> bool:
        """True se la voce non richiede download o i suoi file sono già in voices/."""
        r = resolve_voice(key)
        if r is None:
            return False
        return all(os.path.exists(p) for p, _ in voice_files(r[1], r[2]))

    def prepare(self, key: str, progress=None) -> str:
        """Scarica (se serve) i file di una voce Piper/Kokoro. Ritorna un messaggio d'errore oppure ''."""
        r = resolve_voice(key)
        if r is None or r[1] not in ("piper", "kokoro"):
            return ""
        _, engine, name = r
        if self.is_ready(key):
            return ""
        try:
            os.makedirs(VOICES_DIR, exist_ok=True)
            if engine == "piper":
                if getattr(sys, "frozen", False):           # dentro l'exe non c'è un Python da lanciare con -m
                    from pathlib import Path
                    from piper.download_voices import download_voice
                    download_voice(name, Path(VOICES_DIR))
                else:
                    subprocess.run([sys.executable, "-m", "piper.download_voices", name], cwd=VOICES_DIR,
                                   check=True, timeout=900, capture_output=True)
            else:
                for path, url in voice_files(engine, name):
                    if not os.path.exists(path):
                        logging.info("[VOCE] scarico %s", os.path.basename(path))
                        download_file(url, path, progress)
        except Exception as e:
            return f"Non sono riuscito a scaricare la voce: {e}"
        return "" if self.is_ready(key) else "Download non riuscito."

    def set_voice(self, spec: str, persist: bool = True) -> str:
        """Cambia voce. Ritorna il messaggio da dire all'utente."""
        r = resolve_voice(spec)
        if r is None:
            return f"Non conosco la voce {spec}. Posso usare: {', '.join(PRESETS)}."
        key, kind, name = r
        try:
            engine = self._build_engine(kind, name)
        except NeedsDownload:
            threading.Thread(target=self._download_then_switch, args=(key, persist), daemon=True).start()
            return f"Scarico la voce {key}, ci vorrà qualche minuto. Intanto continuo con quella attuale."
        except EngineUnavailable as e:
            return str(e)
        except Exception as e:
            return f"Non riesco a caricare la voce {key}: {e}"
        self._engine, self.voice_key = engine, key
        if persist:
            self._save(key)
        return f"Ok, ora uso la voce {key}."

    def _download_then_switch(self, key: str, persist: bool):
        err = self.prepare(key)
        if err:
            self._note_error(err)
            self.speak("Non sono riuscito a scaricare la voce.", block=False)
            return
        msg = self.set_voice(key, persist=persist)
        self.speak(msg, block=False)

    def describe_voices(self) -> str:
        names = [f"{k}: {p['desc']}" for k, p in PRESETS.items()]
        return "Posso usare queste voci. " + ". ".join(names) + ". Dì per esempio: usa la voce di Diego."

    def _next_voice(self) -> str:
        keys = list(PRESETS)
        start = keys.index(self.voice_key) if self.voice_key in keys else -1
        last = ""
        for i in range(1, len(keys) + 1):
            key = keys[(start + i) % len(keys)]
            if PRESETS[key]["engine"] in ("piper", "kokoro") and not self.is_ready(key):
                continue                                        # non scaricare nulla durante un semplice "cambia voce"
            last = self.set_voice(key)
            if self.voice_key == key:
                return last
        return last or "Non ho altre voci disponibili."

    def handle_voice_command(self, text: str):
        """Riconosce 'cambia voce', 'usa la voce di Diego', 'elenco voci'. Ritorna la risposta, o None se non è un comando."""
        t = (text or "").lower().strip(" .!?,")
        if re.match(r"^(?:elenco|lista|quali sono|quali)\s+(?:delle\s+|le\s+|tue\s+)*voci\b", t) or re.match(r"^che voci (?:hai|ci sono)\b", t):
            return self.describe_voices()
        m = re.match(r"^(?:jarvis[, ]+)?(?:cambia|imposta|usa|metti|passa(?:\s+a)?|prova)\s+"
                     r"(?:la\s+|una\s+)?(?:tua\s+|altra\s+|nuova\s+)?voce\b(.*)$", t)
        if not m:
            return None
        rest = m.group(1).strip().replace(" hd", "-hd").replace(" alta qualità", "-hd")
        for key in sorted(list(PRESETS) + list(ALIASES), key=len, reverse=True):     # "nicola hd" prima di "nicola"
            if re.search(rf"\b{re.escape(key)}\b", rest):
                return self.set_voice(key)
        if rest in ("", "diversa", "differente", "un'altra", "altra", "nuova"):
            return self._next_voice()
        return f"Non conosco quella voce. Posso usare: {', '.join(PRESETS)}."
