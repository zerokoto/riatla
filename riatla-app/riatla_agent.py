"""
riatla_agent.py — Agente LLM para Riatla
=========================================
Agente autónomo que observa Home Assistant y decide qué hacer
con el avatar Riatla y con el hogar.

Modos de operación:
  - Reactivo:   actúa cuando llega un evento relevante de HA via MQTT
  - Periódico:  revisa el contexto cada INTERVALO_REVISION segundos

Proveedores LLM soportados (cambiar LLM_PROVIDER):
  - "openai"    → GPT-4o, GPT-4o-mini
  - "anthropic" → Claude Sonnet, Haiku
  - "ollama"    → modelos locales (llama3, mistral...)

Dependencias:
    pip install paho-mqtt openai anthropic requests
"""

import json
import time
import threading
import requests
import paho.mqtt.client as mqtt
from datetime import datetime
from collections import deque

# ── Configuración ──────────────────────────────────────────────────────────────

MQTT_HOST = "192.168.1.126"
MQTT_PORT = 1883
MQTT_USER = "meshmqtt"
MQTT_PASS = "m3sq77"

HA_URL   = "http://192.168.1.126:8123"
HA_TOKEN =
# ── Configuración LLM ──────────────────────────────────────────────────────────
# Cambiar LLM_PROVIDER para cambiar de proveedor sin tocar nada más

LLM_PROVIDER = "openai"   # "openai" | "anthropic" | "ollama"

LLM_CONFIG = {
    "openai": {
        "api_key": "sk-...",
        "model":   "gpt-4o-mini",   # o "gpt-4o" para más capacidad
        "base_url": None            # None = default OpenAI
    },
    "anthropic": {
        "api_key": "sk-ant-...",
        "model":   "claude-haiku-4-5-20251001"  # o claude-sonnet-4-6
    },
    "ollama": {
        "api_key": "ollama",        # ollama no necesita key real
        "model":   "llama3.2",
        "base_url": "http://localhost:11434/v1"  # ollama usa API compatible OpenAI
    }
}

INTERVALO_REVISION = 300   # segundos entre revisiones periódicas (5 min)
MAX_HISTORIAL_HA   = 50    # eventos HA a recordar
MAX_HISTORIAL_CONV = 20    # turnos de conversación a recordar

# ── Preferencias del usuario (hardcodeadas) ────────────────────────────────────

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

# ── Topics MQTT ────────────────────────────────────────────────────────────────

TOPIC_HA_ALL  = "homeassistant/#"
TOPIC_RIATLA  = "riatla/{}"

# Eventos de HA que disparan acción reactiva inmediata
EVENTOS_REACTIVOS = {
    "binary_sensor",   # movimiento, puertas, ventanas
    "alarm_control_panel",
    "person",          # presencia
    "media_player",    # música, TV
}

# ── Estado interno ─────────────────────────────────────────────────────────────

contexto_ha    = {}                        # estado actual de entidades
historial_ha   = deque(maxlen=MAX_HISTORIAL_HA)   # eventos recientes
historial_conv = deque(maxlen=MAX_HISTORIAL_CONV)  # conversación con el LLM
_mqtt_client   = None
_lock          = threading.Lock()

# ── Abstracción LLM ────────────────────────────────────────────────────────────

def llm_completar(mensajes: list) -> str:
    """
    Envía mensajes al LLM configurado y devuelve la respuesta como string.
    Cambiar LLM_PROVIDER en la configuración cambia el proveedor automáticamente.
    """
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
        # Separar system del resto de mensajes (Anthropic lo requiere aparte)
        system  = next((m["content"] for m in mensajes if m["role"] == "system"), "")
        msgs    = [m for m in mensajes if m["role"] != "system"]
        respuesta = client.messages.create(
            model=config["model"],
            max_tokens=1024,
            system=system,
            messages=msgs
        )
        return respuesta.content[0].text

    raise ValueError(f"Proveedor LLM desconocido: {LLM_PROVIDER}")

# ── Sistema de prompts ─────────────────────────────────────────────────────────

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

ACCIONES DISPONIBLES PARA HOME ASSISTANT:
- Encender/apagar luces: dominio "light", servicio "turn_on"/"turn_off"
- Control de música: dominio "media_player", servicio "play_media"/"pause"
- Alarma: dominio "alarm_control_panel", servicio "alarm_arm_away"/"alarm_disarm"
- Scripts HA: dominio "script", servicio nombre_del_script

REGLAS:
1. Responde SIEMPRE con JSON válido con la estructura indicada
2. Solo incluye acciones que tengan sentido dado el contexto
3. Si no hay nada relevante que hacer, devuelve acciones vacías
4. Sé sutil — no cambies el avatar constantemente, solo cuando sea relevante
5. Prioriza el bienestar y las preferencias de Kevin

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

def construir_prompt_usuario(motivo: str) -> str:
    """Construye el mensaje de usuario con todo el contexto actual."""
    ahora = datetime.now()

    with _lock:
        # Resumen del contexto HA (solo entidades relevantes)
        dominios_relevantes = {
            "light", "switch", "media_player", "alarm_control_panel",
            "person", "binary_sensor", "sensor", "climate", "calendar",
            "input_boolean", "input_number"
        }
        ctx_filtrado = {
            k: v for k, v in contexto_ha.items()
            if k.split(".")[0] in dominios_relevantes
        }

        # Últimos eventos
        eventos_recientes = list(historial_ha)[-10:]

    return f"""
MOTIVO DE ESTA CONSULTA: {motivo}

HORA Y FECHA ACTUAL: {ahora.strftime("%A %d/%m/%Y %H:%M")} (hora España)
DÍA DE LA SEMANA: {ahora.strftime("%A")}

ESTADO ACTUAL DEL HOGAR:
{json.dumps(ctx_filtrado, indent=2, ensure_ascii=False)}

ÚLTIMOS EVENTOS:
{json.dumps(eventos_recientes, indent=2, ensure_ascii=False)}

Basándote en este contexto y las preferencias de Kevin, ¿qué debe hacer Riatla ahora?
"""

# ── Motor de decisión ──────────────────────────────────────────────────────────

def tomar_decision(motivo: str):
    """
    Consulta al LLM y ejecuta las acciones resultantes.
    Mantiene el historial de conversación para coherencia a largo plazo.
    """
    print(f"\n[Agente] Tomando decisión — motivo: {motivo}")

    try:
        # Construir historial de conversación
        mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Añadir historial previo (para coherencia)
        with _lock:
            mensajes.extend(list(historial_conv))

        # Añadir consulta actual
        prompt_usuario = construir_prompt_usuario(motivo)
        mensajes.append({"role": "user", "content": prompt_usuario})

        # Consultar LLM
        respuesta_raw = llm_completar(mensajes)
        respuesta     = json.loads(respuesta_raw)

        print(f"[Agente] Razonamiento: {respuesta.get('razonamiento', '')}")

        # Guardar en historial de conversación
        with _lock:
            historial_conv.append({"role": "user",      "content": prompt_usuario})
            historial_conv.append({"role": "assistant",  "content": respuesta_raw})

        # Ejecutar acciones
        acciones = respuesta.get("acciones", [])
        if not acciones:
            print("[Agente] Sin acciones que ejecutar")
            return

        for accion in acciones:
            ejecutar_accion(accion)

    except Exception as e:
        print(f"[Agente] Error en tomar_decision: {e}")

def ejecutar_accion(accion: dict):
    """Despacha la acción a Riatla (MQTT) o a Home Assistant (REST)."""
    tipo = accion.get("tipo", "")

    if tipo == "riatla":
        topic = accion.get("topic", "")
        datos = accion.get("datos", {})
        if topic:
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
    topic   = TOPIC_RIATLA.format(topic_sufijo)
    mensaje = json.dumps(payload)
    _mqtt_client.publish(topic, mensaje)
    print(f"[Riatla] → {topic}: {mensaje}")

# ── HA REST API ────────────────────────────────────────────────────────────────

def ha_llamar_servicio(dominio: str, servicio: str, datos: dict = None) -> bool:
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

# ── MQTT callbacks ─────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Conectado a {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_HA_ALL)
    else:
        print(f"[MQTT] Error de conexión: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc}), reconectando...")

def on_message(client, userdata, msg):
    """
    Procesa eventos de HA. Los eventos de dominios reactivos
    disparan una decisión inmediata del agente.
    """
    topic = msg.topic
    try:
        payload = msg.payload.decode("utf-8").strip()
        if not payload:
            return

        partes    = topic.split("/")
        if len(partes) < 3:
            return

        dominio   = partes[1]
        entity_id = f"{dominio}.{'_'.join(partes[2:])}"

        try:
            valor = json.loads(payload)
        except json.JSONDecodeError:
            valor = payload

        evento = {
            "entity_id": entity_id,
            "valor":     valor,
            "ts":        time.strftime("%Y-%m-%dT%H:%M:%S")
        }

        with _lock:
            contexto_ha[entity_id] = {"valor": valor, "ts": evento["ts"]}
            historial_ha.append(evento)

        # Reacción inmediata para dominios relevantes
        if dominio in EVENTOS_REACTIVOS:
            # Lanzar en hilo separado para no bloquear el loop MQTT
            threading.Thread(
                target=tomar_decision,
                args=(f"Evento reactivo: {entity_id} → {valor}",),
                daemon=True
            ).start()

    except Exception as e:
        print(f"[MQTT] Error procesando {topic}: {e}")

# ── Revisión periódica ─────────────────────────────────────────────────────────

def loop_revision_periodica():
    """Revisa el contexto cada INTERVALO_REVISION segundos."""
    while True:
        time.sleep(INTERVALO_REVISION)
        threading.Thread(
            target=tomar_decision,
            args=(f"Revisión periódica ({INTERVALO_REVISION}s)",),
            daemon=True
        ).start()

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _mqtt_client

    print("╔══════════════════════════════════╗")
    print("║      Riatla Agent v0.1           ║")
    print("╚══════════════════════════════════╝")
    print(f"LLM   → {LLM_PROVIDER} / {LLM_CONFIG[LLM_PROVIDER]['model']}")
    print(f"MQTT  → {MQTT_HOST}:{MQTT_PORT}")
    print(f"HA    → {HA_URL}")
    print(f"Revisión cada {INTERVALO_REVISION}s\n")

    # Hilo de revisión periódica
    threading.Thread(target=loop_revision_periodica, daemon=True).start()

    # Cliente MQTT
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    _mqtt_client = client

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[Agente] Detenido.")

if __name__ == "__main__":
    main()