@echo off
chcp 65001 >nul
title Robo Previdenciario - Agendar busca diaria
cd /d "%~dp0"
set HORA=08:00
set /p HORA=Que horas buscar todo dia (dias uteis)? [Enter = 08:00]: 
schtasks /Create /F /TN "Robo Previdenciario - DJEN" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST %HORA% /TR "\"%~dp02_buscar_publicacoes.bat\" --sem-pausa"
if %errorlevel%==0 (
  echo.
  echo Agendado! De segunda a sexta, as %HORA%, o robo busca as publicacoes.
  echo O computador precisa estar LIGADO nesse horario.
) else (
  echo Nao consegui agendar. Clique com o botao direito neste arquivo e escolha "Executar como administrador".
)
pause
