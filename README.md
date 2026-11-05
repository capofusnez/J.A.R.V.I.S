# J.A.R.V.I.S. — assistente vocale locale

Assistente vocale in stile film per Windows: **Python + PyQt6**, ragionamento con **Ollama**, riconoscimento vocale
**faster-whisper**, voci offline (Kokoro/Piper), controllo del PC a voce, moduli creati da Jarvis stesso e
interfaccia HUD con mappa neurale. Tutto gira in locale; i dati restano accanto all'exe.

## Indice

- [Avvio](#avvio)
- [Interfaccia](#interfaccia)
- [Ascolto con il nome](#ascolto-con-il-nome)
- [Riconoscere le voci](#riconoscere-le-voci)
- [Cosa puoi dire](#cosa-puoi-dire)
- [Voce di Jarvis](#voce-di-jarvis)
- [Moduli creati da Jarvis](#moduli-creati-da-jarvis)
- [Impostazioni](#impostazioni)
- [Modelli](#modelli)
- [Risoluzione problemi](#risoluzione-problemi)

## Avvio

1. Estrai tutto in una cartella (per esempio `C:\Jarvis`).
2. Doppio clic su `avvia.bat`: la prima volta installa le librerie (qualche minuto), poi parte da solo.
   Serve **Python 3.11 o più recente**. Se manca Ollama, Jarvis lo scarica e lo installa chiedendo il permesso.
3. Modelli: da **Impostazioni (⚙) → MODELLI** scegli e scarica quelli che vuoi, oppure `ollama pull qwen2.5`.
4. Posta (facoltativa): da **Impostazioni → POSTA / ACCOUNT**, oppure copia `env_example.txt` in `.env` e compila
   indirizzo e "password per le app". Il `.env` sta accanto a `main.py` / `Jarvis.exe`.

Durante l'avvio il pulsante **ANNULLA E CHIUDI** (o Esc / Alt+F4) ferma download e installer e chiude tutto.

## Interfaccia

Al centro la **mappa neurale**: i collegamenti reali di Jarvis.

- catena della voce: ASCOLTO → WHISPER → CERVELLO → VOCE → ALTOPARLANTE
- un nodo per ogni modello Ollama acceso (**BASE** = chat principale), più MEMORIA, POSTA e RICERCA
- tutti i moduli-strumento attorno al cervello; quando Jarvis usa un modello o uno strumento il nodo si illumina

| Segno sulla mappa | Significato |
|---|---|
| linea piena | modulo collegato |
| linea rotta + X | modulo disattivato (`config.json`) o modello non installato |
| nodo vuoto giallo | modulo creato da Jarvis, in attesa del tuo «installa» |
| rombo giallo | modulo creato da Jarvis |

A sinistra, vicino alle specifiche del PC, la riga **MODELLO** mostra il modello base; durante una risposta diventa
`▶ nome · BASE` oppure `▶ nome · POTENTE`. A destra, sotto la chat, il pannello **ELABORAZIONE DATI** mostra in tempo
reale ascolto, input capito, modello usato, strumenti, output e tempi.

| Tasto | Azione |
|---|---|
| F2 | solo mappa (nasconde i pannelli laterali) |
| F8 | microfono muto / attivo |
| F9 | Impostazioni |
| F10 | mostra/nasconde ELABORAZIONE DATI |
| F11 | schermo intero |

Pulsante **MIC ●** (verde = in ascolto) / **MUTO** (rosso = a riposo) in basso: puoi sempre scrivere a Jarvis.

## Ascolto con il nome

All'avvio Jarvis è già in ascolto e ignora tutto finché non dici **«Jarvis»**.

- «ehi Jarvis, che ore sono» → risponde subito.
- Solo «Jarvis» → due note brevi e aspetta che parli (circa 10 s). Se non parli più torna in attesa.
- Se ti fa una domanda o aspetta una conferma tiene il microfono aperto circa 14 s.

Variabili: `JARVIS_WAKE_WAIT`, `JARVIS_REPLY_WAIT` (secondi), `JARVIS_AUTOSTART=0` per non avviare l'ascolto all'accensione.

## Riconoscere le voci

Tutto in locale. Al primo avvio scarica un piccolo modello (~26 MB) in `voices\speaker_model.onnx`; serve `onnxruntime`.
Le impronte (non l'audio) stanno in `data\voiceprints.json`.

| Dì | Effetto |
|---|---|
| «impara la mia voce, sono Andrea» | ascolta quattro frasi e impara; il primo presentato è il proprietario |
| «impara la voce di Marco» | poi fai parlare Marco per quattro frasi |
| «ora sta parlando Marco» | assegna a Marco le frasi appena sentite |
| «chi sta parlando» / «chi conosci» | dice chi riconosce |
| «dimentica la voce di Marco» | la cancella |
| «rispondi solo a me» / «rispondi a tutti» | ignora / ascolta le altre voci |

Gli altri possono chiacchierare con Jarvis, ma spegnimento, cancellazioni, email, mouse/tastiera, moduli e aggiornamenti
li accetta solo dal proprietario (da tastiera sei sempre il proprietario). Variabili: `JARVIS_VOICE_GATE=0` disattiva
il blocco; `JARVIS_VOICE_THRESHOLD` (predefinito `0.42`, più alto = più severo).

## Cosa puoi dire

| Area | Esempi |
|---|---|
| Conversazione | parla normalmente; compiti difficili, codice e moduli usano il modello più adatto |
| Media | «metti in pausa», «riprendi», «prossima canzone» |
| Finestre | «minimizza», «chiudi la finestra», «cambia finestra», «passa a Chrome», «quali finestre ho aperte» |
| Tastiera | «digita ciao a tutti», «premi invio», «premi controllo c», «incolla» |
| Mouse | «clicca», «doppio clic», «scorri giù», «sposta il mouse al centro» |
| Schermo | «fai uno screenshot», «luminosità al 60» |
| Sistema | «blocca il computer», «stato della batteria», «quanto spazio ho sul disco», «apri la calcolatrice» |
| File | «trova il file fattura marzo», «apri la cartella download», «crea una cartella Progetti sul desktop» |
| Posta | «ci sono email nuove?», «leggi l'ultima email», «scrivi un'email a Marco per dirgli che…» |
| Memoria | «ricorda che…», «dimentica che…», «cosa sai di me?» |
| Aggiornamenti | «controlla gli aggiornamenti», «installa l'aggiornamento», «che versione sei» |
| Informazioni | «quali modelli hai», «quali account hai», «usa l'account lavoro» |

**Con conferma a voce** (rispondi «conferma» entro 30 s, oppure «annulla»): spegnere, riavviare, sospendere,
chiudere la sessione, svuotare il cestino, cancellare un file (va nel cestino). «annulla lo spegnimento» lo ferma.
La posta viene inviata solo dopo il tuo «invia». File e cartelle si toccano solo nella cartella utente.

## Voce di Jarvis

«usa la voce di Nicola» (uomo) / «usa la voce di Sara» (donna): voci **offline**, ~90 MB la prima volta.
`nicola-hd` / `sara-hd` sono a qualità massima (~310 MB). Altre: `elsa` (Windows), `diego`, `giuseppe`, `isabella`
(Edge, online), `paola`, `riccardo` (Piper, offline). «cambia voce», «elenco voci». Per provarle: `python provavoce.py`.

## Moduli creati da Jarvis

«crea un modulo che converte le valute»: il modello di codice scrive il modulo, Jarvis lo controlla e lo mette in
`moduli\_pending`. Dì **«installa»** per attivarlo (compare collegato sulla mappa) oppure **«annulla»**. Poi basta
chiedere «converti 10 euro in dollari». Jarvis non modifica mai da solo i suoi file principali.
Se un modulo non si collega: passa il mouse sul nodo (di solito manca una libreria: `pip install nome-libreria`);
il motivo è anche in `logs\jarvis.log`, riga `[MODULI]`. Un modulo con `false` in `config.json` è spento di proposito.

## Impostazioni

Ingranaggio in alto a destra, oppure **F9**.

- **MODELLI** — tutti i modelli Ollama con i GB che occupano; per ognuno acceso/spento e per cosa va usato (chat, veloce,
  difficile, codice, ragionamento, immagini). Jarvis sceglie da solo il più adatto. Scarica dall'elenco (con i GB) o con
  un nome, con barra di avanzamento e Annulla. «Elimina» cancella anche i file dal disco. I modelli *cloud*
  (es. `kimi-k3.1-pro:cloud`) sono a pagamento e restano spenti finché non li accendi tu.
- **POSTA / ACCOUNT** — più account (Gmail, iCloud, Yahoo…): indirizzo, password per le app, nome; «Prova accesso».
  Le password stanno in `data\accounts.json`.
- **VOCI** — le persone riconosciute, «dimentica la voce», «ascolta solo il proprietario».


## Modelli

Se il modello grande non parte (errore 500 di Ollama, di solito memoria insufficiente: un 14b vuole ~9–10 GB liberi),
Jarvis lo dice, usa il modello normale e riprova dopo 10 minuti. Per uno più leggero: `ollama pull qwen2.5-coder:7b`
e `JARVIS_CODER_MODEL=qwen2.5-coder:7b`. Predefiniti: `qwen2.5` (`JARVIS_MODEL`) e `qwen2.5-coder:14b`
(`JARVIS_CODER_MODEL`), caricato solo quando serve.


## Risoluzione problemi

- **`.env` non letto**: deve chiamarsi esattamente `.env` (anche `.env.txt` viene letto) e stare accanto all'exe; riavvia.
  Dì «ci sono email nuove?»: Jarvis ti dice cosa manca.
- **Errore 500 di Ollama**: memoria insufficiente per il modello, vedi [Modelli](#modelli).
- **Qualcosa non parte**: guarda `logs\jarvis.log` e `logs\jarvis_crash.log`.
