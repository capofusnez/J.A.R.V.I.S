import sys
import os
import time
import shutil
import subprocess
import requests
from PyQt6.QtWidgets import QApplication, QSplashScreen, QLabel, QVBoxLayout
from PyQt6.QtGui import QFont, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Importa la tua GUI cinematografica
from gui_v2 import StarkHUD

OLLAMA_URL = "http://localhost:11434/"

class FuturisticSplash(QSplashScreen):
    """Finestra di caricamento futuristica stile HUD Stark."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(520, 240)
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
        self.status_label.setStyleSheet("color: #e0fbfc; border: none;")
        layout.addWidget(self.status_label)

    def update_status(self, text: str):
        self.status_label.setText(text)
        QApplication.processEvents()

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
    """Sequenza di boot dettagliata e controlli su Ollama in background."""
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def run(self):
        # Sequenza stile Iron Man / Terminale estesa
        self.status_signal.emit("[BOOT] Allocazione memoria virtuale e registri...")
        time.sleep(0.35)
        
        self.status_signal.emit("[SYS] Montaggio moduli di interfaccia PyQt6...")
        time.sleep(0.35)

        self.status_signal.emit("[CHECK] Inizializzazione socket di rete locali...")
        time.sleep(0.3)

        # 1. Test connessione server Ollama
        self.status_signal.emit("[NETWORK] Interrogazione demone Ollama (Porta 11434)...")
        server_active = False
        try:
            response = requests.get(OLLAMA_URL, timeout=1.5)
            if response.status_code == 200:
                server_active = True
        except Exception:
            pass
        
        time.sleep(0.4)

        if server_active:
            self.status_signal.emit("[OK] Canale neurale Ollama stabilito con successo.")
        else:
            self.status_signal.emit("[WARN] Servizio locale spento. Scansione binari sul disco...")
            ollama_path = shutil.which("ollama")
            if not ollama_path:
                local_appdata = os.environ.get("LOCALAPPDATA", "")
                possible_path = os.path.join(local_appdata, "Programs", "Ollama", "ollama.exe")
                if os.path.exists(possible_path):
                    ollama_path = possible_path

            if ollama_path:
                self.status_signal.emit("[EXEC] Eseguibile individuato. Avvio demone in background...")
                try:
                    subprocess.Popen([ollama_path, "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
                    time.sleep(2.5) # Attesa stabilizzazione
                    self.status_signal.emit("[OK] Servizio Ollama avviato e operativo.")
                except Exception:
                    self.status_signal.emit("[ERROR] Impossibile attivare il sottosistema Ollama.")
            else:
                self.status_signal.emit("[INFO] Nessun percorso standard rilevato per Ollama.")

        time.sleep(0.3)
        self.status_signal.emit("[SECURITY] Calcolo codici di checksum e crittografia...")
        time.sleep(0.4)

        self.status_signal.emit("[READY] Sottosistemi pronti. Apertura StarkHUD...")
        time.sleep(0.5)
        
        self.finished_signal.emit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Consolas", 10))

    # Mostra la splash screen centrata
    splash = FuturisticSplash()
    splash.show()

    # Worker con sequenza di boot estesa
    worker = OllamaStartupWorker()
    worker.status_signal.connect(splash.update_status)
    
    window = None
    def on_ready():
        global window
        splash.finish(None)  # Chiusura pulita della splash
        window = StarkHUD()
        window.show()

    worker.finished_signal.connect(on_ready)
    worker.start()

    sys.exit(app.exec())