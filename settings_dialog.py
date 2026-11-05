"""Pagina IMPOSTAZIONI di Jarvis: modelli Ollama (scarica / accendi / cancella), account di posta, voci riconosciute.

Si apre dall'ingranaggio in alto (o con F9). Tutto si salva da solo: nessun file da modificare a mano.
La parte logica sta in modules/models.py, modules/accounts.py e modules/voiceid.py; qui c'è solo l'interfaccia.
"""
import os
import shutil
import threading

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox, QProgressBar, QLineEdit,
                             QListWidget, QCheckBox, QMessageBox, QFormLayout, QSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal

from modules.models import SUGGESTED, ALL_TAGS, TAG_LABELS, is_cloud, size_gb, GB
from modules.accounts import get_accounts
from modules.voiceid import get_voiceid

DIALOG_STYLE = """
QDialog { background-color: #02060d; }
QLabel { color: #cdf8ff; background: transparent; }
QLabel#hint { color: #609cb0; }
QLabel#warn { color: #ffb02e; }
QLabel#bad { color: #ff4848; }
QLabel#ok { color: #40ffd6; }
QTabWidget::pane { border: 1px solid rgba(0, 229, 255, 90); top: -1px; }
QTabBar::tab { background: rgba(0, 229, 255, 14); color: #609cb0; padding: 8px 18px; border: 1px solid rgba(0, 229, 255, 60); }
QTabBar::tab:selected { background: rgba(0, 229, 255, 60); color: #ffffff; }
QTableWidget, QListWidget { background: rgba(0, 229, 255, 8); color: #cdf8ff; border: 1px solid rgba(0, 229, 255, 70);
                            gridline-color: rgba(0, 229, 255, 40); selection-background-color: rgba(0, 229, 255, 70); }
QHeaderView::section { background: rgba(0, 229, 255, 30); color: #cdf8ff; border: none; padding: 5px; font-weight: bold; }
QLineEdit, QComboBox, QSpinBox { background: rgba(0, 229, 255, 14); color: #cdf8ff; border: 1px solid rgba(0, 229, 255, 110);
                                 padding: 6px 8px; selection-background-color: rgba(0, 229, 255, 90); }
QComboBox QAbstractItemView { background: #06202e; color: #cdf8ff; selection-background-color: rgba(0, 229, 255, 90); }
QCheckBox { color: #cdf8ff; spacing: 8px; }
QProgressBar { border: 1px solid rgba(0, 229, 255, 110); background: rgba(0, 229, 255, 10); color: #ffffff; text-align: center; }
QProgressBar::chunk { background: rgba(0, 229, 255, 160); }
QPushButton { background: rgba(0, 229, 255, 14); color: #00e5ff; border: 1px solid rgba(0, 229, 255, 150); padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: rgba(0, 229, 255, 60); color: #ffffff; }
QPushButton:disabled { color: rgba(0, 229, 255, 90); border: 1px solid rgba(0, 229, 255, 60); }
QPushButton#danger { color: #ff7a7a; border: 1px solid rgba(255, 72, 72, 160); background: rgba(255, 72, 72, 18); }
QPushButton#danger:hover { background: rgba(255, 72, 72, 120); color: #ffffff; }
"""

COLS = ["Acceso", "Modello", "GB", "Chat base", "Chat", "Veloce", "Difficile", "Codice", "Ragionam.", "Immagini"]
TAG_COL = {"chat": 4, "fast": 5, "complex": 6, "code": 7, "reasoning": 8, "vision": 9}
COL_TAG = {v: k for k, v in TAG_COL.items()}


def restyle(w, name: str):
    """Cambia il colore di un'etichetta (nome oggetto -> regola del foglio di stile) e la ridisegna."""
    w.setObjectName(name)
    w.style().unpolish(w)
    w.style().polish(w)


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


class SettingsDialog(QDialog):
    # segnali per tornare nel thread dell'interfaccia dai thread di scaricamento / prova
    refreshed = pyqtSignal()
    pull_progress = pyqtSignal(str, float, float)
    pull_finished = pyqtSignal(str, str)           # modello, errore ('' = ok)
    delete_finished = pyqtSignal(str, str)
    test_finished = pyqtSignal(bool, str)
    upd_checked = pyqtSignal(object)

    def __init__(self, brain, parent=None):
        super().__init__(parent)
        self.brain = brain
        self.registry = brain.registry
        self.accounts = get_accounts()
        self.voice = get_voiceid()
        self._cancel_pull = False
        self._pulling = False
        self._loading = False
        self.setWindowTitle("Impostazioni - J.A.R.V.I.S.")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(980, 640)

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.tabs.addTab(self._build_models(), "MODELLI")
        self.tabs.addTab(self._build_accounts(), "POSTA / ACCOUNT")
        self.tabs.addTab(self._build_voices(), "VOCI")
        self.tabs.addTab(self._build_updates(), "AGGIORNAMENTI")
        close = QPushButton("Chiudi")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

        self.refreshed.connect(self._fill_models)
        self.pull_progress.connect(self._on_pull_progress)
        self.pull_finished.connect(self._on_pull_finished)
        self.delete_finished.connect(self._on_delete_finished)
        self.test_finished.connect(self._on_test_finished)
        self.upd_checked.connect(self._on_upd_checked)
        if hasattr(parent, "update_progress"):
            parent.update_progress.connect(self._upd_progress)
        self.reload_models()
        self._fill_accounts()
        self._fill_voices()

    # =====================================================================  MODELLI
    def _build_models(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.models_status = QLabel("")
        top.addWidget(self.models_status, 1)
        btn = QPushButton("Aggiorna")
        btn.clicked.connect(self.reload_models)
        top.addWidget(btn)
        lay.addLayout(top)
        lay.addWidget(_hint(
            "Jarvis sceglie da solo il modello più adatto: «Chat base» per le conversazioni di tutti i giorni; «Difficile», «Codice» e "
            "«Ragionam.» per i compiti impegnativi, i moduli e la matematica. Spegni un modello per non farlo usare. "
            "I modelli cloud sono a pagamento e restano spenti finché non li accendi tu."))

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.delete_btn = QPushButton("Elimina il modello selezionato")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete_selected)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(QLabel("Scarica un nuovo modello"))
        dl = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        for name, gb, note in SUGGESTED:
            label = f"{name}  —  {'cloud a pagamento' if gb == 0 else f'circa {gb} GB'}  —  {note}"
            self.combo.addItem(label, name)
        self.combo.setCurrentIndex(-1)
        self.combo.setEditText("")
        self.combo.lineEdit().setPlaceholderText("Scegli dall'elenco o scrivi il nome di un modello Ollama (es. mistral:7b)")
        self.combo.currentTextChanged.connect(self._update_size_hint)
        dl.addWidget(self.combo, 1)
        self.pull_btn = QPushButton("Scarica")
        self.pull_btn.clicked.connect(self._start_pull)
        dl.addWidget(self.pull_btn)
        self.cancel_btn = QPushButton("Annulla")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        dl.addWidget(self.cancel_btn)
        lay.addLayout(dl)
        self.size_hint = QLabel("")
        self.size_hint.setObjectName("hint")
        lay.addWidget(self.size_hint)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        lay.addWidget(self.progress)
        self.pull_label = QLabel("")
        self.pull_label.setObjectName("hint")
        lay.addWidget(self.pull_label)
        return w

    def reload_models(self):
        self.models_status.setText("Leggo i modelli da Ollama...")

        def work():
            self.registry.refresh(force=True)
            self.refreshed.emit()
        threading.Thread(target=work, daemon=True).start()

    def _free_gb(self) -> float:
        try:
            return shutil.disk_usage(os.path.expanduser("~")).free / GB
        except OSError:
            return 0.0

    def _fill_models(self):
        reg = self.registry
        self._loading = True
        self.table.blockSignals(True)
        try:
            names = sorted(reg.installed)
            self.table.setRowCount(len(names))
            chat = reg.chat_model()
            for r, name in enumerate(names):
                prof = reg.profile(name)
                cloud = is_cloud(name)
                self.table.setItem(r, 0, self._check_item(prof["enabled"]))
                it = QTableWidgetItem(name + ("   (cloud, a pagamento)" if cloud else ""))
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setData(Qt.ItemDataRole.UserRole, name)
                self.table.setItem(r, 1, it)
                gb = QTableWidgetItem("—" if cloud else f"{size_gb(reg.installed[name]):.1f}")
                gb.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                gb.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 2, gb)
                self.table.setItem(r, 3, self._check_item(name == chat))
                for tag, c in TAG_COL.items():
                    self.table.setItem(r, c, self._check_item(tag in prof["tags"]))
            if not names:
                self.models_status.setText("Ollama non risponde o non ha modelli installati. Avvia Ollama e premi Aggiorna.")
                restyle(self.models_status, "warn")
            else:
                restyle(self.models_status, "plain")
                self.models_status.setText(f"{len(names)} modelli installati — spazio occupato circa {reg.disk_usage_gb():.1f} GB — "
                                           f"spazio libero sul disco {self._free_gb():.0f} GB")
        finally:
            self.table.blockSignals(False)
            self._loading = False
        self._update_size_hint()

    @staticmethod
    def _check_item(on: bool) -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        return it

    def _row_name(self, row: int) -> str:
        it = self.table.item(row, 1)
        return it.data(Qt.ItemDataRole.UserRole) if it else ""

    def _on_item_changed(self, item):
        if self._loading:
            return
        row, c = item.row(), item.column()
        name = self._row_name(row)
        on = item.checkState() == Qt.CheckState.Checked
        if c == 0:
            self.registry.set_profile(name, enabled=on)
        elif c == 3:
            if on:
                self.registry.set_chat(name)
            self._fill_models()                       # una sola riga "Chat base" alla volta
        elif c in COL_TAG:
            tags = [t for t, col in TAG_COL.items() if self.table.item(row, col).checkState() == Qt.CheckState.Checked]
            self.registry.set_profile(name, tags=tags)

    def _selected_name(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        return self._row_name(rows[0].row()) if rows else ""

    def _delete_selected(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Elimina modello", "Seleziona prima un modello nella tabella.")
            return
        gb = size_gb(self.registry.installed.get(name, {}))
        what = ("Rimuove il collegamento al modello cloud (non c'è nulla da liberare sul disco)." if is_cloud(name)
                else f"Libera circa {gb:.1f} GB sul disco.")
        ok = QMessageBox.question(self, "Elimina modello",
                                  f"Eliminare «{name}»?\n{what}\nPer riaverlo dovrai scaricarlo di nuovo.",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        self.delete_btn.setEnabled(False)
        self.models_status.setText(f"Elimino {name}...")

        def work():
            self.delete_finished.emit(name, self.registry.delete(name))
        threading.Thread(target=work, daemon=True).start()

    def _on_delete_finished(self, name: str, err: str):
        self.delete_btn.setEnabled(True)
        if err:
            QMessageBox.warning(self, "Elimina modello", f"Non sono riuscito a eliminare {name}: {err}")
        self._fill_models()

    # ---- download
    def _combo_model(self) -> str:
        i = self.combo.currentIndex()
        if i >= 0 and self.combo.itemText(i) == self.combo.currentText():
            return str(self.combo.itemData(i))
        return self.combo.currentText().split("  —  ")[0].strip()

    def _update_size_hint(self, *_):
        name = self._combo_model()
        if not name:
            self.size_hint.setText("")
            return
        gb = next((g for n, g, _ in SUGGESTED if n == name), None)
        free = self._free_gb()
        if is_cloud(name):
            txt = "Modello cloud: nessun download, ma è a pagamento e serve aver fatto «ollama signin» nel terminale."
            kind = "warn"
        elif gb is None:
            txt = f"Peso non noto in anticipo: lo vedrai durante lo scaricamento. Spazio libero: {free:.0f} GB."
            kind = "hint"
        elif gb * 1.1 > free:
            txt = f"Download circa {gb:.1f} GB, ma hai solo {free:.0f} GB liberi: potrebbe non starci."
            kind = "bad"
        else:
            txt = f"Download circa {gb:.1f} GB (spazio libero sul disco: {free:.0f} GB)."
            kind = "hint"
        restyle(self.size_hint, kind)
        self.size_hint.setText(txt)

    def _start_pull(self):
        name = self._combo_model()
        if not name or self._pulling:
            return
        self._pulling, self._cancel_pull = True, False
        self.pull_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.pull_label.setText(f"Avvio il download di {name}...")

        def work():
            err = self.registry.pull(name, lambda s, c, t: self.pull_progress.emit(s, float(c), float(t)),
                                     cancel=lambda: self._cancel_pull)
            self.pull_finished.emit(name, err)
        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        self._cancel_pull = True
        self.pull_label.setText("Annullo...")

    def _on_pull_progress(self, status: str, done: float, total: float):
        if total > 0:
            self.progress.setValue(int(100 * done / total))
            self.pull_label.setText(f"{status[:40]} — {done / GB:.2f} / {total / GB:.2f} GB")
        else:
            self.pull_label.setText(status[:60])

    def _on_pull_finished(self, name: str, err: str):
        self._pulling = False
        self.pull_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if err:
            self.pull_label.setText(f"Non completato: {err}")
        else:
            self.progress.setValue(100)
            self.pull_label.setText(f"{name} scaricato. Lo trovi nella tabella: scegli per cosa usarlo.")
        self._fill_models()

    # =====================================================================  ACCOUNT
    def _build_accounts(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        left.addWidget(QLabel("Account di posta"))
        self.acc_list = QListWidget()
        self.acc_list.currentRowChanged.connect(self._on_account_selected)
        left.addWidget(self.acc_list, 1)
        new_btn = QPushButton("Nuovo account")
        new_btn.clicked.connect(self._new_account)
        left.addWidget(new_btn)
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        self.f_label = QLineEdit()
        self.f_label.setPlaceholderText("per esempio: principale, lavoro")
        self.f_addr = QLineEdit()
        self.f_addr.setPlaceholderText("nome@gmail.com")
        self.f_pass = QLineEdit()
        self.f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_pass.setPlaceholderText("password per le app (vuoto = lascia quella salvata)")
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("come firmi le email (facoltativo)")
        self.f_imap = QLineEdit()
        self.f_imap.setPlaceholderText("automatico per Gmail, iCloud, Yahoo")
        self.f_smtp = QLineEdit()
        self.f_smtp.setPlaceholderText("automatico per Gmail, iCloud, Yahoo")
        self.f_port = QSpinBox()
        self.f_port.setRange(0, 65535)
        self.f_port.setSpecialValueText("automatica")
        form.addRow("Nome account", self.f_label)
        form.addRow("Indirizzo email", self.f_addr)
        form.addRow("Password", self.f_pass)
        form.addRow("Il tuo nome", self.f_name)
        form.addRow("Server IMAP", self.f_imap)
        form.addRow("Server SMTP", self.f_smtp)
        form.addRow("Porta SMTP", self.f_port)
        right.addLayout(form)
        guide = QLabel('Per Gmail serve una «password per le app»: attiva la verifica in due passaggi e creala qui: '
                       '<a href="https://myaccount.google.com/apppasswords" style="color:#00e5ff;">myaccount.google.com/apppasswords</a>. '
                       'Non usare la password normale.')
        guide.setObjectName("hint")
        guide.setWordWrap(True)
        guide.setOpenExternalLinks(True)
        right.addWidget(guide)
        self.acc_status = QLabel("")
        self.acc_status.setWordWrap(True)
        right.addWidget(self.acc_status)
        btns = QHBoxLayout()
        for text, slot, name in (("Salva", self._save_account, ""), ("Prova accesso", self._test_account, ""),
                                 ("Usa questo account", self._use_account, ""), ("Elimina", self._delete_account, "danger")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(slot)
            btns.addWidget(b)
            if text == "Prova accesso":
                self.test_btn = b
        right.addLayout(btns)
        right.addWidget(_hint("Le password restano sul tuo PC, nel file data/accounts.json. Jarvis legge la posta in sola lettura "
                              "e invia solo dopo il tuo «invia». A voce: «usa l'account lavoro», «quali account hai»."))
        right.addStretch(1)
        lay.addLayout(right, 2)
        self._editing = ""                              # etichetta dell'account in modifica ('' = nuovo)
        return w

    def _fill_accounts(self, select: str = ""):
        self.acc_list.blockSignals(True)
        self.acc_list.clear()
        active = (self.accounts.active() or {}).get("label", "")
        for a in self.accounts.data["accounts"]:
            self.acc_list.addItem(f"{'● ' if a['label'] == active else '   '}{a['label']}  ({a['address']})")
        self.acc_list.blockSignals(False)
        labels = self.accounts.labels()
        target = select or active
        if target in labels:
            self.acc_list.setCurrentRow(labels.index(target))
            self._load_form(self.accounts.get(target))
        else:
            self._new_account()

    def _on_account_selected(self, row: int):
        labels = self.accounts.labels()
        if 0 <= row < len(labels):
            self._load_form(self.accounts.get(labels[row]))

    def _load_form(self, a: dict):
        self._editing = a["label"]
        self.f_label.setText(a["label"])
        self.f_addr.setText(a["address"])
        self.f_pass.setText("")
        self.f_name.setText(a.get("name", ""))
        self.f_imap.setText(a.get("imap_host", ""))
        self.f_smtp.setText(a.get("smtp_host", ""))
        self.f_port.setValue(int(a.get("smtp_port") or 0))
        self._say("", "hint")

    def _new_account(self):
        self._editing = ""
        for f in (self.f_label, self.f_addr, self.f_pass, self.f_name, self.f_imap, self.f_smtp):
            f.setText("")
        self.f_port.setValue(0)
        self._say("Nuovo account: compila i campi e premi Salva.", "hint")

    def _form(self) -> dict:
        return {"label": self.f_label.text().strip(), "address": self.f_addr.text().strip(), "password": self.f_pass.text(),
                "name": self.f_name.text().strip(), "imap_host": self.f_imap.text().strip(),
                "smtp_host": self.f_smtp.text().strip(), "smtp_port": self.f_port.value()}

    def _say(self, text: str, kind: str = "hint"):
        restyle(self.acc_status, kind)
        self.acc_status.setText(text)

    def _save_account(self, silent=False):
        acc = self._form()
        if "@" not in acc["address"]:
            self._say("Scrivi un indirizzo email valido.", "bad")
            return None
        if not acc["password"] and not (self.accounts.get(self._editing) if self._editing else None):
            self._say("Scrivi la password per le app.", "bad")
            return None
        saved = self.accounts.upsert(acc, self._editing)
        self._editing = saved["label"]
        self._fill_accounts(saved["label"])
        if (self.accounts.active() or {}).get("label") == saved["label"]:
            self.brain.reload_mail()
        if not silent:
            self._say("Salvato.", "ok")
        return saved

    def _test_account(self):
        acc = self._form()
        if "@" not in acc["address"]:
            self._say("Scrivi un indirizzo email valido.", "bad")
            return
        acc["label"] = acc["label"] or self._editing
        self.test_btn.setEnabled(False)
        self._say("Provo ad accedere...", "hint")

        def work():
            ok, msg = self.accounts.test(acc)
            self.test_finished.emit(ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def _on_test_finished(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self._say(msg, "ok" if ok else "bad")

    def _use_account(self):
        saved = self._save_account(silent=True)
        if not saved:
            return
        self.accounts.set_active(saved["label"])
        ok = self.brain.reload_mail()
        self._fill_accounts(saved["label"])
        self._say("Ora Jarvis usa questo account." if ok else "Salvato, ma i dati non bastano per collegarsi: prova l'accesso.",
                  "ok" if ok else "warn")

    def _delete_account(self):
        if not self._editing:
            return
        ok = QMessageBox.question(self, "Elimina account", f"Eliminare l'account «{self._editing}»?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        self.accounts.delete(self._editing)
        self.brain.reload_mail()
        self._editing = ""
        self._fill_accounts()
        self._say("Account eliminato.", "hint")

    # =====================================================================  VOCI
    def _build_voices(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.voice_status = QLabel("")
        self.voice_status.setWordWrap(True)
        lay.addWidget(self.voice_status)
        self.voice_list = QListWidget()
        lay.addWidget(self.voice_list, 1)
        row = QHBoxLayout()
        forget = QPushButton("Dimentica la voce selezionata")
        forget.setObjectName("danger")
        forget.clicked.connect(self._forget_voice)
        row.addWidget(forget)
        row.addStretch(1)
        lay.addLayout(row)
        self.only_owner = QCheckBox("Ascolta solo il proprietario (ignora le altre voci)")
        self.only_owner.stateChanged.connect(self._toggle_only_owner)
        lay.addWidget(self.only_owner)
        lay.addWidget(_hint("Per aggiungere una persona dì: «Jarvis, impara la voce di Marco» e fallo parlare per qualche frase. "
                            "Il proprietario è la prima voce che hai presentato; gli altri possono chiacchierare con Jarvis ma non "
                            "dargli comandi sensibili (spegnere il PC, posta, moduli...)."))
        return w

    # =====================================================================  AGGIORNAMENTI
    def _build_updates(self) -> QWidget:
        from modules import updater
        from modules.version import VERSION
        self._updater = updater
        self._upd_info = None
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"Versione installata: {VERSION}"))
        lay.addWidget(QLabel("Repository: " + (updater.repo() or "non configurato (si scrive in modules/version.py)")))
        self.upd_auto = QCheckBox("Controlla da solo gli aggiornamenti (all'avvio e ogni 6 ore)")
        self.upd_auto.setChecked(updater.load_settings()["auto_check"])
        self.upd_auto.stateChanged.connect(lambda *_: updater.save_settings(self.upd_auto.isChecked()))
        lay.addWidget(self.upd_auto)
        row = QHBoxLayout()
        chk = QPushButton("Controlla ora")
        chk.clicked.connect(self._check_upd)
        self.upd_install = QPushButton("Scarica e installa")
        self.upd_install.setEnabled(False)
        self.upd_install.clicked.connect(self._install_upd)
        for b in (chk, self.upd_install):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.upd_bar = QProgressBar()
        self.upd_bar.setRange(0, 100)
        self.upd_bar.setVisible(False)
        lay.addWidget(self.upd_bar)
        self.upd_status = QLabel("")
        self.upd_status.setWordWrap(True)
        lay.addWidget(self.upd_status)
        lay.addWidget(_hint("Jarvis cerca l'ultima «Release» sul repository GitHub scritto nel suo codice. Se è più recente scarica Jarvis.exe, ne controlla "
                            "l'integrità e si riavvia da solo (l'exe vecchio resta come Jarvis.exe.bak). Per un repository privato metti "
                            "GITHUB_TOKEN nel file .env. Puoi anche dire: «Jarvis, controlla gli aggiornamenti» e «installa l'aggiornamento»."))
        lay.addStretch(1)
        return w

    def _check_upd(self):
        self.upd_status.setText("Controllo su GitHub…")
        self.upd_install.setEnabled(False)
        threading.Thread(target=lambda: self.upd_checked.emit(self._updater.check()), daemon=True).start()

    def _on_upd_checked(self, info):
        self._upd_info = info
        if not info["ok"]:
            self.upd_status.setText(info["error"])
        elif info["available"]:
            self.upd_status.setText(f"Nuova versione disponibile: {info['latest']}\n\n{info['notes'][:600]}")
            self.upd_install.setEnabled(True)
        else:
            self.upd_status.setText(f"Sei aggiornato (ultima versione: {info['latest'] or info['current']}).")

    def _install_upd(self):
        if not self._upd_info or not hasattr(self.parent(), "run_install"):
            return
        self.upd_install.setEnabled(False)
        self.upd_bar.setValue(0)
        self.upd_bar.setVisible(True)
        self.upd_status.setText("Scarico l'aggiornamento… Jarvis si riavvierà da solo.")
        self.parent().run_install(self._upd_info)

    def _upd_progress(self, f):
        self.upd_bar.setValue(int(f * 100))

    def _fill_voices(self):
        v = self.voice
        self.voice_list.clear()
        for n in v.names():
            self.voice_list.addItem(f"{n}{'   (proprietario)' if n == v.owner else ''}   —   {len(v.people[n])} campioni")
        if v.ready:
            self.voice_status.setText("Riconoscimento delle voci attivo." if v.names() else
                                      "Riconoscimento attivo, ma non conosco ancora nessuna voce.")
        else:
            self.voice_status.setText(f"Riconoscimento non attivo: {v.error or 'in preparazione'}.")
        self.only_owner.blockSignals(True)
        self.only_owner.setChecked(bool(v.only_owner))
        self.only_owner.blockSignals(False)

    def _forget_voice(self):
        row = self.voice_list.currentRow()
        names = self.voice.names()
        if 0 <= row < len(names):
            self.voice.forget(names[row])
            self._fill_voices()

    def _toggle_only_owner(self, _state):
        if not self.voice.set_only_owner(self.only_owner.isChecked()):
            self.only_owner.blockSignals(True)
            self.only_owner.setChecked(False)
            self.only_owner.blockSignals(False)
            QMessageBox.information(self, "Voci", "Prima devo conoscere la tua voce: dì «impara la mia voce, sono…».")
