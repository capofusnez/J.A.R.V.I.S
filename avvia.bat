@echo off
setlocal
cd /d "%~dp0"
title Jarvis

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>nul && set "PYCMD=python"
if not defined PYCMD goto :nopython

if exist ".dipendenze_ok" goto :avvia

echo Prima volta: installo le librerie necessarie. Ci vorra' qualche minuto...
%PYCMD% -m pip install -r requirements.txt
if errorlevel 1 goto :errpip
echo ok> .dipendenze_ok
echo.
echo Installo le voci offline, facoltative. Se qualcuna non si installa, si va avanti lo stesso...
for /f "usebackq eol=# tokens=*" %%p in ("requirements-opzionali.txt") do %PYCMD% -m pip install %%p

:avvia
%PYCMD% main.py
if errorlevel 1 goto :errjarvis
goto :fine

:nopython
echo Python non trovato. Installalo da python.org e riprova.
goto :pausa

:errpip
echo.
echo ERRORE nell'installazione delle librerie. Leggi il messaggio qui sopra.
goto :pausa

:errjarvis
echo.
echo Jarvis si e' chiuso con un errore. I dettagli sono nella cartella logs, file jarvis.log
goto :pausa

:pausa
echo.
pause
:fine
