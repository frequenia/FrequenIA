@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "FLUTTER_BIN=C:\Flutter\flutter\bin\flutter.bat"

if not exist "%FLUTTER_BIN%" (
  echo Flutter nao encontrado em %FLUTTER_BIN%.
  echo Ajuste FLUTTER_BIN neste arquivo para o caminho correto.
  pause
  exit /b 1
)

cd /d "%PROJECT_ROOT%mobile"
if errorlevel 1 (
  echo Nao foi possivel acessar a pasta mobile.
  pause
  exit /b 1
)

echo Atualizando dependencias do aplicativo...
call "%FLUTTER_BIN%" pub get
if errorlevel 1 (
  echo Falha ao obter as dependencias Flutter.
  pause
  exit /b 1
)

echo Abrindo o aplicativo mobile no Chrome...
call "%FLUTTER_BIN%" run -d chrome ^
  --dart-define=APP_ENV=development ^
  --dart-define=BASE_URL=http://localhost:5013

if errorlevel 1 (
  echo O Flutter encerrou com erro. Veja a mensagem acima.
  pause
)
