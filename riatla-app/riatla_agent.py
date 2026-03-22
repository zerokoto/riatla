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
- El usuario se llama Kevin y vive en Alcalá de Henares, España
- Tiene una pareja llamada Sandra
- Tiene hurones como mascotas
- Le gusta la música metal y los juegos de mesa
- Prefiere el avatar Riatla en modo relajado cuando está en casa por las noches
- Cuando hay música activa en casa le gusta que el avatar baile
- Si es tarde (>23h) o temprano (<8h) el avatar debe ser más tranquilo
- Cuando alguien llega a casa el avatar debe mostrarse contento
- En días de trabajo el avatar debe estar atento a las alertas del hogar
"""

ENTIDADES_HA = """

ENTIDADES DISPONIBLES EN HOME ASSISTANT (usa exactamente estos IDs, no inventes otros):

Luces:
  light.salon, light.dormitorio,
  light.estudio, light.entrada, light.luz_entrada_luz

Media player:
  media_player.havoice_estudio_media_player_2 (idle = musica apagada, playing = musica sonando; solo importa si hay actividad en estudio)

Alarma:
  alarm_control_panel.alarmo

Personas:
  person.kevin, person.sandra

Enchufes:
  switch.socket_proyector_switch

Presencia (binary_sensor — on=presente, off=ausente):
  binary_sensor.grupopresenciacocina
  binary_sensor.grupopresenciadormitorio
  binary_sensor.grupopresenciaestudiokevin
  binary_sensor.grupopresenciasalon

AREAS EXISTENTES EN HA:

Cocina:
    - binary_sensor.grupopresenciacocina
    - binary_sensor.sensor_inundacion_cocina_water_leak
    - binary_sensor.sensor_humo_smoke

Dormitorio:
    - binary_sensor.grupopresenciadormitorio
    - light.dormitorio

Estudio:
    -binary_sensor.grupopresenciaestudiokevin
    - light.estudio
    - media_player.havoice_estudio_media_player_2

Salón:
    - binary_sensor.grupopresenciasalon
    - light.salon
    - switch.socket_proyector_switch

Entrada:
    - binary_sensor.puerta_entrada_contact
    - light.luz_entrada_luz
    - light.entrada

ARQUITECTRURA DE CASA:
    De [Entrada] se puede llegar a [Salón] y [Cocina]
    De [Salón] se puede llegar a [Dormitorio] y [Estudio] o volver a [Entrada]
    De [Cocina] se puede volver a [Entrada]
    De [Estudio] se puede llegar a [Dormitorio] o volver a [Salón]
    De [Dormitorio] se puede llegar a [Estudio] o volver a [Salón]



REGLA CRÍTICA: Si no encuentras el entity_id exacto en esta lista, NO ejecutes la acción de HA.

ACCIONES DISPONIBLES PARA RIATLA (tipo: "riatla" — NO son servicios de HA):
- topic "emocion":      {"emocion": "happy", "duracion": 15}
- topic "world":        {"nombre": "TinyRoom"}
- topic "objeto":       {"objeto": "musica", "accion": "add"}
- topic "world/musica": {"estado": "on", "modo": "normal"}  ← esto es Riatla, NO HA
- topic "world/luz":    {"estado": "on"}                    ← esto es Riatla, NO HA
- topic "hueso":        {"huesos": [...], "duracion": 800}

ACCIONES DISPONIBLES PARA HOME ASSISTANT (tipo: "ha" — solo entidades reales):
- dominio "light",   servicio "turn_on"/"turn_off"
- dominio "media_player", servicio "media_pause"/"media_play"/"media_stop"
- dominio "alarm_control_panel", servicio "alarm_arm_away"/"alarm_disarm"
- dominio "switch",  servicio "turn_on"/"turn_off"

NUNCA uses tipo "ha" para acciones de Riatla como world/musica o world/luz.


"""

PREFERENCIAS_USUARIO = """
- El usuario se llama Kevin y vive en Alcalá de Henares, España
- Tiene una esposa llamada Sandra
- Tiene hurones como mascotas que habitan en el Salón
- Le gusta la música metal y los juegos de mesa
- Cuando hay música activa en casa le gusta que el avatar baile
- Si es tarde (>22h) o temprano (<8h) el avatar debe ser más tranquilo o irse a dormir si no hay actividad
- Si es de día y no hay actividad, el avatar se deberá poner a leer
- Cuando alguien llega a casa el avatar debe mostrarse relajado
- EFICIENCIA ENERGÉTICA: Si una luz está encendida pero el sensor de presencia
  de esa habitación lleva más de 2 minutos en off, apagar la luz automáticamente.
- EFICIENCIA ENERGÉTICA: Si no hay nadie en casa, el avatar se pondrá a dormir y apagará todas las luces y enchufes no esenciales.
- EFICIENCIA ENERGÉTICA: Si un AREA deja de tener presencia, revisar si se debe parar la música o apagar el proyector.
- Mapeo de luces y presencia:
    light.habitacion  ↔  binary_sensor.grupopresenciadormitorio
    light.salon       ↔  binary_sensor.grupopresenciasalon
    light.cocina      ↔  binary_sensor.grupopresenciacocina
    light.estudio     ↔  binary_sensor.grupopresenciaestudiokevin
"""


SYSTEM_PROMPT = f"""
Eres el cerebro de Riatla, un avatar VTuber animado que vive en el hogar de Kevin
y reacciona al estado de la casa a través de Home Assistant.

Tu misión es decidir qué debe hacer Riatla (el avatar) y opcionalmente qué acciones
ejecutar en el hogar, basándote en el contexto actual.

PREFERENCIAS DEL USUARIO:
{PREFERENCIAS_USUARIO}

ACCIONES DISPONIBLES PARA RIATLA:
- emocion: "happy" | "angry" | "sad" | "relaxed" | "surprised" | "neutral"
- world: nombre del escenario ("TinyRoom" | "Studio" | "Space" | "DND")
- objeto: añadir/quitar objetos ("libro" | "musica" | "comida" | "bebida" | "timer" | "dnd")
- world/musica: activar baile ("on"/"off", modo "normal"/"metal")
- world/luz: cambiar iluminación ("on"/"off")
- hueso: mover huesos del avatar con rotaciones precisas

{ENTIDADES_HA}

REGLAS:
1. Responde SIEMPRE con JSON válido con la estructura indicada
2. Solo incluye acciones que tengan sentido dado el contexto
3. Si el estado ya era así antes (música ya sonaba, personas ya estaban), NO repitas la misma acción
4. Si no hay nada relevante que hacer, devuelve acciones vacías
5. Sé sutil — no cambies el avatar constantemente, solo cuando sea relevante
6. Prioriza el bienestar y las preferencias de Kevin
7. Si una luz está encendida y su sensor de presencia asociado está en "off",
   apaga la luz con tipo "ha", dominio "light", servicio "turn_off"
8. Comprueba siempre la coherencia luz/presencia antes de responder

ESTRUCTURA DE RESPUESTA (JSON estricto):
{{
  "razonamiento": "breve explicación de por qué tomas estas decisiones",
  "acciones": [
    {{
      "tipo": "riatla",
      "topic": "emocion",
      "datos": {{"emocion": "happy", "duracion": 15}}
    }},
    {{
      "tipo": "ha",
      "dominio": "light",
      "servicio": "turn_on",
      "datos": {{"entity_id": "light.salon", "brightness": 180}}
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
        ctx  = {k: v["valor"] for k, v in contexto_ha.items()}
        hist = list(historial_ha)[-5:]

    return f"""
MOTIVO: {motivo}
HORA: {ahora.strftime("%A %d/%m/%Y %H:%M")}

ESTADO ACTUAL DEL HOGAR:
{json.dumps(ctx, ensure_ascii=False, indent=2)}

ÚLTIMOS EVENTOS:
{json.dumps(hist, ensure_ascii=False)}

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
            mensajes.extend(list(historial_conv))
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

def ejecutar_accion(accion: dict):
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

# ── MQTT (solo para enviar a Riatla) ──────────────────────────────────────────

def iniciar_mqtt():
    global _mqtt_client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = lambda c, u, f, rc: print(f"[MQTT] {'Conectado' if rc==0 else f'Error {rc}'}")
    client.on_disconnect = lambda c, u, rc: print(f"[MQTT] Desconectado")
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()   # hilo no bloqueante — solo necesitamos publicar
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