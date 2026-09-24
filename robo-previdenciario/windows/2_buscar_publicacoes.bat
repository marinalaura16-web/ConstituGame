@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Robo Previdenciario - Buscar publicacoes no DJEN
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Rode primeiro o 1_instalar.bat
  pause
  exit /b
)
if not exist dados mkdir dados
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set AGORA=%%i
set SAIDA=dados\publicacoes_%AGORA%.txt

echo Buscando publicacoes no DJEN e interpretando... aguarde.
.venv\Scripts\python -m robo.cli djen --interpretar > "%SAIDA%" 2>&1
type "%SAIDA%"
echo.
echo Resultado salvo em %SAIDA%
if not "%1"=="--sem-pausa" (
  start "" notepad "%SAIDA%"
  pause
)
