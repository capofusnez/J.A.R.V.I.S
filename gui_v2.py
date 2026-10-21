import sys
import platform
import time
import threading
import html
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTextEdit, QLineEdit, 
                             QPushButton, QFrame, QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QTextCursor
import qtawesome as qta

from modules.brain import LocalBrain
from modules.speaker import Speaker
from modules.listener import Listener

CORE_COLOR = QColor(0, 243, 255)
CORE_COLOR_HEX = "#00f3ff"
TEXT_COLOR = QColor(192, 254, 252)
FONT_FAMILY = "Consolas"


class BrainWorker(QThread):
    """Emette una frase alla volta mentre il modello scrive."""
    sentence = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, user_text, brain):
        super().__init__()
        self.user_text = user_text
        self.brain = brain

    def run(self):
        try:
            for s in self.brain.process_input_stream(self.user_text):
                if s:
                    self.sentence.emit(s)
        except Exception as e:
            self.sentence.emit(f"Errore: {e}")
        self.completed.emit()


class ListenerWorker(QThread):
    """Worker di ascolto protetto: ignora i silenzi e i falsi positivi."""
    finished = pyqtSignal(str)
    speech_detected = pyqtSignal(str)

    def __init__(self, listener, continuous=False):
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
            
            # Se la stringa è vuota o contiene errori di trascrizione, salta il ciclo
            if not spoken_text or spoken_text.startswith("Errore"):
                continue

            text_clean = spoken_text.strip().lower()
            
            # Lista nera di frasi che Google sputa fuori quando c'è silenzio o rumore bianco
            ignore_phrases = [
                "non ho sentito nulla", 
                "non ho capito cosa hai detto", 
                "non ho capito", 
                "sottotitoli e revisione a cura di",
                "sottotitoli creati dalla comunità",
                "am", "oh", "eh", ""
            ]
            
            if text_clean in ignore_phrases or (len(text_clean) <= 2 and text_clean not in ("sì", "si", "no", "ok")):
                continue  # Ignora completamente il rumore di fondo o il silenzio!

            # Se siamo arrivati qui, è una frase reale pronunciata dall'utente
            if self.continuous:
                self._paused = True
                self.speech_detected.emit(spoken_text)
            else:
                self.finished.emit(spoken_text)
                break
            
            if not self.continuous:
                break

    def pause(self):
        self._paused = True

    def resume(self):
        time.sleep(0.4) # Ritardo di sicurezza contro l'eco delle casse
        self._paused = False

    def stop(self):
        self._is_running = False


class StarkHUD(QMainWindow):
    mail_alert = pyqtSignal(str)   # avviso di nuova email importante (dal thread di monitoraggio)
    learned = pyqtSignal(str)      # Jarvis ha memorizzato qualcosa

    def __init__(self):
        super().__init__()

        self.setWindowTitle("J.A.R.V.I.S. // STARK INDUSTRIES MARK.I")
        self.setGeometry(100, 100, 1150, 750)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.brain = LocalBrain()
        self.speaker = Speaker()
        self.listener = Listener()
        threading.Thread(target=self.listener.warmup, daemon=True).start()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        self.hud_container = QFrame()
        self.hud_container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(10, 15, 28, 220);
                border: 2px solid {CORE_COLOR_HEX};
                border-radius: 15px;
            }}
        """)
        self.hud_layout = QVBoxLayout(self.hud_container)
        self.hud_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.addWidget(self.hud_container)

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(25)
        glow.setColor(CORE_COLOR)
        glow.setOffset(0, 0)
        self.hud_container.setGraphicsEffect(glow)

        self.setup_ui()
        self.init_animations()
        self.old_pos = self.pos()

        self.is_continuous_active = False
        self.continuous_worker = None

        self.append_chat("JARVIS", "Sistemi operativi Mark.I online., Signore.")

        # Posta e memoria: i callback arrivano da altri thread, quindi passano da segnali Qt
        self.mail_alert.connect(self.on_mail_alert)
        self.learned.connect(self.on_learned)
        self.brain.on_learned = self.learned.emit
        if self.brain.start_mail_watcher(self.mail_alert.emit):
            self.append_chat("JARVIS", "Monitoraggio della posta attivo, Signore.")

    def setup_ui(self):
        header_layout = QHBoxLayout()
        self.hud_layout.addLayout(header_layout)

        self.core_icon = QLabel()
        spin_icon = qta.icon('fa5s.atom', color=CORE_COLOR_HEX)
        self.core_icon.setPixmap(spin_icon.pixmap(QSize(50, 50)))
        header_layout.addWidget(self.core_icon)

        title_v_layout = QVBoxLayout()
        self.title_label = QLabel("⚡ J.A.R.V.I.S.")
        self.title_label.setFont(QFont(FONT_FAMILY, 24, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {CORE_COLOR_HEX}; border: none; background: transparent;")
        
        self.status_label = QLabel("NEURAL CORE: ONLINE // MANUAL MODE")
        self.status_label.setFont(QFont(FONT_FAMILY, 10))
        self.status_label.setStyleSheet("color: #00ff88; border: none; background: transparent;")
        
        title_v_layout.addWidget(self.title_label)
        title_v_layout.addWidget(self.status_label)
        header_layout.addLayout(title_v_layout)

        header_layout.addStretch()

        self.min_btn = QPushButton()
        self.min_btn.setIcon(qta.icon('fa5s.minus', color=CORE_COLOR_HEX))
        self.min_btn.setFixedSize(35, 35)
        self.min_btn.setStyleSheet(f"""
            QPushButton {{ 
                background-color: rgba(0, 243, 255, 30); 
                border: 1px solid {CORE_COLOR_HEX}; 
                border-radius: 17px; 
            }}
            QPushButton:hover {{ background-color: rgba(0, 243, 255, 100); }}
        """)
        self.min_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.min_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(qta.icon('fa5s.times', color="#ff4444"))
        self.close_btn.setFixedSize(35, 35)
        self.close_btn.setStyleSheet("""
            QPushButton { 
                background-color: rgba(255, 68, 68, 50); 
                border: 1px solid #ff4444; 
                border-radius: 17px; 
            }
            QPushButton:hover { background-color: rgba(255, 68, 68, 150); }
        """)
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn)

        center_layout = QHBoxLayout()
        center_layout.setSpacing(15)
        self.hud_layout.addLayout(center_layout)

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setFont(QFont(FONT_FAMILY, 12))
        self.chat_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(0, 0, 0, 100);
                color: {TEXT_COLOR.name()};
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 15px;
            }}
        """)
        center_layout.addWidget(self.chat_box, stretch=3)

        self.diag_panel = QFrame()
        self.diag_panel.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(11, 17, 32, 150);
                border: 1px solid #1e293b;
                border-radius: 10px;
            }}
            QLabel {{ border: none; background: transparent; color: #94a3b8; font-family: {FONT_FAMILY}; }}
        """)
        diag_layout = QVBoxLayout(self.diag_panel)
        diag_layout.setContentsMargins(15, 15, 15, 15)
        
        diag_title = QLabel("[SYSTEM DIAGNOSTICS]")
        diag_title.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold))
        diag_title.setStyleSheet(f"color: {CORE_COLOR_HEX};")
        diag_layout.addWidget(diag_title)

        sys_info = QLabel(f"OS: {platform.system()}\nArch: {platform.machine()}\nEngine: Ollama Local\nModel: qwen2.5")
        sys_info.setFont(QFont(FONT_FAMILY, 9))
        diag_layout.addWidget(sys_info)

        diag_layout.addStretch()
        center_layout.addWidget(self.diag_panel, stretch=1)

        input_layout = QHBoxLayout()
        self.hud_layout.addLayout(input_layout)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Comando di sistema, ricerca web o conversazione...")
        self.entry.setFont(QFont(FONT_FAMILY, 12))
        self.entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(0, 0, 0, 150);
                color: {CORE_COLOR_HEX};
                border: 1px solid {CORE_COLOR_HEX};
                border-radius: 8px;
                padding: 10px 15px;
            }}
        """)
        self.entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.entry)

        # Pulsante Toggle Ascolto Continuo / Manuale
        self.auto_mic_btn = QPushButton(" HUD: MANUALE")
        self.auto_mic_btn.setIcon(qta.icon('fa5s.broadcast-tower', color="#94a3b8"))
        self.auto_mic_btn.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
        self.auto_mic_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(148, 163, 184, 20);
                color: #94a3b8;
                border: 1px solid #94a3b8;
                border-radius: 8px;
                padding: 10px 15px;
            }
            QPushButton:hover { background-color: rgba(148, 163, 184, 50); color: #ffffff; }
        """)
        self.auto_mic_btn.clicked.connect(self.toggle_continuous_listening)
        input_layout.addWidget(self.auto_mic_btn)

        # Pulsante Singolo (Manuale)
        self.mic_btn = QPushButton(" PARLA")
        self.mic_btn.setIcon(qta.icon('fa5s.microphone', color="#00ff88"))
        self.mic_btn.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 255, 136, 30);
                color: #00ff88;
                border: 1px solid #00ff88;
                border-radius: 8px;
                padding: 10px 15px;
            }
            QPushButton:hover { background-color: rgba(0, 255, 136, 100); color: #ffffff; }
        """)
        self.mic_btn.clicked.connect(self.start_listening)
        input_layout.addWidget(self.mic_btn)

        self.send_btn = QPushButton(" ESEGUI")
        self.send_btn.setIcon(qta.icon('fa5s.paper-plane', color="#ffffff"))
        self.send_btn.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #0e7490;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{ background-color: {CORE_COLOR_HEX}; color: #000000; }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

    def init_animations(self):
        self.core_rotation_timer = QTimer(self)
        self.core_rotation_timer.timeout.connect(self.rotate_core)
        self.core_angle = 0
        self.core_rotation_timer.start(50)

    def rotate_core(self):
        self.core_angle = (self.core_angle + 10) % 360
        spin_icon = qta.icon('fa5s.atom', color=CORE_COLOR_HEX, qta_id=self.core_angle)
        self.core_icon.setPixmap(spin_icon.pixmap(QSize(50, 50)))

    def append_chat(self, sender: str, message: str):
        time_str = time.strftime("%H:%M:%S")
        color = CORE_COLOR_HEX if sender.upper() == "JARVIS" else "#3b82f6"
        prefix = f"<span style='color: {color}; font-weight: bold;'>[{time_str}] >> {sender}:</span> "
        self.chat_box.append(f"{prefix}<span style='color: {TEXT_COLOR.name()};'>{message}</span><br>")
        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())

    def toggle_continuous_listening(self):
        if not self.is_continuous_active:
            self.is_continuous_active = True
            self.auto_mic_btn.setText(" HUD: AUTO")
            self.auto_mic_btn.setIcon(qta.icon('fa5s.broadcast-tower', color="#00ff88"))
            self.auto_mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 255, 136, 30);
                    color: #00ff88;
                    border: 1px solid #00ff88;
                    border-radius: 8px;
                    padding: 10px 15px;
                }
            """)
            self.status_label.setText("NEURAL CORE: CONTINUOUS LISTENING ACTIVE")
            self.status_label.setStyleSheet("color: #00ff88; border: none; background: transparent;")
            
            self.continuous_worker = ListenerWorker(self.listener, continuous=True)
            self.continuous_worker.speech_detected.connect(self.on_continuous_speech_detected)
            self.continuous_worker.start()
        else:
            self.is_continuous_active = False
            self.auto_mic_btn.setText(" HUD: MANUALE")
            self.auto_mic_btn.setIcon(qta.icon('fa5s.broadcast-tower', color="#94a3b8"))
            self.auto_mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(148, 163, 184, 20);
                    color: #94a3b8;
                    border: 1px solid #94a3b8;
                    border-radius: 8px;
                    padding: 10px 15px;
                }
            """)
            self.status_label.setText("NEURAL CORE: ONLINE // MANUAL MODE")
            self.status_label.setStyleSheet("color: #00ff88; border: none; background: transparent;")
            
            if self.continuous_worker:
                self.continuous_worker.stop()

    def on_continuous_speech_detected(self, spoken_text):
        if self.is_continuous_active:
            self.append_chat("USER (VOICE)", spoken_text)
            self.process_command(spoken_text)

    def start_listening(self):
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText(" ASCOLTO...")
        self.status_label.setText("NEURAL CORE: LISTENING...")
        self.status_label.setStyleSheet("color: #ffaa00; border: none; background: transparent;")

        self.listener_worker = ListenerWorker(self.listener, continuous=False)
        self.listener_worker.finished.connect(self.on_listen_finished)
        self.listener_worker.start()

    def on_listen_finished(self, spoken_text):
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText(" PARLA")
        self.status_label.setText("NEURAL CORE: ONLINE")
        self.status_label.setStyleSheet("color: #00ff88; border: none; background: transparent;")

        if spoken_text and not spoken_text.startswith("Errore"):
            self.append_chat("USER (VOICE)", spoken_text)
            self.process_command(spoken_text)
        else:
            self.append_chat("JARVIS", "Non ho sentito nulla, Signore.")

    def send_message(self):
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        if self.is_continuous_active and self.continuous_worker:
            self.continuous_worker.pause()
        self.append_chat("USER", text)
        self.process_command(text)

    def process_command(self, user_text: str):
        self.status_label.setText("NEURAL CORE: PROCESSING...")
        self.status_label.setStyleSheet("color: #00f3ff; border: none; background: transparent;")

        self._reply_started = False
        self.worker = BrainWorker(user_text, self.brain)
        self.worker.sentence.connect(self.on_brain_sentence)
        self.worker.completed.connect(self.on_brain_finished)
        self.worker.start()

    def append_chat_stream(self, sentence: str):
        """Aggiunge le frasi successive nello stesso messaggio di JARVIS."""
        safe = html.escape(sentence)
        if not self._reply_started:
            self._reply_started = True
            time_str = time.strftime("%H:%M:%S")
            prefix = f"<span style='color: {CORE_COLOR_HEX}; font-weight: bold;'>[{time_str}] >> JARVIS:</span> "
            self.chat_box.append(f"{prefix}<span style='color: {TEXT_COLOR.name()};'>{safe}</span>")
        else:
            self.chat_box.moveCursor(QTextCursor.MoveOperation.End)
            self.chat_box.insertHtml(f"<span style='color: {TEXT_COLOR.name()};'>&nbsp;{safe}</span>")
        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())

    def on_brain_sentence(self, sentence: str):
        self.append_chat_stream(sentence)
        self.speaker.speak(sentence, block=False)   # parla subito, senza aspettare il resto

    def on_brain_finished(self):
        status_text = "NEURAL CORE: CONTINUOUS LISTENING ACTIVE" if self.is_continuous_active else "NEURAL CORE: ONLINE"
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet("color: #00ff88; border: none; background: transparent;")

        if self._reply_started:
            self.chat_box.append("")

        def resume_when_silent():
            self.speaker.wait_until_done()
            if self.is_continuous_active and self.continuous_worker:
                self.continuous_worker.resume()

        threading.Thread(target=resume_when_silent, daemon=True).start()

    def on_mail_alert(self, text: str):
        """Avviso vocale per una nuova email importante."""
        self.append_chat("JARVIS", html.escape(text))
        if self.is_continuous_active and self.continuous_worker:
            self.continuous_worker.pause()
        self.speaker.speak(text, block=False)

        def resume_when_silent():
            self.speaker.wait_until_done()
            if self.is_continuous_active and self.continuous_worker:
                self.continuous_worker.resume()

        threading.Thread(target=resume_when_silent, daemon=True).start()

    def on_learned(self, text: str):
        self.append_chat("MEMORIA", html.escape(text))

    def closeEvent(self, event):
        if getattr(self.brain, "watcher", None):
            self.brain.watcher.stop()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.old_pos.isNull():
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = QPoint()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont(FONT_FAMILY, 10))
    window = StarkHUD()
    window.show()
    sys.exit(app.exec())