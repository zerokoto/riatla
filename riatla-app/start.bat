@echo off
REM Quick Start para Riatla App en Windows

cls
echo.
echo ====================================================
echo   RIATLA APP - INICIADOR RAPIDO
echo ====================================================
echo.

set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;%PATH%"

node --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    "C:\Program Files\nodejs\node.exe" --version >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Node.js no se encuentra en C:\Program Files\nodejs
        echo     Descargalo desde: https://nodejs.org   (version LTS)
        echo.
        pause
        exit /b 1
    )
    set "PATH=C:\Program Files\nodejs;%PATH%"
)

echo [OK] Node.js detectado:
node --version
echo.

for /f "tokens=1 delims=v." %%a in ('node --version') do set NODE_MAJOR=%%a
if %NODE_MAJOR% LSS 18 (
    echo [!] ATENCION: Se recomienda Node.js v18 o superior.
    echo.
)

if exist "node_modules\electron" (
    echo [OK] Dependencias ya instaladas.
    echo.
    goto :arrancar
)

echo [*] Instalando dependencias npm...
echo.
call npm install
if %ERRORLEVEL% NEQ 0 (
    call npm install --legacy-peer-deps
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
)

if not exist "node_modules\electron" (
    echo [ERROR] electron no se descargo correctamente.
    pause
    exit /b 1
)

:arrancar
echo.
echo ====================================================
echo   VERIFICANDO BINARIO DE ELECTRON
echo ====================================================
echo.

if not exist "node_modules\electron\dist\electron.exe" (
    echo [!] Descargando binario de Electron...
    node node_modules\electron\install.js
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudo descargar el binario de Electron.
        pause
        exit /b 1
    )
)

echo [OK] Electron encontrado.
echo.

echo ====================================================
echo   ARRANCANDO SERVICIOS
echo ====================================================
echo.

REM ── Daemon Python en terminal separada ──────────────────────────────────
echo [*] Arrancando riatla_daemon.py...
start "Riatla Daemon" cmd /k "python riatla_daemon.py"
echo [OK] Daemon arrancado en ventana separada.
echo.

REM ── Preguntar por el agente IA ──────────────────────────────────────────
set /p AGENTE="¿Arrancar tambien el agente de IA (riatla_agent.py)? (S/N): "
if /i "%AGENTE%"=="S" (
    echo [*] Arrancando riatla_agent.py...
    start "Riatla Agent" cmd /k "python riatla_agent.py"
    echo [OK] Agente IA arrancado en ventana separada.
) else (
    echo [*] Agente IA omitido.
)
echo.

REM ── Pequeña pausa para que el daemon se conecte antes de Electron ───────
echo [*] Esperando 2 segundos para que el daemon se conecte...
timeout /t 2 /nobreak >nul
echo.

echo ====================================================
echo   ARRANCANDO ELECTRON
echo ====================================================
echo.
echo IMPORTANTE: Esta ventana debe permanecer ABIERTA.
echo Para cerrar todo, cierra primero Electron y luego esta ventana.
echo.
echo [*] Arrancando Electron...
echo.

PowerShell -NoProfile -ExecutionPolicy Bypass -Command "& '.\node_modules\electron\dist\electron.exe' ."
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% NEQ 0 (
    echo [ERROR] Electron cerro con codigo de error: %EXITCODE%
) else (
    echo [*] Electron cerrado correctamente.
)

exit /b 0