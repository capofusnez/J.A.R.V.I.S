@echo off
title Jarvis - GitHub Auto Push
echo ===================================================
echo   Sincronizzazione modifiche locale -> GitHub
echo ===================================================
echo.

:: Spostamento nella cartella corrente dello script
cd /d "%~dp0"

:: Configurazione identita Git (per sicurezza)
git config user.email "capofusnez@gmail.com"
git config user.name "capofusnez"

:: Tracciamento di tutti i file (nuovi, modificati, eliminati)
echo [1/3] Aggiunta file al tracciamento...
git add -A

:: Chiede il messaggio di commit all'utente
echo.
set /p commit_msg="Inserisci il messaggio del commit (premi INVIO per messaggio di default): "

if "%commit_msg%"=="" (
    set commit_msg=Update Jarvis - %date% %time:~0,5%
)

:: Creazione del commit
echo.
echo [2/3] Creazione commit: "%commit_msg%"...
git commit -m "%commit_msg%"

:: Push sul ramo main
echo.
echo [3/3] Invio modifiche su GitHub...
git push origin main

echo.
echo ===================================================
echo   Completato con successo!
echo ===================================================
echo.
pause