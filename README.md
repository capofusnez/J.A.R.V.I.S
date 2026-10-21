# ⚡ J.A.R.V.I.S. — Local AI Virtual Assistant

**J.A.R.V.I.S.** (Just A Rather Very Intelligent System) è un assistente vocale e testuale 100% locale, sviluppato in Python e PyQt6 con interfaccia grafica in stile Stark Industries HUD (Mark.I).

Il sistema integra modelli di intelligenza artificiale locali via **Ollama**, sintesi/riconoscimento vocale avanzato con **faster-whisper**, integrazione email IMAP/SMTP e memoria a lungo termine.

---

## 📸 Caratteristiche Principali

* **100% Locale e Privato:** Risposte generate da modelli LLM locali (es. `qwen2.5`) senza invio dati a terzi.
* **Interfaccia Grafica Stark HUD:** UI moderna e reattiva realizzata in PyQt6 con indicatore centrale dinamico.
* **Input Vocale con VAD & Whisper:** Trascrizione vocale ad alta precisione tramite `faster-whisper` con soppressione del rumore e filtro per silenzi/falsi positivi.
* **Gestione Posta Elettronica:** Lettura, sintesi, bozza e invio di email via IMAP/SMTP direttamente dall'assistente.
* **Memoria Dinamica:** Mantenimento di fatti ed esigenze personali dell'utente in un database locale JSON.
* **Strumenti di Sistema:** Controllo volume, apertura app/cartelle, monitoraggio diagnostico del PC (CPU, RAM, Disco) e ricerca web.

---

## 📋 Requisiti di Sistema

### 1. Prerequisiti Hardware e OS
* **Sistema Operativo:** Windows 10 / 11 (64-bit)
* **Python:** 3.10 o 3.11 *(consigliati per massima compatibilità con i moduli C/CUDA)*

### 2. Ollama (Neural Core)
Jarvis richiede **Ollama** per la generazione del testo in locale.
1. Scarica e installa [Ollama](https://ollama.com/).
2. Apri il terminale/prompt dei comandi ed esegui il download del modello principale:
   ```bash
   ollama run qwen2.5

---
⚙️ Guida all'Installazione
1. Clona la Repository
   git clone [https://github.com/capofusnez/Jarvis.git](https://github.com/capofusnez/Jarvis.git)
cd Jarvis

---

2. Installa le Dipendenze
pip install -r requirements.txt

Se non hai un file requirements.txt, puoi installare i pacchetti necessari con
pip install PyQt6 qtawesome requests psutil pyttsx3 speechrecognition sounddevice numpy faster-whisper ctranslate2 python-dotenv duckduckgo-search

---

🔐 Configurazione dell'Ambiente (.env)
Per abilitare le funzionalità di lettura e invio delle email, crea un file nominato .env nella cartella principale del progetto (dove si trova main.py)

MAIL_ADDRESS=tua_email@gmail.com

MAIL_PASSWORD=tua_password_app_generata

MAIL_FROM_NAME=TuoNome

⚠️ Nota per gli utenti Gmail: Se utilizzi Gmail, la MAIL_PASSWORD non è la tua password solita, ma una Password per le app da 16 caratteri che devi generare nelle impostazioni di sicurezza del tuo account Google (richiede la verifica a 2 fattori attiva).

---

🚀 Come Avviare Jarvis
Assicurati che Ollama sia in esecuzione in background.

Avvia l'interfaccia principale eseguendo main.py

python main.py


Modalità di Interazione
Manuale: Digita un comando nella barra di testo o premi il pulsante PARLA per inviare un comando vocale singolo.

HUD Auto (Ascolto Continuo): Clicca su HUD: MANUALE per passare a HUD: AUTO. Jarvis ascolterà in continuo la tua voce sospendendo l'ascolto quando prende la parola.

---

📦 Compilazione in file .exe (PyInstaller)
Se vuoi generare un eseguibile stand-alone in unico file senza dover avviare il codice da Python:

pip install pyinstaller

python -m PyInstaller --noconsole --onefile --icon=icona.ico --add-data "icona.ico;." --add-data "modules;modules" --add-data ".env;." --hidden-import=qtawesome --hidden-import=PyQt6 --hidden-import=requests --hidden-import=psutil --hidden-import=pyttsx3 --hidden-import=speech_recognition --hidden-import=sounddevice --hidden-import=numpy --hidden-import=dotenv --hidden-import=ddgs --collect-all faster_whisper --collect-all ctranslate2 --collect-all qtawesome --name "Jarvis" main.py

L'eseguibile pronto si troverà nella cartella dist/Jarvis.exe.

---

Jarvis/
├── main.py              # Entry point dell'applicazione
├── gui_v2.py            # Interfaccia grafica PyQt6 (Stark HUD)
├── .env                 # Configurazione credenziali locali (da creare)
└── modules/
    ├── brain.py         # Logica principale, parsing intenti e ponte verso Ollama
    ├── listener.py      # Gestione microfono e trascrizione via faster-whisper
    ├── speaker.py       # Sintesi vocale TTS (pyttsx3)
    ├── mail.py          # Gestione IMAP/SMTP e rilevamento email importanti
    ├── memory.py        # Gestione memoria locale JSON (memory.json)
    └── tools.py         # Controllo volume, app, processi e stato del sistema

---    
