@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Robo Previdenciario - Painel (NAO FECHE esta janela)
cd /d "%~dp0.."
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (set IP=%%a& goto :achou)
:achou
set IP=%IP: =%
echo ============================================================
echo   PAINEL LIGADO. Mantenha esta janela aberta.
echo   Neste computador:      http://localhost:8000
echo   Nos outros do escritorio: http://%IP%:8000
echo   (Se o Windows perguntar sobre o Firewall, clique em PERMITIR,
echo    marcando "Redes privadas".)
echo ============================================================
start "" http://localhost:8000
.venv\Scripts\python -m robo.cli painel --host 0.0.0.0 --porta 8000
pause
