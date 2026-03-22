"""
openclaw_bridge.py — Puente OpenClaw ↔ Home Assistant ↔ Riatla
==============================================================
Lee el contexto de HA desde MQTT (homeassistant/#) y lo expone
a OpenClaw. Recibe decisiones de OpenClaw y las ejecuta:
  - Comandos al avatar  → publica en riatla/# (el daemon los reenvía al renderer)
  - Acciones en HA      → API REST de Home Assistant

Dependencias:
    pip install paho-mqtt requests

Configuración de OpenClaw:
    - Apuntar el webhook de salida a http://localhost:8766/openclaw
    - O usar el polling MQTT si OpenClaw soporta MQTT nativo
"""

import json
import time
import threading
import requests
import paho.mqtt.client as mqtt
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Configuración ──────────────────────────────────────────────────────────────

MQTT_HOST = "192.168.1.126"
MQTT_PORT = 1883
MQTT_USER = "meshmqtt"
MQTT_PASS = "m3sq77"

HA_URL    = "http://192.168.1.126:8123"   # URL de tu Home Assistant
HA_TOKEN  = "TU_LONG_LIVED_TOKEN_AQUI"    # Settings → Profile → Long-lived tokens

BRIDGE_PORT = 8766   # puerto HTTP para recibir decisiones de OpenClaw

# Topics MQTT
TOPIC_HA_ALL    = "homeassistant/#"   # escuchar todo HA
TOPIC_RIATLA    = "riatla/{}"         # plantilla para publicar al daemon

# ── Estado del contexto HA ─────────────────────────────────────────────────────
# Acumula el estado de todas las entidades recibidas por MQTT.
# OpenClaw lo consulta para tomar decisiones contextuales.

contexto_ha = {}   # { "entity_id": { "state": ..., "attributes": ..., "ts": ... } }
contexto_lock = threading.Lock()

# ── MQTT: escuchar HA ──────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Conectado a {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_HA_ALL)
        print(f"[MQTT] Escuchando: {TOPIC_HA_ALL}")
    else:
        print(f"[MQTT] Error de conexión: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc}), reconectando...")

def on_message(client, userdata, msg):
    """
    Procesa los mensajes de homeassistant/# y actualiza el contexto.
    HA publica en homeassistant/<dominio>/<entity_id>/state o /attributes.
    """
    topic = msg.topic
    try:
        payload = msg.payload.decode("utf-8").strip()
        if not payload:
            return

        # Extraer entity_id del topic: homeassistant/light/salon/state → light.salon
        partes = topic.split("/")
        if len(partes) < 3:
            return

        dominio   = partes[1]
        entity_id = f"{dominio}.{partes[2]}" if len(partes) >= 3 else None
        tipo      = partes[3] if len(partes) >= 4 else "raw"

        if not entity_id:
            return

        with contexto_lock:
            if entity_id not in contexto_ha:
                contexto_ha[entity_id] = {}

            try:
                valor = json.loads(payload)
            except json.JSONDecodeError:
                valor = payload

            contexto_ha[entity_id][tipo] = valor
            contexto_ha[entity_id]["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    except Exception as e:
        print(f"[MQTT] Error procesando {topic}: {e}")

# ── HA REST API ────────────────────────────────────────────────────────────────

def ha_get_estado(entity_id: str) -> dict:
    """Obtiene el estado actual de una entidad desde la API REST de HA."""
    try:
        r = requests.get(
            f"{HA_URL}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            timeout=5
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HA] Error obteniendo {entity_id}: {e}")
        return {}

def ha_llamar_servicio(dominio: str, servicio: str, datos: dict = None) -> bool:
    """
    Llama a un servicio de HA via REST API.
    Ejemplos:
        ha_llamar_servicio("light", "turn_on", {"entity_id": "light.salon"})
        ha_llamar_servicio("media_player", "play_media", {
            "entity_id": "media_player.spotify",
            "media_content_id": "spotify:playlist:...",
            "media_content_type": "playlist"
        })
        ha_llamar_servicio("alarm_control_panel", "alarm_arm_away", {
            "entity_id": "alarm_control_panel.casa"
        })
    """
    try:
        r = requests.post(
            f"{HA_URL}/api/services/{dominio}/{servicio}",
            headers={
                "Authorization": f"Bearer {HA_TOKEN}",
                "Content-Type":  "application/json"
            },
            json=datos or {},
            timeout=5
        )
        r.raise_for_status()
        print(f"[HA] {dominio}.{servicio} → OK")
        return True
    except Exception as e:
        print(f"[HA] Error en {dominio}.{servicio}: {e}")
        return False

def ha_get_contexto_resumido() -> dict:
    """
    Devuelve un resumen compacto del contexto para enviar a OpenClaw.
    Filtra entidades irrelevantes y acompaña con timestamp.
    """
    with contexto_lock:
        # Dominios relevantes para el contexto del avatar
        dominios_relevantes = {
            "light", "switch", "media_player", "alarm_control_panel",
            "person", "binary_sensor", "sensor", "climate", "calendar"
        }
        resumen = {}
        for entity_id, datos in contexto_ha.items():
            dominio = entity_id.split(".")[0]
            if dominio in dominios_relevantes:
                resumen[entity_id] = datos
        return resumen

# ── Riatla: publicar comandos al daemon ───────────────────────────────────────

_mqtt_client = None  # referencia al cliente MQTT para publicar

def riatla_enviar(topic_sufijo: str, payload: dict):
    """
    Publica un mensaje en riatla/<topic_sufijo> para que el daemon
    lo procese y lo reenvíe al renderer.js.

    Ejemplos:
        riatla_enviar("emocion", {"emocion": "happy", "duracion": 10})
        riatla_enviar("world",   {"mundo": "Studio"})
        riatla_enviar("objeto",  {"objeto": "libro", "accion": "add"})
        riatla_enviar("world/musica", {"estado": "on", "modo": "metal"})
    """
    if _mqtt_client is None:
        print("[Riatla] Cliente MQTT no disponible")
        return

    topic   = TOPIC_RIATLA.format(topic_sufijo)
    mensaje = json.dumps(payload)
    _mqtt_client.publish(topic, mensaje)
    print(f"[Riatla] → {topic}: {mensaje}")

# ── HTTP server: recibir decisiones de OpenClaw ────────────────────────────────

class OpenClawHandler(BaseHTTPRequestHandler):
    """
    Servidor HTTP mínimo que recibe las decisiones de OpenClaw.

    OpenClaw llama a este endpoint con un JSON que describe las acciones
    a ejecutar. El bridge las despacha a HA y/o al avatar.

    Formato esperado del payload de OpenClaw:
    {
        "acciones": [
            {
                "tipo": "riatla",
                "topic": "emocion",
                "datos": {"emocion": "happy", "duracion": 10}
            },
            {
                "tipo": "ha",
                "dominio": "light",
                "servicio": "turn_on",
                "datos": {"entity_id": "light.salon", "brightness": 200}
            }
        ]
    }
    """

    def log_message(self, format, *args):
        pass  # silenciar logs HTTP por defecto

    def do_GET(self):
        """
        Endpoint GET /contexto → devuelve el contexto HA actual a OpenClaw.
        OpenClaw lo consulta antes de tomar decisiones.
        """
        if self.path == "/contexto":
            contexto = ha_get_contexto_resumido()
            respuesta = json.dumps(contexto, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(respuesta)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """
        Endpoint POST /openclaw → recibe y ejecuta las decisiones de OpenClaw.
        """
        if self.path != "/openclaw":
            self.send_response(404)
            self.end_headers()
            return

        try:
            longitud = int(self.headers.get("Content-Length", 0))
            payload  = json.loads(self.rfile.read(longitud).decode("utf-8"))
            acciones = payload.get("acciones", [])

            resultados = []
            for accion in acciones:
                resultado = ejecutar_accion(accion)
                resultados.append(resultado)

            respuesta = json.dumps({"ok": True, "resultados": resultados}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(respuesta)

        except Exception as e:
            print(f"[Bridge] Error procesando POST: {e}")
            self.send_response(500)
            self.end_headers()

def ejecutar_accion(accion: dict) -> dict:
    """
    Despacha una acción a Riatla o a Home Assistant según su tipo.
    """
    tipo = accion.get("tipo", "")

    if tipo == "riatla":
        topic = accion.get("topic", "")
        datos = accion.get("datos", {})
        if topic and datos:
            riatla_enviar(topic, datos)
            return {"tipo": "riatla", "topic": topic, "ok": True}
        return {"tipo": "riatla", "ok": False, "error": "topic o datos vacíos"}

    elif tipo == "ha":
        dominio  = accion.get("dominio", "")
        servicio = accion.get("servicio", "")
        datos    = accion.get("datos", {})
        if dominio and servicio:
            ok = ha_llamar_servicio(dominio, servicio, datos)
            return {"tipo": "ha", "servicio": f"{dominio}.{servicio}", "ok": ok}
        return {"tipo": "ha", "ok": False, "error": "dominio o servicio vacíos"}

    return {"tipo": tipo, "ok": False, "error": "tipo desconocido"}

def iniciar_servidor_http():
    """Arranca el servidor HTTP en su propio hilo."""
    servidor = HTTPServer(("localhost", BRIDGE_PORT), OpenClawHandler)
    print(f"[Bridge] Escuchando en http://localhost:{BRIDGE_PORT}")
    print(f"[Bridge]   GET  /contexto   → estado HA para OpenClaw")
    print(f"[Bridge]   POST /openclaw   → ejecutar acciones de OpenClaw")
    servidor.serve_forever()

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _mqtt_client

    print("╔══════════════════════════════════╗")
    print("║    OpenClaw Bridge v0.1          ║")
    print("╚══════════════════════════════════╝")
    print(f"MQTT  → {MQTT_HOST}:{MQTT_PORT}")
    print(f"HA    → {HA_URL}")
    print(f"HTTP  → localhost:{BRIDGE_PORT}\n")

    # Servidor HTTP en hilo propio
    http_thread = threading.Thread(target=iniciar_servidor_http, daemon=True)
    http_thread.start()

    # Cliente MQTT
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    _mqtt_client = client  # exponer para riatla_enviar()

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[Bridge] Detenido.")

if __name__ == "__main__":
    main()