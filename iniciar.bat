@echo off
title Monitor de Ofertas
cd /d "%~dp0"
:loop
python monitor.py
if %errorlevel%==3 (
    echo Reiniciando em 10 segundos...
    timeout /t 10 /nobreak >nul
    goto loop
)
pause
