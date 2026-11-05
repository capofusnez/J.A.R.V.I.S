"""Account di posta salvati da Impostazioni (data/accounts.json). Il primo avvio importa quello del vecchio file .env.

Le password restano sul tuo PC, nel file data/accounts.json (come già nel .env): non vanno mai in chat né nei log.
"""
import os
import re
import json
import imaplib
import socket
import logging

try:
    from modules.paths import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

from modules.mail import MailConfig, PRESETS


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "account"


class AccountStore:
    def __init__(self, path=None):
        self.path = path or os.path.join(DATA_DIR, "accounts.json")
        self.data = {"active": "", "accounts": []}
        self._load()

    # ---- archivio
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data = {"active": d.get("active", ""), "accounts": d.get("accounts", [])}
            return
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.warning("[ACCOUNT] accounts.json non leggibile: %s", e)
            return
        addr, pwd = os.environ.get("MAIL_ADDRESS", "").strip(), os.environ.get("MAIL_PASSWORD", "").strip()
        if addr and pwd:                               # primo avvio: porta con sé l'account del vecchio .env
            self.data = {"active": "principale", "accounts": [{
                "label": "principale", "address": addr, "password": pwd, "name": os.environ.get("MAIL_FROM_NAME", ""),
                "imap_host": os.environ.get("MAIL_IMAP_HOST", ""), "smtp_host": os.environ.get("MAIL_SMTP_HOST", ""),
                "smtp_port": int(os.environ.get("MAIL_SMTP_PORT", "0") or 0)}]}
            self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        except OSError as e:
            logging.warning("[ACCOUNT] non riesco a salvare gli account: %s", e)

    # ---- elenco
    def labels(self):
        return [a["label"] for a in self.data["accounts"]]

    def get(self, label: str):
        low = (label or "").lower()
        return next((a for a in self.data["accounts"] if a["label"].lower() == low), None)

    def find(self, text: str):
        """Trova un account citato a voce (etichetta o parte dell'indirizzo)."""
        t = (text or "").lower()
        for a in self.data["accounts"]:
            if a["label"].lower() in t or a["address"].lower().split("@")[0] in t:
                return a
        return None

    def active(self):
        return self.get(self.data["active"]) or (self.data["accounts"][0] if self.data["accounts"] else None)

    def upsert(self, acc: dict, old_label: str = ""):
        acc = dict(acc)
        acc["label"] = (acc.get("label") or acc.get("address", "").split("@")[0] or "account").strip()
        acc["address"] = acc.get("address", "").strip()
        pw = acc.get("password", "").strip()
        if acc["address"].split("@")[-1].lower() in ("gmail.com", "googlemail.com"):
            pw = re.sub(r"\s+", "", pw)                # Google mostra la password a gruppi con spazi
        acc["password"] = pw
        key = old_label or acc["label"]
        for i, a in enumerate(self.data["accounts"]):
            if a["label"].lower() == key.lower():
                if not acc["password"]:
                    acc["password"] = a.get("password", "")     # campo password lasciato vuoto = non cambiarla
                self.data["accounts"][i] = acc
                if self.data["active"].lower() == key.lower():
                    self.data["active"] = acc["label"]
                break
        else:
            self.data["accounts"].append(acc)
        if not self.data["active"]:
            self.data["active"] = acc["label"]
        self.save()
        return acc

    def delete(self, label: str) -> bool:
        a = self.get(label)
        if not a:
            return False
        self.data["accounts"].remove(a)
        if self.data["active"].lower() == label.lower():
            self.data["active"] = self.data["accounts"][0]["label"] if self.data["accounts"] else ""
        self.save()
        return True

    def set_active(self, label: str) -> bool:
        a = self.get(label)
        if a:
            self.data["active"] = a["label"]
            self.save()
        return bool(a)

    # ---- uso
    def config(self, acc: dict):
        """MailConfig dell'account (None se mancano i dati o il provider è sconosciuto)."""
        if not acc or not acc.get("address") or not acc.get("password"):
            return None
        acc = dict(acc)
        if acc["address"].split("@")[-1].lower() in ("gmail.com", "googlemail.com"):
            acc["password"] = re.sub(r"\s+", "", acc["password"])
        dom = acc["address"].split("@")[-1].lower()
        imap_h, smtp_h, smtp_p = PRESETS.get(dom, (None, None, 465))
        imap_h = acc.get("imap_host") or imap_h
        smtp_h = acc.get("smtp_host") or smtp_h
        smtp_p = int(acc.get("smtp_port") or smtp_p or 465)
        if not imap_h or not smtp_h:
            return None
        return MailConfig(acc["address"], acc["password"], imap_h, smtp_h, smtp_p, display_name=acc.get("name", ""))

    def state_path(self, acc: dict) -> str:
        first = self.data["accounts"][0]["label"] if self.data["accounts"] else ""
        name = "mail_state.json" if acc["label"] == first else f"mail_state_{slug(acc['label'])}.json"
        return os.path.join(DATA_DIR, name)

    def test(self, acc: dict):
        """(ok, messaggio) provando davvero ad accedere alla casella (solo lettura)."""
        acc = dict(acc)
        if not acc.get("password"):
            old = self.get(acc.get("label", ""))
            acc["password"] = (old or {}).get("password", "")
        if acc["address"].split("@")[-1].lower() in ("gmail.com", "googlemail.com"):
            acc["password"] = re.sub(r"\s+", "", acc["password"])
        cfg = self.config(acc)
        if cfg is None:
            return False, ("Mancano indirizzo o password, oppure il provider non è tra quelli noti: "
                           "compila anche i campi IMAP e SMTP.")
        try:
            socket.setdefaulttimeout(12)
            m = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
            try:
                m.login(cfg.address, cfg.password)
            finally:
                try:
                    m.logout()
                except Exception:
                    pass
            return True, "Accesso riuscito."
        except imaplib.IMAP4.error as e:
            txt = str(e)
            hint = ""
            if cfg.imap_host.endswith("gmail.com"):
                hint = " Per Gmail serve una «password per le app» (con la verifica in due passaggi), non quella normale."
            return False, f"Il server ha rifiutato l'accesso: {txt[:120]}.{hint}"
        except (socket.timeout, OSError) as e:
            return False, f"Non riesco a collegarmi a {cfg.imap_host}: {e}"
        finally:
            socket.setdefaulttimeout(None)


_STORE = None


def get_accounts() -> AccountStore:
    global _STORE
    if _STORE is None:
        _STORE = AccountStore()
    return _STORE
