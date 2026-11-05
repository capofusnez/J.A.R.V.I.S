import os
import collections
import threading
import numpy as np
import sounddevice as sd

try:
    from faster_whisper import WhisperModel
    import ctranslate2
    WHISPER_OK = True
except ImportError:
    WHISPER_OK = False

import speech_recognition as sr   # usato solo come ripiego se Whisper non è disponibile


class Listener:
    """Registra solo mentre parli (VAD a energia) e trascrive in locale con faster-whisper.

    model_size: "base" = più veloce, "small" = buon compromesso, "medium" = più preciso.
    Il modello si carica al primo utilizzo (o con warmup()), così la GUI parte subito.
    """

    def __init__(self, model_size="small", samplerate=16000, block_s=0.05,
                 start_timeout=6.0, silence_after=0.8, max_seconds=12.0):
        self.model_size = model_size
        self.samplerate = samplerate
        self.block = int(samplerate * block_s)
        self.block_s = block_s
        self.start_timeout = start_timeout
        self.silence_after = silence_after
        self.max_seconds = max_seconds

        self.threshold = 400.0
        self.level = 0.0                 # 0..1: volume del microfono, letto dall'interfaccia
        self.model = None
        self.device = None
        self.recognizer = sr.Recognizer()
        self._ready = False
        self._init_lock = threading.Lock()
        self.last_speaker = None          # chi ha parlato nell'ultima frase: {"name","score","known"} (None = non disponibile)
        try:
            from modules.voiceid import get_voiceid
            self.voiceid = get_voiceid()
        except Exception as e:           # senza numpy/onnxruntime Jarvis funziona lo stesso, solo senza riconoscere le voci
            print(f"[LISTENER WARNING] riconoscimento voce non disponibile: {e}")
            self.voiceid = None

    # ---------------- preparazione ----------------
    def warmup(self):
        """Da chiamare in un thread all'avvio: calibra il microfono e carica Whisper."""
        try:
            self._ensure_ready()
        except Exception as e:
            print(f"[LISTENER WARNING] warmup: {e}")

    def _ensure_ready(self):
        with self._init_lock:
            if self._ready:
                return
            self.calibrate()
            if WHISPER_OK:
                try:
                    self._load_model()
                except Exception as e:
                    print(f"[LISTENER WARNING] Whisper non caricato, uso Google: {e}")
                    self.model = None
            self._ready = True
        if self.voiceid is not None:      # scarica una volta sola il modello delle voci (circa 26 MB), poi è offline
            threading.Thread(target=self.voiceid.prepare, daemon=True).start()

    def _load_model(self, force_cpu=False):
        if not force_cpu:
            try:
                if ctranslate2.get_cuda_device_count() > 0:
                    self.model = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                    self.device = "cuda"
                    return
            except Exception:
                pass
        self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                  cpu_threads=os.cpu_count() or 4)
        self.device = "cpu"

    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

    def calibrate(self, seconds=1.0):
        try:
            rec = sd.rec(int(seconds * self.samplerate), samplerate=self.samplerate,
                         channels=1, dtype="int16")
            sd.wait()
            self.threshold = max(self._rms(rec) * 2.5, 250.0)
        except Exception:
            pass

    # ---------------- registrazione ----------------
    def _record_phrase(self, start_timeout=None):
        start_timeout = self.start_timeout if start_timeout is None else start_timeout
        preroll = collections.deque(maxlen=int(0.3 / self.block_s))
        frames, speaking = [], False
        silent_blocks, waited = 0, 0.0
        max_blocks = int(self.max_seconds / self.block_s)
        silence_needed = int(self.silence_after / self.block_s)

        with sd.InputStream(samplerate=self.samplerate, channels=1,
                            dtype="int16", blocksize=self.block) as stream:
            while True:
                chunk, _ = stream.read(self.block)
                rms = self._rms(chunk)
                self.level = min(1.0, rms / max(1.0, self.threshold * 4.0))
                loud = rms > self.threshold

                if not speaking:
                    preroll.append(chunk.copy())
                    if loud:
                        speaking = True
                        frames.extend(preroll)
                    else:
                        waited += self.block_s
                        if waited >= start_timeout:
                            return None
                else:
                    frames.append(chunk.copy())
                    silent_blocks = 0 if loud else silent_blocks + 1
                    if silent_blocks >= silence_needed or len(frames) >= max_blocks:
                        break
        return np.concatenate(frames).flatten() if frames else None

    # ---------------- trascrizione ----------------
    def _run_whisper(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="it",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            initial_prompt="Conversazione in italiano con un assistente virtuale chiamato Jarvis.",
        )
        # scarta i segmenti "inventati" da Whisper sul rumore
        good = [s.text.strip() for s in segments
                if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
        return " ".join(good).strip()

    def _transcribe(self, samples: np.ndarray) -> str:
        if self.model is not None:
            audio = samples.astype(np.float32) / 32768.0
            try:
                return self._run_whisper(audio)
            except Exception:
                if self.device == "cuda":      # librerie CUDA mancanti: ripiega su CPU
                    self._load_model(force_cpu=True)
                    return self._run_whisper(audio)
                raise
        try:
            data = sr.AudioData(samples.tobytes(), self.samplerate, 2)
            return self.recognizer.recognize_google(data, language="it-IT")
        except sr.UnknownValueError:
            return ""

    def listen(self, duration=None, start_timeout=None) -> str:
        """`duration` è ignorato (compatibilità). `start_timeout`: secondi di attesa prima che inizi a parlare."""
        try:
            self._ensure_ready()
            samples = self._record_phrase(start_timeout)
            self.level = 0.0
            if samples is None or len(samples) < self.samplerate * 0.4:
                return ""
            text = self._transcribe(samples).strip()
            if "sottotitoli" in text.lower():     # allucinazione tipica di Whisper
                return ""
            self.last_speaker = None
            vid = self.voiceid
            if text and vid is not None and vid.ready:
                try:
                    who = vid.observe(samples)     # chi è? impara da solo se la voce è già nota
                    self.last_speaker = who
                    if vid.only_owner and vid.owner and who.get("name") != vid.owner:
                        return ""                  # "rispondi solo a me": le altre voci vengono ignorate
                except Exception as e:
                    print(f"[LISTENER WARNING] voce: {e}")
            return text
        except Exception as e:
            print(f"[LISTENER ERROR] {e}")
            return ""
