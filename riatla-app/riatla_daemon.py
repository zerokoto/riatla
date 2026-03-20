"""
Riatla Daemon v0.2 — Puente MQTT → Three.js/Electron
=====================================================
Actúa como puente entre Home Assistant (MQTT) y el avatar 3D en Electron (WebSocket).

Arquitectura de hilos
─────────────────────
  Hilo principal   → cliente MQTT bloqueante (paho loop_forever)
  Hilo WS          → servidor asyncio WebSocket (loop propio)
  Comunicación     → asyncio.run_coroutine_threadsafe para cruzar hilos de forma segura

Flujo de un comando
───────────────────
  HA  →  MQTT broker  →  on_message()  →  set_emocion()
      →  enviar_comando()  →  ws_broadcast()  →  Electron (renderer.js)

Topics MQTT de entrada
──────────────────────
  riatla/emocion   →  {"emocion": "angry"}
                      {"emocion": "sad", "duracion": 5}
                      "happy"   ← texto plano también aceptado
  riatla/reset     →  cualquier payload → vuelve a neutral
  riatla/world     →  ruta relativa del GLB/GLTF  (ej: "./world/Attic.vnworld")
  riatla/world/luz →  "on" | "off"  → enciende/apaga la iluminación
  riatla/world/musica → "on" | "off"  → activa/desactiva animación de baile sutil

Topics MQTT de salida (publicados por el daemon)
─────────────────────────────────────────────────
  riatla/estado    →  {"emocion": "angry", "timestamp": "...", "daemon": "online"}

Dependencias
────────────
  pip install paho-mqtt websockets
"""

import json
import time
import asyncio
import threading
import websockets
import paho.mqtt.client as mqtt
from websockets.server import serve

# ── Configuración ─────────────────────────────────────────────────────────────
# Modificar según el entorno. MQTT_PASS se almacena en texto plano; en producción
# considerar variables de entorno o un fichero de secretos externo.

MQTT_HOST = "192.168.1.126"
MQTT_PORT = 1883
MQTT_USER = "meshmqtt"
MQTT_PASS = "m3sq77"

WS_HOST = "localhost"
WS_PORT = 8765  # debe coincidir con WEBSOCKET_URL en renderer.js

TOPIC_EMOCION    = "riatla/emocion"
TOPIC_RESET      = "riatla/reset"
TOPIC_ESTADO     = "riatla/estado"
TOPIC_WORLD      = "riatla/world"
TOPIC_WORLD_LUZ  = "riatla/world/luz"
TOPIC_WORLD_MUSICA = "riatla/world/musica"
TOPIC_WORLD_ALL  = "riatla/world/#"   # agrupa TOPIC_WORLD y todos sus subtopics

# Deben coincidir exactamente con los case de ejecutarComando() en renderer.js
EMOCIONES_VALIDAS = {"happy", "angry", "sad", "relaxed", "surprised", "neutral"}

# ── Estado interno ─────────────────────────────────────────────────────────────
# Compartido entre el hilo MQTT y el hilo WS.
# - clientes_ws: solo se modifica desde ws_handler (loop asyncio), es thread-safe.
# - loop: se escribe una vez al arrancar el hilo WS, luego es de solo lectura.
# - timer_reset: creado/cancelado desde on_message (hilo MQTT).

estado = {
    "emocion_actual": "neutral",
    "clientes_ws": set(),   # websockets activos conectados desde Electron
    "timer_reset":  None,   # threading.Timer del auto-reset daemon-side
    "loop":         None,   # asyncio event loop del servidor WS
}

# ── WebSocket server (asyncio) ─────────────────────────────────────────────────

async def ws_handler(websocket):
    """
    Callback del servidor WS: registra al cliente Electron al conectarse
    y lo elimina cuando se desconecta (cierre normal o error de red).
    El renderer.js solo recibe comandos; nunca envía datos.
    """
    estado["clientes_ws"].add(websocket)
    print(f"[WS] Cliente conectado. Total: {len(estado['clientes_ws'])}")
    try:
        async for _ in websocket:
            pass
    finally:
        estado["clientes_ws"].discard(websocket)
        print(f"[WS] Cliente desconectado. Total: {len(estado['clientes_ws'])}")

async def ws_broadcast(mensaje: dict):
    """
    Envía un comando JSON a todos los clientes Electron conectados.

    NOTA: no usamos websockets.broadcast() porque:
      - No está disponible en versiones < 10 de la librería.
      - Las excepciones individuales quedarían silenciadas.
    En su lugar iteramos manualmente con await para tener control total
    de errores y limpiar conexiones muertas del set.
    """
    if not estado["clientes_ws"]:
        print("[WS] Sin clientes conectados — comando descartado")
        return

    payload  = json.dumps(mensaje)
    caidos   = set()

    for cliente in list(estado["clientes_ws"]):   # copia para iterar sin riesgo
        try:
            await cliente.send(payload)
        except Exception as exc:
            print(f"[WS] Error enviando a cliente: {exc}")
            caidos.add(cliente)

    # Limpiar conexiones muertas detectadas durante el broadcast
    estado["clientes_ws"] -= caidos

    print(f"[WS] Broadcast → {payload}  (clientes: {len(estado['clientes_ws'])})")

def enviar_comando(accion: str, parametros: dict = None):
    """
    Thread-safe: encola ws_broadcast en el loop asyncio del hilo WS.
    Debe llamarse desde cualquier hilo (callbacks MQTT corren en el hilo principal).

    Adjunta un callback al Future para registrar excepciones que de otro modo
    quedarían silenciadas (la Future descartada no propaga errores por sí sola).
    """
    if estado["loop"] is None:
        print("[WS] Loop no disponible aún — comando perdido")
        return

    comando = {"accion": accion, "parametros": parametros or {}}
    future  = asyncio.run_coroutine_threadsafe(ws_broadcast(comando), estado["loop"])

    def _on_done(f):
        exc = f.exception()
        if exc:
            print(f"[WS] Excepción en ws_broadcast: {exc}")

    future.add_done_callback(_on_done)

def iniciar_servidor_ws():
    """
    Arranca el servidor WebSocket en su propio hilo con su propio event loop.
    Bloquea el hilo hasta que el proceso termina (asyncio.Future infinita).
    """
    async def run():
        async with serve(ws_handler, WS_HOST, WS_PORT):
            print(f"[WS] Servidor escuchando en ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()   # mantiene el servidor vivo indefinidamente

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    estado["loop"] = loop            # exponer el loop ANTES de run_until_complete
    loop.run_until_complete(run())

# ── Lógica de emociones ────────────────────────────────────────────────────────

def set_emocion(emocion: str, duracion: int = None, mqtt_client=None):
    """
    Aplica una emoción al avatar:
      1. Valida y normaliza el nombre.
      2. Cancela cualquier timer de auto-reset anterior.
      3. Envía el comando WebSocket a Electron con la duración (si la hay).
      4. Publica el nuevo estado en MQTT (topic riatla/estado).
      5. Si se especificó duración, programa un timer daemon-side que enviará
         emocion_neutral cuando expire (refuerzo del auto-reset del renderer).

    El renderer.js también gestiona su propio timer de reset; el daemon-side
    actúa como red de seguridad en caso de que Electron se reinicie.

    Args:
        emocion:      Nombre de la emoción (case-insensitive).
        duracion:     Segundos hasta volver a neutral. None = permanente.
        mqtt_client:  Cliente paho para publicar en riatla/estado.
    """
    emocion = emocion.lower().strip()

    if emocion not in EMOCIONES_VALIDAS:
        print(f"[Riatla] Emoción desconocida: '{emocion}' — válidas: {EMOCIONES_VALIDAS}")
        return

    # Cancelar timer anterior si existe
    if estado["timer_reset"] is not None:
        estado["timer_reset"].cancel()
        estado["timer_reset"] = None

    # Enviar comando al renderer
    enviar_comando(f"emocion_{emocion}", {"duracion": duracion} if duracion else {})
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
    """
    Llamado por paho al establecer (o restablecer) la conexión con el broker.
    rc == 0 → éxito. Cualquier otro valor es un código de error MQTT.
    Se re-suscribe aquí para que las suscripciones sobrevivan a reconexiones.
    """
    if rc == 0:
        print(f"[MQTT] Conectado a {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_EMOCION)
        client.subscribe(TOPIC_RESET)
        client.subscribe(TOPIC_WORLD_ALL)
        print(f"[MQTT] Escuchando: {TOPIC_EMOCION}, {TOPIC_RESET}, {TOPIC_WORLD_ALL}")
        client.publish(TOPIC_ESTADO, json.dumps({
            "emocion": "neutral",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "daemon": "online"
        }), retain=True)
    else:
        print(f"[MQTT] Error de conexión, código: {rc}")

def on_disconnect(client, userdata, rc):
    """Paho llama a este callback al perder la conexión. Loop_forever reconecta solo."""
    print(f"[MQTT] Desconectado (rc={rc}), reconectando...")

def on_message(client, userdata, msg):
    """
    Punto de entrada para todos los topics suscritos.
    Decodifica el payload y delega a set_emocion() o set_world().
    Acepta tanto JSON ({emocion: ..., duracion: ...}) como texto plano ("happy").
    """
    topic       = msg.topic
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
            emocion  = payload_raw   # acepta texto plano: "happy"
            duracion = None

        set_emocion(emocion, duracion=duracion, mqtt_client=client)

    if topic == TOPIC_WORLD:
        try:
            data   = json.loads(payload_raw)
            nombre = data.get("mundo", "JapaneseRoom")
        except json.JSONDecodeError:
            nombre = payload_raw  # acepta también texto plano: "TinyRoom"
        enviar_comando("world", {"nombre": nombre})
        print(f"[Riatla] World → {nombre}")

    if topic == TOPIC_WORLD_LUZ:
        set_world_luz(payload_raw)

    if topic == TOPIC_WORLD_MUSICA:
        try:
            data          = json.loads(payload_raw)
            estado_musica = data.get("estado", payload_raw)
            modo_musica   = data.get("modo", "normal")
        except json.JSONDecodeError:
            estado_musica = payload_raw   # acepta texto plano: "on" / "off"
            modo_musica   = "normal"
        set_world_musica(estado_musica, modo_musica)

def set_world(path: str, mqtt_client=None):
    """
    Cambia el escenario 3D enviando la ruta del archivo al renderer.
    El renderer eliminará el escenario anterior y cargará el nuevo.
    Args:
        path: Ruta relativa al GLTF/GLB (ej: "./world/Attic.vnworld").
    """
    enviar_comando("world", {"path": path})
    print(f"[Riatla] World → {path}")

def set_world_rotation(angulo: float, mqtt_client=None):
    """Rota el escenario sobre el eje Y. angulo en radianes."""
    enviar_comando("world_rotation", {"y": angulo})

def set_world_luz(estado_luz: str):
    """
    Enciende o apaga la iluminación de la habitación.
    Args:
        estado_luz: "on" | "off" (case-insensitive).
    """
    estado_luz = estado_luz.lower().strip()
    if estado_luz not in ("on", "off"):
        print(f"[Riatla] world/luz: valor desconocido '{estado_luz}' — usar 'on' u 'off'")
        return
    enviar_comando("world_luz", {"estado": estado_luz})
    print(f"[Riatla] Iluminación → {estado_luz}")

def set_world_musica(estado_musica: str, modo: str = 'normal'):
    """
    Activa o desactiva la animación de baile sutil del avatar.
    Args:
        estado_musica: "on" | "off" (case-insensitive).
        modo:          "normal" | "metal" (default: "normal").
    """
    estado_musica = estado_musica.lower().strip()
    modo          = modo.lower().strip()
    if estado_musica not in ("on", "off"):
        print(f"[Riatla] world/musica: valor desconocido '{estado_musica}' — usar 'on' u 'off'")
        return
    if modo not in ("normal", "metal"):
        print(f"[Riatla] world/musica: modo desconocido '{modo}' — usar 'normal' o 'metal'")
        modo = 'normal'
    params = {"estado": estado_musica}
    if estado_musica == "on":
        params["modo"] = modo
    enviar_comando("world_musica", params)
    print(f"[Riatla] Música → {estado_musica}" + (f" ({modo})" if estado_musica == "on" else ""))



# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """
    Punto de entrada del daemon:
      1. Arranca el servidor WebSocket en un hilo secundario (asyncio).
      2. Espera 0.5 s a que el loop asyncio esté listo para recibir coroutines.
      3. Conecta el cliente MQTT y bloquea en loop_forever() en el hilo principal.
    Al recibir Ctrl+C publica un estado "offline" antes de salir.
    """
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