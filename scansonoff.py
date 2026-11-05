"""Cerca sulla tua rete le placche/interruttori eWeLink (Sonoff) e controlla se si lasciano comandare in locale.

Uso:   python scansonoff.py          (il PC deve stare nella STESSA rete Wi-Fi/cavo delle placche)
Non installa nulla e non cambia nulla: manda una domanda mDNS e legge le risposte per circa 10 secondi.
Il risultato resta anche nel file scansonoff_risultato.txt (puoi mandarlo a chi ti aiuta: non contiene password).
"""
import json
import socket
import struct
import sys
import time
import urllib.request

MDNS_ADDR, MDNS_PORT = "224.0.0.251", 5353
SERVICES = ["_ewelink._tcp.local", "_http._tcp.local"]
LISTEN_SECONDS = 10


# ------------------------------------------------------------------ DNS minimale
def build_query(names):
    out = struct.pack(">HHHHHH", 0, 0, len(names), 0, 0, 0)
    for n in names:
        for part in n.strip(".").split("."):
            out += bytes([len(part)]) + part.encode()
        out += b"\x00" + struct.pack(">HH", 12, 0x8001)            # PTR, classe IN con richiesta di risposta diretta
    return out


def read_name(data, off):
    labels, jumped, end = [], False, off
    for _ in range(64):
        n = data[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | data[off + 1]
            if not jumped:
                end = off + 2
            off, jumped = ptr, True
            continue
        labels.append(data[off + 1: off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
    if not jumped:
        end = off
    return ".".join(labels), end


def parse(data):
    """Ritorna una lista di record (tipo, nome, valore)."""
    recs = []
    if len(data) < 12:
        return recs
    _, _, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    off = 12
    for _ in range(qd):
        _, off = read_name(data, off)
        off += 4
    for _ in range(an + ns + ar):
        name, off = read_name(data, off)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[off: off + 10])
        off += 10
        rd = data[off: off + rdlen]
        if rtype == 12:                                              # PTR
            recs.append(("PTR", name, read_name(data, off)[0]))
        elif rtype == 33:                                            # SRV
            port = struct.unpack(">H", rd[4:6])[0]
            recs.append(("SRV", name, (port, read_name(data, off + 6)[0])))
        elif rtype == 16:                                            # TXT
            txt, i = {}, 0
            while i < len(rd):
                ln = rd[i]
                item = rd[i + 1: i + 1 + ln].decode("utf-8", "replace")
                k, _, v = item.partition("=")
                txt[k] = v
                i += 1 + ln
            recs.append(("TXT", name, txt))
        elif rtype == 1 and rdlen == 4:                              # A
            recs.append(("A", name, socket.inet_ntoa(rd)))
        off += rdlen
    return recs


# ------------------------------------------------------------------ scansione
def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))                                   # nessun pacchetto: serve solo a scegliere la scheda di rete
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


def scan():
    ip = local_ip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
    except OSError:
        pass
    sock.bind((ip if ip != "0.0.0.0" else "", 0))
    sock.settimeout(0.5)
    found = {}                                                       # nome istanza -> dati
    ptrs, srv, txt, addr = {}, {}, {}, {}
    t0, last_q = time.time(), 0.0
    while time.time() - t0 < LISTEN_SECONDS:
        if time.time() - last_q > 2.5:                               # ripete la domanda: alcune placche rispondono tardi
            sock.sendto(build_query(SERVICES), (MDNS_ADDR, MDNS_PORT))
            last_q = time.time()
        try:
            data, src = sock.recvfrom(9000)
        except socket.timeout:
            continue
        except OSError:
            continue
        try:
            for kind, name, val in parse(data):
                if kind == "PTR":
                    ptrs[val] = name
                elif kind == "SRV":
                    srv[name] = val
                elif kind == "TXT":
                    txt[name] = val
                elif kind == "A":
                    addr[name] = val
                    addr.setdefault("@" + name, src[0])
        except Exception:
            continue
    sock.close()
    for inst, service in ptrs.items():
        port, host = srv.get(inst, (None, ""))
        t = txt.get(inst, {})
        if "ewelink" not in service and not any(k in t for k in ("deviceid", "type", "data1")) \
                and "eWeLink" not in inst and "ewelink" not in inst.lower():
            continue
        found[inst] = {"service": service, "port": port, "host": host, "ip": addr.get(host) or addr.get("@" + host), "txt": t}
    return ip, found


def probe(ip, port):
    """Il comando 'info' della modalità locale (DIY): se risponde, la placca si lascia comandare senza cloud."""
    try:
        req = urllib.request.Request(f"http://{ip}:{port}/zeroconf/info", data=json.dumps(
            {"deviceid": "", "data": {}}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            return "risponde", json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return f"non risponde ({type(e).__name__})", None


def main():
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out(f"Cerco placche eWeLink/Sonoff per {LISTEN_SECONDS} secondi... (il tuo PC: {local_ip()})")
    ip, found = scan()
    if not found:
        out("\nNessuna placca trovata in locale.")
        out("Possibili motivi: il PC è su un'altra rete (ospiti, extender, cavo con router diverso), il router isola i dispositivi")
        out("Wi-Fi tra loro, il firewall di Windows ha bloccato Python (consenti l'accesso alla rete privata quando lo chiede),")
        out("oppure le placche non annunciano nulla in locale. In quel caso si passa al cloud eWeLink.")
    for inst, d in found.items():
        out("\n--- " + inst.split(".")[0])
        out(f"  indirizzo: {d['ip']}  porta: {d['port']}  servizio: {d['service']}")
        t = d["txt"]
        for k in ("id", "deviceid", "type", "apivers", "encrypt", "iv", "switches", "data1"):
            if k in t:
                v = t[k] if len(t[k]) < 70 else t[k][:67] + "..."
                out(f"  {k}: {v}")
        encrypted = str(t.get("encrypt", "")).lower() == "true" or "iv" in t
        if d["ip"] and d["port"]:
            res, info = probe(d["ip"], d["port"])
            out(f"  prova comando locale (/zeroconf/info): {res}")
            if info:
                out("  risposta: " + json.dumps(info)[:300])
        if encrypted:
            out("  -> modalità LAN CIFRATA: comandabile in locale, ma serve la chiave del dispositivo (si ricava una volta dall'account).")
        else:
            out("  -> locale APERTA: la più semplice, si comanda con un normale comando di rete.")
    out(f"\nTrovate: {len(found)}")
    try:
        with open("scansonoff_risultato.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        out("Risultato salvato in scansonoff_risultato.txt")
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    if sys.platform == "win32" and sys.stdin and sys.stdin.isatty():
        input("\nPremi Invio per chiudere...")
