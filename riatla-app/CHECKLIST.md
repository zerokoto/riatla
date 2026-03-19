📋 CHECKLIST DE INSTALACIÓN Y VERIFICACIÓN
════════════════════════════════════════════════════════════════════════════

ANTES DE EMPEZAR
════════════════════════════════════════════════════════════════════════════

[ ] Node.js 14+ instalado
    Verifica: node --version (debe ser v14 o superior)

[ ] npm instalado
    Verifica: npm --version

[ ] riatla_daemon.py está listo (en directorio padre)

[ ] Modelo riatla.vrm está en: riatla-app/models/riatla.vrm
    Verifica: dir riatla-app\models\


INSTALACIÓN
════════════════════════════════════════════════════════════════════════════

[ ] Entrar en carpeta riatla-app
    cd riatla-app

[ ] Ejecutar quickstart.bat (Windows) o quickstart.sh (Linux/macOS)
    OR: npm install

[ ] Esperar a que descargue node_modules (~2 minutos)
    Verifica: dir node_modules\ debe tener electron, three, @pixiv

[ ] Verificar que no hay errores en npm install
    Si hay errores, ejecutar: npm install --legacy-peer-deps


ANTES DE EJECUTAR LA APP
════════════════════════════════════════════════════════════════════════════

[ ] Iniciar riatla_daemon.py en otra terminal:
    cd ..
    python riatla_daemon.py

[ ] Verificar que el daemon está escuchando en puerto 8765:
    Windows: netstat -ano | findstr 8765
    Linux: netstat -tlnp | grep 8765
    Debe mostrar "LISTENING"

[ ] Si no hay puerto 8765, modificar en electron.py:
    const WEBSOCKET_URL = 'ws://localhost:8765'
    (cambiar si el daemon usa otro puerto)


EJECUCIÓN
════════════════════════════════════════════════════════════════════════════

[ ] Ejecutar la app:
    npm start

[ ] Esperar a que se abra la ventana (5-10 segundos)
    (La primera vez es más lenta)

[ ] Ver panel de debug en esquina superior izquierda:
    ✓ "Inicializando Riatla..."
    ✓ "Cargando VRM..."
    ✓ "✓ Modelo VRM cargado"
    ✓ "✓ WebSocket conectado"

[ ] Ver indicador en esquina inferior derecha:
    ✓ Verde con "WebSocket: Conectado"


VERIFICACIÓN DE FUNCIONALIDAD
════════════════════════════════════════════════════════════════════════════

[ ] Avatar aparece en pantalla
    (debe verse el modelo VRM con fondo degradado)

[ ] Panel de debug funciona
    (aparecen logs en tiempo real)

[ ] Enviar comando de prueba desde otra terminal:
    Windows PowerShell:
    $ws = New-WebSocketClientConnection -Uri 'ws://localhost:8765'
    $ws.SendAsync('{"accion":"emocion_happy"}')
    
    O usar: python (script de prueba abajo)

[ ] Avatar cambia de expresión al recibir comando
    (debe sonreír si envías "emocion_happy")

[ ] Indicador WebSocket muestra "Conectado" (verde)


SCRIPT DE PRUEBA EN PYTHON
════════════════════════════════════════════════════════════════════════════

Crear archivo: test_riatla.py

```python
import websocket
import json
import time

def test_emocion(emocion):
    try:
        ws = websocket.create_connection('ws://localhost:8765')
        comando = {"accion": f"emocion_{emocion}"}
        ws.send(json.dumps(comando))
        ws.close()
        print(f"✓ Comando enviado: {emocion}")
    except Exception as e:
        print(f"✗ Error: {e}")

# Pruebas
print("Enviando comandos de prueba...")
test_emocion("happy")
time.sleep(2)
test_emocion("sad")
time.sleep(2)
test_emocion("surprised")
time.sleep(2)
test_emocion("reset")
print("✓ Test completado")
```

Ejecutar:
  pip install websocket-client
  python test_riatla.py


INTEGRACIÓN CON DAEMON
════════════════════════════════════════════════════════════════════════════

[ ] Modificar riatla_daemon.py para enviar a riatla-app
    (Ver INTEGRATION.md para detalles)

[ ] Función enviar_a_app() agregada a daemon

[ ] Modificar set_emocion() para llamar a enviar_a_app()

[ ] Configurar Home Assistant para publicar a riatla/emocion

[ ] Enviar evento MQTT y verificar que avatar reacciona


DESARROLLO
════════════════════════════════════════════════════════════════════════════

[ ] npm run dev
    (abre DevTools automáticamente)

[ ] Modificar renderer.js y presionar Ctrl+R para recargar

[ ] Usar F12 para inspeccionar canvas y ver errores

[ ] Ver console.log() en DevTools


FULLSCREEN (OPCIONAL)
════════════════════════════════════════════════════════════════════════════

[ ] Abrir electron-main.js

[ ] Descommentar líneas 54-55:
    // mainWindow.setFullScreen(true);
    // mainWindow.setKiosk(true);

[ ] Guardar y reiniciar app con npm start

[ ] Presionar ESC para salir del fullscreen


PROBLEMAS COMUNES
════════════════════════════════════════════════════════════════════════════

❌ "Cannot find module 'electron'"
[ ] npm install
[ ] npm install --legacy-peer-deps
[ ] Eliminar node_modules y reinstalar

❌ "EACCES: permission denied"
[ ] sudo npm install (Linux)
[ ] Ejecutar terminal como admin (Windows)

❌ WebSocket no conecta
[ ] Verificar daemon.py ejecutándose: python riatla_daemon.py
[ ] Verificar puerto: netstat -ano | findstr 8765
[ ] Ver logs en panel debug de riatla-app (DevTools)

❌ VRM no aparece
[ ] Verificar ruta: models/riatla.vrm existe
[ ] Ver error en DevTools (F12)
[ ] Verificar formato VRM es válido

❌ Expresiones no funcionan
[ ] Verificar que VRM tiene BlendShapes
[ ] Ver nombres de expresiones en DevTools console
[ ] Ajustar nombres en renderer.js si es necesario

❌ App se cierra al iniciar
[ ] Ejecutar npm start desde terminal para ver error
[ ] Verificar node_modules completo: ls node_modules/electron
[ ] Reinstalar: rm -rf node_modules && npm install


PRODUCCIÓN (OPTIONAL)
════════════════════════════════════════════════════════════════════════════

[ ] npm run build:win
    (genera ejecutable para Windows)

[ ] Instalador está en: dist/Riatla Avatar Setup 1.0.0.exe

[ ] Distribuir executable


VERIFICACIÓN FINAL
════════════════════════════════════════════════════════════════════════════

✓ npm start funciona sin errores
✓ Avatar aparece en pantalla
✓ WebSocket conecta automáticamente (verde)
✓ VRM carga correctamente
✓ Expresiones responden a comandos JSON
✓ Panel debug muestra logs
✓ App puede reiniciarse sin problemas

¡Si todo está ✓, la instalación está completa!


NEXT STEPS
════════════════════════════════════════════════════════════════════════════

1. Integrar con riatla_daemon.py (ver INTEGRATION.md)
2. Conectar Home Assistant MQTT 
3. Configurar expresiones según tu VRM
4. Personalizar controles
5. Compilar para producción si es necesario
