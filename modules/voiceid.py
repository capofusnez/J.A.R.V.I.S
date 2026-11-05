"""Riconoscimento della voce: capisce chi sta parlando e impara le persone che gli presenti.

Tutto è locale. Un piccolo modello (circa 26 MB, wespeaker) trasforma ogni frase in una "impronta" di 256 numeri;
due frasi della stessa persona hanno impronte vicine. Il modello si scarica una volta sola in voices/ e poi funziona offline.
Le impronte (non l'audio) stanno in data/voiceprints.json. Servono solo numpy e onnxruntime.
"""
import os
import json
import time
import math
import logging
import threading
import urllib.request
from collections import deque

import numpy as np

try:
    from modules.paths import DATA_DIR, VOICES_DIR
except Exception:                                      # uso fuori dal progetto
    DATA_DIR = VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
             "wespeaker_en_voxceleb_resnet34.onnx")
MODEL_NAME = "speaker_model.onnx"
SAMPLE_RATE = 16000
MIN_SECONDS = 1.2            # sotto questa durata l'impronta non è affidabile
THRESHOLD = float(os.environ.get("JARVIS_VOICE_THRESHOLD", "0.42"))   # somiglianza minima per dire "è lui"
ADAPT_MARGIN = 0.15          # sopra soglia + margine la voce è sicura: la usa per affinare il profilo
MAX_PRINTS = 40              # impronte conservate per persona (le prime 6 restano sempre)
KEEP_FIRST = 6


# ----------------------------------------------------------------------------- caratteristiche audio (fbank stile Kaldi)
def _mel(f):
    return 1127.0 * np.log(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


_FB_CACHE = {}


def _mel_bank(num_bins=80, n_fft=512, sr=SAMPLE_RATE, low=20.0, high=None):
    key = (num_bins, n_fft, sr)
    if key in _FB_CACHE:
        return _FB_CACHE[key]
    high = high or sr / 2.0
    mel_low, mel_high = _mel(low), _mel(high)
    delta = (mel_high - mel_low) / (num_bins + 1)
    freqs = _mel(np.arange(n_fft // 2) * (sr / n_fft))
    bank = np.zeros((num_bins, n_fft // 2), dtype=np.float32)
    for b in range(num_bins):
        left, center, right = mel_low + b * delta, mel_low + (b + 1) * delta, mel_low + (b + 2) * delta
        up = (freqs - left) / (center - left)
        down = (right - freqs) / (right - center)
        bank[b] = np.maximum(0.0, np.minimum(up, down))
    _FB_CACHE[key] = bank
    return bank


def fbank(samples: np.ndarray, num_bins=80) -> np.ndarray:
    """samples: int16 a 16 kHz -> (frame, 80) log-mel con la media tolta, come si aspetta il modello."""
    x = samples.astype(np.float32)                                  # scala int16, come "normalize_samples = 0"
    win, hop, n_fft = 400, 160, 512
    if len(x) < win:
        return np.zeros((0, num_bins), dtype=np.float32)
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx]
    frames = frames - frames.mean(axis=1, keepdims=True)           # via la componente continua
    prev = np.concatenate([frames[:, :1], frames[:, :-1]], axis=1)  # pre-enfasi 0.97
    frames = frames - 0.97 * prev
    window = np.power(0.5 - 0.5 * np.cos(2 * np.pi * np.arange(win) / (win - 1)), 0.85).astype(np.float32)  # finestra "povey"
    frames = frames * window
    spec = np.abs(np.fft.rfft(frames, n=n_fft, axis=1))[:, : n_fft // 2] ** 2
    mel = np.maximum(spec @ _mel_bank(num_bins, n_fft).T, np.finfo(np.float32).eps)
    feats = np.log(mel)
    return (feats - feats.mean(axis=0, keepdims=True)).astype(np.float32)


# ----------------------------------------------------------------------------- riconoscitore
class VoiceID:
    def __init__(self, models_dir=None, data_dir=None):
        self.models_dir = models_dir or VOICES_DIR
        self.data_dir = data_dir or DATA_DIR
        self.model_path = os.path.join(self.models_dir, MODEL_NAME)
        self.store_path = os.path.join(self.data_dir, "voiceprints.json")
        self.session = None
        self.error = ""                                  # perché non funziona (libreria o modello mancante)
        self._lock = threading.RLock()
        self.people = {}                                 # nome -> [impronte]
        self.owner = ""                                  # il primo che presenti è il "proprietario"
        self.only_owner = False                          # True = ignora chi non è il proprietario
        self.recent = deque(maxlen=8)                    # ultime frasi: (impronta, ora, nome riconosciuto o None)
        self.learning = None                             # {"name": .., "left": n}: sta imparando una voce
        self.last = {"name": None, "score": 0.0, "known": False, "t": 0.0}
        self._load()

    # ---- archivio
    def _load(self):
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.people = {n: [np.asarray(v, dtype=np.float32) for v in vs] for n, vs in d.get("people", {}).items()}
            self.owner = d.get("owner", "") if d.get("owner", "") in self.people else ""
            self.only_owner = bool(d.get("only_owner", False)) and bool(self.owner)
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.warning("[VOCE] voiceprints.json non leggibile: %s", e)

    def _save(self):
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.store_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"owner": self.owner, "only_owner": self.only_owner,
                           "people": {n: [v.round(5).tolist() for v in vs] for n, vs in self.people.items()}}, f)
            os.replace(tmp, self.store_path)
        except OSError as e:
            logging.warning("[VOCE] non riesco a salvare le impronte: %s", e)

    # ---- modello
    def _session(self):
        if self.session is not None:
            return self.session
        if not os.path.isfile(self.model_path):
            self.error = "modello non ancora scaricato"
            return None
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            self.session = ort.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])
            self.error = ""
        except ImportError:
            self.error = "manca la libreria onnxruntime (pip install onnxruntime)"
        except Exception as e:
            self.error = f"modello non caricabile: {e}"
            logging.warning("[VOCE] %s", self.error)
        return self.session

    def prepare(self, progress=None) -> bool:
        """Scarica il modello (una volta sola, circa 26 MB). Ritorna True se è pronto."""
        if not os.path.isfile(self.model_path):
            try:
                os.makedirs(self.models_dir, exist_ok=True)
                tmp = self.model_path + ".part"
                with urllib.request.urlopen(MODEL_URL, timeout=60) as r, open(tmp, "wb") as f:
                    total = int(r.headers.get("Content-Length") or 0)
                    done = 0
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress and total:
                            progress(done / total)
                os.replace(tmp, self.model_path)
                logging.info("[VOCE] modello scaricato in %s", self.model_path)
            except Exception as e:
                self.error = f"download del modello non riuscito: {e}"
                logging.warning("[VOCE] %s", self.error)
                return False
        return self._session() is not None

    @property
    def ready(self) -> bool:
        return self._session() is not None

    # ---- impronte
    def embed(self, samples: np.ndarray):
        """Impronta (256 numeri, norma 1) di una frase, oppure None se è troppo corta o il modello manca."""
        if samples is None or len(samples) < SAMPLE_RATE * MIN_SECONDS:
            return None
        sess = self._session()
        if sess is None:
            return None
        feats = fbank(np.asarray(samples).reshape(-1))
        if len(feats) < 100:
            return None
        try:
            out = sess.run(None, {"feats": feats[None, :, :]})[0][0]
        except Exception as e:
            logging.warning("[VOCE] errore del modello: %s", e)
            return None
        n = float(np.linalg.norm(out))
        return (out / n).astype(np.float32) if n > 0 else None

    @staticmethod
    def _centroid(vs):
        c = np.mean(vs, axis=0)
        return c / (np.linalg.norm(c) or 1.0)

    def match(self, emb):
        """(nome, somiglianza) della persona più vicina; nome None se nessuno supera la soglia."""
        best, best_s = None, -1.0
        with self._lock:
            for name, vs in self.people.items():
                if not vs:
                    continue
                s = float(np.dot(emb, self._centroid(vs)))
                if s > best_s:
                    best, best_s = name, s
        return (best if best_s >= THRESHOLD else None), max(best_s, 0.0)

    # ---- uso durante l'ascolto
    def observe(self, samples: np.ndarray) -> dict:
        """Da chiamare per ogni frase sentita. Ritorna {"name", "score", "known"} e impara da solo."""
        emb = self.embed(samples)
        now = time.time()
        if emb is None:                                  # frase troppo corta: vale la voce di poco fa
            if self.last["t"] and now - self.last["t"] < 20:
                return dict(self.last, short=True)
            return {"name": None, "score": 0.0, "known": False, "short": True}
        name, score = self.match(emb)
        with self._lock:
            if self.learning:
                lname = self.learning["name"]
                self._add(lname, emb)
                self.learning["left"] -= 1
                name, score = lname, 1.0
                if self.learning["left"] <= 0:
                    self.learning = None
                    self._save()
            elif name and score >= THRESHOLD + (ADAPT_MARGIN if len(self.people[name]) >= KEEP_FIRST else 0.04):
                self._add(name, emb)                      # si adatta: affina il profilo con le frasi sicure
                if len(self.people[name]) % 5 == 0 or len(self.people[name]) <= KEEP_FIRST:
                    self._save()                          # (un profilo ancora scarno impara più in fretta)
            self.recent.append((emb, now, name))
        self.last = {"name": name, "score": float(score), "known": name is not None, "t": now}
        return dict(self.last)

    def _add(self, name, emb):
        vs = self.people.setdefault(name, [])
        vs.append(emb)
        if len(vs) > MAX_PRINTS:
            del vs[KEEP_FIRST]                           # tiene le prime impronte e le più recenti
        if not self.owner:
            self.owner = name

    # ---- comandi
    def start_learning(self, name: str, phrases: int = 4):
        with self._lock:
            self.learning = {"name": name, "left": phrases}
            self.people.setdefault(name, [])
            if not self.owner:
                self.owner = name

    def enroll_recent(self, name: str, include_last: bool = False, max_age: float = 90.0, count: int = 3) -> int:
        """Assegna a `name` le ultime frasi sentite (della stessa voce dell'ultima).
        include_last=False: l'ultima frase è il comando di chi te lo dice ("sta parlando Marco"), quindi si salta;
        include_last=True: la persona si presenta da sola ("sono Marco"), quindi vale anche l'ultima."""
        now = time.time()
        with self._lock:
            items = [r for r in self.recent if now - r[1] <= max_age]
            if not include_last:
                items = items[:-1]
            if not items:
                return 0
            ref = items[-1][0]
            chosen = [r for r in items if float(np.dot(r[0], ref)) >= THRESHOLD][-count:]
            for emb, _, _ in chosen:
                self._add(name, emb)
            if chosen:
                self.last = {"name": name, "score": 1.0, "known": True, "t": now}
                self._save()
            return len(chosen)

    def forget(self, name: str) -> bool:
        with self._lock:
            key = next((n for n in self.people if n.lower() == name.lower()), None)
            if not key:
                return False
            del self.people[key]
            if self.owner == key:
                self.owner = next(iter(self.people), "")
            if not self.owner:
                self.only_owner = False
            self._save()
            return True

    def names(self):
        return [n for n, vs in self.people.items() if vs]

    def set_only_owner(self, on: bool) -> bool:
        if on and not self.owner:
            return False
        self.only_owner = on
        self._save()
        return True

    def save(self):
        self._save()


_INSTANCE = None


def get_voiceid() -> VoiceID:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = VoiceID()
    return _INSTANCE
