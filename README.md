---
⚡ J.A.R.V.I.S. — Local AI Virtual Assistant 

J.A.R.V.I.S. (Just A Rather Very Intelligent System) è un assistente vocale e testuale 100% locale, sviluppato in Python e PyQt6 con interfaccia grafica in stile Stark Industries HUD (Mark.I).

Il sistema integra modelli di intelligenza artificiale locali via Ollama, sintesi/riconoscimento vocale avanzato con faster-whisper, integrazione email IMAP/SMTP e memoria a lungo termine.

---
⚡ Quick Start: Release Pronta all'Uso (.exe)

Se desideri utilizzare subito Jarvis senza installare Python o configurare l'ambiente di sviluppo, puoi scaricare l'eseguibile Standalone già compilato per Windows:

1. **Scarica il file:** Vai alla pagina della [Release V1.1.0 su GitHub](https://github.com/capofusnez/J.A.R.V.I.S/releases/tag/V1.1.0) e scarica il file `Jarvis.exe` dagli *Assets*.
2. **Configura i servizi opzionali (Opzionale):** Crea o inserisci un file `.env` nella stessa cartella dell'eseguibile se vuoi abilitare le funzionalità email.
3. **Avvia l'applicazione:** Fai doppio click su `Jarvis.exe`.

💡 Gestione Automatica Ollama

All'avvio, Jarvis verifica la presenza di Ollama sul sistema. Se il servizio non è in esecuzione, lo avvia automaticamente in background. Se il modello neurale (qwen2.5) non è presente, ti avviserà e avvierà il download automatico con la barra di avanzamento.

---
📸 Caratteristiche Principali

100% Locale e Privato: Risposte generate da modelli LLM locali (es. qwen2.5) senza invio dati a server terzi.

Interfaccia Grafica Stark HUD: UI moderna e reattiva realizzata in PyQt6 con indicatore centrale dinamico.

Input Vocale con VAD & Whisper: Trascrizione vocale ad alta precisione tramite faster-whisper con soppressione del rumore e filtro per silenzi/falsi positivi.

Automazione Ollama Integrata: Rilevamento, avvio automatico del servizio e download assistito del modello neurale.

Gestione Posta Elettronica: Lettura, sintesi, bozza e invio di email via IMAP/SMTP direttamente dall'assistente.

Memoria Dinamica: Mantenimento di fatti ed esigenze personali dell'utente in un database locale JSON.

Strumenti di Sistema: Controllo volume, apertura app/cartelle, monitoraggio diagnostico del PC (CPU, RAM, Disco) e ricerca web.

---
📋 Requisiti di Sistema

1. Prerequisiti Hardware e OS
Sistema Operativo: Windows 10 / 11 (64-bit)

Python: 3.10 o 3.11 (necessario solo se esegui il codice sorgente; consigliato per massima compatibilità con i moduli C/CUDA)

2. Ollama (Neural Core)
Jarvis richiede Ollama per l'elaborazione del linguaggio naturale in locale.

Scarica e installa Ollama.

Jarvis si occuperà di avviare il servizio in background e di scaricare il modello qwen2.5 al primo avvio se non presente nella libreria locale.

---
⚙️ Guida all'Installazione da Codice Sorgente

1. Clona la Repository
Bash
git clone https://github.com/capofusnez/Jarvis.git
cd Jarvis
2. Installa le Dipendenze
Bash
pip install -r requirements.txt
Se non hai un file requirements.txt, puoi installare manualmente i pacchetti necessari:

Bash
pip install PyQt6 qtawesome requests psutil pyttsx3 speechrecognition sounddevice numpy faster-whisper ctranslate2 python-dotenv duckduckgo-search
🔐 Configurazione dell'Ambiente (.env)
Per abilitare le funzionalità di lettura e invio delle email, crea un file nominato .env nella cartella principale del progetto (dove si trova main.py o accanto a Jarvis.exe)

MAIL_ADDRESS=tua_email@gmail.com

MAIL_PASSWORD=tua_password_app_generata

MAIL_FROM_NAME=TuoNome

⚠️ Nota per gli utenti Gmail: Se utilizzi Gmail, la MAIL_PASSWORD non è la tua password solita, ma una Password per le app da 16 caratteri generata nelle impostazioni di sicurezza del tuo account Google (richiede la verifica a 2 fattori attiva).

----
🚀 Come Avviare Jarvis da Sorgente

Avvia l'interfaccia principale eseguendo main.py:

Bash
python main.py
Modalità di Interazione
Manuale: Digita un comando nella barra di testo o premi il pulsante PARLA per inviare un comando vocale singolo.

HUD Auto (Ascolto Continuo): Clicca su HUD: MANUALE per passare a HUD: AUTO. Jarvis ascolterà in continuo la tua voce sospendendo l'ascolto quando prende la parola.

---
📦 Compilazione dell'Eseguibile (.exe)

Se desideri ricompilare in autonomia l'eseguibile stand-alone per Windows:

Installa PyInstaller:

Bash
pip install pyinstaller
Esegui il comando di build (escludendo il file .env per sicurezza):

Bash
python -m PyInstaller --noconsole --onefile --icon=icona.ico --add-data "icona.ico;." --add-data "modules;modules" --hidden-import=qtawesome --hidden-import=PyQt6 --hidden-import=requests --hidden-import=psutil --hidden-import=pyttsx3 --hidden-import=speech_recognition --hidden-import=sounddevice --hidden-import=numpy --hidden-import=dotenv --hidden-import=ddgs --collect-all faster_whisper --collect-all ctranslate2 --collect-all qtawesome --name "Jarvis" main.py
L'eseguibile generato si troverà nella cartella dist/Jarvis.exe.

---
