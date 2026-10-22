import os
import sys
import time
import atexit
import inspect
import logging
import threading
import traceback
import faulthandler
from PyQt6.QtWidgets import QApplication, QSplashScreen, QLabel, QVBoxLayout, QMessageBox, QFrame
from PyQt6.QtGui import QFont, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal

# Importa la tua GUI cinematografica
from gui_v2 import StarkHUD
from modules.brain import LocalBrain
from modules.ollama_setup import OllamaSetup

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.log")


def setup_logging():
    """Tutto quello che succede all'avvio finisce in jarvis.log: utile se qualcosa va storto."""
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")


def install_excepthook():
    """Senza un excepthook proprio PyQt6 chiude il programma in silenzio al primo errore dentro uno slot."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.critical("Eccezione non gestita:\n%s", text)
        try:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() is app.thread():
                box = QMessageBox()
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle("Errore in Jarvis")
                box.setText(f"Si è verificato un errore: {exc}\n\nI dettagli sono in jarvis.log")
                box.setDetailedText(text)
                box.exec()
        except Exception:
            pass

    sys.excepthook = hook
    threading.excepthook = lambda a: logging.critical(
        "Eccezione nel thread:\n%s", "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


# Il modello da controllare/scaricare è lo stesso che usa Jarvis (valore predefinito di LocalBrain)
MODEL_NAME = inspect.signature(LocalBrain.__init__).parameters["model_name"].default

class HudProgressBar(QFrame):
    """Barra di avanzamento HUD fatta con widget standard (nessun disegno personalizzato):
    percentuale reale, oppure blocco che scorre quando la dimensione non è nota."""

    def __init__(self):
        super().__init__()
        self.setObjectName("hudbar")
        self.setFixedHeight(12)
        self.setStyleSheet("QFrame#hudbar { background-color: #0d1b2a; border: 1px solid #00a8b3; }")
        self.fill = QFrame(self)
        self.fill.setStyleSheet("background-color: #00f3ff; border: none;")
        self._frac = 0.0
        self._busy = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def _layout_fill(self):
        inner_w = max(0, self.width() - 4)
        h = max(0, self.height() - 4)
        if self._busy:
            block = int(inner_w * 0.25)
            x = int((inner_w + block) * self._phase) - block
            left, right = max(0, x), min(inner_w, x + block)
            self.fill.setGeometry(2 + left, 2, max(0, right - left), h)
        else:
            self.fill.setGeometry(2, 2, int(inner_w * self._frac), h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_fill()

    def _tick(self):
        self._phase = (self._phase + 0.02) % 1.0
        self._layout_fill()

    def set_progress(self, v: int):
        """-1 = nascondi, -2 = animata (senza percentuale), 0..1000 = percentuale."""
        if v == -1:
            self._timer.stop()
            self.hide()
            return
        self._busy = (v == -2)
        if self._busy:
            if not self._timer.isActive():
                self._timer.start(30)
        else:
            self._timer.stop()
            self._frac = max(0, min(v, 1000)) / 1000.0
        self.show()
        self._layout_fill()


class FuturisticSplash(QSplashScreen):
    """Finestra di caricamento futuristica stile HUD Stark."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(520, 290)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # Centratura automatica sullo schermo primario
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        # Layout e stile visivo high-tech
        self.setStyleSheet("""
            QWidget {
                background-color: #080c14;
                color: #00f3ff;
                border: 1px solid #00f3ff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Titolo principale HUD
        title_label = QLabel("JARVIS SYSTEM // INITIALIZATION")
        title_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00f3ff; border: none; letter-spacing: 2px;")
        layout.addWidget(title_label)
        
        # Sottotitolo / Versione
        sub_label = QLabel("MARK.I PROTOCOL - LOCAL AI NEURAL CORE")
        sub_label.setFont(QFont("Consolas", 8))
        sub_label.setStyleSheet("color: #4a7a8c; border: none;")
        layout.addWidget(sub_label)
        
        layout.addSpacing(15)
        
        # Testo di stato dinamico (stile log di terminale)
        self.status_label = QLabel("[INIT] Caricamento kernel di sistema...")
        self.status_label.setFont(QFont("Consolas", 9))
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(56)
        self.status_label.setStyleSheet("color: #e0fbfc; border: none;")
        layout.addWidget(self.status_label)

        self.progress_bar = HudProgressBar()
        layout.addWidget(self.progress_bar)
        layout.addStretch(1)

    def update_status(self, text: str):
        self.status_label.setText(text)

    def paintEvent(self, event):
        """Disegna piccoli dettagli geometrici HUD agli angoli della finestra."""
        super().paintEvent(event)
        painter = QPainter(self)
        
        color = QColor("#00f3ff")
        color.setAlpha(180)
        painter.setPen(QPen(color, 2))
        
        w, h = self.width(), self.height()
        # Top-left
        painter.drawLine(0, 0, 15, 0)
        painter.drawLine(0, 0, 0, 15)
        # Top-right
        painter.drawLine(w - 15, 0, w, 0)
        painter.drawLine(w, 0, w, 15)
        # Bottom-left
        painter.drawLine(0, h - 15, 0, h)
        painter.drawLine(0, h, 15, h)
        # Bottom-right
        painter.drawLine(w - 15, h, w, h)
        painter.drawLine(w, h - 15, w, h)


class OllamaStartupWorker(QThread):
    """Sequenza di boot: controlla Ollama (lo installa se manca, con il permesso dell'utente) e il modello."""
    status_signal = pyqtSignal(str)
    ask_signal = pyqtSignal(str, str, str, str)   # titolo, testo, pulsante sì, pulsante no (mostrata dal thread GUI)
    progress_signal = pyqtSignal(int)      # -1 nascondi, -2 animata, 0..1000 percentuale
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._answer = False
        self._answered = threading.Event()

    def answer(self, value: bool):
        self._answer = value
        self._answered.set()

    def _status(self, text: str):
        now = time.time()
        if "%" not in text or now - getattr(self, "_last_log", 0) > 15:     # non loggare ogni aggiornamento di progresso
            self._last_log = now
            logging.info("[SPLASH] %s", text.replace("\n", " | "))
        self.status_signal.emit(text)

    def _progress(self, v):
        """v: float 0..1 = percentuale, None = attività senza percentuale, False = nascondi."""
        self.progress_signal.emit(-1 if v is False else -2 if v is None else int(v * 1000))

    def _ask(self, title: str, text: str, yes: str = "Sì", no: str = "No") -> bool:
        self._answer = False
        self._answered.clear()
        self.ask_signal.emit(title, text, yes, no)
        if not self._answered.wait(timeout=600):                 # mai bloccati all'infinito
            logging.warning("[ASK] %s -> nessuna risposta (timeout)", title)
            return False
        logging.info("[ASK] %s -> %s", title, "SÌ" if self._answer else "NO")
        return self._answer

    def run(self):
        try:
            self.status_signal.emit("[BOOT] Allocazione memoria virtuale e registri...")
            time.sleep(0.35)
            self.status_signal.emit("[SYS] Montaggio moduli di interfaccia PyQt6...")
            time.sleep(0.35)
            self.status_signal.emit("[CHECK] Inizializzazione socket di rete locali...")
            time.sleep(0.3)

            setup = OllamaSetup(MODEL_NAME, self._status, self._ask, self._progress)
            ok = False
            for _ in range(3):
                ok = setup.ensure()
                if ok or not setup.last_error:
                    break
                # errore vero (non un semplice rifiuto): resta visibile e si può riprovare
                if not self._ask("Problema con Ollama", f"{setup.last_error}\n\nVuoi riprovare?",
                                 "Riprova", "Continua senza"):
                    break
            if ok:
                time.sleep(0.3)
                self.status_signal.emit("[SECURITY] Calcolo codici di checksum e crittografia...")
                time.sleep(0.4)
                self.status_signal.emit("[READY] Sottosistemi pronti. Apertura StarkHUD...")
                time.sleep(0.5)
            else:
                # non dire "pronti" se non lo sono: lascia leggere lo stato reale
                time.sleep(2.0)
                self.status_signal.emit("[WARN] Ollama o il modello non sono pronti: Jarvis si apre con funzioni limitate.")
                time.sleep(2.5)
        except Exception as e:
            self.status_signal.emit(f"[ERROR] Avvio incompleto: {e}")
            time.sleep(1.5)
        finally:
            self.finished_signal.emit()            # la GUI si apre comunque, anche se qualcosa è andato storto


def show_question(title: str, text: str, yes_text: str, no_text: str, worker: "OllamaStartupWorker", splash):
    """Finestra di conferma in stile HUD. Risponde SEMPRE al worker, anche in caso di errore."""
    answer = False
    try:
        box = QMessageBox()
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        yes_btn = box.addButton(yes_text, QMessageBox.ButtonRole.YesRole)
        box.addButton(no_text, QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes_btn)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.setStyleSheet("""
            QMessageBox { background-color: #080c14; }
            QLabel { color: #e0fbfc; font-family: Consolas; }
            QPushButton { background-color: #0d1b2a; color: #00f3ff; border: 1px solid #00f3ff;
                          padding: 6px 18px; font-family: Consolas; }
            QPushButton:hover { background-color: #00f3ff; color: #080c14; }
        """)
        logging.info("[DIALOG] finestre prima: %s", [(type(w).__name__, w.isVisible()) for w in QApplication.topLevelWidgets()])
        box.exec()
        logging.info("[DIALOG] finestre dopo: %s", [(type(w).__name__, w.isVisible()) for w in QApplication.topLevelWidgets()])
        # si guarda il RUOLO del pulsante premuto, non il valore numerico restituito da exec()
        answer = box.buttonRole(box.clickedButton()) == QMessageBox.ButtonRole.YesRole
    except Exception:
        logging.exception("Errore nella finestra di conferma")
    finally:
        worker.answer(answer)
        try:
            splash.raise_()                                      # riporta la splash in primo piano dopo la domanda
            splash.activateWindow()
        except Exception:
            pass


if __name__ == "__main__":
    setup_logging()
    install_excepthook()
    # errori nativi (crash di Qt, segfault) finiscono in jarvis_crash.log invece di sparire
    _crash_file = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_crash.log"),
                       "a", encoding="utf-8")
    faulthandler.enable(_crash_file)
    atexit.register(lambda: logging.info("Il processo sta terminando"))
    logging.info("=== Avvio Jarvis ===")
    app = QApplication(sys.argv)
    app.setFont(QFont("Consolas", 10))
    # Durante l'avvio (splash, domande, download) il programma NON deve chiudersi da solo
    # quando una finestra si chiude: lo riattiviamo quando la GUI principale è aperta.
    app.setQuitOnLastWindowClosed(False)
    app.lastWindowClosed.connect(lambda: logging.info("[QT] lastWindowClosed"))
    app.aboutToQuit.connect(lambda: logging.info("[QT] aboutToQuit"))

    # Mostra la splash screen centrata
    splash = FuturisticSplash()
    splash.show()

    # Worker con sequenza di boot estesa
    worker = OllamaStartupWorker()
    worker.status_signal.connect(splash.update_status)
    worker.progress_signal.connect(splash.progress_bar.set_progress)
    worker.ask_signal.connect(lambda t, x, y, n: show_question(t, x, y, n, worker, splash))
    
    window = None
    def on_ready():
        global window
        splash.finish(None)  # Chiusura pulita della splash
        try:
            window = StarkHUD()
            window.show()
            app.setQuitOnLastWindowClosed(True)      # da ora chiudere la GUI chiude il programma
            logging.info("GUI principale aperta")
        except Exception:
            logging.exception("Impossibile aprire la GUI principale")
            QMessageBox.critical(None, "Errore in Jarvis",
                                 "Impossibile aprire l'interfaccia. I dettagli sono in jarvis.log")
            app.quit()

    worker.finished_signal.connect(on_ready)
    worker.start()

    sys.exit(app.exec())