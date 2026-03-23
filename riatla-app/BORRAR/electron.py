"""
RIATLA APP - CLIENTE ELECTRON
════════════════════════════════════════════════════════════════════════════

ESTRUCTURA DEL PROYECTO:
├── package.json           → Configuración npm (electron, three, @pixiv/three-vrm)
├── electron-main.js       → Proceso principal de Electron (crea ventana)
├── preload.js             → Script de preload (seguridad)
├── index.html             → HTML principal con canvas
├── renderer.js            → Script renderer (THREE.js + VRM + WebSocket)
├── models/
│   └── riatla.vrm        → Modelo del avatar
└── assets/
    └── icon.png          → Icono de la app (opcional)

INSTALACIÓN Y EJECUCIÓN:
════════════════════════════════════════════════════════════════════════════

1. Instalar dependencias:
   cd riatla-app
   npm install

2. Ejecutar la app en desarrollo:
   npm start

3. Para fullscreen (opcional):
   Descomtentar línea en electron-main.js: mainWindow.setFullScreen(true)

CARACTERÍSTICAS:
════════════════════════════════════════════════════════════════════════════

✓ Carga modelo VRM (riatla.vrm) con Three.js
✓ WebSocket cliente conecta a daemon Python (localhost:8765)
✓ Expresiones faciales (happy, sad, angry, surprised, relaxed, neutral)
✓ Movimientos de cabeza (mirar arriba, abajo, izquierda, derecha)
✓ Panel de debug en tiempo real
✓ Indicador de estado WebSocket
✓ Reconexión automática si se cae la conexión

COMANDOS WEBSOCKET (desde riatla_daemon.py):
════════════════════════════════════════════════════════════════════════════

{
  "accion": "hablar",              // sinónimo: emocion_happy
  "parametros": {}
}

{
  "accion": "escuchar",            // sinónimo: emocion_neutral
  "parametros": {}
}

{
  "accion": "alerta",              // sinónimo: emocion_surprised
  "parametros": {}
}

{
  "accion": "emocion_angry",
  "parametros": {}
}

{
  "accion": "emocion_sad",
  "parametros": {}
}

{
  "accion": "emocion_relaxed",
  "parametros": {}
}

{
  "accion": "mirar",
  "parametros": { "x": 0.3, "y": 0.1, "z": 0 }
}

{
  "accion": "reset",               // vuelve a neutral
  "parametros": {}
}

MODIFICAR PARA FULLSCREEN:
════════════════════════════════════════════════════════════════════════════

En electron-main.js, líneas 30-31:
  mainWindow.setFullScreen(true);
  mainWindow.setKiosk(true);  // salir con ESC

CONFIGURAR PUERTO WEBSOCKET:
════════════════════════════════════════════════════════════════════════════

En renderer.js, línea 15:
  const WEBSOCKET_URL = 'ws://localhost:8765'; // ← cambiar si es necesario

SINCRONIZAR CON DAEMON:
════════════════════════════════════════════════════════════════════════════

Asegúrate que riatla_daemon.py está ejecutándose:
  cd ..
  python riatla_daemon.py
"""