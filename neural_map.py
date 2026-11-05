"""Mappa neurale di Jarvis: il centro dell'HUD.

Mostra i collegamenti REALI del sistema:
  - la catena della voce:  ASCOLTO -> WHISPER -> CERVELLO -> VOCE -> ALTOPARLANTE
  - i due modelli (chat e coder), la memoria, la posta e la ricerca web
  - tutti i moduli-strumento: collegati (linea piena), disattivati (collegamento interrotto con una X rossa)
    oppure creati da Jarvis e ancora in attesa del tuo "installa" (nodo vuoto, nessun collegamento).
Quando Jarvis lavora gli impulsi viaggiano lungo i collegamenti: ascolto, trascrizione, cervello, modello,
strumento usato, risposta.

Dati in ingresso:  set_snapshot(dict)  (brain.neural_snapshot)   e   on_event(tipo, nome)  (brain.on_event).
"""
import math
import time
import random
import logging

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QRadialGradient, QFontMetricsF

CYAN = (0, 229, 255)
ICE = (205, 248, 255)
DIM = (96, 156, 176)
AMBER = (255, 176, 46)
RED = (255, 72, 72)
MINT = (64, 255, 214)

STATE_COLORS = {
    "idle": (0, 229, 255), "listening": (64, 255, 214), "thinking": (255, 186, 64),
    "speaking": (150, 238, 255), "alert": (255, 150, 40), "offline": (255, 72, 72),
}
STAGES = ["ASCOLTO", "TRASCRIZIONE", "ELABORAZIONE", "RISPOSTA"]

# posizioni fisse (coordinate unitarie: x in [-1, 1] sul raggio orizzontale, y in [-1, 1] su quello verticale)
FIXED = {
    "mic":    dict(pos=(-0.88, 0.00), label="ASCOLTO",      sub="MICROFONO",   kind="io"),
    "stt":    dict(pos=(-0.52, 0.00), label="WHISPER",      sub="TRASCRIZIONE", kind="io"),
    "tts":    dict(pos=(0.52, 0.00),  label="VOCE",         sub="",            kind="io"),
    "spk":    dict(pos=(0.88, 0.00),  label="ALTOPARLANTE", sub="USCITA",      kind="io"),
    "memory": dict(pos=(-0.30, 0.42),  label="MEMORIA",     sub="",            kind="service"),
    "mail":   dict(pos=(0.0, 0.54),    label="POSTA",       sub="",            kind="service"),
    "web":    dict(pos=(0.30, 0.42),   label="RICERCA",     sub="INTERNET",    kind="service"),
}
PIPELINE = [("mic", "stt"), ("stt", "brain"), ("brain", "tts"), ("tts", "spk")]
SPOKES = ["memory", "mail", "web"]                 # i nodi dei modelli sono dinamici (uno per modello acceso)
ROLE_SHORT = {"chat": "CHAT", "fast": "VELOCE", "complex": "DIFFICILE", "code": "CODICE", "reasoning": "RAGION.", "vision": "IMMAGINI"}


def col(c, a=255) -> QColor:
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(max(0, min(255, a))))


def make_font(size: float, bold: bool = False, mono: bool = True) -> QFont:
    f = QFont()
    f.setFamilies(["Consolas", "Cascadia Mono", "Courier New"] if mono else ["Bahnschrift", "Segoe UI", "Arial"])
    f.setPointSizeF(float(size))
    f.setBold(bool(bold))
    return f


def make_pen(c, a, width) -> QPen:
    pen = QPen(col(c, a), float(width))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


class _Node:
    def __init__(self, nid, label, kind, pos, sub=""):
        self.id, self.label, self.kind, self.pos, self.sub = nid, label, kind, pos, sub
        self.status = "on"          # on | off (disattivato/mancante) | pending (in attesa di installazione)
        self.ext = False            # creato da Jarvis
        self.tools = 0
        self.glow = 0.0
        self.hold = 0.0             # fino a quando resta acceso
        self.born = -99.0
        self.xy = (0.0, 0.0)        # pixel
        self.angle = 0.0            # per le etichette dei moduli
        self.slot = 0
        self.bend = 0.0


class NeuralMap(QWidget):
    N_NEURONS = 90

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 440)
        self.setMouseTracking(True)
        self._broken = False
        self.t = 0.0
        self.spin = 0.0
        self.speed = 1.0
        self.state = "idle"
        self.caption = "SISTEMA ONLINE"
        self.level = 0.0
        self.color = [float(x) for x in STATE_COLORS["idle"]]
        self.activity = ""
        self.activity_until = 0.0
        self.input_until = 0.0
        self.ollama = True

        self.nodes = {}
        self.order = []
        for nid, d in FIXED.items():
            n = _Node(nid, d["label"], d["kind"], d["pos"], d["sub"])
            self.nodes[nid] = n
        self.nodes["brain"] = _Node("brain", "CERVELLO", "hub", (0.0, 0.0))
        self.modules = []
        self.model_nodes = []
        self._model_key = None
        self._first_snapshot = True
        self._snap_key = None
        self._layout_key = None
        self._curves = {}
        self.pulses = []
        self._delayed = []
        self._timers = {}

        rnd = random.Random(7)
        self.neurons = []
        for _ in range(self.N_NEURONS):
            self.neurons.append({"x": rnd.uniform(-1.05, 1.05), "y": rnd.uniform(-1.0, 1.0),
                                 "ph": rnd.uniform(0, 6.28), "fire": 0.0})
        self.synapses = []
        for i, a in enumerate(self.neurons):
            near = sorted(((math.hypot(a["x"] - b["x"], a["y"] - b["y"]), j) for j, b in enumerate(self.neurons) if j != i))
            for dist, j in near[:2]:
                if dist < 0.30 and (j, i) not in self.synapses:
                    self.synapses.append((i, j))

        self._f_label = make_font(7.5, bold=True)
        self._f_sub = make_font(6.5)
        self._f_title = make_font(8.5, bold=True)
        self._f_caption = make_font(10.5, bold=True, mono=False)
        self._f_small = make_font(7.0)

    # ------------------------------------------------------------------ dati dal sistema
    def set_snapshot(self, snap: dict):
        """Riceve lo stato reale dei collegamenti (brain.neural_snapshot)."""
        try:
            mods = snap.get("modules", [])
            models = snap.get("models", {})
            services = snap.get("services", {})
            self.ollama = bool(snap.get("ollama", True))
            self._set_models(models.get("list", []))
            self.nodes["mail"].status = "on" if services.get("mail") else "off"
            self.nodes["mail"].sub = "COLLEGATA" if services.get("mail") else "NON CONFIGURATA"
            self.nodes["web"].status = "on" if services.get("web") else "off"
            self.nodes["web"].sub = "INTERNET" if services.get("web") else "NON DISPONIBILE"
            self.nodes["memory"].status = "on"
            self.nodes["memory"].sub = f"{int(services.get('memory', 0))} FATTI"

            order = sorted(mods, key=lambda m: ({"connected": 0, "disabled": 1, "pending": 2}.get(m["state"], 3),
                                                bool(m.get("ext")), m["key"]))
            key = tuple((m["key"], m["state"], bool(m.get("ext")), int(m.get("tools", 0))) for m in order)
            if key == self._snap_key:
                return
            self._snap_key = key
            now = time.time()
            wanted = {"m:" + m["key"] for m in order}
            for nid in [k for k in self.nodes if k.startswith("m:") and k not in wanted]:
                del self.nodes[nid]
            for m in order:
                nid = "m:" + m["key"]
                n = self.nodes.get(nid)
                if n is None:
                    n = _Node(nid, m["key"].upper().replace("_", " "), "module", (0, 0))
                    n.born = -99.0 if self._first_snapshot else now      # i moduli nuovi appaiono con un'animazione
                    self.nodes[nid] = n
                    if not self._first_snapshot:
                        self._note(f"NUOVO MODULO: {m['key'].upper()}", 5.0)
                n.ext = bool(m.get("ext"))
                n.tools = int(m.get("tools", 0))
                n.status = {"connected": "on", "disabled": "off", "pending": "pending"}.get(m["state"], "off")
                n.sub = {"connected": f"{n.tools} FUNZIONI", "disabled": "DISATTIVATO",
                         "pending": "IN ATTESA"}.get(m["state"], "")
                if n.ext and m["state"] == "connected":
                    n.sub = "CREATO DA JARVIS"
                n.error = str(m.get("error") or "")
                if n.error and m["state"] != "connected":
                    n.sub = "ERRORE: NON SI CARICA"
            self.modules = [self.nodes["m:" + m["key"]] for m in order]
            self._first_snapshot = False
            self._layout_key = None
        except Exception:
            logging.exception("Mappa neurale: snapshot non valido")

    def _set_models(self, items):
        """Un nodo per ogni modello acceso in Impostazioni: se ne accendi o spegni, la mappa si adatta."""
        key = tuple((m["name"], bool(m.get("ok")), bool(m.get("base"))) for m in items) + (self.ollama,)
        if key == self._model_key:
            return
        self._model_key = key
        wanted = {"d:" + m["name"] for m in items}
        for nid in [k for k in self.nodes if k.startswith("d:") and k not in wanted]:
            del self.nodes[nid]
        now = time.time()
        count = len(items)
        spacing = 0.26 if count <= 3 else (0.22 if count <= 5 else 0.19)
        self.model_nodes = []
        for i, m in enumerate(items):
            nid = "d:" + m["name"]
            x = (i - (count - 1) / 2.0) * spacing
            y = -0.40 if count < 4 else (-0.34 if i % 2 == 0 else -0.55)       # a zig-zag se sono tanti, per non sovrapporre le scritte
            n = self.nodes.get(nid)
            if n is None:
                n = _Node(nid, "", "model", (x, y))
                n.born = -99.0 if self._first_snapshot else now
                self.nodes[nid] = n
            n.pos = (x, y)
            base, _, variant = m["name"].partition(":")
            n.label = base.upper()
            n.model = m["name"]
            n.base = bool(m.get("base"))
            roles = "·".join(ROLE_SHORT[t] for t in m.get("tags", []) if t in ROLE_SHORT and t != "chat")[:14]
            variant = "CLOUD" if m.get("cloud") else ("" if variant.lower() == "latest" else variant.upper())
            n.sub = " ".join(x for x in ("BASE" if n.base else "", variant, roles) if x)[:24]
            n.status = "on" if (m.get("ok") and self.ollama) else "off"
            self.model_nodes.append(n)
        self._layout_key = None

    def _model_id(self, name: str):
        for n in self.model_nodes:
            m = getattr(n, "model", "")
            if m == name or m == name + ":latest" or m.split(":")[0] == name:
                return n.id
        return None

    def on_event(self, kind: str, name: str = ""):
        """Eventi dal cervello: 'think', 'model' (chat/coder), 'tool' (modulo), 'service' (mail/web/memory), 'done'."""
        try:
            now = time.time()
            if kind == "think":
                self.input_until = now + 1.2
                self._pulse("stt", "brain", AMBER, 1.3)
                self._hold("stt", 1.0)
                self._note("RICHIESTA RICEVUTA", 3.0)
            elif kind == "model":
                nid = self._model_id(name)
                if nid:
                    node = self.nodes[nid]
                    self._pulse("brain", nid, AMBER, 1.2)
                    self._after(0.7, lambda: self._pulse(nid, "brain", AMBER, 1.2))
                    self._hold(nid, 2.5)
                    self._note(f"RAGIONA CON {node.label}" + (" (BASE)" if getattr(node, "base", False) else ""), 3.5)
            elif kind == "tool":
                nid = "m:" + name if "m:" + name in self.nodes else None
                if nid:
                    self._pulse("brain", nid, CYAN, 1.5, strong=True)
                    self._after(0.65, lambda: self._pulse(nid, "brain", MINT, 1.5, strong=True))
                    self._hold(nid, 2.4)
                    self._note("STRUMENTO: " + self.nodes[nid].label, 4.0)
            elif kind == "service" and name in ("mail", "web", "memory"):
                self._pulse("brain", name, CYAN, 1.4, strong=True)
                self._after(0.6, lambda: self._pulse(name, "brain", MINT, 1.4, strong=True))
                self._hold(name, 2.4)
                self._note("SERVIZIO: " + self.nodes[name].label, 4.0)
        except Exception:
            logging.exception("Mappa neurale: evento non gestito")

    # ------------------------------------------------------------------ piccoli aiuti
    def _note(self, text, secs):
        self.activity, self.activity_until = text, time.time() + secs

    def _hold(self, nid, secs):
        n = self.nodes.get(nid)
        if n:
            n.hold = max(n.hold, time.time() + secs)
            n.glow = 1.0

    def _after(self, delay, fn):
        self._delayed.append((time.time() + delay, fn))

    def _link_ok(self, a, b) -> str:
        """'ok' | 'broken' | 'none' (nessun collegamento)."""
        for nid in (a, b):
            n = self.nodes.get(nid)
            if n is None:
                return "none"
            if n.status == "pending":
                return "none"
            if n.status == "off" and n.kind in ("module", "model", "service"):
                return "broken"
        return "ok"

    def _links(self):
        out = [(a, b, 0.0) for a, b in PIPELINE]
        for i, nid in enumerate(SPOKES):
            out.append(("brain", nid, 0.0))
        for n in self.model_nodes:
            out.append(("brain", n.id, 0.0))
        for i, n in enumerate(self.modules):
            out.append(("brain", n.id, n.bend))
        return out

    def _pulse(self, a, b, color, speed=1.2, strong=False, faint=False):
        if a in self.nodes and b in self.nodes and self._link_ok(a, b) == "ok":
            self.pulses.append({"a": a, "b": b, "t": 0.0, "speed": speed, "c": color,
                                "k": 0.45 if faint else (1.0 if strong else 0.8)})

    def _due(self, name, period):
        if self.t >= self._timers.get(name, 0.0):
            self._timers[name] = self.t + period * (0.7 + 0.6 * random.random())
            return True
        return False

    # ------------------------------------------------------------------ geometria
    def _geometry(self, w, h):
        mx, top, bot = max(54.0, min(96.0, w * 0.12)), 50.0, 78.0
        cx = w / 2.0
        cy = top + (h - top - bot) / 2.0
        rx = max(120.0, w / 2.0 - mx)
        ry = max(100.0, (h - top - bot) / 2.0 - 26.0)
        return cx, cy, rx, ry

    def _relayout(self, w, h):
        key = (int(w), int(h), len(self.modules), tuple(n.id for n in self.modules),
               tuple((n.id, n.pos) for n in self.model_nodes))
        if key == self._layout_key:
            return
        self._layout_key = key
        cx, cy, rx, ry = self._geometry(w, h)
        for n in self.nodes.values():
            if n.kind != "module":
                n.xy = (cx + n.pos[0] * rx, cy + n.pos[1] * ry)
        mods = self.modules
        m = len(mods)
        n_top = (m + 1) // 2
        slots = []
        for count, (a0, a1) in ((n_top, (208.0, 332.0)), (m - n_top, (28.0, 152.0))):
            for i in range(count):
                slots.append(a0 + (a1 - a0) * (i + 0.5) / count)
        # ordine di disegno: alternato alto/basso così i collegamenti sono bilanciati
        for i, n in enumerate(mods):
            ang = math.radians(slots[i])
            n.angle = ang
            n.slot = i
            n.xy = (cx + math.cos(ang) * rx * 0.84, cy + math.sin(ang) * ry * 0.86)
            n.bend = 0.10 * (1 if i % 2 == 0 else -1)
        self._curves = {}
        for a, b, bend in self._links():
            self._curves[(a, b)] = self._make_curve(self.nodes[a].xy, self.nodes[b].xy, bend)

    @staticmethod
    def _make_curve(p0, p2, bend, segs=18):
        mx, my = (p0[0] + p2[0]) / 2.0, (p0[1] + p2[1]) / 2.0
        dx, dy = p2[0] - p0[0], p2[1] - p0[1]
        dist = math.hypot(dx, dy) or 1.0
        c = (mx - dy / dist * bend * dist, my + dx / dist * bend * dist)
        pts = []
        for i in range(segs + 1):
            u = i / segs
            x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * c[0] + u * u * p2[0]
            y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * c[1] + u * u * p2[1]
            pts.append((x, y))
        return pts

    @staticmethod
    def _at(pts, u):
        u = max(0.0, min(1.0, u))
        f = u * (len(pts) - 1)
        i = min(len(pts) - 2, int(f))
        r = f - i
        return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * r, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * r)

    # ------------------------------------------------------------------ animazione
    def step(self, dt: float, state: str, level: float, caption: str):
        now = time.time()
        self.t += dt
        self.state, self.caption = state, caption
        target = STATE_COLORS.get(state, STATE_COLORS["idle"])
        k = min(1.0, dt * 6.0)
        for i in range(3):
            self.color[i] += (target[i] - self.color[i]) * k
        speed_t = {"idle": 1.0, "listening": 1.5, "thinking": 3.0, "speaking": 1.9, "alert": 4.0, "offline": 0.15}.get(state, 1.0)
        self.speed += (speed_t - self.speed) * min(1.0, dt * 3.0)
        self.spin += dt * self.speed
        self.level += (level - self.level) * min(1.0, dt * 12.0)

        # eventi ritardati
        if self._delayed:
            due = [d for d in self._delayed if d[0] <= now]
            self._delayed = [d for d in self._delayed if d[0] > now]
            for _, fn in due:
                try:
                    fn()
                except Exception:
                    logging.exception("Mappa neurale: azione ritardata")

        # attività legata allo stato
        if state == "listening":
            if self._due("listen", 0.60 - 0.35 * self.level):
                self._pulse("mic", "stt", MINT, 1.4, strong=self.level > 0.15)
            self.nodes["mic"].glow = max(self.nodes["mic"].glow, 0.35 + 0.65 * self.level)
        elif state == "speaking":
            if self._due("speak", 0.42):
                self._pulse("brain", "tts", CYAN, 1.5, strong=True)
                self._after(0.40, lambda: self._pulse("tts", "spk", ICE, 1.5, strong=True))
            for nid in ("tts", "spk"):
                self.nodes[nid].glow = max(self.nodes[nid].glow, 0.45 + 0.4 * self.level)
        elif state == "thinking":
            if self._due("think", 0.24):
                live = [n.id for n in self.nodes.values() if n.id != "brain" and n.kind in ("module", "model", "service")
                        and self._link_ok("brain", n.id) == "ok"]
                if live:
                    nid = random.choice(live)
                    self._pulse("brain", nid, AMBER, 1.6, faint=True)
        else:
            if self._due("idle", 3.2):
                live = [n.id for n in self.nodes.values() if n.kind in ("module", "model", "service")
                        and self._link_ok("brain", n.id) == "ok"]
                if live:
                    self._pulse("brain", random.choice(live), CYAN, 0.9, faint=True)
        if self._due("fire", 0.30 if state == "thinking" else 1.1):
            random.choice(self.neurons)["fire"] = 1.0

        for nd in self.neurons:
            nd["fire"] *= math.exp(-dt * 2.2)
        for n in self.nodes.values():
            if now < n.hold:
                n.glow = max(n.glow, 0.9)
            else:
                n.glow *= math.exp(-dt * 2.0)
        alive = []
        for pl in self.pulses:
            pl["t"] += dt * pl["speed"]
            if pl["t"] >= 1.0:
                nb = self.nodes.get(pl["b"])
                if nb is not None:
                    nb.glow = max(nb.glow, 0.9 * pl["k"] + 0.1)
            else:
                alive.append(pl)
        self.pulses = alive[-60:]

    # ------------------------------------------------------------------ disegno
    def paintEvent(self, event):
        if self._broken:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self.draw(painter, float(self.width()), float(self.height()))
        except Exception:
            self._broken = True
            logging.exception("Errore nel disegno della mappa neurale")
        finally:
            painter.end()

    def mouseMoveEvent(self, event):
        try:
            pos = event.position()
            best, bd = None, 18.0
            for n in self.nodes.values():
                d = math.hypot(n.xy[0] - pos.x(), n.xy[1] - pos.y())
                if d < bd:
                    best, bd = n, d
            if best is None:
                self.setToolTip("")
            else:
                state = {"on": "collegato", "off": "disattivato / non disponibile", "pending": "in attesa di installazione"}[best.status]
                extra = f"\n{best.sub}" if best.sub else ""
                if getattr(best, "error", ""):
                    extra += "\n" + best.error[:160]
                self.setToolTip(f"{best.label.title()} - {state}{extra}")
        except Exception:
            pass

    def _text(self, p, x, y, text, font, c, a, center=True):
        p.setFont(font)
        w = QFontMetricsF(font).horizontalAdvance(text)
        p.setPen(make_pen(c, a, 1))
        p.drawText(QPointF(x - w / 2.0 if center else x, y), text)

    def _poly(self, p, pts, c, a, width, u0=0.0, u1=1.0, dashed=False):
        n = len(pts) - 1
        i0, i1 = int(u0 * n), max(int(u0 * n) + 1, int(math.ceil(u1 * n)))
        p.setPen(make_pen(c, a, width))
        for i in range(i0, min(n, i1)):
            if dashed and i % 2:
                continue
            p.drawLine(QPointF(*pts[i]), QPointF(*pts[i + 1]))

    def draw(self, p: QPainter, w: float, h: float):
        self._relayout(w, h)
        cx, cy, rx, ry = self._geometry(w, h)
        c = (int(self.color[0]), int(self.color[1]), int(self.color[2]))
        now = time.time()
        t = self.t

        # ---- anelli radar e rete di neuroni di sfondo
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k, f in enumerate((0.40, 0.66, 0.92)):
            p.setPen(make_pen(c, 20 + 8 * k, 1))
            rect = QRectF(cx - rx * f, cy - ry * f, 2 * rx * f, 2 * ry * f)
            for s in range(24):
                p.drawArc(rect, int((s * 15 + (self.spin * (3 + 2 * k)) * (1 if k % 2 else -1)) * 16), int(8 * 16))
        for i, j in self.synapses:
            a_, b_ = self.neurons[i], self.neurons[j]
            f = max(a_["fire"], b_["fire"])
            p.setPen(make_pen(c, 14 + 90 * f, 1))
            p.drawLine(QPointF(cx + a_["x"] * rx, cy + a_["y"] * ry), QPointF(cx + b_["x"] * rx, cy + b_["y"] * ry))
        p.setPen(Qt.PenStyle.NoPen)
        for nd in self.neurons:
            r = 1.3 + 2.2 * nd["fire"]
            p.setBrush(QBrush(col(c, 40 + 28 * math.sin(t * 1.3 + nd["ph"]) + 170 * nd["fire"])))
            p.drawEllipse(QPointF(cx + nd["x"] * rx, cy + nd["y"] * ry), r, r)

        # ---- collegamenti
        for a, b, _bend in self._links():
            pts = self._curves.get((a, b))
            if not pts:
                continue
            na, nb = self.nodes[a], self.nodes[b]
            status = self._link_ok(a, b)
            act = max(na.glow if a != "brain" else 0.0, nb.glow if b != "brain" else 0.0)   # il bagliore del cervello non conta
            if status == "ok":
                if act > 0.05:
                    self._poly(p, pts, c, 30 * act, 5.0)
                self._poly(p, pts, c, 62 + 130 * act, 1.2 + 1.0 * act)
                for k in range(3):                                   # puntini che scorrono: il collegamento è vivo
                    u = ((t * 0.18 + k / 3.0) % 1.0)
                    q = self._at(pts, u)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(col(c, 70 + 90 * act)))
                    p.drawEllipse(QPointF(q[0], q[1]), 1.5, 1.5)
            elif status == "broken":
                self._poly(p, pts, RED, 70, 1.2, 0.0, 0.50, dashed=True)
                self._poly(p, pts, RED, 55, 1.2, 0.90, 1.0, dashed=True)
                q = self._at(pts, 0.76)
                flick = 0.55 + 0.45 * abs(math.sin(t * 3.0 + hash(b) % 7))
                p.setPen(make_pen(RED, 120 + 110 * flick, 1.8))
                p.drawLine(QPointF(q[0] - 4, q[1] - 4), QPointF(q[0] + 4, q[1] + 4))
                p.drawLine(QPointF(q[0] - 4, q[1] + 4), QPointF(q[0] + 4, q[1] - 4))
            elif nb.status == "pending" or na.status == "pending":
                self._poly(p, pts, AMBER, 60, 1.2, 0.80, 1.0, dashed=True)      # solo un moncone: manca il collegamento

        # ---- impulsi
        for pl in self.pulses:
            pts = self._curves.get((pl["a"], pl["b"]))
            if not pts:
                continue
            for k in range(7):
                u = pl["t"] - k * 0.028
                if u < 0:
                    break
                q = self._at(pts, u)
                a = (230 if k == 0 else 150 - k * 20) * pl["k"]
                r = (3.6 if k == 0 else 2.6 - k * 0.25) * (0.8 + 0.4 * pl["k"])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col(pl["c"], a)))
                p.drawEllipse(QPointF(q[0], q[1]), r, r)
            q = self._at(pts, pl["t"])
            halo = QRadialGradient(QPointF(q[0], q[1]), 15.0)
            halo.setColorAt(0.0, col(pl["c"], 120 * pl["k"]))
            halo.setColorAt(1.0, col(pl["c"], 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(q[0], q[1]), 15.0, 15.0)

        # ---- nodi
        for n in self.nodes.values():
            if n.id != "brain":
                self._draw_node(p, n, c, now, cx, cy)
        self._draw_hub(p, cx, cy, min(rx, ry), c)

        # ---- testi di contorno
        n_ok = sum(1 for m in self.modules if m.status == "on")
        n_pend = sum(1 for m in self.modules if m.status == "pending")
        title = f"MAPPA NEURALE   MODULI COLLEGATI {n_ok}/{len(self.modules)}" + (f"   IN ATTESA {n_pend}" if n_pend else "")
        self._text(p, 22, 28, title, self._f_title, c, 215, center=False)
        if now < self.activity_until:
            fade = min(1.0, (self.activity_until - now) * 2.0)
            self._text(p, w - 22 - QFontMetricsF(self._f_title).horizontalAdvance(self.activity), 28,
                       self.activity, self._f_title, AMBER, 230 * fade, center=False)
        self._draw_strip(p, w, h, c)
        self._draw_legend(p, w, h)

    def _draw_node(self, p, n, c, now, cx, cy):
        x, y = n.xy
        base_r = {"io": 9.0, "model": 10.0, "service": 9.0, "module": 8.0}.get(n.kind, 8.0)
        age = now - n.born
        grow = 1.0 if age > 1.0 else 0.25 + 0.75 * max(0.0, age)
        r = base_r * grow
        on, off, pend = n.status == "on", n.status == "off", n.status == "pending"
        if on:
            nc = AMBER if n.ext else (c if n.kind != "module" else CYAN)
            if n.glow > 0.02 or n.kind != "module":
                g = QRadialGradient(QPointF(x, y), r * 3.6)
                g.setColorAt(0.0, col(nc, 70 + 150 * n.glow))
                g.setColorAt(1.0, col(nc, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawEllipse(QPointF(x, y), r * 3.6, r * 3.6)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(make_pen(nc, 150 + 100 * n.glow, 1.8))
            p.drawEllipse(QPointF(x, y), r, r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col(nc, 130 + 120 * n.glow)))
            p.drawEllipse(QPointF(x, y), r * (0.40 + 0.25 * n.glow), r * (0.40 + 0.25 * n.glow))
            lab_a, sub_a, lab_c = 230, 140, ICE
        elif off:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(make_pen(DIM, 120, 1.5))
            p.drawEllipse(QPointF(x, y), r, r)
            p.setPen(make_pen(RED, 140, 1.4))
            p.drawLine(QPointF(x - r * 0.5, y - r * 0.5), QPointF(x + r * 0.5, y + r * 0.5))
            p.drawLine(QPointF(x - r * 0.5, y + r * 0.5), QPointF(x + r * 0.5, y - r * 0.5))
            lab_a, sub_a, lab_c = 130, 120, DIM
        else:                                                       # in attesa di installazione
            p.setBrush(Qt.BrushStyle.NoBrush)
            for k in range(10):
                p.setPen(make_pen(AMBER, 90 + 60 * math.sin(self.t * 3 + k), 1.5))
                p.drawArc(QRectF(x - r, y - r, 2 * r, 2 * r), int((k * 36 + self.spin * 20) * 16), int(20 * 16))
            lab_a, sub_a, lab_c = 190, 190, AMBER

        if n.ext:                                                    # rombo: creato da Jarvis
            d = r + 5.0
            p.setPen(make_pen(AMBER, 200, 1.3))
            pts = [QPointF(x + d, y - d - 3), QPointF(x + d + 4, y - d + 1), QPointF(x + d, y - d + 5), QPointF(x + d - 4, y - d + 1)]
            for i in range(4):
                p.drawLine(pts[i], pts[(i + 1) % 4])
        if 0.0 <= age < 2.2:                                         # onda di "nuovo modulo"
            q = age / 2.2
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(make_pen(AMBER, 220 * (1 - q), 2.0))
            p.drawEllipse(QPointF(x, y), base_r * (1.5 + 5 * q), base_r * (1.5 + 5 * q))

        # etichette: i moduli sull'anello vanno verso l'esterno, gli altri sotto il nodo
        label = n.label if len(n.label) <= 13 else n.label[:12] + "."
        if n.kind == "module":
            stagger = 13.0 if n.slot % 2 else 0.0
            if math.sin(n.angle) < 0:                                 # arco alto: etichette verso l'alto
                ly, sy = y - r - 17.0 - stagger, y - r - 7.0 - stagger
            else:                                                     # arco basso: verso il basso
                ly, sy = y + r + 15.0 + stagger, y + r + 25.0 + stagger
        elif n.kind == "model":
            ly, sy = y - r - 16.0, y - r - 6.0
        else:
            ly, sy = y + r + 15.0, y + r + 25.0
        self._text(p, x, ly, label, self._f_label, lab_c, lab_a)
        if n.sub:
            self._text(p, x, sy, n.sub, self._f_sub, AMBER if (pend or n.ext) else (RED if off else DIM), sub_a)

    def _draw_hub(self, p, cx, cy, size, c):
        R = max(34.0, size * 0.17)
        sp, t = self.spin, self.t
        pulse = 0.5 + 0.5 * math.sin(t * 2.2)
        energy = 0.4 + 0.6 * self.level if self.state in ("speaking", "listening") else 0.5 + 0.2 * pulse
        halo = QRadialGradient(QPointF(cx, cy), R * 3.4)
        halo.setColorAt(0.0, col(c, 90 + 70 * energy))
        halo.setColorAt(0.45, col(c, 28 + 20 * energy))
        halo.setColorAt(1.0, col(c, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), R * 3.4, R * 3.4)
        # tacche
        for i in range(60):
            ang = 2 * math.pi * i / 60 + math.radians(sp * 5.0)
            major = i % 5 == 0
            r0, r1 = R * (1.62 if major else 1.67), R * 1.76
            p.setPen(make_pen(c, 180 if major else 90, 1.8 if major else 1.1))
            p.drawLine(QPointF(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                       QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1))
        # archi
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(3):
            rect = QRectF(cx - R * 1.45, cy - R * 1.45, 2 * R * 1.45, 2 * R * 1.45)
            st = int((-sp * 14.0 + k * 120.0) * 16)
            p.setPen(make_pen(c, 28, 7.0))
            p.drawArc(rect, st, int(70 * 16))
            p.setPen(make_pen(c, 220, 3.0))
            p.drawArc(rect, st, int(70 * 16))
        # anello d'onda
        n = 56
        for i in range(n):
            ang = 2 * math.pi * i / n - math.pi / 2.0
            if self.state == "speaking":
                v = self.level * (0.3 + 0.7 * abs(math.sin(i * 0.71 + t * 9.0) * math.sin(i * 0.23 - t * 5.0)))
            elif self.state == "listening":
                v = 0.05 + self.level * (0.35 + 0.65 * abs(math.sin(i * 0.93 + t * 13.0)))
            elif self.state == "thinking":
                v = 0.12 + 0.55 * max(0.0, math.sin(2 * math.pi * i / n * 3 - t * 6.0)) ** 2
            else:
                v = 0.05 + 0.03 * math.sin(i * 0.5 + t * 1.6)
            r0, r1 = R * 1.12, R * (1.16 + 0.36 * v)
            p.setPen(make_pen(c, 110 + 140 * v, 2.0))
            p.drawLine(QPointF(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                       QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1))
        # nucleo
        core_r = R * (0.62 + 0.05 * pulse + 0.10 * self.level)
        core = QRadialGradient(QPointF(cx, cy), core_r * 1.6)
        core.setColorAt(0.0, QColor(255, 255, 255, int(235 * min(1.0, 0.55 + energy))))
        core.setColorAt(0.30, col(c, 210))
        core.setColorAt(0.65, col(c, 70))
        core.setColorAt(1.0, col(c, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), core_r * 1.6, core_r * 1.6)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(make_pen(c, 190, 1.6))
        p.drawEllipse(QPointF(cx, cy), core_r * 0.62, core_r * 0.62)
        self._text(p, cx, cy + R * 2.15, "CERVELLO", self._f_label, ICE, 235)
        self._text(p, cx, cy + R * 2.15 + 14.0, self.caption, self._f_small, c, 200)

    def _draw_strip(self, p, w, h, c):
        """Le quattro fasi di una richiesta: la fase attiva si accende."""
        now = time.time()
        if self.state == "speaking":
            stage = 3
        elif self.state == "thinking":
            stage = 2 if now > self.input_until else 1
        elif self.state == "listening":
            stage = 0
        else:
            stage = -1
        y = h - 40.0
        fm = QFontMetricsF(self._f_label)
        sep = "   >   "
        total = sum(fm.horizontalAdvance(s) for s in STAGES) + fm.horizontalAdvance(sep) * (len(STAGES) - 1)
        x = w / 2.0 - total / 2.0
        p.setFont(self._f_label)
        for i, s in enumerate(STAGES):
            on = i == stage
            p.setPen(make_pen(c if on else DIM, 255 if on else 110, 1))
            p.drawText(QPointF(x, y), s)
            sw = fm.horizontalAdvance(s)
            if on:
                p.setPen(make_pen(c, 255, 2.2))
                p.drawLine(QPointF(x, y + 6.0), QPointF(x + sw, y + 6.0))
            x += sw
            if i < len(STAGES) - 1:
                p.setPen(make_pen(DIM, 90, 1))
                p.drawText(QPointF(x, y), sep)
                x += fm.horizontalAdvance(sep)

    def _draw_legend(self, p, w, h):
        items = [(CYAN, "COLLEGATO"), (RED, "DISATTIVATO"), (AMBER, "IN ATTESA / CREATO DA JARVIS")]
        fm = QFontMetricsF(self._f_small)
        x = 22.0
        y = h - 14.0
        for c_, text in items:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col(c_, 220)))
            p.drawEllipse(QPointF(x + 3, y - 3), 3.0, 3.0)
            self._text(p, x + 12, y, text, self._f_small, DIM, 180, center=False)
            x += 12 + fm.horizontalAdvance(text) + 18
