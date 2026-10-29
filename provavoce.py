"""Prova le voci di Jarvis una dopo l'altra e salva quella che preferisci.

Uso (dalla cartella principale):   python provavoce.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.speaker import Speaker, PRESETS, VOICES_DIR

SAMPLE = "Buongiorno, sono Jarvis. Tutti i sistemi sono operativi. Come posso aiutarti oggi?"


def main():
    sp = Speaker(voice="elsa")
    print("\nPROVA DELLE VOCI DI JARVIS")
    print("Ascolta ogni voce, poi scegli quella che preferisci.")
    print("Le voci online (diego, giuseppe, isabella) richiedono internet; le altre funzionano offline (nicola e sara: dopo il primo download restano sul tuo PC).\n")
    tried = []
    for key, p in PRESETS.items():
        print(f"[{key}] {p['desc']}")
        if p["engine"] in ("piper", "kokoro") and not sp.is_ready(key):
            if input("   Va scaricata una volta sola (poi resta offline). Scaricarla e provarla? [s/N] ").strip().lower() != "s":
                continue
            print("   Scarico (può richiedere qualche minuto)...")
            err = sp.prepare(key, progress=lambda g, t: print(f"\r   {g // 1048576} / {t // 1048576} MB", end="", flush=True) if t else None)
            print()
            if err:
                print("   ", err)
                continue
        msg = sp.set_voice(key, persist=False)
        if sp.voice_key != key:
            print("    saltata:", msg)
            continue
        sp.last_error = ""
        print("    in riproduzione...")
        sp.speak(SAMPLE)
        if sp.last_error:
            print("    attenzione: è stata usata la voce di Windows ->", sp.last_error)
        else:
            tried.append(key)

    if not tried:
        print("\nNessuna voce provata.")
        return
    choice = input(f"\nQuale voce vuoi usare? ({', '.join(tried)}) [invio = non cambiare nulla]: ").strip().lower()
    if choice in tried:
        print(sp.set_voice(choice))
        print("Salvata in voice.json: al prossimo avvio Jarvis userà questa voce.")
        print("Puoi cambiarla anche a voce, dicendo ad esempio: usa la voce di Diego.")
    else:
        print("Nessuna modifica.")


if __name__ == "__main__":
    main()
