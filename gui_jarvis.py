"""J.A.R.V.I.S. HUD - interfaccia in stile film (Iron Man).

Nucleo centrale ad anelli animati che reagisce a voce, ascolto ed elaborazione, pannelli olografici con
telemetria reale del PC, registro eventi e canale di comunicazione. Usa gli stessi moduli di prima
(LocalBrain, Speaker, Listener) e mantiene tutte le funzioni: ascolto continuo, ascolto singolo,
nome utente, avvisi posta, memoria.

Per usarla: in main.py   from gui_jarvis import JarvisHUD as StarkHUD
"""
import sys
import time
import math
import html
import logging
import platform
import threading
from collections import deque

import psutil
import requests

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QLineEdit, QPushButton, QSizeGrip, QFrame)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import (QFont, QColor, QPainter, QPen, QBrush, QRadialGradient, QLinearGradient,
                         QTextCursor, QFontMetricsF)

from modules.brain import LocalBrain
from modules.speaker import Speaker
from modules.listener import Listener

# ----------------------------------------------------------------------------- palette
CYAN = (0, 229, 255)
ICE = (205, 248, 255)
DIM = (96, 156, 176)
AMBER = (255, 176, 46)
RED = (255, 72, 72)

CYAN_HEX, ICE_HEX, DIM_HEX, AMBER_HEX = "#00e5ff", "#cdf8ff", "#609cb0", "#ffb02e"

STATE_COLORS = {
    "idle": (0, 229, 255),
    "listening": (64, 255, 214),
    "thinking": (255, 186, 64),
    "speaking": (150, 238, 255),
    "alert": (255, 150, 40),
    "offline": (255, 72, 72),
}
STATE_LABELS = {
    "idle": "SISTEMA ONLINE",
    "listening": "IN ASCOLTO",
    "thinking": "ELABORAZIONE",
    "speaking": "RISPOSTA IN CORSO",
    "alert": "NUOVA COMUNICAZIONE",
    "offline": "NUCLEO NEURALE OFFLINE",
}
# velocità di rotazione degli anelli per stato
STATE_SPEED = {"idle": 1.0, "listening": 1.5, "thinking": 3.2, "speaking": 1.9, "alert": 4.0, "offline": 0.15}

DAYS = ["LUNEDÌ", "MARTEDÌ", "MERCOLEDÌ", "GIOVEDÌ", "VENERDÌ", "SABATO", "DOMENICA"]
MONTHS = ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO",
          "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"]

STYLE = """
QMainWindow { background-color: #02060d; }
QLabel { color: #cdf8ff; background: transparent; }
QTextEdit { background: transparent; border: none; color: #cdf8ff;
            selection-background-color: rgba(0, 229, 255, 90); }
QLineEdit { background: rgba(0, 229, 255, 14); color: #cdf8ff; border: none;
            border-bottom: 2px solid rgba(0, 229, 255, 160); padding: 10px 14px;
            selection-background-color: rgba(0, 229, 255, 90); }
QLineEdit:focus { background: rgba(0, 229, 255, 26); border-bottom: 2px solid #00e5ff; }
QPushButton { background: rgba(0, 229, 255, 14); color: #00e5ff; border: 1px solid rgba(0, 229, 255, 150);
              padding: 9px 18px; font-weight: bold; }
QPushButton:hover { background: rgba(0, 229, 255, 60); color: #ffffff; }
QPushButton:pressed { background: rgba(0, 229, 255, 110); }
QPushButton:disabled { color: rgba(0, 229, 255, 90); border: 1px solid rgba(0, 229, 255, 60); }
QPushButton#winbtn { border: none; background: transparent; padding: 4px 12px; color: #609cb0; }
QPushButton#winbtn:hover { background: rgba(0, 229, 255, 40); color: #ffffff; }
QPushButton#closebtn { border: none; background: transparent; padding: 4px 12px; color: #609cb0; }
QPushButton#closebtn:hover { background: rgba(255, 72, 72, 150); color: #ffffff; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(0, 229, 255, 110); border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #06202e; color: #cdf8ff; border: 1px solid #00e5ff; }
"""

AUTO_ON_STYLE = ("QPushButton { background: rgba(64, 255, 214, 60); color: #40ffd6; "
                 "border: 1px solid #40ffd6; padding: 9px 18px; font-weight: bold; }"
                 "QPushButton:hover { background: rgba(64, 255, 214, 100); color: #ffffff; }")


# ----------------------------------------------------------------------------- utilità di disegno
def col(c, a=255) -> QColor:
    """Tupla (r, g, b) + alpha -> QColor. PyQt6 vuole interi: niente float."""
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(max(0, min(255, a))))


def make_font(size: float, bold: bool = False, mono: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(["Consolas", "Cascadia Mono", "Courier New"] if mono
                  else ["Bahnschrift", "Segoe UI", "Arial"])
    f.setPointSizeF(float(size))
    f.setBold(bool(bold))
    return f


def fmt_rate(bps: float) -> str:
    return f"{bps / 1e6:.1f} MB/s" if bps >= 1e6 else f"{bps / 1e3:.0f} KB/s"


def spaced(text: str) -> str:
    """'IN ASCOLTO' -> 'I N   A S C O L T O' (spaziatura da HUD senza dipendere dai font)."""
    return "  ".join(" ".join(word) for word in text.split(" "))


def make_pen(c, a, width) -> QPen:
    pen = QPen(col(c, a), float(width))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


class SafePaint(QWidget):
    """Base: se il disegno solleva un errore lo registra una volta sola invece di rompere la finestra."""

    _paint_broken = False

    def paintEvent(self, event):
        if self._paint_broken:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self.draw(painter, float(self.width()), float(self.height()))
        except Exception:
            self._paint_broken = True
            logging.exception("Errore nel disegno di %s", type(self).__name__)
        finally:
            painter.end()

    def draw(self, p: QPainter, w: float, h: float):
        raise NotImplementedError


# ----------------------------------------------------------------------------- nucleo centrale
class ArcCore(SafePaint):
    """Il cuore dell'HUD: anelli concentrici animati + anello d'onda che reagisce a voce/microfono."""

    N_BARS = 84
    N_TICKS = 120

    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 380)
        self.t = 0.0
        self.spin = 0.0                      # tempo "di rotazione": avanza più veloce quando Jarvis elabora
        self.speed = 1.0
        self.state = "idle"
        self.level = 0.0
        self.caption = STATE_LABELS["idle"]
        self.color = [float(x) for x in STATE_COLORS["idle"]]
        self.bars = [0.0] * self.N_BARS
        self._f_small = make_font(7.5, mono=True)
        self._f_caption = make_font(11, bold=True)

    # ---- animazione (chiamata dal timer della finestra)
    def step(self, dt: float, state: str, level: float, caption: str):
        self.t += dt
        self.state = state
        self.caption = caption
        target = STATE_COLORS.get(state, STATE_COLORS["idle"])
        k = min(1.0, dt * 6.0)
        for i in range(3):
            self.color[i] += (target[i] - self.color[i]) * k
        self.speed += (STATE_SPEED.get(state, 1.0) - self.speed) * min(1.0, dt * 3.0)
        self.spin += dt * self.speed
        self.level += (level - self.level) * min(1.0, dt * 14.0)

        t, n = self.t, self.N_BARS
        for i in range(n):
            if state == "speaking":
                base = self.level * (0.30 + 0.70 * abs(math.sin(i * 0.71 + t * 9.0) * math.sin(i * 0.23 - t * 5.0)))
            elif state == "listening":
                base = 0.05 + self.level * (0.35 + 0.65 * abs(math.sin(i * 0.93 + t * 13.0)))
            elif state == "thinking":
                base = 0.12 + 0.50 * max(0.0, math.sin(2 * math.pi * i / n * 3 - t * 6.0)) ** 2
            elif state == "alert":
                base = 0.20 + 0.35 * abs(math.sin(t * 8.0 + i * 0.35))
            elif state == "offline":
                base = 0.02
            else:
                base = 0.035 + 0.025 * math.sin(i * 0.5 + t * 1.6)
            self.bars[i] += (max(0.0, min(1.0, base)) - self.bars[i]) * 0.35

    # ---- primitive
    @staticmethod
    def _circle(p, cx, cy, r, c, a, width):
        p.setPen(make_pen(c, a, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), float(r), float(r))

    @staticmethod
    def _arc(p, cx, cy, r, start_deg, span_deg, c, a, width, glow=True):
        rect = QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if glow:                                               # alone: due passate larghe e trasparenti
            p.setPen(make_pen(c, a * 0.10, width * 3.2))
            p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))
            p.setPen(make_pen(c, a * 0.22, width * 1.9))
            p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))
        p.setPen(make_pen(c, a, width))
        p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))

    @staticmethod
    def _radial(p, cx, cy, r0, r1, ang, c, a, width):
        ca, sa = math.cos(ang), math.sin(ang)
        p.setPen(make_pen(c, a, width))
        p.drawLine(QPointF(cx + ca * r0, cy + sa * r0), QPointF(cx + ca * r1, cy + sa * r1))

    # ---- disegno
    def draw(self, p: QPainter, w: float, h: float):
        cx, cy = w / 2.0, h / 2.0 - 14.0
        R = max(60.0, min(w, h - 44.0) / 2.0 - 8.0)
        c = (int(self.color[0]), int(self.color[1]), int(self.color[2]))
        sp = self.spin
        pulse = 0.5 + 0.5 * math.sin(self.t * 2.2)
        energy = 0.35 + 0.65 * self.level if self.state in ("speaking", "listening") else 0.5 + 0.2 * pulse

        # alone esterno
        halo = QRadialGradient(QPointF(cx, cy), float(R * 1.12))
        halo.setColorAt(0.55, col(c, 0))
        halo.setColorAt(0.86, col(c, 22 + 26 * energy))
        halo.setColorAt(1.0, col(c, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), float(R * 1.12), float(R * 1.12))

        # 1) anello di tacche (ruota lentamente)
        off = math.radians(sp * 5.0)
        for i in range(self.N_TICKS):
            ang = 2 * math.pi * i / self.N_TICKS + off
            major = (i % 10 == 0)
            mid = (i % 5 == 0)
            r0 = R * (0.935 if major else 0.955 if mid else 0.965)
            self._radial(p, cx, cy, r0, R * 0.99, ang, c, 190 if major else 120 if mid else 70, 2.0 if major else 1.2)

        # 2) gradi ai quattro punti cardinali
        p.setFont(self._f_small)
        fm = QFontMetricsF(self._f_small)
        for deg, lab in ((0, "000"), (90, "090"), (180, "180"), (270, "270")):
            ang = math.radians(deg - 90)
            tx = cx + math.cos(ang) * R * 0.895 - fm.horizontalAdvance(lab) / 2.0
            ty = cy + math.sin(ang) * R * 0.895 + 3.0
            p.setPen(make_pen(c, 130, 1))
            p.drawText(QPointF(tx, ty), lab)

        # 3) tre archi spessi (ruotano in senso opposto)
        base = -sp * 14.0
        for k in range(3):
            self._arc(p, cx, cy, R * 0.82, base + k * 120.0, 78.0, c, 215, 3.6)

        # 4) cerchio sottile + nodi
        self._circle(p, cx, cy, R * 0.755, c, 75, 1.2)
        for k in range(8):
            ang = 2 * math.pi * k / 8 + math.radians(sp * 9.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col(c, 200)))
            p.drawEllipse(QPointF(cx + math.cos(ang) * R * 0.755, cy + math.sin(ang) * R * 0.755), 2.6, 2.6)

        # 5) anello tratteggiato
        d0 = sp * 22.0
        for k in range(36):
            self._arc(p, cx, cy, R * 0.70, d0 + k * 10.0, 5.0, c, 150, 2.0, glow=False)

        # 6) anello d'onda: reagisce alla voce
        n = self.N_BARS
        r_base = R * 0.50
        for i in range(n):
            ang = 2 * math.pi * i / n - math.pi / 2.0
            length = R * (0.012 + 0.165 * self.bars[i])
            a = 105 + 150 * self.bars[i]
            self._radial(p, cx, cy, r_base, r_base + length, ang, c, a, 2.4)

        # 7) anello interno + triangoli
        self._circle(p, cx, cy, R * 0.465, c, 130, 1.6)
        self._arc(p, cx, cy, R * 0.40, sp * 30.0, 100.0, c, 190, 2.2)
        self._arc(p, cx, cy, R * 0.40, sp * 30.0 + 180.0, 100.0, c, 190, 2.2)
        for k in range(6):
            ang = 2 * math.pi * k / 6 - math.radians(sp * 16.0)
            r_t = R * 0.545
            tip = QPointF(cx + math.cos(ang) * (r_t - 8.0), cy + math.sin(ang) * (r_t - 8.0))
            left = QPointF(cx + math.cos(ang - 0.07) * r_t * 0.99, cy + math.sin(ang - 0.07) * r_t * 0.99)
            right = QPointF(cx + math.cos(ang + 0.07) * r_t * 0.99, cy + math.sin(ang + 0.07) * r_t * 0.99)
            p.setPen(make_pen(c, 150, 1.4))
            p.drawLine(left, tip)
            p.drawLine(tip, right)

        # 8) nucleo luminoso (respira; con la voce si accende)
        core_r = R * (0.30 + 0.035 * pulse + 0.07 * self.level)
        core = QRadialGradient(QPointF(cx, cy), float(core_r * 1.5))
        white = 255 if self.state in ("speaking", "alert") else 215
        core.setColorAt(0.0, QColor(white, 255, 255, int(235 * min(1.0, 0.55 + energy))))
        core.setColorAt(0.28, col(c, 200))
        core.setColorAt(0.62, col(c, 70))
        core.setColorAt(1.0, col(c, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), float(core_r * 1.5), float(core_r * 1.5))
        self._circle(p, cx, cy, core_r * 0.62, c, 170, 1.6)

        # 9) didascalia dello stato
        text = spaced(self.caption)
        p.setFont(self._f_caption)
        fm2 = QFontMetricsF(self._f_caption)
        p.setPen(make_pen(c, 235, 1))
        p.drawText(QPointF(cx - fm2.horizontalAdvance(text) / 2.0, cy + R + 30.0), text)


# ----------------------------------------------------------------------------- sfondo
class HudBackground(SafePaint):
    """Sfondo scuro con griglia, fascio di scansione e cornice ad angoli."""

    def __init__(self):
        super().__init__()
        self.t = 0.0

    def draw(self, p: QPainter, w: float, h: float):
        bg = QRadialGradient(QPointF(w * 0.5, h * 0.46), float(max(w, h) * 0.78))
        bg.setColorAt(0.0, QColor(7, 32, 48))
        bg.setColorAt(0.55, QColor(3, 13, 24))
        bg.setColorAt(1.0, QColor(1, 4, 9))
        p.fillRect(QRectF(0.0, 0.0, w, h), QBrush(bg))

        p.setPen(make_pen(CYAN, 11, 1))
        step = 48.0
        x = 0.0
        while x < w:
            p.drawLine(QPointF(x, 0.0), QPointF(x, h))
            x += step
        y = 0.0
        while y < h:
            p.drawLine(QPointF(0.0, y), QPointF(w, y))
            y += step

        sy = (self.t * 64.0) % (h + 160.0) - 80.0                  # fascio di scansione
        band = QLinearGradient(QPointF(0.0, sy), QPointF(0.0, sy + 80.0))
        band.setColorAt(0.0, col(CYAN, 0))
        band.setColorAt(0.5, col(CYAN, 16))
        band.setColorAt(1.0, col(CYAN, 0))
        p.fillRect(QRectF(0.0, sy, w, 80.0), QBrush(band))

        m, ln = 8.0, 34.0                                           # cornice ad angoli
        p.setPen(make_pen(CYAN, 210, 2.2))
        for (x0, y0, sx, sy2) in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + sx * ln, y0))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + sy2 * ln))


# ----------------------------------------------------------------------------- pannelli
class HudPanel(SafePaint):
    """Riquadro olografico con angoli smussati e titolo."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 40, 16, 14)
        self.body.setSpacing(8)
        self._f_title = make_font(8.5, bold=True)

    def draw(self, p: QPainter, w: float, h: float):
        cut = 16.0
        p.fillRect(QRectF(0.0, 0.0, w, h), col((3, 14, 24), 150))
        pts = [QPointF(cut, 0.5), QPointF(w - 0.5, 0.5), QPointF(w - 0.5, h - cut), QPointF(w - cut, h - 0.5),
               QPointF(0.5, h - 0.5), QPointF(0.5, cut), QPointF(cut, 0.5)]
        p.setPen(make_pen(CYAN, 120, 1.2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        p.setPen(make_pen(CYAN, 235, 2.4))                           # tratti luminosi agli angoli
        p.drawLine(QPointF(cut, 0.5), QPointF(cut + 26.0, 0.5))
        p.drawLine(QPointF(0.5, cut), QPointF(0.5, cut + 26.0))
        p.drawLine(QPointF(w - 0.5, h - cut - 26.0), QPointF(w - 0.5, h - cut))
        p.drawLine(QPointF(w - cut - 26.0, h - 0.5), QPointF(w - cut, h - 0.5))
        p.fillRect(QRectF(16.0, 17.0, 7.0, 7.0), col(CYAN, 230))     # quadratino + titolo
        p.setFont(self._f_title)
        p.setPen(make_pen(CYAN, 240, 1))
        p.drawText(QPointF(30.0, 25.0), spaced(self.title))
        p.setPen(make_pen(CYAN, 55, 1))
        p.drawLine(QPointF(16.0, 34.0), QPointF(w - 16.0, 34.0))


class RingGauge(SafePaint):
    """Indicatore circolare con percentuale."""

    def __init__(self, label: str):
        super().__init__()
        self.label = label
        self.value = 0.0
        self._shown = 0.0
        self.setFixedSize(84, 100)
        self._f_val = make_font(11, bold=True, mono=True)
        self._f_lab = make_font(7.5, mono=True)

    def set_value(self, v: float):
        self.value = max(0.0, min(100.0, float(v)))
        self._shown += (self.value - self._shown) * 0.6
        self.update()

    def draw(self, p: QPainter, w: float, h: float):
        cx, cy, r = w / 2.0, 42.0, 31.0
        v = self._shown
        c = CYAN if v < 70 else AMBER if v < 90 else RED
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(make_pen(CYAN, 45, 5))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(make_pen(c, 70, 9))
        p.drawArc(rect, 90 * 16, int(-v / 100.0 * 360.0 * 16))
        p.setPen(make_pen(c, 240, 5))
        p.drawArc(rect, 90 * 16, int(-v / 100.0 * 360.0 * 16))
        p.setFont(self._f_val)
        txt = f"{int(round(v))}%"
        fm = QFontMetricsF(self._f_val)
        p.setPen(make_pen(ICE, 255, 1))
        p.drawText(QPointF(cx - fm.horizontalAdvance(txt) / 2.0, cy + 5.0), txt)
        p.setFont(self._f_lab)
        fm2 = QFontMetricsF(self._f_lab)
        p.setPen(make_pen(DIM, 255, 1))
        p.drawText(QPointF(cx - fm2.horizontalAdvance(self.label) / 2.0, 94.0), self.label)


class Sparkline(SafePaint):
    """Storico del carico CPU degli ultimi secondi."""

    def __init__(self, samples: int = 60):
        super().__init__()
        self.samples = samples
        self.data = deque([0.0] * samples, maxlen=samples)
        self.setFixedHeight(54)

    def push(self, v: float):
        self.data.append(max(0.0, min(100.0, float(v))))
        self.update()

    def draw(self, p: QPainter, w: float, h: float):
        p.setPen(make_pen(CYAN, 40, 1))
        p.drawLine(QPointF(0.0, h - 1.0), QPointF(w, h - 1.0))
        p.drawLine(QPointF(0.0, h / 2.0), QPointF(w, h / 2.0))
        n = len(self.data)
        if n < 2:
            return
        dx = w / (n - 1)
        pts = [QPointF(i * dx, (h - 3.0) - (v / 100.0) * (h - 8.0)) for i, v in enumerate(self.data)]
        p.setPen(make_pen(CYAN, 38, 1))
        for pt in pts:
            p.drawLine(QPointF(pt.x(), h - 1.0), pt)
        p.setPen(make_pen(CYAN, 235, 1.6))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)


# ----------------------------------------------------------------------------- barra del titolo
class TopBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(14)

        title = QLabel(spaced("J.A.R.V.I.S."))
        title.setFont(make_font(17, bold=True))
        title.setStyleSheet(f"color: {CYAN_HEX};")
        sub = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        sub.setFont(make_font(7.5, mono=True))
        sub.setStyleSheet(f"color: {DIM_HEX};")
        col_l = QVBoxLayout()
        col_l.setSpacing(0)
        col_l.addWidget(title)
        col_l.addWidget(sub)
        lay.addLayout(col_l)
        lay.addStretch(1)

        self.status_label = QLabel(spaced("LINK NEURALE STABILE"))
        self.status_label.setFont(make_font(9, bold=True, mono=True))
        self.status_label.setStyleSheet(f"color: {DIM_HEX};")
        lay.addWidget(self.status_label)
        lay.addStretch(1)

        self.operator_label = QLabel("OPERATORE: TU")
        self.operator_label.setFont(make_font(8.5, mono=True))
        self.operator_label.setStyleSheet(f"color: {DIM_HEX};")
        lay.addWidget(self.operator_label)

        self.pin_btn = self._wbtn("PIN", "Tieni sempre in primo piano", window.toggle_on_top)
        self.min_btn = self._wbtn("–", "Riduci a icona", window.showMinimized)
        self.max_btn = self._wbtn("□", "Schermo intero (F11)", window.toggle_fullscreen)
        self.close_btn = self._wbtn("✕", "Chiudi", window.close, name="closebtn")
        for b in (self.pin_btn, self.min_btn, self.max_btn, self.close_btn):
            lay.addWidget(b)
        self.setFixedHeight(52)

    @staticmethod
    def _wbtn(text, tip, slot, name="winbtn"):
        b = QPushButton(text)
        b.setObjectName(name)
        b.setToolTip(tip)
        b.setFont(make_font(9, bold=True, mono=True))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.win.windowHandle()
            if handle is not None:
                handle.startSystemMove()                  # trascinamento nativo (compreso lo snap di Windows)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.win.toggle_maximize()


# ----------------------------------------------------------------------------- worker (come prima)
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

    @property
    def is_paused(self) -> bool:
        return self._paused

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
                if not self.continuous:
                    self.finished.emit("")
                    break
                continue

            text_clean = spoken_text.strip().lower()
            ignore_phrases = ["non ho sentito nulla", "non ho capito cosa hai detto", "non ho capito",
                              "sottotitoli e revisione a cura di", "sottotitoli creati dalla comunità",
                              "am", "oh", "eh", ""]
            if text_clean in ignore_phrases or (len(text_clean) <= 2 and text_clean not in ("sì", "si", "no", "ok")):
                if not self.continuous:
                    self.finished.emit("")
                    break
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


# ----------------------------------------------------------------------------- finestra principale
class JarvisHUD(QMainWindow):
    mail_alert = pyqtSignal(str)
    learned = pyqtSignal(str)
    ollama_status = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S.")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1020, 700)
        self.setStyleSheet(STYLE)
        screen = QApplication.primaryScreen().geometry()
        w, h = min(1320, screen.width() - 80), min(820, screen.height() - 80)
        self.setGeometry((screen.width() - w) // 2, (screen.height() - h) // 2, w, h)

        self.user_label = "TU"
        self.brain = LocalBrain()
        self.speaker = Speaker()
        self.listener = Listener()
        threading.Thread(target=self.listener.warmup, daemon=True).start()

        self.is_continuous_active = False
        self.continuous_worker = None
        self.listener_worker = None
        self.worker = None
        self._manual_listening = False
        self._brain_busy = False
        self._reply_started = False
        self._was_speaking = False
        self._running = True
        self.ollama_ok = True
        self.flash_until = 0.0
        self.events = deque(maxlen=7)
        self._state = "idle"
        self._frame = 0
        self._last_tick = time.time()
        self._t0 = time.time()
        self._net_last = None

        self._build_ui()

        self.mail_alert.connect(self.on_mail_alert)
        self.learned.connect(self.on_learned)
        self.ollama_status.connect(self._on_ollama_status)
        self.brain.on_learned = self.learned.emit
        if self.brain.start_mail_watcher(self.mail_alert.emit):
            self.log_event("MAIL WATCH: ATTIVO")

        threading.Thread(target=self._ollama_watch, daemon=True).start()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._tick)
        self.ui_timer.start(33)
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(1000)
        self._update_stats()

        self.append_chat("JARVIS", "Sistemi online. Sono qui: parlami oppure scrivi.")
        self.log_event("SISTEMA AVVIATO")

    # ------------------------------------------------------------------ costruzione interfaccia
    def _build_ui(self):
        self.bg = HudBackground()
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(12)

        self.topbar = TopBar(self)
        root.addWidget(self.topbar)

        mid = QHBoxLayout()
        mid.setSpacing(18)
        root.addLayout(mid, 1)

        # colonna sinistra: sistema + registro eventi
        left_w = QWidget()
        left_w.setFixedWidth(316)
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(14)

        self.sys_panel = HudPanel("SISTEMA")
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setFont(make_font(30, mono=False))
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(f"color: {ICE_HEX};")
        self.date_label = QLabel("")
        self.date_label.setFont(make_font(8, mono=True))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(f"color: {DIM_HEX};")
        self.sys_panel.body.addWidget(self.clock_label)
        self.sys_panel.body.addWidget(self.date_label)

        gauges = QHBoxLayout()
        gauges.setSpacing(2)
        self.g_cpu, self.g_ram, self.g_disk = RingGauge("CPU"), RingGauge("RAM"), RingGauge("DISCO")
        for g in (self.g_cpu, self.g_ram, self.g_disk):
            gauges.addWidget(g)
        self.sys_panel.body.addLayout(gauges)
        self.sys_panel.body.addWidget(self._small_label("CARICO CPU · ULTIMI 60 s"))
        self.spark = Sparkline(60)
        self.sys_panel.body.addWidget(self.spark)
        self.info_label = QLabel("")
        self.info_label.setFont(make_font(8.5, mono=True))
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        self.sys_panel.body.addWidget(self.info_label)
        self.sys_panel.body.addStretch(1)
        left.addWidget(self.sys_panel, 7)

        self.event_panel = HudPanel("REGISTRO EVENTI")
        self.event_label = QLabel("")
        self.event_label.setFont(make_font(8.5, mono=True))
        self.event_label.setTextFormat(Qt.TextFormat.RichText)
        self.event_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self.event_panel.body.addWidget(self.event_label, 1)
        left.addWidget(self.event_panel, 3)
        mid.addWidget(left_w)

        # centro: nucleo
        self.core = ArcCore()
        mid.addWidget(self.core, 1)

        # colonna destra: canale di comunicazione
        right_w = QWidget()
        right_w.setMinimumWidth(350)
        right_w.setMaximumWidth(440)
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 0, 0)
        self.comm_panel = HudPanel("CANALE DI COMUNICAZIONE")
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_box.setFont(make_font(10, mono=True))
        self.comm_panel.body.addWidget(self.chat_box)
        right.addWidget(self.comm_panel)
        mid.addWidget(right_w)

        # barra di input
        row = QHBoxLayout()
        row.setSpacing(10)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Parla oppure scrivi a Jarvis...")
        self.entry.setFont(make_font(11, mono=True))
        self.entry.returnPressed.connect(self.send_message)
        row.addWidget(self.entry, 1)
        self.auto_btn = QPushButton("AUTO")
        self.auto_btn.setToolTip("Ascolto continuo")
        self.mic_btn = QPushButton("PARLA")
        self.mic_btn.setToolTip("Ascolto singolo")
        self.send_btn = QPushButton("INVIA")
        for b in (self.auto_btn, self.mic_btn, self.send_btn):
            b.setFont(make_font(9.5, bold=True, mono=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        self.auto_btn.clicked.connect(self.toggle_continuous_listening)
        self.mic_btn.clicked.connect(self.start_listening)
        self.send_btn.clicked.connect(self.send_message)
        grip = QSizeGrip(self)
        grip.setFixedSize(18, 18)
        grip.setStyleSheet("background: transparent;")
        row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        root.addLayout(row)

    @staticmethod
    def _small_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setFont(make_font(7.5, mono=True))
        lab.setStyleSheet(f"color: {DIM_HEX};")
        return lab

    # ------------------------------------------------------------------ finestra
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_on_top(self):
        on_top = not bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        self.show()                                   # cambiare i flag nasconde la finestra: la riapriamo
        self.topbar.pin_btn.setStyleSheet(f"color: {CYAN_HEX};" if on_top else "")
        self.log_event("PRIMO PIANO: " + ("ON" if on_top else "OFF"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._running = False
        if getattr(self.brain, "watcher", None):
            self.brain.watcher.stop()
        if self.continuous_worker:
            self.continuous_worker.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------ stato e animazione
    def _compute_state(self) -> str:
        if not self.ollama_ok:
            return "offline"
        if time.time() < self.flash_until:
            return "alert"
        if self.speaker.is_speaking:
            return "speaking"
        if self._brain_busy:
            return "thinking"
        lw = self.continuous_worker
        if self.is_continuous_active and lw is not None and not lw.is_paused:
            return "listening"
        if self._manual_listening:
            return "listening"
        return "idle"

    def _compute_level(self, state: str, now: float) -> float:
        if state == "speaking":                       # inviluppo sintetico simile al parlato
            return max(0.0, min(1.0, 0.30 + 0.45 * abs(math.sin(now * 7.3)) * abs(math.sin(now * 2.9 + 1.0))
                                + 0.12 * abs(math.sin(now * 17.0))))
        if state == "listening":
            return max(0.0, min(1.0, float(getattr(self.listener, "level", 0.0))))
        if state == "thinking":
            return 0.5
        return 0.0

    def _tick(self):
        if not self.isVisible() or self.isMinimized():
            self._last_tick = time.time()
            return
        now = time.time()
        dt = max(0.001, min(0.2, now - self._last_tick))
        self._last_tick = now

        state = self._compute_state()
        if state != self._state:
            self._on_state_change(self._state, state)
            self._state = state
        caption = STATE_LABELS[state]
        self.core.step(dt, state, self._compute_level(state, now), caption)
        self.core.update()

        self._frame += 1
        self.bg.t = now - self._t0
        if self._frame % 3 == 0:                      # lo sfondo non serve a 30 fps
            self.bg.update()

    def _on_state_change(self, old: str, new: str):
        if new == "speaking":
            self.log_event("VOCE: RISPOSTA")
        elif new == "listening":
            self.log_event("VOCE: ASCOLTO")
        elif new == "thinking":
            self.log_event("NUCLEO NEURALE: ELABORA")
        elif new == "offline":
            self.log_event("OLLAMA NON RAGGIUNGIBILE")

    # ------------------------------------------------------------------ telemetria
    def _update_stats(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/").percent
        except Exception:
            cpu = ram = disk = 0.0
        self.g_cpu.set_value(cpu)
        self.g_ram.set_value(ram)
        self.g_disk.set_value(disk)
        self.spark.push(cpu)

        lt = time.localtime()
        self.clock_label.setText(time.strftime("%H:%M:%S", lt))
        self.date_label.setText(spaced(f"{DAYS[lt.tm_wday]} {lt.tm_mday} {MONTHS[lt.tm_mon - 1]} {lt.tm_year}"))

        def row(k, v, c=ICE_HEX):
            return f"<span style='color:{DIM_HEX};'>{k}</span> <span style='color:{c};'>{html.escape(str(v))}</span>"

        try:
            facts = len(self.brain.memory.facts())
        except Exception:
            facts = 0
        mail = "ATTIVA" if getattr(self.brain, "watcher", None) else "NON CONFIGURATA"
        down = up = 0.0
        try:
            nio, tnow = psutil.net_io_counters(), time.time()
            if self._net_last:
                dtn = max(0.001, tnow - self._net_last[0])
                down, up = (nio.bytes_recv - self._net_last[1]) / dtn, (nio.bytes_sent - self._net_last[2]) / dtn
            self._net_last = (tnow, nio.bytes_recv, nio.bytes_sent)
        except Exception:
            pass
        self.info_label.setText("<br>".join([
            row("MODELLO ", self.brain.model_name),
            row("OLLAMA  ", "ONLINE" if self.ollama_ok else "OFFLINE", CYAN_HEX if self.ollama_ok else "#ff4848"),
            row("VOCE    ", str(getattr(self.speaker, "voice_key", "-")).upper()),
            row("RETE    ", f"↓ {fmt_rate(down)}  ↑ {fmt_rate(up)}"),
            row("POSTA   ", mail),
            row("MEMORIA ", f"{facts} FATTI"),
        ]))

    def _ollama_watch(self):
        while self._running:
            try:
                ok = requests.get("http://localhost:11434/", timeout=2).status_code == 200
            except Exception:
                ok = False
            self.ollama_status.emit(ok)
            for _ in range(16):
                if not self._running:
                    return
                time.sleep(0.5)

    def _on_ollama_status(self, ok: bool):
        if ok != self.ollama_ok:
            self.log_event("OLLAMA ONLINE" if ok else "OLLAMA OFFLINE")
        self.ollama_ok = ok
        label = self.topbar.status_label
        label.setText(spaced("LINK NEURALE STABILE" if ok else "LINK NEURALE INTERROTTO"))
        label.setStyleSheet(f"color: {DIM_HEX};" if ok else "color: #ff4848;")

    def log_event(self, text: str):
        self.events.append((time.strftime("%H:%M:%S"), text))
        lines = []
        n = len(self.events)
        for i, (ts, txt) in enumerate(self.events):
            c = CYAN_HEX if i == n - 1 else DIM_HEX             # l'evento più recente è evidenziato
            lines.append(f"<span style='color:{DIM_HEX};'>{ts}</span> "
                         f"<span style='color:{c};'>{html.escape(txt)}</span>")
        self.event_label.setText("<br>".join(lines))

    # ------------------------------------------------------------------ chat
    def check_user_name(self, text: str):
        t_lower = text.lower()
        name = None
        for marker in ("mi chiamo", "il mio nome è"):
            if marker in t_lower:
                parts = t_lower.split(marker, 1)[1].strip().split()
                if parts:
                    name = parts[0].strip(".,!?").capitalize()
        if name and len(name) > 1:
            self.user_label = name.upper()
            self.topbar.operator_label.setText(f"OPERATORE: {self.user_label}")
            self.log_event(f"OPERATORE: {self.user_label}")

    def append_chat(self, sender: str, message: str):
        ts = time.strftime("%H:%M:%S")
        s = sender.upper()
        if s in ("USER", "USER (VOICE)"):
            label, color = self.user_label, ICE_HEX
        elif s == "JARVIS":
            label, color = "JARVIS", CYAN_HEX
        else:
            label, color = s, AMBER_HEX
        self.chat_box.append(
            f"<span style='color:{DIM_HEX};'>{ts}</span> <span style='color:{color}; font-weight:bold;'>{html.escape(label)}</span>"
            f"<br><span style='color:{ICE_HEX};'>{html.escape(message)}</span><br>")
        self._scroll_chat()

    def _scroll_chat(self):
        sb = self.chat_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_chat_stream(self, sentence: str):
        safe = html.escape(sentence)
        if not self._reply_started:
            self._reply_started = True
            ts = time.strftime("%H:%M:%S")
            self.chat_box.append(
                f"<span style='color:{DIM_HEX};'>{ts}</span> <span style='color:{CYAN_HEX}; font-weight:bold;'>JARVIS</span>"
                f"<br><span style='color:{ICE_HEX};'>{safe}</span>")
        else:
            self.chat_box.moveCursor(QTextCursor.MoveOperation.End)
            self.chat_box.insertHtml(f"<span style='color:{ICE_HEX};'>&nbsp;{safe}</span>")
        self._scroll_chat()

    # ------------------------------------------------------------------ flusso conversazione
    def send_message(self):
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        if self.is_continuous_active and self.continuous_worker:
            self.continuous_worker.pause()
        self.check_user_name(text)
        self.append_chat("USER", text)
        self.process_command(text)

    def _try_voice_command(self, text: str) -> bool:
        """'cambia voce', 'usa la voce di Diego', 'elenco voci': li gestisce lo speaker, senza passare dal modello."""
        handler = getattr(self.speaker, "handle_voice_command", None)
        if handler is None or getattr(self.brain, "pending", None):     # durante una bozza email non si interpreta
            return False
        try:
            reply = handler(text)
        except Exception:
            logging.exception("Errore nel comando di cambio voce")
            return False
        if reply is None:
            return False
        self.append_chat("JARVIS", reply)
        self.speaker.speak(reply, block=False)                          # già nella voce nuova
        self.log_event("VOCE: " + str(getattr(self.speaker, "voice_key", "")).upper())
        self._resume_listener_when_silent()
        return True

    def process_command(self, user_text: str):
        if self._try_voice_command(user_text):
            return
        self._brain_busy = True
        self._reply_started = False
        self.worker = BrainWorker(user_text, self.brain)
        self.worker.sentence.connect(self.on_brain_sentence)
        self.worker.completed.connect(self.on_brain_finished)
        self.worker.start()

    def on_brain_sentence(self, sentence: str):
        self.append_chat_stream(sentence)
        self.speaker.speak(sentence, block=False)

    def on_brain_finished(self):
        self._brain_busy = False
        if self._reply_started:
            self.chat_box.append("")
        self._resume_listener_when_silent()

    def _resume_listener_when_silent(self):
        def resume_when_silent():
            self.speaker.wait_until_done()
            if self.is_continuous_active and self.continuous_worker:
                self.continuous_worker.resume()

        threading.Thread(target=resume_when_silent, daemon=True).start()

    def on_mail_alert(self, text: str):
        self.flash_until = time.time() + 3.0
        self.append_chat("JARVIS", text)
        self.log_event("POSTA: NUOVA COMUNICAZIONE")
        if self.is_continuous_active and self.continuous_worker:
            self.continuous_worker.pause()
        self.speaker.speak(text, block=False)
        self._resume_listener_when_silent()

    def on_learned(self, text: str):
        self.append_chat("MEMORIA", text)
        self.log_event("MEMORIA AGGIORNATA")

    # ------------------------------------------------------------------ microfono
    def toggle_continuous_listening(self):
        if not self.is_continuous_active:
            self.is_continuous_active = True
            self.auto_btn.setText("AUTO ●")
            self.auto_btn.setStyleSheet(AUTO_ON_STYLE)
            self.continuous_worker = ListenerWorker(self.listener, continuous=True)
            self.continuous_worker.speech_detected.connect(self.on_continuous_speech_detected)
            self.continuous_worker.start()
            self.log_event("ASCOLTO CONTINUO: ON")
        else:
            self.is_continuous_active = False
            self.auto_btn.setText("AUTO")
            self.auto_btn.setStyleSheet("")
            if self.continuous_worker:
                self.continuous_worker.stop()
            self.log_event("ASCOLTO CONTINUO: OFF")

    def on_continuous_speech_detected(self, spoken_text: str):
        if self.is_continuous_active:
            self.check_user_name(spoken_text)
            self.append_chat("USER", spoken_text)
            self.process_command(spoken_text)

    def start_listening(self):
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("ASCOLTO...")
        self._manual_listening = True
        self.listener_worker = ListenerWorker(self.listener, continuous=False)
        self.listener_worker.finished.connect(self.on_listen_finished)
        self.listener_worker.start()

    def on_listen_finished(self, spoken_text: str):
        self._manual_listening = False
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText("PARLA")
        if spoken_text and not spoken_text.startswith("Errore"):
            self.check_user_name(spoken_text)
            self.append_chat("USER", spoken_text)
            self.process_command(spoken_text)
        else:
            self.append_chat("JARVIS", "Non ho sentito nulla. Riprova pure.")


# Compatibilità con main.py esistente (from gui_v2 import StarkHUD)
StarkHUD = JarvisHUD


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JarvisHUD()
    window.show()
    sys.exit(app.exec())
