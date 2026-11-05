@echo off
title Jarvis - GitHub FORCE Push
echo ===================================================
echo   ATTENZIONE: Push Forzato (Sovrascrive GitHub)
echo ===================================================
echo.

cd /d "%~dp0"

git config user.email "capofusnez@gmail.com"
git config user.name "capofusnez"

echo [1/3] Tracciamento completo file...
git add -A

set /p commit_msg="Inserisci il messaggio per il commit forzato: "

if "%commit_msg%"=="" (
    set commit_msg=Force Update Jarvis - %date% %time:~0,5%
)

echo.
echo [2/3] Creazione commit...
git commit -m "%commit_msg%"

echo.
echo [3/3] Forzatura invio su GitHub (origin/main)...
git push -u origin main --force

echo.
echo ===================================================
echo   Allineamento forzato completato!
echo ===================================================
echo.
pause