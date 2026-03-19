🎭 RIATLA-APP - ESTRUCTURA COMPLETA
════════════════════════════════════════════════════════════════════════════

riatla-app/
│
├── 📋 CONFIGURACIÓN
│   ├── package.json           ← Dependencias npm (Electron, Three.js, VRM)
│   ├── .gitignore             ← Archivos a ignorar en git
│   ├── .env.example           ← Variables de entorno (ejemplo)
│   └── electron-main.js       ← Proceso principal de Electron
│
├── 🌐 INTERFAZ WEB
│   ├── index.html             ← HTML principal (canvas para Three.js)
│   ├── preload.js             ← Script de preload (seguridad)
│   └── renderer.js            ← LÓGICA PRINCIPAL ★
│                                 - Three.js setup
│                                 - VRM loading
│                                 - WebSocket client
│                                 - Expresiones y movimientos
│
├── 🎨 ASSETS
│   └── models/
│       └── riatla.vrm         ← Modelo avatar VRM
│
├── 📚 DOCUMENTACIÓN
│   ├── README.md              ← Guía principal
│   ├── INTEGRATION.md         ← Cómo integrar con daemon
│   ├── electron.py            ← Notas y comandos (Python)
│   └── ESTRUCTURA.md           ← Este archivo
│
└── 🚀 STARTUP
    ├── quickstart.bat         ← Iniciador rápido (Windows)
    └── quickstart.sh          ← Iniciador rápido (Linux/macOS)

FLUJO DE EJECUCIÓN
════════════════════════════════════════════════════════════════════════════

1. npm start
   ↓
2. electron-main.js
   ├─ Crea ventana principal
   ├─ Carga index.html
   └─ Carga renderer.js
   ↓
3. renderer.js
   ├─ setupScene()          → Three.js, cámara, luces
   ├─ loadVRM()             → Carga riatla.vrm
   ├─ connectWebSocket()    → Se conecta a ws://localhost:8765
   └─ animate()             → Loop de renderización
   ↓
4. WebSocket client escucha comandos JSON
   └─ ejecutarComando(comando)
      ├─ expresiones (happy, sad, angry, etc)
      ├─ movimientos (mirar, girar cabeza, etc)
      └─ control (reset)

ARQUITECTURA SISTEMA COMPLETO
════════════════════════════════════════════════════════════════════════════

┌─────────────────────┐
│   Home Assistant    │
│   (MQTT Events)     │
└──────────┬──────────┘
           │ mqtt.publish("riatla/emocion", {...})
           ↓
┌──────────────────────────────────────┐
│   riatla_daemon.py                   │
│   ┌────────────────────────────────┐ │
│   │ MQTT Subscriber                │ │
│   │ on_message() →                 │ │
│   │   set_emocion() →              │ │
│   │   enviar_a_app(comando)        │ │
│   └────────────────┬───────────────┘ │
│                    │ ws.send(JSON)   │
└────────┬───────────┴────────────────┘
         │
         ↓ WebSocket JSON
         │ {"accion": "emocion_happy", ...}
         │
┌────────┴────────────────────────────────────┐
│   riatla-app (Electron + WebGL)              │
│   ┌──────────────────────────────────────┐  │
│   │ rendez.js                            │  │
│   │ WebSocket Server                     │  │
│   │   onmessage() →                      │  │
│   │   ejecutarComando(comando) →         │  │
│   │   activarExpresion() / mirarHacia()  │  │
│   └──────────────┬───────────────────────┘  │
│                  │                          │
│   ┌──────────────▼───────────────────────┐  │
│   │ Three.js Rendering                   │  │
│   │                                       │  │
│   │  scene + camera + renderer            │  │
│   │       ↓                               │  │
│   │  currentVRM (BlendShapes + Bones)     │  │
│   │       ↓                               │  │
│   │  Canvas → DisplayPort                 │  │
│   └───────────────────────────────────────┘  │
└────────────────────────────────────────────┘

EXPRESIONES DISPONIBLES
════════════════════════════════════════════════════════════════════════════

- emocion_happy      (sonrisa)
- emocion_sad        (tristeza)
- emocion_angry      (enojo)
- emocion_surprised  (sorpresa)
- emocion_relaxed    (relajado)
- emocion_neutral    (default)

MOVIMIENTOS DISPONIBLES
════════════════════════════════════════════════════════════════════════════

mirar(x, y, z) → Rotación de cabeza
  x: -1 (abajo) a 1 (arriba)
  y: -1 (izquierda) a 1 (derecha)
  z: -1 a 1 (rotación)

REQUISITOS
════════════════════════════════════════════════════════════════════════════

✓ Node.js 14+ (con npm)
✓ Electron (instalado automático via npm)
✓ Three.js (instalado automático via npm)
✓ @pixiv/three-vrm (instalado automático via npm)
✓ Modelo VRM (riatla.vrm en models/)

INSTALACIÓN RÁPIDA
════════════════════════════════════════════════════════════════════════════

Windows:
  1. Doble click en: quickstart.bat
  2. Esperar descarga de node_modules...
  3. npm start

Linux/macOS:
  1. chmod +x quickstart.sh
  2. ./quickstart.sh
  3. npm start

Manual:
  npm install
  npm start

ARCHIVOS CLAVE
════════════════════════════════════════════════════════════════════════════

★ renderer.js
  - Contiene TODA la lógica principal
  - 300+ líneas bien documentadas
  - Fácil de modificar y extender

★ electron-main.js
  - Proceso principal de Electron
  - Manejo de ventana
  - Control de ciclo de vida de la app

★ index.html
  - HTML mínimo
  - Solo canvas y elementos de UI
  - Estilos CSS básicos

PERSONALIZACIÓN
════════════════════════════════════════════════════════════════════════════

Puerto WebSocket
  Archivo: renderer.js (línea 15)
  Cambiar: const WEBSOCKET_URL = 'ws://localhost:8765'

Resolución ventana
  Archivo: electron-main.js (línea 17-18)
  Cambiar: width: 1920, height: 1080

Fullscreen
  Archivo: electron-main.js (linea 54-55)
  Descomentar: mainWindow.setFullScreen(true)

Expresiones disponibles
  Archivo: renderer.js (función ejecutarComando, línea ~200)
  Depende del modelo VRM (verificar BlendShapes en Blender/Unity)

DEBUG Y DESARROLLO
════════════════════════════════════════════════════════════════════════════

npm run dev
  → Abre DevTools (F12)
  → Ve logs y errores en consola
  → Hot reload no automático (reinicia app para cambios)

Chrome DevTools integrado
  F12 o Ctrl+Shift+I → Abre inspector
  Console → Ve console.log(), errores
  Performance → Perfil de GPU

TROUBLESHOOTING
════════════════════════════════════════════════════════════════════════════

❌ "Cannot find module 'three'"
   → npm install
   → Eliminar node_modules y reinstalar

❌ "WebSocket conecta pero no responde"
   → Verificar que daemon está ejecutándose
   → Verificar puerto 8765 está abierto
   → Ver logs en app (panel debug inferior-izquierda)

❌ "VRM no aparece"
   → Verificar ruta: models/riatla.vrm
   → Abrir DevTools y ver error en console

❌ "App se cierra al iniciar"
   → Ver logs en terminal
   → Verificar que node_modules está completo

CONTACTO Y SOPORTE
════════════════════════════════════════════════════════════════════════════

Docs:
  - README.md → Guía general
  - INTEGRATION.md → Integración con daemon
  - electron.py → Notas del proyecto
  - Este archivo → Estructura completa
