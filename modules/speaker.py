import queue
import threading
import time
import pythoncom

try:
    import win32com.client
    SAPI_OK = True
except ImportError:
    SAPI_OK = False

try:
    import pyttsx3          # solo ripiego se SAPI non è utilizzabile
except ImportError:
    pyttsx3 = None


class Speaker:
    """Sintesi vocale con SAPI di Windows usata direttamente (niente pyttsx3 persistente, che si blocca).

    - Un solo thread dedicato con coda di frasi.
    - Ogni frase ha un tempo massimo: se SAPI si pianta viene interrotta e il motore viene ricreato,
      così la voce non resta mai muta.
    - rate: da -10 (lento) a +10 (veloce). 0 ≈ voce normale, 1-2 è un po' più scattante.
    """

    def __init__(self, rate=1, volume=100):
        self.rate = rate
        self.volume = volume
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0              # frasi in coda + in riproduzione
        self._thread = None
        self._start_thread()

    # ---------------- stato ----------------
    @property
    def is_speaking(self) -> bool:
        return self._pending > 0

    def wait_until_done(self, poll=0.05, timeout=90.0):
        """Aspetta la fine della voce, ma mai all'infinito."""
        t0 = time.time()
        while self.is_speaking and time.time() - t0 < timeout:
            time.sleep(poll)

    # ---------------- thread ----------------
    def _start_thread(self):
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _create_voice(self):
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate = self.rate
        voice.Volume = self.volume
        try:
            tokens = voice.GetVoices()
            chosen = None
            for i in range(tokens.Count):
                tok = tokens.Item(i)
                try:
                    if tok.GetAttribute("Language").split(";")[0].strip() == "410":   # it-IT
                        chosen = tok
                        break
                except Exception:
                    pass
                desc = (tok.GetDescription() or "").lower()
                if chosen is None and ("ital" in desc or "elsa" in desc):
                    chosen = tok
            if chosen is not None:
                voice.Voice = chosen
        except Exception:
            pass
        return voice

    @staticmethod
    def _say_sapi(voice, text: str):
        voice.Speak(text, 1)                                   # 1 = asincrono
        limit = 10 + len(text) / 8                             # secondi massimi (stima prudente)
        t0 = time.time()
        while not voice.WaitUntilDone(200):                    # attende a passi di 200 ms
            if time.time() - t0 > limit:
                voice.Speak("", 3)                             # 3 = asincrono + svuota la coda SAPI
                raise TimeoutError("SAPI bloccato, riavvio il motore vocale")

    @staticmethod
    def _say_pyttsx3(text: str):
        engine = pyttsx3.init()                                # ricreato a ogni frase: lento ma affidabile
        engine.say(text)
        engine.runAndWait()

    def _worker(self):
        pythoncom.CoInitialize()
        voice = None
        use_sapi = SAPI_OK
        while True:
            text, done = self._q.get()
            try:
                if use_sapi:
                    if voice is None:
                        try:
                            voice = self._create_voice()
                        except Exception as e:
                            print(f"[SPEAKER] SAPI non disponibile ({e}), uso pyttsx3")
                            use_sapi = False
                    if use_sapi:
                        self._say_sapi(voice, text)
                if not use_sapi and pyttsx3 is not None:
                    self._say_pyttsx3(text)
            except Exception as e:
                print(f"[SPEAKER] Errore sintesi vocale: {e}")
                voice = None                                   # forza la ricreazione del motore
            finally:
                with self._lock:
                    self._pending -= 1
                if done:
                    done.set()

    # ---------------- API ----------------
    def speak(self, text: str, block: bool = True):
        """block=True: ritorna a fine frase. block=False: accoda e ritorna subito."""
        if not text:
            return
        if not self._thread.is_alive():                        # il thread non deve mai restare morto
            self._start_thread()
        done = threading.Event() if block else None
        with self._lock:
            self._pending += 1
        self._q.put((text, done))
        if done:
            done.wait()
