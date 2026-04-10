@echo off
setlocal
title E-Lixo Zero - Local Server

echo ==========================================
echo       INICIAR SERVIDOR E-LIXO ZERO
echo ==========================================
echo.
echo [1] Iniciar normalmente (Localhost apenas)
echo [2] Iniciar com ngrok (Link Publico)
echo.

set /p choice="Escolha uma opcao (1 ou 2): "

rem --- CONFIGURACAO DE EMAIL (GMAIL) ---
set MAIL_USERNAME=gabrielcrodrigues2008@gmail.com
set MAIL_PASSWORD=dtfvlgdpfredsrup

rem --- CONFIGURACAO NGROK ---
set NGROK_AUTHTOKEN=3AwGWkIOFFb4hD2gKMjPUbKyy5g_3Bb8SqXjwnqQHLf5u3ACk

if "%choice%"=="2" (
    echo.
    echo Iniciando com ngrok e Gmail...
    python app.py --ngrok
) else (
    echo.
    echo Iniciando normalmente com Gmail...
    python app.py
)

pause
