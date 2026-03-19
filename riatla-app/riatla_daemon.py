"""
Riatla Daemon v0.2 - Puente MQTT → Three.js/Electron
Escucha topics MQTT de Home Assistant y controla el avatar via WebSocket

Requiere: pip install paho-mqtt websockets

Topics MQTT:
    riatla/emocion      → {"emocion": "happy"}
                          {"emocion": "sad", "duracion": 5}
    riatla/reset        → cualquier mensaje → vuelve a neutral
    riatla/estado       → (publicado por el daemon) estado actual del sistema
"""

import json
import time
import asyncio
import threading
import websockets
import paho.mqtt.client as mqtt
from websockets.server import serve

# ── Configuración ─────────────────────────────────────────────────────────────

MQTT_HOST     = "192.168.1.126"
MQTT_PORT     = 1883
MQTT_USER     = "meshmqtt"
MQTT_PASS     = "m3sq77"

WS_HOST       = "localhost"
WS_PORT       = 8765           # ← debe coincidir con renderer.js

TOPIC_EMOCION = "riatla/emocion"
TOPIC_RESET   = "riatla/reset"
TOPIC_ESTADO  = "riatla/estado"
TOPIC_WORLD = "riatla/world"

# Deben coincidir exactamente con los case de ejecutarComando() en renderer.js
EMOCIONES_VALIDAS = {"happy", "angry", "sad", "relaxed", "surprised", "neutral"}

# ── Estado interno ─────────────────────────────────────────────────────────────

estado = {
    "emocion_actual": "neutral",
    "clientes_ws": set(),          # clientes Electron conectados
    "timer_reset": None,
    "loop": None                   # asyncio event loop del servidor WS
}

# ── WebSocket server (asyncio) ─────────────────────────────────────────────────

async def ws_handler(websocket):
    """Registra cada cliente Electron que se conecte."""
    estado["clientes_ws"].add(websocket)
    print(f"[WS] Cliente conectado. Total: {len(estado['clientes_ws'])}")
    try:
        async for _ in websocket:
            pass  # el renderer no envía nada, sólo recibe
    finally:
        estado["clientes_ws"].discard(websocket)
        print(f"[WS] Cliente desconectado. Total: {len(estado['clientes_ws'])}")

async def ws_broadcast(mensaje: dict):
    """Envía un comando JSON a todos los clientes Electron conectados."""
    if not estado["clientes_ws"]:
        print("[WS] Sin clientes conectados, comando descartado")
        return
    payload = json.dumps(mensaje)
    # websockets.broadcast es más eficiente que iterar manualmente
    websockets.broadcast(estado["clientes_ws"], payload)
    print(f"[WS] Broadcast → {payload}")

def enviar_comando(accion: str, parametros: dict = None):
    """
    Thread-safe: encola un broadcast en el loop asyncio del servidor WS.
    Se llama desde los callbacks MQTT (hilo distinto).
    """
    if estado["loop"] is None:
        print("[WS] Loop no disponible aún")
        return
    comando = {"accion": accion, "parametros": parametros or {}}
    asyncio.run_coroutine_threadsafe(ws_broadcast(comando), estado["loop"])

def iniciar_servidor_ws():
    """Arranca el servidor WebSocket en su propio hilo con su propio event loop."""
    async def run():
        estado["loop"] = asyncio.get_event_loop()
        async with serve(ws_handler, WS_HOST, WS_PORT):
            print(f"[WS] Servidor escuchando en ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()  # mantiene el servidor vivo indefinidamente

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    estado["loop"] = loop
    loop.run_until_complete(run())

# ── Lógica de emociones ────────────────────────────────────────────────────────

def set_emocion(emocion: str, duracion: int = None, mqtt_client=None):
    emocion = emocion.lower().strip()  # normalizar siempre a minúsculas

    if emocion not in EMOCIONES_VALIDAS:
        print(f"[Riatla] Emoción desconocida: '{emocion}'")
        return

    # Cancelar timer anterior si existe
    if estado["timer_reset"] is not None:
        estado["timer_reset"].cancel()
        estado["timer_reset"] = None

    # Enviar comando al renderer
    enviar_comando(f"emocion_{emocion}")
    estado["emocion_actual"] = emocion
    print(f"[Riatla] Emoción → {emocion}" + (f" (durante {duracion}s)" if duracion else ""))

    # Publicar estado en MQTT
    if mqtt_client:
        mqtt_client.publish(TOPIC_ESTADO, json.dumps({
            "emocion": emocion,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }), retain=True)

    # Timer de reset automático
    if duracion and emocion != "neutral":
        def auto_reset():
            print(f"[Riatla] Auto-reset a neutral tras {duracion}s")
            enviar_comando("emocion_neutral")
            estado["emocion_actual"] = "neutral"
            if mqtt_client:
                mqtt_client.publish(TOPIC_ESTADO, json.dumps({
                    "emocion": "neutral",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                }), retain=True)

        t = threading.Timer(duracion, auto_reset)
        t.daemon = True
        t.start()
        estado["timer_reset"] = t

# ── MQTT callbacks ─────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Conectado a {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_EMOCION)
        client.subscribe(TOPIC_RESET)
        client.subscribe(TOPIC_WORLD)
        print(f"[MQTT] Escuchando: {TOPIC_EMOCION}, {TOPIC_RESET}")
        client.publish(TOPIC_ESTADO, json.dumps({
            "emocion": "neutral",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "daemon": "online"
        }), retain=True)
    else:
        print(f"[MQTT] Error de conexión, código: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc}), reconectando...")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload_raw = msg.payload.decode("utf-8").strip()
    print(f"[MQTT] {topic} → {payload_raw}")

    if topic == TOPIC_RESET:
        set_emocion("neutral", mqtt_client=client)
        return

    if topic == TOPIC_EMOCION:
        try:
            data     = json.loads(payload_raw)
            emocion  = data.get("emocion", "neutral")
            duracion = data.get("duracion", None)
        except json.JSONDecodeError:
            emocion  = payload_raw   # acepta también texto plano: "happy"
            duracion = None

        set_emocion(emocion, duracion=duracion, mqtt_client=client)

    if topic == TOPIC_WORLD:
        set_world(payload_raw, mqtt_client=client)

def set_world(path: str, mqtt_client=None):
    """Cambia el escenario 3D enviando la ruta del GLB."""
    enviar_comando("world", {"path": path})
    print(f"[Riatla] World → {path}")

def set_world_rotation(angulo: float, mqtt_client=None):
    enviar_comando("world_rotation", {"y": angulo})



# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════╗")
    print("║       Riatla Daemon v0.2         ║")
    print("╚══════════════════════════════════╝")
    print(f"MQTT  → {MQTT_HOST}:{MQTT_PORT}")
    print(f"WS    → ws://{WS_HOST}:{WS_PORT}\n")

    # Servidor WS en hilo propio (asyncio)
    ws_thread = threading.Thread(target=iniciar_servidor_ws, daemon=True)
    ws_thread.start()

    # Pequeña pausa para asegurar que el loop asyncio esté listo
    time.sleep(0.5)

    # Cliente MQTT (bloqueante, hilo principal)
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[Riatla] Daemon detenido.")
        client.publish(TOPIC_ESTADO, json.dumps({"daemon": "offline"}), retain=True)
        client.disconnect()

if __name__ == "__main__":
    main()