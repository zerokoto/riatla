# 🎭 Riatla App - Android Avatar Client

Cliente **Electron** + **Three.js** + **VRM** que renderiza el avatar Riatla y recibe comandos de animación vía WebSocket desde el daemon Python.

## 📋 Estructura

```
riatla-app/
├── package.json          ← Dependencias npm
├── electron-main.js      ← Proceso principal de Electron
├── preload.js            ← Script de preload (seguridad)
├── index.html            ← HTML principal
├── renderer.js           ← Logic (THREE.js + VRM + WebSocket)
├── models/
│   └── riatla.vrm       ← Modelo VRM del avatar
└── electron.py          ← Notas e instrucciones
```

## 🚀 Instalación

```bash
cd riatla-app
npm install
```

**Requisitos:**
- Node.js 14+ 
- npm o yarn
- El daemon Python ejecutándose (`python ../riatla_daemon.py`)

## ▶️ Ejecutar

```bash
npm start        # Inicia la app
npm run dev      # Con DevTools abierto
```

## 🎮 Comandos WebSocket

El app escucha en `ws://localhost:8765` los siguientes comandos JSON:

### Expresiones

```json
{ "accion": "hablar" }           // = emocion_happy
{ "accion": "emocion_happy" }  
{ "accion": "emocion_sad" }    
{ "accion": "emocion_angry" }   
{ "accion": "emocion_surprised" }
{ "accion": "emocion_relaxed" }
{ "accion": "emocion_neutral" }  // = escuchar
```

### Movimientos

```json
{
  "accion": "mirar",
  "parametros": { "x": -0.2, "y": 0.1, "z": 0 }
}
```

### Control

```json
{ "accion": "reset" }  // Vuelve a neutral y centra la cabeza
```

## ⚙️ Configuración

### Puerto WebSocket

**renderer.js** (línea 15):

```javascript
const WEBSOCKET_URL = 'ws://localhost:8765'; // ← cambiar si es necesario
```

### Fullscreen

**electron-main.js** (líneas 30-33):

```javascript
// Descomenta para fullscreen
// mainWindow.setFullScreen(true);
// mainWindow.setKiosk(true);  // ESC para salir
```

## 🔧 Integración con riatla_daemon.py

El daemon debe enviar comandos por WebSocket:

```python
def enviar_comando(accion, parametros=None):
    comando = {
        "accion": accion,
        "parametros": parametros or {}
    }
    # Enviar a ws://localhost:8765
    ws.send(json.dumps(comando))

# Ejemplos
enviar_comando("hablar")
enviar_comando("emocion_happy")
enviar_comando("mirar", {"x": 0.3, "y": 0, "z": 0})
enviar_comando("reset")
```

## 🎨 Panel de Debug

Esquina superior-izquierda: último evento
Esquina inferior-derecha: estado WebSocket

## 📦 Dependencias Principales

- **electron**: Framework de escritorio
- **three**: Motor 3D
- **@pixiv/three-vrm**: Loader y utils para modelos VRM

## ⚠️ Notas

- El modelo VRM debe estar en `models/riatla.vrm`
- La app intenta reconectar automáticamente si pierde la conexión WebSocket
- Los BlendShapes (expresiones) deben estar en el modelo VRM
- Los huesos (bones) deben seguir el estándar VRM (head, chest, etc)

## 🐛 Troubleshooting

**Error: "Cannot find module 'three'"**
```bash
npm install
```

**WebSocket desconecta cada 3 segundos**
- Verifica que `riatla_daemon.py` está ejecutándose
- Comprueba puerto 8765 no está bloqueado

**Avatar no se ve**
- Verifica ruta a `models/riatla.vrm`
- Abre DevTools (F12) para ver errores

**Expresiones no funcionan**
- Comprueba que el VRM tiene BlendShapes en Mixamo/Unity
- Revisa console para nombres de expresiones disponibles
