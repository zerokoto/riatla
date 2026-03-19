# 🎭 Riatla App — Avatar Client

Cliente **Electron** + **Three.js** + **VRM** que renderiza el avatar Riatla y recibe comandos de animación desde el daemon Python vía WebSocket.

---

## 🗺️ Flujo completo del sistema

### Visión general

```
Home Assistant  ──MQTT──►  riatla_daemon.py  ──WebSocket──►  Riatla App (Electron)
```

### Flujo detallado

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HOME ASSISTANT                                                          │
│  Publica en topic MQTT: riatla/emocion                                  │
│  Payload: "happy" | "sad" | "neutral" | ...                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ MQTT (broker mosquitto / HA interno)
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  riatla_daemon.py   (proceso Python, carpeta padre)                     │
│  ① Suscrito al topic MQTT                                               │
│  ② Recibe el mensaje y construye comando JSON:                          │
│       {"accion": "emocion_happy", "parametros": {}}                     │
│  ③ Abre conexión WebSocket a ws://localhost:8765                        │
│  ④ Envía el comando JSON                                                │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ WebSocket (puerto 8765, JSON)
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ELECTRON — proceso principal   (main-log.js)                           │
│  • Lanza BrowserWindow con index.html                                   │
│  • Gestiona ciclo de vida de la app (ready / window-all-closed / quit)  │
│  • Carga preload.js para aislar el renderer del proceso Node            │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ carga
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  RENDERER PROCESS   (index.html → renderer.js)                          │
│                                                                          │
│  ┌─── WebSocket client ──────────────────────────────────────────────┐  │
│  │  connectWebSocket()                                                │  │
│  │  ws.onmessage → JSON.parse → ejecutarComando(comando)             │  │
│  └───────────────────────────────┬────────────────────────────────── ┘  │
│                                  │                                       │
│             ┌────────────────────┴──────────────────┐                   │
│             ▼                                        ▼                   │
│  ┌── Expresiones ──────────┐          ┌── Movimiento ──────────────┐    │
│  │  activarExpresion(name) │          │  mirarHacia(x, y, z)       │    │
│  │  VRM expressionManager  │          │  humanoid.getBoneNode(head) │    │
│  │  BlendShapes del .vrm   │          │  bone.rotation.x/y/z       │    │
│  └────────────┬────────────┘          └──────────────┬─────────────┘    │
│               │                                      │                   │
│               └──────────────┬───────────────────────┘                  │
│                              ▼                                           │
│  ┌── Three.js render loop ───────────────────────────────────────────┐  │
│  │  animate() — requestAnimationFrame (60 FPS)                       │  │
│  │  currentVRM.update(1/60)   ← actualiza física VRM (springs)       │  │
│  │  renderer.render(scene, camera)  ← dibuja el frame                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌── VRM Model ──────────────────────────────────────────────────────┐  │
│  │  models/riatla.vrm  (cargado con GLTFLoader + VRMLoaderPlugin)    │  │
│  │  • BlendShapes → expresiones faciales                             │  │
│  │  • Humanoid bones → movimiento de cabeza / cuerpo                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Comandos JSON que viajan por WebSocket

| Campo `accion`       | Efecto en el avatar                     |
|----------------------|-----------------------------------------|
| `emocion_happy`      | BlendShape "happy" → 1.0                |
| `emocion_sad`        | BlendShape "sad" → 1.0                  |
| `emocion_angry`      | BlendShape "angry" → 1.0                |
| `emocion_surprised`  | BlendShape "surprised" → 1.0            |
| `emocion_neutral`    | Todas las expresiones → 0               |
| `hablar`             | Alias de `emocion_happy`                |
| `mirar`              | `parametros: {x, y, z}` → rotación bone head |
| `reset`              | Expresión neutral + cabeza centrada     |

---

## 📋 Estructura del proyecto

```
riatla-app/
├── package.json          ← Dependencias npm (main: main-log.js)
├── main-log.js           ← Proceso principal Electron (crea BrowserWindow, logs)
├── electron-main.js      ← Versión alternativa del main (sin logs a fichero)
├── preload.js            ← Script de preload (aislamiento de contexto)
├── index.html            ← HTML principal (importmap para three/@pixiv)
├── renderer.js           ← Toda la lógica: Three.js + VRM + WebSocket + animaciones
├── animations.js         ← Referencia/snippets de animaciones (no se carga en producción)
├── websocket.js          ← Referencia/snippets de WebSocket (no se carga en producción)
├── models/
│   └── riatla.vrm        ← Modelo VRM del avatar (requerido)
└── electron-log.txt      ← Log generado automáticamente por main-log.js
```

> **Nota:** `renderer.js` concentra toda la lógica real (WebSocket, Three.js, VRM, animaciones).
> `animations.js` y `websocket.js` son ficheros de referencia/documentación de código.

---

## 🚀 Instalación y arranque

**Requisitos:**
- Node.js 18 o superior (verificar: `node --version`)
- El daemon Python ejecutándose en paralelo (`python riatla_daemon.py`)

```bash
# 1. Instalar dependencias (solo la primera vez)
cd riatla-app
npm install

# 2. Arrancar la app
npm start

# Alternativa con DevTools abierto desde el inicio
npm run dev
```

En Windows también puedes usar `quickstart.bat` que instala dependencias y arranca Electron.

---

## ⚙️ Configuración

### Puerto WebSocket (`renderer.js`, línea 9)

```javascript
const WEBSOCKET_URL = 'ws://localhost:8765'; // cambiar si el daemon usa otro puerto
```

### Fullscreen / Kiosk (`main-log.js`)

```javascript
// Añadir dentro de createWindow(), tras mainWindow.loadFile():
mainWindow.setFullScreen(true);   // fullscreen normal
// mainWindow.setKiosk(true);     // kiosk (ESC no sale)
```

---

## 🔧 Integración con riatla_daemon.py

Añadir en el daemon esta función para enviar comandos al avatar:

```python
import websocket, json

def enviar_a_riatla_app(accion, parametros=None):
    try:
        ws = websocket.create_connection('ws://localhost:8765')
        ws.send(json.dumps({"accion": accion, "parametros": parametros or {}}))
        ws.close()
    except Exception as e:
        print(f"[riatla-app] Error enviando comando: {e}")

# Uso en set_emocion():
enviar_a_riatla_app("emocion_happy")
enviar_a_riatla_app("mirar", {"x": -0.2, "y": 0.1, "z": 0})
enviar_a_riatla_app("reset")
```

Ver `INTEGRATION.md` para el ejemplo completo con MQTT.

---

## 🐛 Troubleshooting

**`Failed to resolve module specifier '@pixiv/three-vrm'`** (en DevTools Console)
```bash
# Las dependencias no se instalaron bien. Reinstalar limpio:
Remove-Item -Recurse -Force .\node_modules
npm install
```

**Electron arranca y se cierra inmediatamente**
```bash
# El binario de electron no se descargó. Forzar descarga:
node node_modules\electron\install.js
```

**`Cannot find module 'electron'`**
```bash
npm install --save-dev electron@latest --legacy-peer-deps
```

**WebSocket siempre en rojo (Desconectado)**
- Verificar que `riatla_daemon.py` está ejecutándose en otra terminal
- Comprobar que escucha en el puerto 8765: `netstat -ano | findstr 8765`

**Avatar no aparece (solo fondo morado)**
- Abrir DevTools (F12) → pestaña Console → buscar errores en rojo
- Verificar que el fichero VRM existe: `Test-Path .\models\riatla.vrm`

---

## 📦 Dependencias principales

| Paquete | Versión | Uso |
|---|---|---|
| `electron` | latest | Framework de escritorio (BrowserWindow, IPC) |
| `three` | 0.137.0 | Motor 3D (escena, cámara, renderer WebGL) |
| `@pixiv/three-vrm` | latest | Loader VRM, BlendShapes, humanoid bones |

