🚀 PRIMEROS PASOS CON RIATLA-APP
════════════════════════════════════════════════════════════════════════════


⏱️  5 MINUTOS DE CONFIGURACIÓN
════════════════════════════════════════════════════════════════════════════

PASO 1: Instalar Node.js (si no lo tienes)
─────────────────────────────────────────────────────────────────────────

Descargar e instalar desde: https://nodejs.org
(Seleccionar versión LTS - Long Term Support)

Verificar instalación:
  Windows: Abrir PowerShell
  Escribir: node --version
  Debe salir: v16.x.x (o superior)


PASO 2: Descargar dependencias (2 minutos)
─────────────────────────────────────────────────────────────────────────

Opción A - RÁPIDO (Windows):
  1. Ir a: riatla-app/
  2. Doble-click en: quickstart.bat
  3. Esperar a que termine

Opción B - MANUAL:
  1. Abrir PowerShell/Terminal
  2. Navegar a: cd riatla-app
  3. Escribir: npm install
  4. Esperar a que descargue node_modules/


PASO 3: Ejecutar la aplicación
─────────────────────────────────────────────────────────────────────────

En la misma terminal (riatla-app/):
  npm start

Esperado:
  ✓ Se abre ventana de Electron
  ✓ Ve fondo degradado morado/gris
  ✓ Panel de debug en esquina superior izquierda
  ✓ Indicador "WebSocket: Desconectado" (rojo) en esquina inferior derecha


PASO 4: Cargar el avatar (automático)
─────────────────────────────────────────────────────────────────────────

La app cargará automáticamente:
  ✓ Ve logs: "Cargando VRM... 25%, 50%, 100%"
  ✓ Cuando cargue: "✓ Modelo VRM cargado correctamente"
  ✓ Avatar aparece en pantalla


PASO 5: Conectar riatla_daemon.py (en otra terminal)
─────────────────────────────────────────────────────────────────────────

En otra PowerShell/Terminal:
  1. Navegar a: cd ..
  2. Escribir: python riatla_daemon.py
  3. Verás logs Starting MQTT/WebSocket

En riatla-app:
  ✓ Indicador cambia a verde: "WebSocket: Conectado"
  ✓ Panel de debug muestra: "✓ WebSocket conectado"


¡LISTO! El sistema está funcionando
════════════════════════════════════════════════════════════════════════════


📝 PRUEBA DE FUNCIONALIDAD (10 segundos)
════════════════════════════════════════════════════════════════════════════

Abrir una TERCERA terminal y ejecutar:

Windows PowerShell:
  Enter-PSSession localhost  # (puede no ser necesario)
  $ws = New-WebSocket -Uri 'ws://localhost:8765'
  $ws.send('{"accion":"emocion_happy"}')

O simplemente usar Python (más fácil):

Crear archivo: test.py en riatla-app/

  import websocket
  import json
  
  ws = websocket.create_connection('ws://localhost:8765')
  ws.send(json.dumps({"accion":"emocion_happy"}))
  ws.close()

Ejecutar:
  python test.py

RESULTADO:
  ✓ Avatar sonríe
  ✓ Panel de debug muestra: "Expresión: happy"


🎮 COMANDOS BÁSICOS PARA PROBAR
════════════════════════════════════════════════════════════════════════════

Happyness (Feliz):
  {"accion":"emocion_happy"}

Sadness (Triste):
  {"accion":"emocion_sad"}

Surprise (Sorprendido):
  {"accion":"emocion_surprised"}

Angry (Enojado):
  {"accion":"emocion_angry"}

Neutral (Normal):
  {"accion":"emocion_neutral"}

Reset (Todo a default):
  {"accion":"reset"}

Look Up (Mirar arriba):
  {"accion":"mirar","parametros":{"x":-0.3,"y":0,"z":0}}

Look Left (Mirar izquierda):
  {"accion":"mirar","parametros":{"x":0,"y":-0.3,"z":0}}


🔧 PROBLEMAS COMUNES Y SOLUCIONES
════════════════════════════════════════════════════════════════════════════

❌ "Cannot find module 'electron'"
✅ SOLUCIÓN:
   cd riatla-app
   npm install
   npm install --legacy-peer-deps

❌ "WebSocket sigue en rojo (desconectado)"
✅ SOLUCIÓN:
   1. Verifica que riatla_daemon.py está ejecutándose
   2. En terminal daemon, debe haber mensajes por segundo
   3. Si no, ejecuta: python riatla_daemon.py

❌ "Avatar no aparece, solo fondo"
✅ SOLUCIÓN:
   1. Ver panel de debug para errores
   2. Abrir DevTools: F12
   3. Ver pestaña Console para error específico
   4. Verificar que riatla.vrm existe en models/

❌ "npm install se queda pegado"
✅ SOLUCIÓN:
   Presionar Ctrl+C
   npm install --legacy-peer-deps --no-audit

❌ "Expresión no cambia"
✅ SOLUCIÓN:
   1. Verificar que WebSocket muestra VERDE conectado
   2. Verificar que VRM tiene los BlendShapes
   3. Ver logs en DevTools (F12)


💻 MODO DESARROLLO (Con editor abierto)
════════════════════════════════════════════════════════════════════════════

Ejecutar con DevTools:
  npm run dev

Te abre:
  ✓ La app de Electron
  ✓ DevTools (F12) con Console lista

Modificar renderer.js:
  Presiona Ctrl+R en riatla-app para recargar
  (los cambios se reflejan al instante)


📚 DOCUMENTACIÓN COMPLETA
════════════════════════════════════════════════════════════════════════════

Una vez todo funciona, lee estos archivos en orden:

1. README.md 
   → Visión general y características

2. INTEGRATION.md
   → Cómo conectar con riatla_daemon.py y Home Assistant

3. CHECKLIST.md
   → Verificación detallada de todos los pasos

4. ESTRUCTURA.md
   → Arquitectura técnica profunda


🎯 PRÓXIMO PASO: INTEGRACIÓN CON DAEMON
════════════════════════════════════════════════════════════════════════════

Una vez que todo funciona:

1. Abrir archivo: riatla_daemon.py (en carpeta padre)

2. Modificar función set_emocion() para enviar a riatla-app

3. Ejemplo de código:

   def enviar_a_riatla_app(comando):
       try:
           ws = websocket.create_connection('ws://localhost:8765')
           ws.send(json.dumps(comando))
           ws.close()
       except:
           pass

   # En set_emocion(), al final:
   enviar_a_riatla_app({
       "accion": f"emocion_{emocion}",
       "parametros": {}
   })

4. Ver INTEGRATION.md para ejemplo completo


🏆 META: CONECTAR HOME ASSISTANT
════════════════════════════════════════════════════════════════════════════

Una vez integrado con el daemon:

1. Configurar Home Assistant MQTT
2. Publicar a topic: riatla/emocion
3. El daemon recibe y envía a riatla-app
4. Avatar reacciona automáticamente


╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║              ¿PREGUNTAS? VER ARCHIVOS .md EN LA CARPETA                   ║
║                                                                            ║
║  • README.md           → Guía general                                      ║
║  • CHECKLIST.md        → Verificación paso a paso                         ║
║  • INTEGRATION.md      → Conectar con daemon                              ║
║  • ESTRUCTURA.md       → Detalles técnicos                                ║
║  • electron.py         → Notas del proyecto                               ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
