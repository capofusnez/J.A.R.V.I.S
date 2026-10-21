import queue
import threading
import pythoncom
import pyttsx3


class Speaker:
    """Motore TTS creato una sola volta in un thread dedicato, con coda di frasi."""

    def __init__(self, rate=185):
        self.rate = rate
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0          # frasi in coda + in riproduzione
        threading.Thread(target=self._worker, daemon=True).start()

    @property
    def is_speaking(self) -> bool:
        return self._pending > 0

    def wait_until_done(self, poll=0.05):
        import time
        while self.is_speaking:
            time.sleep(poll)

    def _worker(self):
        pythoncom.CoInitialize()
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        for voice in engine.getProperty("voices"):
            vid = voice.id.lower()
            if "italian" in voice.name.lower() or "it_it" in vid or "it-it" in vid:
                engine.setProperty("voice", voice.id)
                break

        while True:
            text, done = self._q.get()
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"Errore sintesi vocale: {e}")
            finally:
                with self._lock:
                    self._pending -= 1
                if done:
                    done.set()

    def speak(self, text: str, block: bool = True):
        """block=True: ritorna a fine frase. block=False: accoda e ritorna subito."""
        if not text:
            return
        done = threading.Event() if block else None
        with self._lock:
            self._pending += 1
        self._q.put((text, done))
        if done:
            done.wait()
