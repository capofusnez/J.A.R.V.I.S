# Changelog

Tutte le modifiche, le evoluzioni architetturali, i fix e i miglioramenti implementati in **J.A.R.V.I.S.** (Local AI Virtual Assistant) sono documentati in questo file con il massimo livello di dettaglio.

Il formato si basa su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/)
e il progetto aderisce al `Semantic Versioning`.

---

## [1.1.1] - 2026-10-22

### 🏗️ Architettura e Modularità (Refactoring completo dei Tool)
* **Disaccoppiamento della classe `LocalTools`:** La classe monolitica precedente è stata completamente rimossa e suddivisa in un pacchetto Python strutturato all'interno della cartella `modules/tools/`, separando nettamente le competenze logiche in file dedicati:
  * `audio_tools.py`: Isolata tutta la logica di interfaccia con le API di Windows e la libreria `pycaw`.
  * `system_tools.py`: Isolate le funzioni basate su `psutil` per il monitoraggio hardware, la chiusura dei processi e la navigazione del filesystem (`smart_open`).
  * `web_tools.py`: Isolate le funzioni di automazione del browser, le ricerche web su Google e la gestione delle scorciatoie predefinite.
* **Pattern Facade in `__init__.py`:** Implementata una classe unificata in `modules/tools/__init__.py` che eredita da tutti i singoli sotto-moduli tramite ereditarietà multipla, garantendo la retrocompatibilità totale con il resto dell'applicazione (`main.py` e `brain.py`) senza richiedere modifiche alle chiamate esistenti.
* **Configurazione esterna centralizzata tramite `config.json`:** Introdotta la lettura delle preferenze da un file JSON esterno posizionato nella root del progetto. Permette di configurare dinamicamente il modello LLM in uso, l'URL di Ollama, il tempo di permanenza in memoria (`keep_alive`) e lo stato di abilitazione dei singoli moduli (`audio`, `system`, `web`).
* **Auto-generazione intelligente della configurazione:** Aggiunto un controllo di esistenza nel metodo `_load_config()`. Qualora il file `config.json` non venga rilevato nella root (durante una nuova installazione pulita o dopo la compilazione dell'eseguibile), Jarvis provvede a crearlo autonomamente scrivendo un dizionario con i parametri di default predefiniti.

### 🔊 Sistema Audio, Hardware e Fix Definitivo di `pycaw`
* **Risoluzione degli errori di scoping e attributi:** Eliminati definitivamente gli errori critici di esecuzione come `AudioDevice object has no attribute Activate` e i conflitti di importazione locale della libreria `comtypes`.
* **Helper sicuro `_get_volume_interface()`:** Sviluppato un livello di astrazione interno che verifica la struttura dell'oggetto restituito da `pycaw` (`AudioUtilities.GetSpeakers()`), supportando in modo nativo e retrocompatibile sia il metodo `.Activate()` sia la proprietà diretta `.EndpointVolume`.
* **Supporto avanzato per volumi relativi e assoluti:** Implementata la gestione sia dei livelli percentuali fissi (es. *"volume al 60%"*) sia degli incrementi e decrementi incrementali (es. *"alza il volume"* e *"abbassa il volume"* con variazioni fisse del `±15%`), oltre alle scorciatoie rapide per il mute e il livello massimo al 100%.

### ⚡ Fast Path, Routing e Diagnostica in Tempo Reale
* **Estensione del vocabolario di intercettazione (Regex):** Aggiornate le regole di riconoscimento rapido (`_fast_path`) all'interno del modulo `brain.py` per catturare i comandi verbali naturali relativi al controllo audio senza sovraccaricare o passare dall'elaborazione dell'LLM.
* **Funzione di diagnostica `get_modules_status()`:** Implementato un metodo di controllo dello stato operativo che verifica in tempo reale sia le preferenze booleane impostate nel `config.json` sia la reale disponibilità fisica delle librerie di terze parti sul sistema (come `pycaw` e `psutil`), restituendo un report dettagliato all'avvio o su richiesta.

### 📦 Compilazione, Pacchettizzazione e Release (PyInstaller)
* **Ottimizzazione dei parametri di build:** Aggiornato il comando di compilazione con PyInstaller (`--onefile --noconsole`) aggiungendo il parametro `--add-data "modules;modules"` per assicurarsi che l'intera struttura dei pacchetti interni venga correttamente inglobata nell'eseguibile, mantenendo tuttavia l'isolamento dei file di configurazione esterni (`config.json` e `.env`) per garantire la massima flessibilità di modifica post-compilazione.

---

## [1.1.0] - 2026-10-15 (Prima Release Pubblicata)

### 🚀 Nuove Funzionalità & Core Iniziale
* **Rilascio Ufficiale Iniziale:** Prima versione pubblica e stabile di **J.A.R.V.I.S.** (Local AI Virtual Assistant).
* **Integrazione Ollama e Modello Base:** Connessione nativa con i modelli linguistici locali basati sulla versione **`qwen2.5` standard**, configurati con la gestione del parametro `keep_alive` (impostato a `30m`) per l'allocazione temporanea e la permanenza ottimizzata in VRAM/RAM.
* **Interfaccia Grafica Stark HUD:** Progettazione e sviluppo della GUI avanzata basata su framework PyQt6, caratterizzata da un'estetica ispirata ai sistemi Stark, gestione dei temi e integrazione di icone vettoriali tramite `qtawesome`.
* **Voice Profiling e Sicurezza Multi-Utente:** Prima implementazione del sistema di riconoscimento vocale basato su `speechbrain` per identificare l'operatore e della frase di backdoor amministrativa per l'override dei comandi protetti.
* **Stability Watchdog e Logging:** Introduzione del tracciamento globale delle eccezioni non gestite tramite `sys.excepthook` e `faulthandler`, unitamente a un sistema di monitoraggio integrato per prevenire il blocco imprevisto del motore di sintesi vocale SAPI di Windows.

---

## [1.0.0] - Antecedenti / Prototipo e Sviluppo Iniziale
* **Prototipazione dei comandi di sistema:** Scrittura delle funzioni preliminari per l'interazione diretta con il sistema operativo Windows, sfruttando le capacità di monitoraggio di `psutil` e l'automazione del browser tramite `webbrowser`.
* **Sperimentazione delle librerie audio legacy:** Esecuzione dei primi test di interfacciamento con il mixer di sistema di Windows e la gestione del livello audio tramite l'adozione iniziale della libreria `pycaw`.
* **Impostazione dell'architettura monolitica:** Creazione della logica di base orientata agli oggetti per la gestione dei tool locali, inizialmente racchiusa all'interno di un unico file centralizzato (`tools.py`) prima della transizione all'attuale struttura modulare a pacchetti.
