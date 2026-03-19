@echo off
REM Quick Start para Riatla App en Windows

cls
echo.
echo ====================================================
echo   RIATLA APP - INICIADOR RAPIDO
echo ====================================================
echo.

REM Verificar si Node.js está instalado
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Node.js no esta instalado.
    echo Descargalo desde: https://nodejs.org
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js detectado
echo.
echo [*] Instalando dependencias npm...
echo.

REM Configurar PATH para Node.js
set PATH=C:\Program Files\nodejs;%PATH%

REM Instalar dependencias
call npm install

echo.
echo ====================================================
echo   [OK] Instalacion completada
echo ====================================================
echo.
echo Para iniciar la app:
echo   npm start
echo.
echo Para desarrollo (con DevTools):
echo   npm run dev
echo.
echo Documentacion en: README.md e INTEGRATION.md
echo.
pause
