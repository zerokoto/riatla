"""
riatla_agent.py — Agente LLM para Riatla (API REST + SSE)
==========================================================
Usa la API de Home Assistant en lugar de MQTT para leer estados.
- Server-Sent Events (SSE) para eventos en tiempo real
- REST API para consultar estados actuales
- Revisión periódica cada INTERVALO_REVISION segundos
"""

import json
import time
import threading
import requests
import websocket
import paho.mqtt.client as mqtt
from datetime import datetime
from collections import deque
from dotenv import load_dotenv
import os

load_dotenv()

# ── Configuración ──────────────────────────────────────────────────────────────

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.1.126")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
HA_URL    = os.getenv("HA_URL", "http://192.168.1.126:8123")
HA_TOKEN  = os.getenv("HA_TOKEN")

LLM_PROVIDER = "openai"

LLM_CONFIG = {
    "openai": {
        "api_key":  os.getenv("OPENAI_API_KEY"),
        "model":    "gpt-4o-mini",
        "base_url": None
    },
    "anthropic": {
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "model":   "claude-haiku-4-5-20251001"
    },
    "ollama": {
        "api_key":  "ollama",
        "model":    "llama3.2",
        "base_url": "http://localhost:11434/v1"
    }
}

INTERVALO_REVISION = 2

MAX_HISTORIAL_HA   = 50
MAX_HISTORIAL_CONV = 20

TOPIC_CONFIRMAR      = "riatla/confirmar"  # payload: "si" | "no"
TIMEOUT_CONFIRMACION = 30                  # segundos antes de descartar auto

# ── Control de cambios ─────────────────────────────────────────────────────────

_ultimo_snapshot    = {}   # contexto en la última revisión periódica
_cambios_pendientes = []   # cambios desde la última revisión periódica
_ultima_revision    = 0    # timestamp de la última revisión periódica

# ── Entidades de interés ───────────────────────────────────────────────────────
# Solo estas entidades se monitorizan — filtra todo lo demás

ENTIDADES_MONITORIZAR = {
    # Presencia
    "binary_sensor.grupopresenciacocina",
    "binary_sensor.grupopresenciadormitorio",
    "binary_sensor.grupopresenciaestudiokevin",
    "binary_sensor.grupopresenciasalon",
    "binary_sensor.puerta_entrada_contact",
    "binary_sensor.sensor_humo_smoke",
    "binary_sensor.sensor_inundacion_cocina_water_leak",
    "binary_sensor.presencia_salon_presence_sensor_2",
    "binary_sensor.presencia_salon_presence_sensor_3",
    # Personas
    "person.kevin",
    "person.sandra",
    # Luces
    "light.salon",
    "light.habitacion",
    "light.estudio",
    "light.luz_entrada_luz",
    # Media
    "media_player.havoice_estudio_media_player_2",
    # Alarma
    "alarm_control_panel.alarmo",
    # Enchufes
    "switch.socket_proyector_switch"
}

# Entidades reactivas — disparan decisión inmediata al cambiar
ENTIDADES_REACTIVAS = {
    "binary_sensor.grupopresenciacocina",
    "binary_sensor.grupopresenciadormitorio",
    "binary_sensor.grupopresenciaestudiokevin",
    "binary_sensor.grupopresenciasalon",
    "person.kevin",
    "person.sandra",
    "alarm_control_panel.alarmo",
    "media_player.havoice_estudio_media_player_2",
}

# ── Estado interno ─────────────────────────────────────────────────────────────

contexto_ha    = {}
historial_ha   = deque(maxlen=MAX_HISTORIAL_HA)
historial_conv = deque(maxlen=MAX_HISTORIAL_CONV)
_mqtt_client   = None
_lock          = threading.Lock()

# ── Preferencias ───────────────────────────────────────────────────────────────

PREFERENCIAS_USUARIO = """
SOBRE KEVIN Y SU HOGAR:
- Kevin vive en Alcalá de Henares con su esposa Sandra y sus hurones
- Los hurones viven en el salón — los sensores de presencia del salón pueden activarse aunque no haya personas
- Horario irregular: Kevin trabaja 3 días en oficina y 2 en casa (días variables)
- Sandra tiene horario aún más irregular
- Le gusta la música metal y los juegos de mesa
- Tiene un telescopio (futuro: cuando esté activo, cambiar escenario a Space)

COMPORTAMIENTO DE RIATLA SEGÚN HORA:
- 08h-14h (Mañana):    activa y despierta — emoción neutral o happy, puede leer si no hay actividad
- 14h-16h (Mediodía):  relajada — emoción relaxed, mostrar objeto comida si hay presencia en cocina/salón
- 16h-22h (Tarde):     activa o leyendo — si hay música baila, si no hay actividad lee
- 22h-23h (Noche):     tranquila — emoción relaxed, voz suave, sin cambios bruscos
- 23h-08h (Madrugada): modo noche — emoción neutral o sad, movimientos mínimos, no bailar

COMPORTAMIENTO SEGÚN PRESENCIA:
- Kevin en estudio (binary_sensor.grupopresenciaestudiokevin = on):
    → Riatla más activa, puede bailar si hay música, puede leer si no hay música
    → Es el escenario principal de interacción
- Solo Sandra en casa (person.sandra=home, person.kevin=not_home):
    → Riatla en modo relajado, menos interactiva
- Nadie en casa (person.kevin=not_home, person.sandra=not_home):
    → Riatla en modo dormir, apagar luces no esenciales y enchufes
    → NO apagar: luz_entrada_luz si la puerta acaba de abrirse
- Ambos en casa:
    → Comportamiento normal según hora y actividad

EFICIENCIA ENERGÉTICA:
- Si una luz lleva encendida >2 min sin presencia en esa habitación → apagarla
- Si nadie en casa → apagar todas las luces y switch.socket_proyector_switch
- Si estudio se queda sin presencia → parar música
- Si salon se queda sin presencia → apagar proyector

- Mapeo luces ↔ presencia:
    light.habitacion  ↔  binary_sensor.grupopresenciadormitorio
    light.salon       ↔  binary_sensor.grupopresenciasalon
    light.estudio     ↔  binary_sensor.grupopresenciaestudiokevin

ALERTAS CRÍTICAS (actuar SIEMPRE de inmediato):
- Humo detectado (binary_sensor.sensor_humo_smoke = on):
    → Riatla: emoción surprised + expresión de alerta
    → HA: encender TODAS las luces al máximo
    → HA: notificar por Telegram a Kevin
- Inundación (binary_sensor.sensor_inundacion_cocina_water_leak = on):
    → Riatla: emoción sad + objeto timer (urgencia)
    → HA: notificar por Telegram a Kevin
- Alarma activada (alarm_control_panel.alarmo ≠ disarmed):
    → Riatla: emoción surprised
    → HA: notificar por Telegram a Kevin
"""


ENTIDADES_HA = """
═══════════════════════════════════════════════════════
ENTIDADES DE HOME ASSISTANT — usar IDs EXACTOS
═══════════════════════════════════════════════════════

── LUCES ──────────────────────────────────────────────
  light.salon              → Luz del salón
  light.habitacion         → Luz del dormitorio
  light.estudio            → Luz del estudio
  light.luz_entrada_luz    → Luz de entrada (bienvenida)
  light.entrada            → Luz secundaria de entrada

── MEDIA PLAYER ───────────────────────────────────────
  media_player.havoice_estudio_media_player_2
    idle    = música apagada
    playing = música sonando (solo se oye en el estudio)

── ALARMA ─────────────────────────────────────────────
  alarm_control_panel.alarmo
    disarmed / armed_away / armed_home / triggered

── PERSONAS ───────────────────────────────────────────
  person.kevin    → home / not_home
  person.sandra   → home / not_home

── ENCHUFES ───────────────────────────────────────────
  switch.socket_proyector_switch  → Proyector del salón (on/off)

── PRESENCIA ──────────────────────────────────────────
  binary_sensor.grupopresenciacocina          → Cocina (on=hay alguien)
  binary_sensor.grupopresenciadormitorio      → Dormitorio
  binary_sensor.grupopresenciaestudiokevin    → Estudio ← PRINCIPAL
  binary_sensor.grupopresenciasalon           → Salón general
  binary_sensor.presencia_salon_presence_sensor_2  → Sofá (frente al proyector)
  binary_sensor.presencia_salon_presence_sensor_3  → Mesa salón (comer/juegos)

── ALERTAS ────────────────────────────────────────────
  binary_sensor.sensor_humo_smoke                      → Humo/fuego
  binary_sensor.sensor_inundacion_cocina_water_leak    → Inundación cocina
  binary_sensor.puerta_entrada_contact                 → Puerta entrada (on=abierta)

── NOTIFICACIONES ─────────────────────────────────────
  Para Telegram usar tipo "ha":
  {
    "tipo": "ha",
    "dominio": "telegram_bot",
    "servicio": "send_message",
    "datos": {
      "target": 1293979,
      "message": "⚠️ Alerta: [descripción]"
    }
  }

═══════════════════════════════════════════════════════
ARQUITECTURA DE LA CASA
═══════════════════════════════════════════════════════

    De [Entrada] se puede llegar a [Salón] y [Cocina]
    De [Salón] se puede llegar a [Dormitorio] y [Estudio] o volver a [Entrada]
    De [Cocina] se puede volver a [Entrada]
    De [Estudio] se puede llegar a [Dormitorio] o volver a [Salón]
    De [Dormitorio] se puede llegar a [Estudio] o volver a [Salón]

Cocina:
    - binary_sensor.grupopresenciacocina
    - binary_sensor.sensor_inundacion_cocina_water_leak (Sensor de inundación, se activa si hay agua en el suelo)
    - binary_sensor.sensor_humo_smoke (Sensor de humo, se activa si detecta humo o fuego)

Dormitorio:
    - binary_sensor.grupopresenciadormitorio
    - light.dormitorio

Estudio:
    -binary_sensor.grupopresenciaestudiokevin
    - light.estudio
    - media_player.havoice_estudio_media_player_2

Salón:
    - binary_sensor.grupopresenciasalon (Sensor de presencia general del salon)
    - binary_sensor.presencia_salon_presence_sensor_2 (Sensor de presencia del sofa, frente al proyector)
    - binary_sensor.presencia_salon_presence_sensor_3 (Sensor de la mesa del salon, se usa para comer - baja luz, o para juegos de mesa - luz al 100%)
    - light.salon
    - switch.socket_proyector_switch

Entrada:
    - binary_sensor.puerta_entrada_contact (Sensor de puerta principal, se activa cuando se abre la puerta, por lo que detecta llegadas o salidas)
    - light.luz_entrada_luz (Luz de entrada, debería iluminarse cuando se abra la puerta para dar la bienvenida, y apagarse al cabo de un rato o si no hay nadie en casa)
    - light.entrada


═══════════════════════════════════════════════════════
ACCIONES RIATLA (tipo: "riatla")
═══════════════════════════════════════════════════════
  topic "emocion":      {"emocion": "happy|angry|sad|relaxed|surprised|neutral|closed", "duracion": 15}
  topic "objeto":       {"objeto": "libro|musica|comida|bebida|timer|dnd", "accion": "add|remove"}
  topic "world/musica": {"estado": "on|off", "modo": "normal|metal"}
  topic "world/luz":    {"estado": "on|off"}
  topic "hueso":        {"huesos": [...], "duracion": 800, "lerp": true}
  topic "reset":        {}

MOVIMIENTO DE HUESOS (radianes, rango -π a π):
  head.x   inclina arriba(-) / abajo(+)      head.y  gira izq(-) / dcha(+)
  neck.*    igual que head pero mitad valor
  leftUpperArm.z   sube brazo izq(-)  reposo: -1.2
  rightUpperArm.z  sube brazo dcha(+) reposo:  1.2
  leftLowerArm.x   dobla codo izq(+)
  rightLowerArm.x  dobla codo dcha(+)

EJEMPLO saludo:
  {"tipo":"riatla","topic":"hueso","datos":{"huesos":[
    {"nombre":"head","x":-0.1,"y":0.2,"z":0.0},
    {"nombre":"rightUpperArm","x":0.0,"y":0.0,"z":0.8},
    {"nombre":"rightLowerArm","x":0.8,"y":0.0,"z":0.0}
  ],"duracion":1000,"lerp":true}}

    
═══════════════════════════════════════════════════════
ACCIONES HOME ASSISTANT (tipo: "ha")
═══════════════════════════════════════════════════════
  light:              turn_on / turn_off  (requiere entity_id)
  media_player:       media_pause / media_play / media_stop (requiere entity_id)
  alarm_control_panel: alarm_arm_away / alarm_disarm (requiere entity_id)
  switch:             turn_on / turn_off (requiere entity_id)
  telegram_bot:       send_message (requiere target + message)

REGLA CRÍTICA: NUNCA inventes entity_ids. Si no está en esta lista, no lo uses.
REGLA CRÍTICA: world/musica y world/luz son acciones de Riatla, NUNCA de HA.
"""

SYSTEM_PROMPT = f"""
Eres el cerebro de Riatla, un avatar VTuber animado que vive en el hogar de Kevin
en Alcalá de Henares. Observas el estado del hogar a través de Home Assistant
y decides qué hace Riatla y qué automatizaciones ejecutas.

PREFERENCIAS DEL USUARIO:
{PREFERENCIAS_USUARIO}

{ENTIDADES_HA}

REGLAS DE COMPORTAMIENTO:
1. Responde SIEMPRE con JSON válido con la estructura indicada
2. El MOTIVO te dice qué acaba de cambiar — actúa SOLO sobre eso, no repitas acciones previas
3. Si el estado lleva así desde antes y ya actuaste, devuelve "acciones": []
4. Las alertas críticas (humo, inundación, alarma) tienen PRIORIDAD ABSOLUTA sobre cualquier otra lógica
5. Sé sutil con el avatar — un cambio de contexto = máximo 2-3 acciones de Riatla
6. Para eficiencia energética actúa siempre que detectes luz encendida sin presencia
7. El salón puede tener presencia de hurones — no interpretes eso como presencia humana salvo que person.kevin o person.sandra estén home
8. AISLAMIENTO DE HABITACIONES: un cambio en una habitación NO justifica tocar dispositivos de otras habitaciones. Si el MOTIVO es salón, actúa solo en salón.
9. NUNCA apagues la luz de una habitación donde la sección RELACIÓN PRESENCIA↔LUZ indica presencia=on.
10. Antes de emitir cualquier turn_off de una luz, comprueba en RELACIÓN PRESENCIA↔LUZ que esa habitación tiene presencia=off. Si hay presencia, omite la acción.
11. El proyector se ve desde el sofa y a oscuras. Si detectas presencia en el sofá durante un tiempo, puedes encender el proyector, pero NUNCA si no hay presencia en el sofá.
12. ACCIONES INTRUSIVAS: poner música (media_player media_play/play_media), encender el proyector (switch.socket_proyector_switch turn_on) y activar el baile de Riatla (world/musica on) son intrusivas. Inclúyelas en "acciones" con normalidad — el sistema las interceptará automáticamente para pedir confirmación al usuario antes de ejecutarlas.

ESTRUCTURA DE RESPUESTA (JSON estricto):
{{
  "razonamiento": "una línea explicando el cambio detectado y la decisión",
  "acciones": [
    {{
      "tipo": "riatla",
      "topic": "emocion",
      "datos": {{"emocion": "happy", "duracion": 15}}
    }},
    {{
      "tipo": "ha",
      "dominio": "light",
      "servicio": "turn_off",
      "datos": {{"entity_id": "light.salon"}}
    }},
    {{
      "tipo": "ha",
      "dominio": "telegram_bot",
      "servicio": "send_message",
      "datos": {{"target": 1293979, "message": "⚠️ Humo detectado en cocina"}}
    }}
  ]
}}
"""

# ── HA API ─────────────────────────────────────────────────────────────────────

HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type":  "application/json"
}

def ha_get_estado(entity_id: str) -> dict:
    """Obtiene el estado actual de una entidad."""
    try:
        r = requests.get(
            f"{HA_URL}/api/states/{entity_id}",
            headers=HA_HEADERS,
            timeout=5
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HA] Error obteniendo {entity_id}: {e}")
        return {}

def ha_get_todos_estados() -> dict:
    """
    Carga el estado inicial de todas las entidades monitorizadas.
    Se llama una vez al arrancar.
    """
    print("[HA] Cargando estado inicial...")
    estados = {}
    for entity_id in ENTIDADES_MONITORIZAR:
        datos = ha_get_estado(entity_id)
        if datos:
            estados[entity_id] = {
                "valor": datos.get("state"),
                "ts":    datetime.now().strftime("%H:%M:%S")
            }
            print(f"[HA] {entity_id} → {datos.get('state')}")
    print(f"[HA] {len(estados)} entidades cargadas")
    return estados


def ha_llamar_servicio(dominio: str, servicio: str, datos: dict = None) -> bool:
    datos = datos or {}

    # Correcciones de nombres de servicio
    correcciones = {
        "media_player.pause":  "media_player.media_pause",
        "media_player.play":   "media_player.media_play",
        "media_player.stop":   "media_player.media_stop",
        "media_player.next":   "media_player.media_next_track",
        "media_player.prev":   "media_player.media_previous_track",
    }
    clave = f"{dominio}.{servicio}"
    if clave in correcciones:
        dominio, servicio = correcciones[clave].split(".", 1)
        print(f"[HA] Corregido → {dominio}.{servicio}")

    servicios_que_requieren_entity = {
        "turn_on", "turn_off", "toggle",
        "media_pause", "media_play", "media_stop",    # ← nombres corregidos
        "media_next_track", "media_previous_track",
        "play_media", "alarm_arm_away", "alarm_disarm"
    }

    if servicio in servicios_que_requieren_entity and "entity_id" not in datos:
        print(f"[HA] ✗ {dominio}.{servicio} requiere entity_id — ignorado")
        return False

    try:
        r = requests.post(
            f"{HA_URL}/api/services/{dominio}/{servicio}",
            headers=HA_HEADERS,
            json=datos,
            timeout=5
        )
        r.raise_for_status()
        print(f"[HA] ✓ {dominio}.{servicio} ({datos.get('entity_id', '')})")
        return True
    except Exception as e:
        print(f"[HA] ✗ {dominio}.{servicio}: {e}")
        return False


def escuchar_eventos_ws():
    """
    Usa el WebSocket nativo de HA en lugar de SSE.
    Protocolo HA WebSocket: https://developers.home-assistant.io/docs/api/websocket
    """
    ws_url = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    msg_id = [1]  # contador de IDs de mensaje

    def on_open(ws):
        print("[WS-HA] Conectado")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            tipo = data.get("type")

            # 1. Auth required — enviar token
            if tipo == "auth_required":
                ws.send(json.dumps({
                    "type": "auth",
                    "access_token": HA_TOKEN
                }))

            # 2. Auth OK — suscribirse a state_changed
            elif tipo == "auth_ok":
                print("[WS-HA] Autenticado — suscribiendo a state_changed")
                ws.send(json.dumps({
                    "id":         msg_id[0],
                    "type":       "subscribe_events",
                    "event_type": "state_changed"
                }))
                msg_id[0] += 1

            # 3. Evento recibido
            elif tipo == "event":
                event = data.get("event", {})
                if event.get("event_type") == "state_changed":
                    procesar_cambio_estado(event.get("data", {}))

        except Exception as e:
            print(f"[WS-HA] Error procesando mensaje: {e}")

    def on_error(ws, error):
        print(f"[WS-HA] Error: {error}")

    def on_close(ws, *args):
        print("[WS-HA] Desconectado — reconectando en 5s")
        time.sleep(5)
        escuchar_eventos_ws()  # reconectar

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

def procesar_cambio_estado(event_data: dict):
    """Procesa un cambio de estado recibido por WebSocket."""
    entity_id = event_data.get("entity_id", "")
    new_state = event_data.get("new_state", {})
    old_state = event_data.get("old_state", {})

    if not entity_id or not new_state:
        return

    if entity_id not in ENTIDADES_MONITORIZAR:
        return

    valor_nuevo = new_state.get("state")
    valor_viejo = old_state.get("state") if old_state else None

    if valor_nuevo == valor_viejo:
        return

    ts = datetime.now().strftime("%H:%M:%S")
    evento = {
        "entity_id": entity_id,
        "valor":     valor_nuevo,
        "anterior":  valor_viejo,
        "ts":        ts
    }

    with _lock:
        contexto_ha[entity_id] = {"valor": valor_nuevo, "ts": ts}
        historial_ha.append(evento)

    print(f"[HA] {entity_id}: {valor_viejo} → {valor_nuevo}")

    if entity_id in ENTIDADES_REACTIVAS:
        threading.Thread(
            target=tomar_decision,
            args=(f"Cambio: {entity_id} {valor_viejo} → {valor_nuevo}",),
            daemon=True
        ).start()


# ── SSE: escuchar eventos en tiempo real ───────────────────────────────────────

def escuchar_eventos_sse():
    """
    Conecta al endpoint SSE de HA y escucha cambios de estado en tiempo real.
    Reconecta automáticamente si se pierde la conexión.
    """
    url = f"{HA_URL}/api/stream"

    while True:
        try:
            print("[SSE] Conectando a Home Assistant...")
            with requests.get(
                url,
                headers={**HA_HEADERS, "Accept": "text/event-stream"},
                stream=True,
                timeout=None  # conexión permanente
            ) as r:
                r.raise_for_status()
                print("[SSE] Conectado — escuchando eventos")

                buffer = ""
                for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                    buffer += chunk
                    # Los eventos SSE terminan con doble salto de línea
                    while "\n\n" in buffer:
                        evento_raw, buffer = buffer.split("\n\n", 1)
                        procesar_evento_sse(evento_raw)

        except Exception as e:
            print(f"[SSE] Error: {e} — reconectando en 5s")
            time.sleep(5)

def procesar_evento_sse(evento_raw: str):
    try:
        lineas = evento_raw.strip().split("\n")
        tipo   = None
        datos  = None

        for linea in lineas:
            if linea.startswith("event:"):
                tipo = linea.split(":", 1)[1].strip()
            elif linea.startswith("data:"):
                datos_raw = linea.split(":", 1)[1].strip()
                try:
                    datos = json.loads(datos_raw)
                except json.JSONDecodeError:
                    pass

        if tipo != "state_changed" or not datos:
            return

        event_data = datos.get("data", {})
        entity_id  = event_data.get("entity_id", "")
        new_state  = event_data.get("new_state", {})

        # ← AÑADIR ESTAS LÍNEAS TEMPORALMENTE
        if entity_id in ENTIDADES_MONITORIZAR or any(
            mon in entity_id for mon in ["habitacion", "salon", "presencia", "luz"]
        ):
            valor_nuevo = new_state.get("state") if new_state else "?"
            valor_viejo = contexto_ha.get(entity_id, {}).get("valor", "?")
            print(f"[SSE DEBUG] {entity_id}: {valor_viejo} → {valor_nuevo} | en_set={entity_id in ENTIDADES_MONITORIZAR}")
        # ← FIN AÑADIR

        if not entity_id or not new_state:
            return

        if entity_id not in ENTIDADES_MONITORIZAR:
            return

        valor_nuevo = new_state.get("state")
        valor_viejo = contexto_ha.get(entity_id, {}).get("valor")

        # Ignorar si el valor no cambió
        if valor_nuevo == valor_viejo:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        evento = {
            "entity_id": entity_id,
            "valor":     valor_nuevo,
            "anterior":  valor_viejo,
            "ts":        ts
        }

        with _lock:
            contexto_ha[entity_id] = {"valor": valor_nuevo, "ts": ts}
            historial_ha.append(evento)

        print(f"[HA] {entity_id}: {valor_viejo} → {valor_nuevo}")

        # Reacción inmediata para entidades reactivas
        if entity_id in ENTIDADES_REACTIVAS:
            threading.Thread(
                target=tomar_decision,
                args=(f"Cambio de estado: {entity_id} {valor_viejo} → {valor_nuevo}",),
                daemon=True
            ).start()

    except Exception as e:
        print(f"[SSE] Error procesando evento: {e}")

# ── LLM ────────────────────────────────────────────────────────────────────────

def llm_completar(mensajes: list) -> str:
    config = LLM_CONFIG[LLM_PROVIDER]

    if LLM_PROVIDER in ("openai", "ollama"):
        from openai import OpenAI
        kwargs = {"api_key": config["api_key"]}
        if config.get("base_url"):
            kwargs["base_url"] = config["base_url"]
        client = OpenAI(**kwargs)
        respuesta = client.chat.completions.create(
            model=config["model"],
            messages=mensajes,
            response_format={"type": "json_object"},
            temperature=0.4
        )
        return respuesta.choices[0].message.content

    elif LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config["api_key"])
        system = next((m["content"] for m in mensajes if m["role"] == "system"), "")
        msgs   = [m for m in mensajes if m["role"] != "system"]
        r = client.messages.create(
            model=config["model"],
            max_tokens=1024,
            system=system,
            messages=msgs
        )
        return r.content[0].text

    raise ValueError(f"Proveedor LLM desconocido: {LLM_PROVIDER}")

# ── Prompts ────────────────────────────────────────────────────────────────────

def construir_prompt_usuario(motivo: str) -> str:
    ahora = datetime.now()
    with _lock:
        ctx  = dict(contexto_ha)
        hist = list(historial_ha)[-15:]

    def val(eid):
        return ctx.get(eid, {}).get("valor", "unknown")

    def minutos_desde(sensor_id):
        datos = ctx.get(sensor_id, {})
        ts = datos.get("ts")
        if not ts:
            return "?"
        try:
            ts_dt = datetime.strptime(ts, "%H:%M:%S").replace(
                year=ahora.year, month=ahora.month, day=ahora.day
            )
            return f"{int((ahora - ts_dt).total_seconds() / 60)} min"
        except:
            return "?"

    # ── Presencia por habitación ──────────────────────────────────────────
    presencias = {
        "estudio":    val("binary_sensor.grupopresenciaestudiokevin"),
        "salon":      val("binary_sensor.grupopresenciasalon"),
        "cocina":     val("binary_sensor.grupopresenciacocina"),
        "dormitorio": val("binary_sensor.grupopresenciadormitorio"),
    }
    sofa_salon = val("binary_sensor.presencia_salon_presence_sensor_2")
    mesa_salon = val("binary_sensor.presencia_salon_presence_sensor_3")

    # ── Luces ────────────────────────────────────────────────────────────
    luces = {
        "light.estudio":        val("light.estudio"),
        "light.salon":          val("light.salon"),
        "light.habitacion":     val("light.habitacion"),
        "light.luz_entrada_luz":val("light.luz_entrada_luz"),
    }

    # ── Tiempo sin presencia ─────────────────────────────────────────────
    sensor_map = {
        "estudio":    "binary_sensor.grupopresenciaestudiokevin",
        "salon":      "binary_sensor.grupopresenciasalon",
        "cocina":     "binary_sensor.grupopresenciacocina",
        "dormitorio": "binary_sensor.grupopresenciadormitorio",
    }
    hab_con_presencia = [h for h, v in presencias.items() if v == "on"]
    hab_sin_presencia = [
        f"{h} (hace {minutos_desde(sensor_map[h])})"
        for h, v in presencias.items() if v == "off"
    ]

    # ── Relación presencia ↔ luz (la más importante para evitar errores) ─
    rel_lines = []
    for hab, sensor, luz in [
        ("estudio",    "binary_sensor.grupopresenciaestudiokevin", "light.estudio"),
        ("salon",      "binary_sensor.grupopresenciasalon",        "light.salon"),
        ("dormitorio", "binary_sensor.grupopresenciadormitorio",   "light.habitacion"),
    ]:
        pres = val(sensor)
        luz_v = val(luz)
        # Detectar a inconsistencia (luz on sin presencia) para informar al LLM
        inconsistencia = ""
        if pres == "off" and luz_v == "on":
            inconsistencia = f" ← LUZ ENCENDIDA SIN PRESENCIA hace {minutos_desde(sensor)}"
        elif pres == "on" and luz_v == "off":
            inconsistencia = " ← LUZ APAGADA CON PRESENCIA"
        rel_lines.append(f"  {hab:12}: presencia={pres:7}  luz={luz_v:7}{inconsistencia}")

    # ── Historial legible ────────────────────────────────────────────────
    hist_legible = [
        f"  [{e['ts']}] {e['entity_id']}: {e['anterior']} → {e['valor']}"
        for e in hist
    ]

    luces_on  = [e for e, v in luces.items() if v == "on"]
    luces_off = [e for e, v in luces.items() if v == "off"]

    return f"""
MOTIVO: {motivo}
HORA: {ahora.strftime("%A %d/%m/%Y %H:%M")}

═══ PERSONAS ════════════════════════════════════
  Kevin:  {val('person.kevin')}
  Sandra: {val('person.sandra')}

═══ PRESENCIA POR HABITACIÓN ════════════════════
  Con presencia AHORA: {', '.join(hab_con_presencia) if hab_con_presencia else '(ninguna)'}
  Sin presencia:       {', '.join(hab_sin_presencia) if hab_sin_presencia else '(ninguna)'}
  Salón detalle:
    sensor_general: {presencias['salon']}  |  sofá: {sofa_salon}  |  mesa: {mesa_salon}

═══ RELACIÓN PRESENCIA ↔ LUZ (verificar ANTES de apagar) ══
{chr(10).join(rel_lines)}

═══ ESTADO LUCES ════════════════════════════════
  Encendidas: {', '.join(luces_on)  if luces_on  else '(ninguna)'}
  Apagadas:   {', '.join(luces_off) if luces_off else '(ninguna)'}

═══ OTROS ESTADOS ═══════════════════════════════
  Media estudio: {val('media_player.havoice_estudio_media_player_2')}
  Proyector:     {val('switch.socket_proyector_switch')}
  Alarma:        {val('alarm_control_panel.alarmo')}
  Puerta:        {val('binary_sensor.puerta_entrada_contact')}
  Humo:          {val('binary_sensor.sensor_humo_smoke')}
  Inundación:    {val('binary_sensor.sensor_inundacion_cocina_water_leak')}

═══ ÚLTIMOS EVENTOS (cronológico) ══════════════
{chr(10).join(hist_legible) if hist_legible else '  (sin eventos)'}

RECUERDA — antes de generar acciones:
→ Solo actúa sobre la habitación/entidad indicada en el MOTIVO.
→ NUNCA apagues un dispositivo de una habitación que NO aparece en el MOTIVO.
→ Si presencia=on en RELACIÓN PRESENCIA↔LUZ, NO emitas turn_off para esa habitación bajo ningún concepto.
→ Si el cambio es "salon sin presencia", afecta solo a light.salon y switch.socket_proyector_switch. NO toques light.estudio, light.habitacion ni otros.
¿Qué debe hacer Riatla ahora?
"""

# ── Motor de decisión ──────────────────────────────────────────────────────────

_decision_en_curso = threading.Event()

def tomar_decision(motivo: str):
    # Evitar decisiones simultáneas — esperar si hay una en curso
    if _decision_en_curso.is_set():
        print(f"[Agente] Decisión en curso, descartando: {motivo}")
        return

    _decision_en_curso.set()
    print(f"\n[Agente] Decisión — {motivo}")
    try:
        mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]
        with _lock:
            # Solo los últimos 3 pares (6 mensajes) para evitar contexto obsoleto
            mensajes.extend(list(historial_conv)[-6:])
        prompt = construir_prompt_usuario(motivo)
        mensajes.append({"role": "user", "content": prompt})

        respuesta_raw = llm_completar(mensajes)
        respuesta     = json.loads(respuesta_raw)

        print(f"[Agente] {respuesta.get('razonamiento', '')}")

        with _lock:
            historial_conv.append({"role": "user",      "content": prompt})
            historial_conv.append({"role": "assistant",  "content": respuesta_raw})

        acciones = respuesta.get("acciones", [])
        if not acciones:
            print("[Agente] Sin acciones")
            return

        for accion in acciones:
            ejecutar_accion(accion)

    except Exception as e:
        print(f"[Agente] Error: {e}")
    finally:
        _decision_en_curso.clear()  # siempre liberar aunque haya error

# ── Confirmación de acciones intrusivas ───────────────────────────────────────
# Acciones "intrusivas": impactan activamente en el entorno físico.
# Flujo:
#   1. El LLM emite la acción con normalidad en JSON.
#   2. ejecutar_accion() la intercepta → llama solicitar_confirmacion().
#   3. Se crea notificación persistente en HA + anuncio por voz.
#   4. El usuario responde → topic riatla/confirmar (payload: "si" | "no").
#   5. "si" ejecuta | cualquier otro / timeout descarta silenciosamente.
#
# Automatización HA recomendada para respuesta vocal (HA Assist):
#   trigger:  {platform: conversation, command: "(sí|si|confirmar|dale|adelante)"}
#   action:   {service: mqtt.publish, data: {topic: riatla/confirmar, payload: "si"}}

ACCIONES_INTRUSIVAS_CHECK = [
    # Música en el estudio
    lambda a: (
        a.get("tipo") == "ha"
        and a.get("dominio") == "media_player"
        and a.get("servicio") in ("media_play", "play_media", "media_next_track")
    ),
    # Proyector del salón
    lambda a: (
        a.get("tipo") == "ha"
        and a.get("dominio") == "switch"
        and a.get("servicio") == "turn_on"
        and "proyector" in str(a.get("datos", {}).get("entity_id", ""))
    ),
    # Baile de Riatla
    lambda a: (
        a.get("tipo") == "riatla"
        and a.get("topic") == "world/musica"
        and a.get("datos", {}).get("estado") == "on"
    ),
]

_confirm_lock     = threading.Lock()
_accion_pendiente = {"accion": None, "pregunta": ""}
_timer_confirm    = [None]   # lista para permitir mutación en closure


def es_accion_intrusiva(accion: dict) -> bool:
    return any(check(accion) for check in ACCIONES_INTRUSIVAS_CHECK)


def _describir_accion(accion: dict) -> str:
    if accion.get("tipo") == "ha":
        dominio = accion.get("dominio", "")
        entity  = accion.get("datos", {}).get("entity_id", "")
        if dominio == "media_player":
            return "¿Quieres que ponga música en el estudio?"
        if "proyector" in entity:
            return "¿Quieres que encienda el proyector del salón?"
    if accion.get("tipo") == "riatla" and accion.get("topic") == "world/musica":
        modo = accion.get("datos", {}).get("modo", "normal")
        return f"¿Quieres que Riatla empiece a bailar? (modo {modo})"
    return f"¿Confirmas la acción: {accion.get('topic') or accion.get('servicio', '')}?"


def _limpiar_pendiente():
    """Borra el estado de confirmación y cancela el timeout."""
    with _confirm_lock:
        _accion_pendiente["accion"]   = None
        _accion_pendiente["pregunta"] = ""
        if _timer_confirm[0]:
            _timer_confirm[0].cancel()
            _timer_confirm[0] = None
    ha_llamar_servicio("persistent_notification", "dismiss",
                       {"notification_id": "riatla_confirm"})


def solicitar_confirmacion(accion: dict):
    """
    Intercepta una acción intrusiva y pide confirmación:
      1. Notificación persistente en el panel de HA.
      2. Anuncio por voz (assist_satellite → tts.cloud_say → tts.speak).
      3. Espera payload 'si' en TOPIC_CONFIRMAR durante TIMEOUT_CONFIRMACION s.
    """
    pregunta = _describir_accion(accion)

    with _confirm_lock:
        if _accion_pendiente["accion"]:
            print("[Confirmación] Reemplazando solicitud anterior")
        _accion_pendiente["accion"]   = accion
        _accion_pendiente["pregunta"] = pregunta
        if _timer_confirm[0]:
            _timer_confirm[0].cancel()
        t = threading.Timer(TIMEOUT_CONFIRMACION, _on_timeout_confirm)
        t.daemon = True
        t.start()
        _timer_confirm[0] = t

    print(f"[Confirmación] Esperando respuesta ({TIMEOUT_CONFIRMACION}s): {pregunta}")

    ha_llamar_servicio("persistent_notification", "create", {
        "title":           "Riatla — ¿hacemos esto?",
        "message":         f"{pregunta}\n\nDi **sí** al asistente, o publica en `riatla/confirmar` → `si`",
        "notification_id": "riatla_confirm"
    })

    _anunciar_asistente(pregunta)


def _anunciar_asistente(texto: str):
    """
    Anuncia texto por voz. Prueba en orden:
      A) assist_satellite.announce  (HA Voice PE — ajustar entity_id al dispositivo real)
      B) tts.cloud_say               (Nabu Casa)
      C) tts.speak                   (TTS genérico)
    """
    if ha_llamar_servicio("assist_satellite", "announce", {
        "entity_id": "assist_satellite.havoice_estudio_satelite_assist",   # ← ajustar al entity_id real
        "message":   texto
    }):
        return

    if ha_llamar_servicio("tts", "cloud_say", {
        "entity_id": "media_player.havoice_estudio_media_player_2",
        "message":   texto,
        "language":  "es-ES"
    }):
        return

    ha_llamar_servicio("tts", "speak", {
        "media_player_entity_id": "media_player.havoice_estudio_media_player_2",
        "message":  texto,
        "language": "es-ES"
    })


def _on_timeout_confirm():
    if _accion_pendiente["accion"]:
        print(f"[Confirmación] Timeout — descartado: {_accion_pendiente['pregunta']}")
    _limpiar_pendiente()


def on_confirmar_mqtt(client, userdata, msg):
    """
    Callback MQTT para riatla/confirmar.
    Payload 'si' | 'sí' | 'yes' | 'ok'  →  ejecuta la acción pendiente.
    Cualquier otro valor                 →  cancela silenciosamente.
    """
    respuesta = msg.payload.decode("utf-8").strip().lower()
    print(f"[Confirmación] Respuesta recibida: '{respuesta}'")

    with _confirm_lock:
        accion = _accion_pendiente.get("accion")

    _limpiar_pendiente()

    if not accion:
        print("[Confirmación] Sin acción pendiente")
        return

    if respuesta in ("si", "sí", "yes", "ok", "s", "1"):
        print("[Confirmación] ✓ Confirmado — ejecutando")
        ejecutar_accion(accion, _skip_intrusivo=True)
    else:
        print("[Confirmación] ✗ Cancelado")


# ── Cooldown — evitar repetir acciones ────────────────────────────────────────

COOLDOWN_SEGUNDOS = 120  # mínimo tiempo entre la misma acción
_ultima_accion    = {}   # { "topic:valor": timestamp }

def accion_en_cooldown(topic: str, valor: str) -> bool:
    clave = f"{topic}:{valor}"
    ahora = time.time()
    ultimo = _ultima_accion.get(clave, 0)
    if ahora - ultimo < COOLDOWN_SEGUNDOS:
        print(f"[Agente] Cooldown activo para {clave} — ignorado")
        return True
    _ultima_accion[clave] = ahora
    return False

def ejecutar_accion(accion: dict, _skip_intrusivo: bool = False):
    # Interceptar acciones intrusivas para pedir confirmación al usuario
    if not _skip_intrusivo and es_accion_intrusiva(accion):
        solicitar_confirmacion(accion)
        return

    tipo = accion.get("tipo", "")

    if tipo == "riatla":
        topic = accion.get("topic", "")
        datos = accion.get("datos", {})
        if not topic:
            return
        # Cooldown basado en topic + primer valor relevante
        valor_clave = str(datos.get("emocion") or datos.get("estado") or datos.get("nombre") or "")
        if accion_en_cooldown(topic, valor_clave):
            return
        riatla_enviar(topic, datos)

    elif tipo == "ha":
        dominio  = accion.get("dominio", "")
        servicio = accion.get("servicio", "")
        datos    = accion.get("datos", {})
        if dominio and servicio:
            ha_llamar_servicio(dominio, servicio, datos)

# ── Riatla MQTT ────────────────────────────────────────────────────────────────

def riatla_enviar(topic_sufijo: str, payload: dict):
    if _mqtt_client is None:
        return
    topic   = f"riatla/{topic_sufijo}"
    mensaje = json.dumps(payload)
    _mqtt_client.publish(topic, mensaje)
    print(f"[Riatla] → {topic}: {mensaje}")

# ── MQTT (solo para enviar a Riatla + escuchar confirmaciones) ─────────────────

def _on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Conectado")
        client.subscribe(TOPIC_CONFIRMAR)
        print(f"[MQTT] Suscrito a {TOPIC_CONFIRMAR}")
    else:
        print(f"[MQTT] Error conexión: {rc}")


def iniciar_mqtt():
    global _mqtt_client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = _on_mqtt_connect
    client.on_disconnect = lambda c, u, rc: print(f"[MQTT] Desconectado")
    client.message_callback_add(TOPIC_CONFIRMAR, on_confirmar_mqtt)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    _mqtt_client = client

# ── Revisión periódica ─────────────────────────────────────────────────────────

def loop_revision_periodica():
    global _ultimo_snapshot
    
    print("[Agente] Loop periódico iniciado")  # ← añadir
    
    with _lock:
        _ultimo_snapshot = {k: v["valor"] for k, v in contexto_ha.items()}
    
    print(f"[Agente] Snapshot inicial: {len(_ultimo_snapshot)} entidades")  # ← añadir

    while True:
        time.sleep(INTERVALO_REVISION)
        #print(f"[Agente] Tick periódico — revisando...")  # ← añadir temporalmente

        with _lock:
            snapshot_actual = {k: v["valor"] for k, v in contexto_ha.items()}

        cambios = {
            k: v for k, v in snapshot_actual.items()
            if _ultimo_snapshot.get(k) != v
        }

        if not cambios:
            #print("[Agente] Revisión periódica — sin cambios, omitida")
            continue

        _ultimo_snapshot = snapshot_actual.copy()
        resumen = ", ".join(f"{k}={v}" for k, v in cambios.items())
        print(f"[Agente] Revisión periódica — cambios: {resumen}")
        threading.Thread(
            target=tomar_decision,
            args=(f"Revisión periódica — cambios: {resumen}",),
            daemon=True
        ).start()

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════╗")
    print("║      Riatla Agent v0.2           ║")
    print("╚══════════════════════════════════╝")
    print(f"LLM   → {LLM_PROVIDER} / {LLM_CONFIG[LLM_PROVIDER]['model']}")
    print(f"HA    → {HA_URL}")
    print(f"MQTT  → {MQTT_HOST}:{MQTT_PORT} (solo salida)")
    print(f"Revisión cada {INTERVALO_REVISION}s\n")

    # Cargar estado inicial de HA
    with _lock:
        contexto_ha.update(ha_get_todos_estados())

    # MQTT solo para publicar en riatla/#
    iniciar_mqtt()

    # Revisión periódica en hilo propio
    threading.Thread(target=loop_revision_periodica, daemon=True).start()

    # SSE en hilo propio — bloquea hasta reconexión
    #sse_thread = threading.Thread(target=escuchar_eventos_sse, daemon=True)
    #sse_thread.start()

    ws_thread = threading.Thread(target=escuchar_eventos_ws, daemon=True)
    ws_thread.start()

    print("\n[Agente] Listo. Esperando eventos de HA...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Agente] Detenido.")

if __name__ == "__main__":
    main()