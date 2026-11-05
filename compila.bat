@echo off
setlocal
cd /d "%~dp0"
REM Se il tuo Python e' in un altro percorso, cambia la riga qui sotto.
set "PY=C:\Users\capof\AppData\Local\Python\pythoncore-3.14-64\python.exe"

echo === Compilazione di Jarvis ===
echo Cartella: %CD%
if not exist "%PY%" (
    echo ERRORE: non trovo Python in "%PY%"
    echo Apri questo file con il Blocco note e correggi la riga "set PY=".
    goto :fine
)
if not exist "main.py" (
    echo ERRORE: main.py non e' in questa cartella.
    goto :fine
)

echo.
echo [1/2] Installo/aggiorno PyInstaller...
"%PY%" -m pip install -U pyinstaller
if errorlevel 1 (
    echo ERRORE: installazione di PyInstaller non riuscita.
    goto :fine
)

echo.
echo [2/2] Compilo (puo' richiedere diversi minuti)...
"%PY%" compila.py
if errorlevel 1 (
    echo.
    echo ERRORE: la compilazione e' fallita. Copia le ultime righe qui sopra e mandamele.
    goto :fine
)

echo.
if exist "dist\Jarvis.exe" (
    echo FATTO: dist\Jarvis.exe
    echo Copia l'exe dove vuoi e metti il file .env nella stessa cartella.
) else (
    echo NON RIUSCITA: dist\Jarvis.exe non e' stato creato.
)

:fine
echo.
pause
