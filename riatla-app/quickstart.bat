@echo off
REM Quick Start para Riatla App en Windows
REM NOTA: Este script instala dependencias Y arranca Electron.

cls
echo.
echo ====================================================
echo   RIATLA APP - INICIADOR RAPIDO
echo ====================================================
echo.

REM Agregar rutas de Node.js al PATH antes de cualquier comprobacion
REM Las comillas alrededor del nombre=valor son obligatorias cuando hay espacios
set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;%PATH%"

REM Verificar si Node.js esta instalado
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

REM Verificar version minima de Node (v18+)
for /f "tokens=1 delims=v." %%a in ('node --version') do set NODE_MAJOR=%%a
if %NODE_MAJOR% LSS 18 (
    echo [!] ATENCION: Se recomienda Node.js v18 o superior.
    echo     Version actual: 
    node --version
    echo     Puedes continuar, pero puede haber problemas con electron.
    echo.
)

REM Comprobar si ya existen node_modules/electron
if exist "node_modules\electron" (
    echo [OK] Dependencias ya instaladas. Saltando npm install.
    echo      Si quieres reinstalar, borra la carpeta node_modules\ y ejecuta de nuevo.
    echo.
    goto :arrancar
)

echo [*] Instalando dependencias npm (tarda 1-3 minutos, paciencia)...
echo.

call npm install
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] npm install fallo. Intentando con --legacy-peer-deps...
    echo.
    call npm install --legacy-peer-deps
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [ERROR] No se pudieron instalar las dependencias.
        echo         Revisa los errores de arriba y consulta GETTING_STARTED.md
        echo.
        pause
        exit /b 1
    )
)

echo.
echo ====================================================
echo   [OK] Dependencias instaladas correctamente
echo ====================================================
echo.

REM Verificar que electron se instalo
if not exist "node_modules\electron" (
    echo [ERROR] electron no se descargo correctamente en node_modules.
    echo         Ejecuta manualmente: npm install --save-dev electron@latest
    echo.
    pause
    exit /b 1
)

:arrancar
echo.
echo ====================================================
echo   VERIFICANDO BINARIO DE ELECTRON
echo ====================================================
echo.

REM electron.exe debe existir en node_modules\electron\dist\
REM Si no existe, la descarga del binario fallo (paso separado al npm install)
if not exist "node_modules\electron\dist\electron.exe" (
    echo [!] El binario de Electron no esta descargado.
    echo     Descargando ahora...
    echo.
    node node_modules\electron\install.js
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [ERROR] No se pudo descargar el binario de Electron.
        echo         Posibles causas:
        echo           - Sin conexion a internet
        echo           - Proxy corporativo bloqueando la descarga
        echo         Solucion manual:
        echo           npm install electron --save-dev --force
        echo.
        pause
        exit /b 1
    )
    echo [OK] Binario descargado correctamente.
    echo.
)

echo [OK] Electron encontrado en: node_modules\electron\dist\electron.exe
echo.

echo ====================================================
echo   ARRANCAR ELECTRON
echo ====================================================
echo.
echo IMPORTANTE:
echo   - Esta ventana debe permanecer ABIERTA mientras usas la app
echo   - Para arrancar el daemon Python, abre OTRA terminal y ejecuta:
echo       python riatla_daemon.py
echo.
set /p RESPUESTA="Iniciar la app ahora? (S/N): "
if /i "%RESPUESTA%"=="S" goto :iniciar
if /i "%RESPUESTA%"=="si" goto :iniciar
echo.
echo Para arrancar manualmente despues, ejecuta en esta carpeta:
echo   npm start
echo.
pause
exit /b 0

:iniciar
echo.
echo [*] Arrancando Electron...
echo.

REM Ejecutar electron directamente en lugar de npm start para ver errores
node_modules\electron\dist\electron.exe .
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% NEQ 0 (
    echo [ERROR] Electron cerro con codigo de error: %EXITCODE%
    echo         Abre DevTools con F12 o revisa electron-log.txt para mas detalles.
) else (
    echo [*] Electron cerrado correctamente.
)
pause
