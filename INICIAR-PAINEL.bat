@echo off
chcp 65001 >nul
title Painel da Equipe - VetHome
cd /d "%~dp0"

echo.
echo   ============================================
echo     PAINEL DA EQUIPE - VetHome
echo   ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo   [!] O Python nao foi encontrado neste computador.
  echo       Instale em https://python.org e tente de novo.
  echo.
  pause
  exit /b
)

if not exist "tools\cms-config.json" (
  echo   Primeira vez aqui: escolha a senha do painel.
  echo   Ela nao aparece na tela enquanto voce digita - e normal.
  echo.
  python tools\cms.py --definir-senha
  echo.
  if not exist "tools\cms-config.json" (
    echo   Senha nao definida. Rode este arquivo de novo.
    echo.
    pause
    exit /b
  )
)

echo   Abrindo o painel no navegador...
echo.
echo   Painel: http://localhost:8791/admin
echo   Site:   http://localhost:8791/
echo.
echo   IMPORTANTE: deixe esta janela preta ABERTA enquanto usa o painel.
echo   Para encerrar, feche esta janela.
echo.

start "" http://localhost:8791/admin
python tools\cms.py

pause
