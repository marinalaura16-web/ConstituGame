@echo off
chcp 65001 >nul
title Robo Previdenciario - Instalacao
cd /d "%~dp0.."

echo ============================================================
echo   INSTALACAO DO ROBO PREVIDENCIARIO
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (
  where python >nul 2>nul
  if %errorlevel%==0 (set PY=python) else (
    echo O Python nao esta instalado. Instalando agora pelo Windows...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo Python instalado. FECHE esta janela e clique de novo em 1_instalar.bat
    pause
    exit /b
  )
)

echo [1/3] Criando ambiente do robo...
%PY% -m venv .venv || goto erro

echo [2/3] Instalando componentes (pode levar alguns minutos)...
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt -q || goto erro

echo [3/3] Preparando configuracao...
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Vai abrir o arquivo de configuracao no Bloco de Notas.
  echo Preencha pelo menos DJEN_OABS e ANTHROPIC_API_KEY, SALVE e feche.
  pause
  notepad .env
)

echo.
echo ============================================================
echo   PRONTO! Agora use 2_buscar_publicacoes.bat
echo ============================================================
pause
exit /b

:erro
echo.
echo *** Algo deu errado. Tire um print desta janela e envie. ***
pause
