import sys
import platform
import time
import threading
import html
import random
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTextEdit, QPlainTextEdit, QLineEdit, 
                             QPushButton, QFrame, QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QTextCursor
import qtawesome as qta

from modules.brain import LocalBrain
from modules.speaker import Speaker
from modules.listener import Listener

# Palette Cyber-Stark (Ciano Olografico + Magenta/Neon Accents)
CYAN_CORE = QColor(0, 243, 255)
CYAN_HEX = "#00f3ff"
MAGENTA_CYBER = QColor(255, 0, 127)
MAGENTA_HEX = "#ff007f"
TEXT_COLOR = QColor(200, 255, 255)
FONT_FAMILY = "Consolas"


class BrainWorker(QThread):
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
            
            if not self.continuous:
                break

    def pause(self):
        self._paused = True

    def resume(self):
        time.sleep(0.4)
        self._paused = False

    def stop(self):
        self._is_running = False


class StarkHUD(QMainWindow):
    mail_alert = pyqtSignal(str)
    learned = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("J.A.R.V.I.S. // CYBER-STARK PROTOCOL v2.5")
        
        width, height = 1200, 780
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        
        self.setGeometry(x, y, width, height)
        self.setMinimumSize(900, 600)
        
        self.setStyleSheet("QMainWindow { background-color: #030508; }")

        # Etichetta utente dinamica (inizialmente TU, cambia se ti presenti)
        self.user_label = "TU"

        self.brain = LocalBrain()
        self.speaker = Speaker()
        self.listener = Listener()
        threading.Thread(target=self.listener.warmup, daemon=True).start()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(15, 15, 15, 15)

        self.hud_container = QFrame()
        self.hud_container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(5, 10, 20, 240);
                border: 2px solid {CYAN_HEX};
                border-radius: 12px;
            }}
        """)
        self.hud_layout = QVBoxLayout(self.hud_container)
        self.hud_layout.setContentsMargins(18, 18, 18, 18)
        self.main_layout.addWidget(self.hud_container)

        self.glow = QGraphicsDropShadowEffect()
        self.glow.setBlurRadius(30)
        self.glow.setColor(CYAN_CORE)
        self.glow.setOffset(0, 0)
        self.hud_container.setGraphicsEffect(self.glow)

        self.setup_ui()
        self.init_animations()
        self.apply_windows_dark_mode()

        self.is_continuous_active = False
        self.continuous_worker = None

        self.append_chat("JARVIS", "Sistemi neurali Cyber-Stark online. Identificazione utente in attesa...")

        self.mail_alert.connect(self.on_mail_alert)
        self.learned.connect(self.on_learned)
        self.brain.on_learned = self.learned.emit
        if self.brain.start_mail_watcher(self.mail_alert.emit):
            self.append_chat("JARVIS", "Sub-processo di sorveglianza mail attivo.")

    def apply_windows_dark_mode(self):
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = int(self.winId())
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

    def setup_ui(self):
        header_layout = QHBoxLayout()
        self.hud_layout.addLayout(header_layout)

        self.core_icon = QLabel()
        spin_icon = qta.icon('fa5s.atom', color=CYAN_HEX)
        self.core_icon.setPixmap(spin_icon.pixmap(QSize(55, 55)))
        header_layout.addWidget(self.core_icon)

        title_v_layout = QVBoxLayout()
        self.title_label = QLabel("⚡ J.A.R.V.I.S. // NET-RUNNER HUD")
        self.title_label.setFont(QFont(FONT_FAMILY, 22, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {CYAN_HEX}; border: none; background: transparent; letter-spacing: 1px;")
        
        self.status_label = QLabel("STATUS: [ACTIVE] // NEURAL LINK STABLE")
        self.status_label.setFont(QFont(FONT_FAMILY, 9, QFont.Weight.Bold))
        self.status_label.setStyleSheet(f"color: {MAGENTA_HEX}; border: none; background: transparent;")
        
        title_v_layout.addWidget(self.title_label)
        title_v_layout.addWidget(self.status_label)
        header_layout.addLayout(title_v_layout)

        header_layout.addStretch()

        center_layout = QHBoxLayout()
        center_layout.setSpacing(15)
        self.hud_layout.addLayout(center_layout)

        # Chat box principale (a sinistra)
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setFont(QFont(FONT_FAMILY, 11))
        self.chat_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(2, 5, 12, 220);
                color: {TEXT_COLOR.name()};
                border: 1px solid rgba(0, 243, 255, 100);
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        center_layout.addWidget(self.chat_box, stretch=3)

        # Colonna di destra: Terminale ultraveloce SOPRA + Pannello Diagnostico SOTTO (centrato)
        right_column_layout = QVBoxLayout()
        right_column_layout.setSpacing(8)
        center_layout.addLayout(right_column_layout, stretch=1)

        # 1. Terminale / Codice Casuale
        self.code_stream_box = QPlainTextEdit()
        self.code_stream_box.setReadOnly(True)
        self.code_stream_box.setFont(QFont(FONT_FAMILY, 8))
        self.code_stream_box.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: rgba(1, 3, 8, 240);
                color: #00ff88;
                border: 1px solid {MAGENTA_HEX};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        self.code_stream_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.code_stream_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_column_layout.addWidget(self.code_stream_box, stretch=2)

        # 2. Pannello Diagnostico
        self.diag_panel = QFrame()
        self.diag_panel.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(8, 15, 30, 180);
                border: 1px solid {CYAN_HEX};
                border-radius: 8px;
            }}
            QLabel {{ border: none; background: transparent; color: #a5f3fc; font-family: {FONT_FAMILY}; }}
        """)
        diag_layout = QVBoxLayout(self.diag_panel)
        diag_layout.setContentsMargins(6, 6, 6, 6)
        diag_layout.setSpacing(0)
        
        full_diag_text = (
            f"<div style='text-align: center;'>"
            f"<span style='color: {CYAN_HEX}; font-weight: bold;'>⚙ &nbsp; [SYSTEM DIAGNOSTICS]</span><br>"
            f"<div style='margin-top: 6px; font-size: 8pt; color: #a5f3fc;'>"
            f"OS: {platform.system()} ({platform.machine()})<br>"
            f"CORE: OLLAMA / QWEN<br>"
            f"REACTOR: STARK-ARC [99.8%]<br>"
            f"NEURAL SYNC: 142.5 MHz<br>"
            f"MEMORY BUFF: OPTIMIZED<br>"
            f"ENCRYPTION: AES-256-GCM<br>"
            f"STATUS: SECURE // ONLINE"
            f"</div>"
            f"</div>"
        )
        
        diag_label = QLabel(full_diag_text)
        diag_layout.addWidget(diag_label)
        
        right_column_layout.addWidget(self.diag_panel, stretch=1)

        # Barra di input e pulsanti inferiori
        input_layout = QHBoxLayout()
        self.hud_layout.addLayout(input_layout)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Inserisci comando di sistema o query neurale...")
        self.entry.setFont(QFont(FONT_FAMILY, 11))
        self.entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(2, 5, 12, 200);
                color: {CYAN_HEX};
                border: 1px solid {CYAN_HEX};
                border-radius: 6px;
                padding: 10px 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {MAGENTA_HEX};
            }}
        """)
        self.entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.entry)

        self.auto_mic_btn = QPushButton(" HUD: MANUALE")
        self.auto_mic_btn.setFont(QFont(FONT_FAMILY, 9, QFont.Weight.Bold))
        self.auto_mic_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 0, 127, 20);
                color: {MAGENTA_HEX};
                border: 1px solid {MAGENTA_HEX};
                border-radius: 6px;
                padding: 10px 14px;
            }}
            QPushButton:hover {{ background-color: rgba(255, 0, 127, 80); color: #ffffff; }}
        """)
        self.auto_mic_btn.clicked.connect(self.toggle_continuous_listening)
        input_layout.addWidget(self.auto_mic_btn)

        self.mic_btn = QPushButton(" PARLA")
        self.mic_btn.setFont(QFont(FONT_FAMILY, 9, QFont.Weight.Bold))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 255, 136, 20);
                color: #00ff88;
                border: 1px solid #00ff88;
                border-radius: 6px;
                padding: 10px 14px;
            }
            QPushButton:hover { background-color: rgba(0, 255, 136, 80); color: #ffffff; }
        """)
        self.mic_btn.clicked.connect(self.start_listening)
        input_layout.addWidget(self.mic_btn)

        self.send_btn = QPushButton(" ESEGUI")
        self.send_btn.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CYAN_HEX};
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
            }}
            QPushButton:hover {{ background-color: {MAGENTA_HEX}; color: #ffffff; }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

    def check_user_name(self, text: str):
        """Intercetta se l'utente dice il proprio nome e aggiorna l'etichetta."""
        t_lower = text.lower()
        name_to_set = None
        if "mi chiamo" in t_lower:
            parts = t_lower.split("mi chiamo")
            if len(parts) > 1:
                name_to_set = parts[1].strip().split()[0].capitalize()
        elif "il mio nome è" in t_lower:
            parts = t_lower.split("il mio nome è")
            if len(parts) > 1:
                name_to_set = parts[1].strip().split()[0].capitalize()
        
        if name_to_set and len(name_to_set) > 1:
            self.user_label = name_to_set
            self.append_chat("JARVIS", f"Identificazione completata. Utente riconosciuto: {self.user_label}. Benvenuto, Signore.")

    def init_animations(self):
        self.core_rotation_timer = QTimer(self)
        self.core_rotation_timer.timeout.connect(self.animate_hud)
        self.core_angle = 0
        self.pulse_state = True
        self.core_rotation_timer.start(80)

        self.code_stream_timer = QTimer(self)
        self.code_stream_timer.timeout.connect(self.append_random_code_line)
        self.code_stream_timer.start(150)

    def animate_hud(self):
        self.core_angle = (self.core_angle + 12) % 360
        spin_icon = qta.icon('fa5s.atom', color=CYAN_HEX, qta_id=self.core_angle)
        self.core_icon.setPixmap(spin_icon.pixmap(QSize(55, 55)))

        self.pulse_state = not self.pulse_state
        blur_val = 28 if self.pulse_state else 33
        self.glow.setBlurRadius(blur_val)

    def append_random_code_line(self):
        snippets = [
            "0x7F8E: parse_neural_packet()",
            "OVERRIDE_CORE_FREQ(9400.0)",
            "STARK_OS // secure_tunnel_open",
            "exec_bytecode(0x04FF) -> OK",
            "sync_matrix_node(cluster_b)",
            "bypass_firewall_subroutine()",
            "ALLOCATE_MEM_BUFFER(1024KB)",
            "ai_tensor_weights_loaded[QWEN]",
            "SCANNING_LOCAL_GRID...",
            "vector_matrix_mult(0x9A, 0x11)",
            "daemon_thread_status: RUNNING"
        ]
        line = random.choice(snippets)
        timestamp = time.strftime("%H:%M:%S")
        text_line = f"[{timestamp}] {line}"
        
        self.code_stream_box.appendPlainText(text_line)
        
        doc = self.code_stream_box.document()
        if doc.blockCount() > 25:
            cursor = self.code_stream_box.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
            
        self.code_stream_box.verticalScrollBar().setValue(self.code_stream_box.verticalScrollBar().maximum())

    def inject_easter_egg_code(self, user_text: str):
        timestamp = time.strftime("%H:%M:%S")
        text_line = f"[{timestamp}] >> INJECTED: \"{user_text}\""
        self.code_stream_box.appendPlainText(text_line)
        self.code_stream_box.verticalScrollBar().setValue(self.code_stream_box.verticalScrollBar().maximum())

    def append_chat(self, sender: str, message: str):
        time_str = time.strftime("%H:%M:%S")
        # Se il mittente è l'utente, usa l'etichetta dinamica (es. TU oppure ANDREA)
        display_sender = self.user_label if sender.upper() in ["USER", "USER (VOICE)"] else sender
        color = CYAN_HEX if display_sender.upper() == "JARVIS" else MAGENTA_HEX
        prefix = f"<span style='color: {color}; font-weight: bold;'>[{time_str}] >> {display_sender}:</span> "
        self.chat_box.append(f"{prefix}<span style='color: {TEXT_COLOR.name()};'>{message}</span><br>")
        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())

    def toggle_continuous_listening(self):
        if not self.is_continuous_active:
            self.is_continuous_active = True
            self.auto_mic_btn.setText(" HUD: AUTO")
            self.auto_mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(0, 255, 136, 40);
                    color: #00ff88;
                    border: 1px solid #00ff88;
                    border-radius: 6px;
                    padding: 10px 14px;
                }}
            """)
            self.status_label.setText("STATUS: [ACTIVE] // CONTINUOUS LISTENING RUNNING")
            
            self.continuous_worker = ListenerWorker(self.listener, continuous=True)
            self.continuous_worker.speech_detected.connect(self.on_continuous_speech_detected)
            self.continuous_worker.start()
        else:
            self.is_continuous_active = False
            self.auto_mic_btn.setText(" HUD: MANUALE")
            self.auto_mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 0, 127, 20);
                    color: {MAGENTA_HEX};
                    border: 1px solid {MAGENTA_HEX};
                    border-radius: 6px;
                    padding: 10px 14px;
                }}
            """)
            self.status_label.setText("STATUS: [ACTIVE] // MANUAL MODE")
            
            if self.continuous_worker:
                self.continuous_worker.stop()

    def on_continuous_speech_detected(self, spoken_text):
        if self.is_continuous_active:
            self.check_user_name(spoken_text)
            self.inject_easter_egg_code(spoken_text)
            self.append_chat("USER", spoken_text)
            self.process_command(spoken_text)

    def start_listening(self):
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText(" ASCOLTO...")
        self.status_label.setText("STATUS: [LISTENING]...")

        self.listener_worker = ListenerWorker(self.listener, continuous=False)
        self.listener_worker.finished.connect(self.on_listen_finished)
        self.listener_worker.start()

    def on_listen_finished(self, spoken_text):
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText(" PARLA")
        self.status_label.setText("STATUS: [ACTIVE] // ONLINE")

        if spoken_text and not spoken_text.startswith("Errore"):
            self.check_user_name(spoken_text)
            self.inject_easter_egg_code(spoken_text)
            self.append_chat("USER", spoken_text)
            self.process_command(spoken_text)
        else:
            self.append_chat("JARVIS", "Nessun input vocale registrato, Signore.")

    def send_message(self):
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        if self.is_continuous_active and self.continuous_worker:
            self.continuous_worker.pause()
        
        self.check_user_name(text)
        self.inject_easter_egg_code(text)
        self.append_chat("USER", text)
        self.process_command(text)

    def process_command(self, user_text: str):
        self.status_label.setText("STATUS: [PROCESSING NEURAL QUERY]...")

        self._reply_started = False
        self.worker = BrainWorker(user_text, self.brain)
        self.worker.sentence.connect(self.on_brain_sentence)
        self.worker.completed.connect(self.on_brain_finished)
        self.worker.start()

    def append_chat_stream(self, sentence: str):
        safe = html.escape(sentence)
        if not self._reply_started:
            self._reply_started = True
            time_str = time.strftime("%H:%M:%S")
            prefix = f"<span style='color: {CYAN_HEX}; font-weight: bold;'>[{time_str}] >> JARVIS:</span> "
            self.chat_box.append(f"{prefix}<span style='color: {TEXT_COLOR.name()};'>{safe}</span>")
        else:
            self.chat_box.moveCursor(QTextCursor.MoveOperation.End)
            self.chat_box.insertHtml(f"<span style='color: {TEXT_COLOR.name()};'>&nbsp;{safe}</span>")
        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())

    def on_brain_sentence(self, sentence: str):
        self.append_chat_stream(sentence)
        self.speaker.speak(sentence, block=False)

    def on_brain_finished(self):
        status_text = "STATUS: [ACTIVE] // CONTINUOUS LISTENING RUNNING" if self.is_continuous_active else "STATUS: [ACTIVE] // ONLINE"
        self.status_label.setText(status_text)

        if self._reply_started:
            self.chat_box.append("")

        def resume_when_silent():
            self.speaker.wait_until_done()
            if self.is_continuous_active and self.continuous_worker:
                self.continuous_worker.resume()

        threading.Thread(target=resume_when_silent, daemon=True).start()

    def on_mail_alert(self, text: str):
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont(FONT_FAMILY, 10))
    window = StarkHUD()
    window.show()
    sys.exit(app.exec())