"""
Riatla Daemon - Puente MQTT → VNyan
Escucha topics MQTT de Home Assistant y controla el avatar via WebSocket

Requiere: pip install paho-mqtt websocket-client

Topics MQTT:
    riatla/emocion      → {"emocion": "Smile"}
                          {"emocion": "Sad", "duracion": 5}
    riatla/reset        → cualquier mensaje → vuelve a Neutral
    riatla/estado       → (publicado por el daemon) estado actual del sistema
"""

import json
import time
import threading
import websocket
import paho.mqtt.client as mqtt

# ── Configuración ─────────────────────────────────────────────────────────────

MQTT_HOST     = "192.168.1.126"
MQTT_PORT     = 1883
MQTT_USER     = "meshmqtt"
MQTT_PASS     = "m3sq77"

VNYAN_HOST    = "ws://localhost:8000/vnyan"

TOPIC_EMOCION = "riatla/emocion"
TOPIC_RESET   = "riatla/reset"
TOPIC_ESTADO  = "riatla/estado"

EMOCIONES_VALIDAS = ["happy", "angry", "sad", "relaxed", "surprised", "neutral"] 

# ── Estado interno ─────────────────────────────────────────────────────────────

estado = {
    "emocion_actual": "Neutral",
    "vnyan_disponible": False,
    "timer_reset": None
}

# ── VNyan ──────────────────────────────────────────────────────────────────────

def vnyan_send(command: str):
    """Envía un comando de texto plano a VNyan."""
    try:
        def on_open(ws):
            ws.send(command)
            ws.close()

        def on_error(ws, error):
            if "NoneType" not in str(error):
                print(f"[VNyan] Error: {error}")
                estado["vnyan_disponible"] = False

        def on_close(ws, *a):
            estado["vnyan_disponible"] = True

        ws = websocket.WebSocketApp(
            VNYAN_HOST,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )
        ws.run_forever()

    except Exception as e:
        print(f"[VNyan] No se pudo conectar: {e}")
        estado["vnyan_disponible"] = False

def set_emocion(emocion: str, duracion: int = None, mqtt_client=None):
    """Aplica una emoción al avatar con reset previo y timer opcional."""
    if emocion not in EMOCIONES_VALIDAS:
        print(f"[Riatla] Emoción desconocida: '{emocion}'")
        return

    # Cancelar timer de reset anterior si existe
    if estado["timer_reset"] is not None:
        estado["timer_reset"].cancel()
        estado["timer_reset"] = None

    # Reset previo
    if emocion != "neutral":
        vnyan_send("neutral")
        time.sleep(0.3)

    # Aplicar nueva emoción
    vnyan_send(emocion)
    estado["emocion_actual"] = emocion
    print(f"[Riatla] Emoción → {emocion}" + (f" (durante {duracion}s)" if duracion else ""))

    # Publicar estado en MQTT
    if mqtt_client:
        mqtt_client.publish(TOPIC_ESTADO, json.dumps({
            "emocion": emocion,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }), retain=True)

    # Timer de reset automático si se especifica duración
    if duracion and emocion != "neutral":
        def auto_reset():
            print(f"[Riatla] Auto-reset a neutral tras {duracion}s")
            vnyan_send("neutral")
            estado["emocion_actual"] = "neutral"
            if mqtt_client:
                mqtt_client.publish(TOPIC_ESTADO, json.dumps({
                    "emocion": "Neutral",
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
        print(f"[MQTT] Escuchando: {TOPIC_EMOCION}, {TOPIC_RESET}")
        # Publicar estado inicial
        client.publish(TOPIC_ESTADO, json.dumps({
            "emocion": "Neutral",
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

    # ── riatla/reset ──────────────────────────────────────────
    if topic == TOPIC_RESET:
        set_emocion("Neutral", mqtt_client=client)
        return

    # ── riatla/emocion ────────────────────────────────────────
    if topic == TOPIC_EMOCION:
        try:
            # Acepta JSON: {"emocion": "Smile"} o {"emocion": "Sad", "duracion": 5}
            data = json.loads(payload_raw)
            emocion  = data.get("emocion", "Neutral")
            duracion = data.get("duracion", None)
        except json.JSONDecodeError:
            # Acepta también texto plano: "Smile"
            emocion  = payload_raw
            duracion = None

        set_emocion(emocion, duracion=duracion, mqtt_client=client)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════╗")
    print("║       Riatla Daemon v0.1         ║")
    print("╚══════════════════════════════════╝")
    print(f"MQTT  → {MQTT_HOST}:{MQTT_PORT}")
    print(f"VNyan → {VNYAN_HOST}\n")

    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    # Reconexión automática
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
