"""
GUÍA DE INTEGRACIÓN: RIATLA-DAEMON ↔ RIATLA-APP
════════════════════════════════════════════════════════════════════════════

Este documento explica cómo integrar riatla_daemon.py (puente MQTT) con
riatla-app (cliente Electron con Three.js VRM).

ARQUITECTURA
════════════════════════════════════════════════════════════════════════════

┌──────────────────┐
│  Home Assistant  │
│     (MQTT)       │
└────────┬─────────┘
         │
         │ mqtt.subscribe("riatla/emocion")
         │ mqtt.subscribe("riatla/reset")
         │
┌────────▼──────────────────────────────┐
│    riatla_daemon.py                    │
│   ┌──────────────────────────────┐    │
│   │  MQTT Listener (paho-mqtt)    │    │
│   │  ↓                            │    │
│   │  set_emocion(emocion)        │    │
│   │  ↓                            │    │
│   │  WebSocket Cliente            │    │
│   └──────────────┬────────────────┘    │
└────────────────┬─────────────────────┘
                 │
                 │ ws.send(JSON)
                 │ (comando VRM)
                 │
┌────────────────▼────────────────────────┐
│    riatla-app (index.html)              │
│   ┌──────────────────────────────┐      │
│   │  WebSocket Server (renderer)  │      │
│   │  ↓                            │      │
│   │  ejecutarComando(comando)     │      │
│   │  ↓                            │      │
│   │  Three.js + VRM              │      │
│   │  (Expresiones + Movimientos) │      │
│   └──────────────────────────────┘      │
└─────────────────────────────────────────┘

CONFIGURACIÓN DAEMON
════════════════════════════════════════════════════════════════════════════

En riatla_daemon.py, modificar estas líneas:

# Línea ~20
MQTT_HOST = "192.168.1.126"    # Tu servidor MQTT
MQTT_PORT = 1883
MQTT_USER = "meshmqtt"
MQTT_PASS = "m3sq77"

# Línea ~22
VNYAN_HOST = "ws://localhost:8765"  ← CAMBIAR A:
WEBSOCKET_APP_URL = "ws://localhost:8765"  # URL de riatla-app

# Línea ~52 (función vnyan_send)
def enviar_a_app(comando: dict):
    """Envía comando JSON a riatla-app via WebSocket"""
    try:
        ws = websocket.create_connection(WEBSOCKET_APP_URL)
        ws.send(json.dumps(comando))
        ws.close()
    except Exception as e:
        print(f"[Riatla-App] Error enviando comando: {e}")

MODIFICACIÓN EN SET_EMOCION
════════════════════════════════════════════════════════════════════════════

En riatla_daemon.py, función set_emocion (línea ~60):

def set_emocion(emocion: str, duracion: int = None, mqtt_client=None):
    
    # ... código existente ...
    
    # AÑADIR AL FINAL:
    
    # Enviar comandos a riatla-app
    threading.Thread(
        target=enviar_a_app,
        args=({
            "accion": f"emocion_{emocion.lower()}",
            "parametros": {"duracion": duracion}
        },),
        daemon=True
    ).start()

EJEMPLO: REACCIONAR A EVENTOS MQTT
════════════════════════════════════════════════════════════════════════════

En on_message() de riatla_daemon.py:

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    
    try:
        data = json.loads(payload)
        emocion = data.get("emocion", "neutral")
        duracion = data.get("duracion", None)
        
        # Aplicar emoción (con timer de reset)
        set_emocion(emocion, duracion, client)
        
        # También publicar el estado
        client.publish(
            "riatla/estado",
            json.dumps({
                "emocion_actual": emocion,
                "timestamp": time.time()
            })
        )
        
    except json.JSONDecodeError:
        print(f"[MQTT] Error decodificando JSON: {payload}")

EJEMPLOS DE COMANDOS A RIATLA-APP
════════════════════════════════════════════════════════════════════════════

1. EXPRESIÓN FELIZ
   {
     "accion": "emocion_happy",
     "parametros": {"duracion": 2}
   }

2. EXPRESIÓN SORPRESA
   {
     "accion": "emocion_surprised",
     "parametros": {"duracion": 1}
   }

3. MOVER CABEZA
   {
     "accion": "mirar",
     "parametros": {
       "x": 0.2,   # arriba/abajo (-1 a 1)
       "y": 0.1,   # izquierda/derecha
       "z": 0      # rotación
     }
   }

4. RESET TOTAL
   {
     "accion": "reset",
     "parametros": {}
   }

FLUJO COMPLETO EJEMPLO
════════════════════════════════════════════════════════════════════════════

Home Assistant publica:
  Tema: riatla/emocion
  Payload: {"emocion": "happy", "duracion": 3}
           (evento: alguien sonrió)

↓ riatla_daemon.py escucha

↓ Ejecuta set_emocion("happy", 3)

↓ Envía a riatla-app:
  {
    "accion": "emocion_happy",
    "parametros": {"duracion": 3}
  }

↓ riatla-app recibe por WebSocket

↓ renderer.js ejecuta activarExpresion("happy")

↓ Three.js anima el BlendShape "happy" en el VRM

↓ Avatar muestra sonrisa por 3 segundos

↓ Timer expira, vuelve a neutral

TEST SIN HOME ASSISTANT
════════════════════════════════════════════════════════════════════════════

Si no tienes Home Assistant configurado, puedes simular eventos MQTT:

1. Abrir otro terminal:
   mosquitto_pub -h 192.168.1.126 -p 1883 \\
                 -u meshmqtt -P m3sq77 \\
                 -t riatla/emocion \\
                 -m '{"emocion":"happy"}'

2. O usar un cliente Python:
   import paho.mqtt.client as mqtt
   import json
   
   client = mqtt.Client()
   client.username_pw_set("meshmqtt", "m3sq77")
   client.connect("192.168.1.126", 1883)
   client.publish(
     "riatla/emocion",
     json.dumps({"emocion": "happy", "duracion": 2})
   )
   client.disconnect()

TROUBLESHOOTING
════════════════════════════════════════════════════════════════════════════

❌ Problema: "riatla-app no recibe comandos"
✓ Solución:
  - Verificar que riatla-app está ejecutándose (npm start)
  - Verificar Puerto 8765 no está bloqueado (netstat -an | grep 8765)
  - Verificar URL en daemon: localhost vs IP real

❌ Problema: "daemon no se conecta a MQTT"
✓ Solución:
  - Verificar IP y puerto MQTT
  - Usuario y contraseña correctos
  - Mosquitto ejecutándose

❌ Problema: "WebSocket se desconecta cada 3 segundos"
✓ Solución:
  - El daemon intenta reconectar automáticamente
  - Verifica logs del daemon (riatla_daemon.py)
  - Aumentar timeout en websocket.create_connection()

MONITOREO EN TIEMPO REAL
════════════════════════════════════════════════════════════════════════════

Terminal 1 (Ver logs MQTT):
  mosquitto_sub -h 192.168.1.126 -u meshmqtt -P m3sq77 -t riatla/#

Terminal 2 (Ejecutar daemon):
  python riatla_daemon.py

Terminal 3 (Ejecutar app):
  cd riatla-app && npm start

Terminal 4 (Enviar eventos):
  mosquitto_pub -h 192.168.1.126 -u meshmqtt -P m3sq77 \\
    -t riatla/emocion -m '{"emocion":"happy", "duracion":2}'

Verás el flujo completo en los logs.
"""