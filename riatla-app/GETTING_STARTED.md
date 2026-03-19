🚀 PRIMEROS PASOS CON RIATLA-APP
════════════════════════════════════════════════════════════════════════════

IMPORTANTE: quickstart.bat SOLO instala dependencias, no arranca Electron.
Debes ejecutar "npm start" manualmente después. Sigue esta guía paso a paso.

════════════════════════════════════════════════════════════════════════════
PASO 1: REQUISITOS PREVIOS
════════════════════════════════════════════════════════════════════════════

Node.js v18 o superior (recomendado v20 LTS):
  Descarga desde: https://nodejs.org  →  sección "LTS"

Verificar que está instalado correctamente:
  Abre PowerShell y ejecuta:
    node --version    → debe mostrar v18.x.x o superior
    npm --version     → debe mostrar 9.x.x o superior

  Si alguno de los dos falla → reinstalar Node.js y reiniciar PowerShell.


════════════════════════════════════════════════════════════════════════════
PASO 2: ABRIR POWERSHELL EN LA CARPETA CORRECTA
════════════════════════════════════════════════════════════════════════════

Todos los comandos deben ejecutarse DESDE la carpeta riatla-app.

Opción A (más fácil):
  1. Abre el Explorador de archivos
  2. Navega hasta la carpeta riatla-app/
  3. Escribe "powershell" en la barra de dirección y pulsa Enter
  → Se abre PowerShell ya posicionado en riatla-app/

Opción B (manual):
  1. Abre PowerShell
  2. Navega a la carpeta:
       cd "C:\ruta\hasta\riatla-app"
  3. Verifica que estás en el lugar correcto:
       Get-ChildItem
       → Debes ver: package.json, main-log.js, index.html, renderer.js, models/


════════════════════════════════════════════════════════════════════════════
PASO 3: INSTALAR DEPENDENCIAS (solo la primera vez)
════════════════════════════════════════════════════════════════════════════

NOTA: quickstart.bat realiza este paso automáticamente, pero NO arranca la app.

Desde PowerShell dentro de riatla-app/, ejecuta:

  npm install

Esto descarga ~300 MB en node_modules/ (tarda 1-3 minutos).

Salida esperada al terminar:
  added XXX packages ...
  (sin líneas que digan "npm ERR!")

Si aparece error de permisos o peer deps, usa:
  npm install --legacy-peer-deps

Verifica que la instalación fue correcta:
  Test-Path .\node_modules\electron
  → Debe devolver: True

  Test-Path .\node_modules\three
  → Debe devolver: True

  Test-Path ".\node_modules\@pixiv\three-vrm"
  → Debe devolver: True

  Si alguno devuelve False → vuelve a ejecutar npm install


════════════════════════════════════════════════════════════════════════════
PASO 4: ARRANCAR ELECTRON (la app)
════════════════════════════════════════════════════════════════════════════

IMPORTANTE: Este paso es separado de quickstart.bat.
Desde la misma PowerShell (en riatla-app/), ejecuta:

  npm start

¿Qué ocurre al ejecutarlo?
  1. PowerShell muestra:  "=== ELECTRON INICIANDO ==="
  2. Aparece una ventana oscura de Electron
  3. Se abre automáticamente el panel DevTools (consola)
  4. En el fondo de la ventana verás: degradado morado/gris
  5. Esquina inferior derecha: "WebSocket: Desconectado" (en rojo) ← NORMAL
  6. Esquina superior izquierda: panel de debug

Si la ventana se abre pero queda en negro unos segundos → es normal mientras
carga el modelo VRM.

Si ves en la consola DevTools:
  "Failed to resolve module specifier"
  → Significa que node_modules no se instaló bien. Sigue el paso 3B abajo.


════════════════════════════════════════════════════════════════════════════
PASO 5: VERIFICAR QUE EL MODELO VRM CARGA
════════════════════════════════════════════════════════════════════════════

En el panel de debug (esquina superior izquierda de la app) debes ver:
  "Cargando VRM... 25%"
  "Cargando VRM... 50%"
  "Cargando VRM... 100%"
  "✓ Modelo VRM cargado correctamente"

Y el avatar 3D aparecerá en pantalla.

Si NO aparece el avatar:
  1. Pulsa F12 para abrir DevTools (si no está ya abierto)
  2. Ve a la pestaña "Console"
  3. Busca errores en rojo
  4. Verifica que el archivo existe:
       Test-Path .\models\riatla.vrm
       → Debe devolver: True


════════════════════════════════════════════════════════════════════════════
PASO 6: CONECTAR EL DAEMON PYTHON (en otra terminal)
════════════════════════════════════════════════════════════════════════════

Abre UNA NUEVA PowerShell (no cierres la anterior con Electron).

En la nueva terminal, navega a la carpeta PADRE (riatla/):
  cd "..\riatla"         (si ya estabas en riatla-app/)
  O navega directamente a donde está riatla_daemon.py

Ejecuta el daemon:
  python riatla_daemon.py

Salida esperada en el daemon:
  "Starting MQTT..."
  "WebSocket server listening on port 8765"

En la ventana de Electron:
  ✓ El indicador cambia a VERDE: "WebSocket: Conectado"
  ✓ Panel de debug: "✓ WebSocket conectado"


¡LISTO! El sistema está completamente operativo.
════════════════════════════════════════════════════════════════════════════


📝 PRUEBA RÁPIDA (verificar que todo funciona)
════════════════════════════════════════════════════════════════════════════

Abre UNA TERCERA PowerShell y ejecuta este script Python:

  Crea un archivo test.py con este contenido:

    import websocket, json
    ws = websocket.create_connection('ws://localhost:8765')
    ws.send(json.dumps({"accion": "emocion_happy"}))
    ws.close()
    print("Comando enviado OK")

  Ejecuta:
    python test.py

RESULTADO ESPERADO:
  ✓ Avatar sonríe
  ✓ Panel de debug muestra: "Expresión: happy"


🎮 COMANDOS DISPONIBLES
════════════════════════════════════════════════════════════════════════════

  {"accion":"emocion_happy"}       → Feliz
  {"accion":"emocion_sad"}         → Triste
  {"accion":"emocion_surprised"}   → Sorprendido
  {"accion":"emocion_angry"}       → Enojado
  {"accion":"emocion_neutral"}     → Neutral
  {"accion":"reset"}               → Reset total

  {"accion":"mirar","parametros":{"x":-0.3,"y":0,"z":0}}   → Mirar arriba
  {"accion":"mirar","parametros":{"x":0,"y":-0.3,"z":0}}   → Mirar izquierda


🔧 PROBLEMAS COMUNES Y SOLUCIONES
════════════════════════════════════════════════════════════════════════════

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: "Failed to resolve module specifier '@pixiv/three-vrm'"
   (aparece en DevTools Console al arrancar)
─────────────────────────────────────────────────────────────────────────
CAUSA: Las dependencias no se instalaron correctamente.
✅ SOLUCIÓN:
   1. Cierra la app (Ctrl+C en la terminal de npm start)
   2. Ejecuta en orden:
        Remove-Item -Recurse -Force .\node_modules
        Remove-Item -Force .\package-lock.json
        npm install
   3. Vuelve a ejecutar: npm start

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: "Cannot find module 'electron'" o la ventana no se abre
─────────────────────────────────────────────────────────────────────────
CAUSA: electron no se descargó en node_modules.
✅ SOLUCIÓN:
   npm install --save-dev electron@latest --legacy-peer-deps
   npm start

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: La terminal se cierra sola al hacer doble-click en quickstart.bat
─────────────────────────────────────────────────────────────────────────
CAUSA: quickstart.bat abre y cierra en su propia ventana. Eso es normal.
✅ SOLUCIÓN:
   No uses doble-click. Abre PowerShell manualmente y ejecuta:
     cd riatla-app
     npm install
     npm start

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: "WebSocket: Desconectado" sigue en rojo después de npm start
─────────────────────────────────────────────────────────────────────────
CAUSA: riatla_daemon.py no está corriendo.
✅ SOLUCIÓN:
   En otra terminal (carpeta padre):
     python riatla_daemon.py

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: Avatar no aparece (solo fondo morado vacío)
─────────────────────────────────────────────────────────────────────────
✅ SOLUCIÓN:
   1. Pulsa F12 → pestaña Console → busca errores en rojo
   2. Verifica que el archivo VRM existe:
        Test-Path .\models\riatla.vrm
   3. Si no existe, copia riatla.vrm a la carpeta models/

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: npm install tarda mucho o se queda colgado
─────────────────────────────────────────────────────────────────────────
✅ SOLUCIÓN:
   Ctrl+C para cancelar, luego:
     npm install --legacy-peer-deps --no-audit --no-fund

─────────────────────────────────────────────────────────────────────────
❌ PROBLEMA: Error de permisos en PowerShell ("execution policy")
─────────────────────────────────────────────────────────────────────────
✅ SOLUCIÓN:
   Abrir PowerShell como Administrador y ejecutar:
     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   Luego vuelve a abrir PowerShell normal y ejecuta npm install / npm start.


💻 MODO DESARROLLO (DevTools desde el inicio)
════════════════════════════════════════════════════════════════════════════

Para arrancar con DevTools abierto desde el principio:
  npm run dev

Para recargar la app sin cerrarla (tras editar renderer.js):
  Pulsa Ctrl+R dentro de la ventana de Electron


📚 RESUMEN DE COMANDOS (referencia rápida)
════════════════════════════════════════════════════════════════════════════

  # Instalar dependencias (solo primera vez):
  cd riatla-app
  npm install

  # Arrancar la app:
  npm start

  # Arrancar con DevTools:
  npm run dev

  # Si hay errores de módulos, reinstalar limpio:
  Remove-Item -Recurse -Force .\node_modules
  npm install

  # En otra terminal - arrancar daemon:
  cd ..\riatla
  python riatla_daemon.py


📚 DOCUMENTACIÓN COMPLETA
════════════════════════════════════════════════════════════════════════════

  • README.md        → Visión general y características
  • INTEGRATION.md   → Cómo conectar con riatla_daemon.py y Home Assistant
  • CHECKLIST.md     → Verificación detallada de todos los pasos
  • ESTRUCTURA.md    → Arquitectura técnica profunda


╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   SECUENCIA CORRECTA DE ARRANQUE (resumen):                               ║
║                                                                            ║
║   Terminal 1 (riatla-app/):   npm install   →   npm start                 ║
║   Terminal 2 (riatla/):       python riatla_daemon.py                     ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
