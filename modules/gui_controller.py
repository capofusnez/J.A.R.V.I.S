import time
import html
import threading
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from modules.brain import LocalBrain
from modules.speaker import Speaker
from modules.listener import Listener


class BrainWorker(QThread):
    """Worker in background per la generazione streaming delle risposte da Ollama."""
    sentence = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, user_text: str, brain: LocalBrain):
        super().__init__()
        self.user_text = user_text
        self.brain = brain

    def run(self):
        try:
            for s in self.brain.process_input_stream(self.user_text):
                if s:
                    self.sentence.emit(s)
        except Exception as e:
            self.sentence.emit(f"Errore neural brain: {e}")
        self.completed.emit()


class ListenerWorker(QThread):
    """Worker in background per l'ascolto continuo o manuale del microfono."""
    finished = pyqtSignal(str)
    speech_detected = pyqtSignal(str)

    def __init__(self, listener: Listener, continuous: bool = False):
        super().__init__()
        self.listener = listener
        self.continuous = continuous
        self._is_running = True
        self._paused = False

    def run(self):
        while self._is_running:
            if self._paused:
                time.sleep(0.5)
                continue

            try:
                spoken_text = self.listener.listen()
            except Exception:
                spoken_text = ""

            if not spoken_text or spoken_text.startswith("Errore"):
                continue

            text_clean = spoken_text.strip().lower()
            ignore_phrases = [
                "non ho sentito nulla", "non ho capito cosa hai detto",
                "non ho capito", "sottotitoli e revisione a cura di",
                "sottotitoli creati dalla comunità", "am", "oh", "eh", ""
            ]

            if text_clean in ignore_phrases or (len(text_clean) <= 2 and text_clean not in ("sì", "si", "no", "ok")):
                continue

            if self.continuous:
                self._paused = True
                self.speech_detected.emit(spoken_text)
            else:
                self.finished.emit(spoken_text)
                break

    def pause(self):
        self._paused = True

    def resume(self):
        time.sleep(0.4)
        self._paused = False

    def stop(self):
        self._is_running = False


class JARVISController(QObject):
    """Controller centrale che disaccoppia la grafica dalla logica di esecuzione."""
    mail_alert = pyqtSignal(str)
    learned = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.brain = LocalBrain()
        self.speaker = Speaker()
        self.listener = Listener()

        # Inizializza il warmup del modello Whisper in background
        threading.Thread(target=self.listener.warmup, daemon=True).start()

        # Collega l'evento di apprendimento
        self.brain.on_learned = self.learned.emit

        self.continuous_worker = None
        self.brain_worker = None
        self.listener_worker = None

    def start_mail_watcher(self):
        return self.brain.start_mail_watcher(self.mail_alert.emit)

    def speak_sentence(self, sentence: str):
        self.speaker.speak(sentence, block=False)

    def wait_speaker_and_resume_listener(self):
        def _wait_thread():
            self.speaker.wait_until_done()
            if self.continuous_worker:
                self.continuous_worker.resume()

        threading.Thread(target=_wait_thread, daemon=True).start()

    def stop_services(self):
        if getattr(self.brain, "watcher", None):
            self.brain.watcher.stop()
        if self.continuous_worker:
            self.continuous_worker.stop()