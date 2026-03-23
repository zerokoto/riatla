#!/usr/bin/env python3
"""
bone_editor.py — Editor visual de huesos VRM para Riatla
=========================================================
Mueve huesos en tiempo real via MQTT → riatla/hueso mientras ves
el resultado en la ventana de Electron.  Ideal para ajustar poses
y copiar los valores exactos a renderer.js.

Uso:  python bone_editor.py
Requiere: pip install paho-mqtt python-dotenv
"""

import json
import math
import tkinter as tk
from tkinter import ttk

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MQTT_HOST   = os.getenv("MQTT_HOST", "192.168.1.126")
MQTT_PORT   = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER   = os.getenv("MQTT_USER")
MQTT_PASS   = os.getenv("MQTT_PASS")
TOPIC_HUESO = "riatla/hueso"
TOPIC_HUESO  = "riatla/hueso"


# ── Huesos VRM agrupados ──────────────────────────────────────────────────────
GRUPOS = {
    "Torso": [
        "hips", "spine", "chest", "upperChest",
    ],
    "Cabeza": [
        "neck", "head",
    ],
    "Brazo Izq.": [
        "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    ],
    "Brazo Dcho.": [
        "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    ],
    "Pierna Izq.": [
        "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes",
    ],
    "Pierna Dcha.": [
        "rightUpperLeg", "rightLowerLeg", "rightFoot", "rightToes",
    ],
    "Dedos Izq.": [
        "leftThumbProximal", "leftThumbIntermediate", "leftThumbDistal",
        "leftIndexProximal",  "leftIndexIntermediate",  "leftIndexDistal",
        "leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal",
        "leftRingProximal",   "leftRingIntermediate",   "leftRingDistal",
        "leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal",
    ],
    "Dedos Dcho.": [
        "rightThumbProximal",  "rightThumbIntermediate",  "rightThumbDistal",
        "rightIndexProximal",  "rightIndexIntermediate",  "rightIndexDistal",
        "rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal",
        "rightRingProximal",   "rightRingIntermediate",   "rightRingDistal",
        "rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal",
    ],
}

# Colores (paleta Catppuccin Mocha)
BG   = "#1e1e2e"
BG2  = "#181825"
BG3  = "#313244"
BG4  = "#45475a"
FG   = "#cdd6f4"
FG2  = "#6c7086"
ACC  = "#89b4fa"
RED  = "#f38ba8"
GRN  = "#a6e3a1"
YEL  = "#f9e2af"
LIL  = "#cba6f7"

AXIS_COLORS = {"X": RED, "Y": GRN, "Z": ACC}


class BoneEditor(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Riatla — Editor de Huesos")
        self.configure(bg=BG)
        self.resizable(True, True)

        # Estado
        self._mqtt_connected = False
        self._mqtt_client    = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._bone_values    = {}   # {nombre_hueso: {"X": float, "Y": float, "Z": float}}
        self._current_bone   = None
        self._send_after_id  = None
        self._block_slider   = False  # evita bucle slider↔entry

        self.status_var = tk.StringVar(value="🟡 Conectando…")

        self._build_ui()
        self.after(300, self._mqtt_connect)

    # ── MQTT ──────────────────────────────────────────────────────────────────

    def _mqtt_connect(self):
        if MQTT_USER:
            self._mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)

        def on_connect(client, userdata, flags, rc):
            self._mqtt_connected = (rc == 0)
            if rc == 0:
                self.status_var.set("🟢 Conectado")
                client.subscribe(TOPIC_ESTADO)   # ← pide el estado retenido
            else:
                self.status_var.set(f"🔴 Error rc={rc}")

        def on_message(client, userdata, msg):
            if msg.topic == TOPIC_ESTADO:
                try:
                    datos = json.loads(msg.payload.decode())
                    # datos = {"head": {"x":0.1,"y":0.0,"z":0.0}, ...}
                    huesos = {}
                    for nombre, vals in datos.items():
                        huesos[nombre] = {
                            "X": float(vals.get("x", 0.0)),
                            "Y": float(vals.get("y", 0.0)),
                            "Z": float(vals.get("z", 0.0)),
                        }
                    # Actualizar en el hilo principal de Tk
                    self.after(0, lambda h=huesos: self._aplicar_estado(h))
                except Exception as e:
                    self.after(0, lambda: self.status_var.set(f"⚠️ Estado inválido: {e}"))

        def on_disconnect(client, userdata, rc):
            self._mqtt_connected = False
            self.status_var.set("🟡 Desconectado")

        self._mqtt_client.on_connect    = on_connect
        self._mqtt_client.on_disconnect = on_disconnect
        self._mqtt_client.on_message    = on_message

        try:
            self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            self._mqtt_client.loop_start()
        except Exception as e:
            self.status_var.set(f"🔴 {e}")

    def _publicar(self, nombre, x, y, z):
        if not self._mqtt_connected:
            return
        try:
            duracion = int(self.dur_var.get())
        except ValueError:
            duracion = 150
        payload = json.dumps({
            "huesos":   [{"nombre": nombre,
                          "x": round(x, 4),
                          "y": round(y, 4),
                          "z": round(z, 4)}],
            "duracion": duracion,
            "lerp":     self.lerp_var.get(),
        })
        self._mqtt_client.publish(TOPIC_HUESO, payload)

    def _aplicar_estado(self, huesos: dict):
        """Carga los valores recibidos de riatla/estado al arrancar."""
        self._bone_values.update(huesos)
        self.status_var.set(f"🟢 Conectado  ({len(huesos)} huesos cargados)")

        # Si ya hay un hueso seleccionado, refresca sus sliders
        if self._current_bone and self._current_bone in huesos:
            v = huesos[self._current_bone]
            self._set_sliders(v["X"], v["Y"], v["Z"])

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self._build_bone_list(body)
        self._build_controls(body)
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG2, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🦴  Editor de Huesos VRM", bg=BG2, fg=ACC,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=14)
        tk.Label(hdr, textvariable=self.status_var, bg=BG2, fg=FG,
                 font=("Segoe UI", 9)).pack(side="right", padx=14)

    def _build_bone_list(self, parent):
        frame = tk.Frame(parent, bg=BG2, bd=0)
        frame.pack(side="left", fill="y", padx=(0, 10), pady=8)

        tk.Label(frame, text="Selecciona un hueso", bg=BG2, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=(6, 2))

        list_frame = tk.Frame(frame, bg=BG2)
        list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        sb = tk.Scrollbar(list_frame, orient="vertical", bg=BG3)
        self.listbox = tk.Listbox(
            list_frame, yscrollcommand=sb.set,
            bg=BG2, fg=FG,
            selectbackground=ACC, selectforeground=BG2,
            font=("Consolas", 10), activestyle="none",
            width=25, height=32, bd=0, highlightthickness=0,
        )
        sb.config(command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)

        # Poblar lista
        self._list_map = []  # (type, nombre)
        first_bone_idx = None
        for grupo, huesos in GRUPOS.items():
            self.listbox.insert("end", f" ── {grupo}")
            self.listbox.itemconfig("end", fg=FG2,
                                    selectbackground=BG2, selectforeground=FG2)
            self._list_map.append(("group", grupo))
            for h in huesos:
                self.listbox.insert("end", f"    {h}")
                self._list_map.append(("bone", h))
                if first_bone_idx is None:
                    first_bone_idx = len(self._list_map) - 1

        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _build_controls(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, pady=8)

        # Nombre del hueso activo
        self.bone_label_var = tk.StringVar(value="(ningún hueso seleccionado)")
        tk.Label(right, textvariable=self.bone_label_var, bg=BG, fg=ACC,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))

        # Sliders
        self._svars  = {}  # axis → DoubleVar (slider)
        self._evars  = {}  # axis → StringVar (entry texto)
        self._dvars  = {}  # axis → StringVar (grados)

        sliders_frame = tk.Frame(right, bg=BG)
        sliders_frame.pack(fill="x")

        for axis in ("X", "Y", "Z"):
            self._build_axis_row(sliders_frame, axis)

        # Separador
        sep = tk.Frame(right, bg=BG3, height=1)
        sep.pack(fill="x", pady=10)

        # Atajos π
        self._build_pi_shortcuts(right)

        sep2 = tk.Frame(right, bg=BG3, height=1)
        sep2.pack(fill="x", pady=10)

        # Opciones lerp / duración
        self._build_options(right)

        # Botones
        self._build_buttons(right)

        # Código generado
        self._build_code_box(right)

    def _build_axis_row(self, parent, axis):
        color = AXIS_COLORS[axis]

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)

        # Etiqueta eje
        tk.Label(row, text=axis, bg=BG, fg=color,
                 font=("Segoe UI", 11, "bold"), width=2).pack(side="left")

        # Slider
        svar = tk.DoubleVar(value=0.0)
        self._svars[axis] = svar
        slider = tk.Scale(
            row, variable=svar, orient="horizontal",
            from_=-math.pi, to=math.pi, resolution=0.001,
            bg=BG, fg=FG, troughcolor=BG3,
            highlightthickness=0, bd=0, showvalue=False,
            length=340, sliderlength=14,
            command=lambda val, a=axis: self._on_slider(a, float(val)),
        )
        slider.pack(side="left", padx=4)

        # Entry numérico (rad)
        evar = tk.StringVar(value="0.000")
        self._evars[axis] = evar
        entry = tk.Entry(
            row, textvariable=evar,
            bg=BG3, fg=FG, insertbackground=FG,
            font=("Consolas", 10), width=7,
            bd=0, highlightthickness=1,
            highlightcolor=color, highlightbackground=BG4,
            relief="flat",
        )
        entry.pack(side="left", padx=(4, 2))
        entry.bind("<Return>",   lambda e, a=axis: self._on_entry(a))
        entry.bind("<FocusOut>", lambda e, a=axis: self._on_entry(a))

        # Grados (informativo)
        dvar = tk.StringVar(value="  0.0°")
        self._dvars[axis] = dvar
        tk.Label(row, textvariable=dvar, bg=BG, fg=FG2,
                 font=("Consolas", 9), width=7, anchor="w").pack(side="left")

        # Botón reset eje
        tk.Button(
            row, text="×0", bg=BG3, fg=FG2, bd=0,
            padx=5, pady=0, font=("Consolas", 9),
            activebackground=BG4, activeforeground=FG,
            relief="flat",
            command=lambda a=axis: self._reset_axis(a),
        ).pack(side="left", padx=2)

    def _build_pi_shortcuts(self, parent):
        """Fila de atajos de valores comunes (fracciones de π)."""
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x")

        tk.Label(frame, text="Atajos:", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))

        shortcuts = [
            ("-π",   -math.pi),
            ("-π/2", -math.pi / 2),
            ("-π/4", -math.pi / 4),
            ("-π/8", -math.pi / 8),
            ("0",     0.0),
            ("π/8",   math.pi / 8),
            ("π/4",   math.pi / 4),
            ("π/2",   math.pi / 2),
            ("π",     math.pi),
        ]
        for label, val in shortcuts:
            tk.Button(
                frame, text=label, bg=BG3, fg=YEL, bd=0,
                padx=5, pady=2, font=("Consolas", 8),
                activebackground=BG4, activeforeground=FG,
                relief="flat",
                command=lambda v=val: self._apply_shortcut(v),
            ).pack(side="left", padx=1)

        # Selector de eje para los atajos
        self.shortcut_axis = tk.StringVar(value="X")
        tk.Label(frame, text="→ eje:", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 2))
        for axis in ("X", "Y", "Z"):
            tk.Radiobutton(
                frame, text=axis, variable=self.shortcut_axis, value=axis,
                bg=BG, fg=AXIS_COLORS[axis], selectcolor=BG3,
                activebackground=BG, activeforeground=FG,
                font=("Segoe UI", 8), indicatoron=True,
            ).pack(side="left")

    def _apply_shortcut(self, value):
        axis = self.shortcut_axis.get()
        self._set_axis(axis, value)
        self._do_send()

    def _build_options(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x")

        self.lerp_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame, text="Lerp suave", variable=self.lerp_var,
            bg=BG, fg=FG, selectcolor=BG3,
            activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(side="left")

        tk.Label(frame, text="  Duración (ms):", bg=BG, fg=FG2,
                 font=("Segoe UI", 9)).pack(side="left")
        self.dur_var = tk.StringVar(value="150")
        tk.Entry(
            frame, textvariable=self.dur_var,
            bg=BG3, fg=FG, insertbackground=FG,
            font=("Consolas", 9), width=5,
            bd=0, highlightthickness=1,
            highlightcolor=ACC, highlightbackground=BG4,
            relief="flat",
        ).pack(side="left", padx=4)

    def _build_buttons(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(10, 6))

        tk.Button(
            frame, text="⟲  Reset hueso (0, 0, 0)",
            bg=BG3, fg=RED, bd=0, padx=10, pady=5,
            font=("Segoe UI", 9), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._reset_bone,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            frame, text="📋  Copiar lerpHueso()",
            bg=BG3, fg=GRN, bd=0, padx=10, pady=5,
            font=("Segoe UI", 9), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._copy_code,
        ).pack(side="left")

    def _build_code_box(self, parent):
        box = tk.LabelFrame(
            parent, text="  Código generado  ",
            bg=BG, fg=FG2, font=("Segoe UI", 8),
            bd=1, relief="solid", labelanchor="nw",
        )
        box.pack(fill="x", pady=(6, 0))

        self.code_var = tk.StringVar(
            value='lerpHueso(currentVRM, "…", { x: 0, y: 0, z: 0 });')
        tk.Label(
            box, textvariable=self.code_var,
            bg=BG2, fg=LIL, font=("Consolas", 10),
            anchor="w", padx=10, pady=8,
        ).pack(fill="x")

    def _build_footer(self):
        foot = tk.Frame(self, bg=BG2, pady=4)
        foot.pack(fill="x", side="bottom")
        tk.Label(
            foot,
            text=f"MQTT  {MQTT_HOST}:{MQTT_PORT}  →  {TOPIC_HUESO}",
            bg=BG2, fg=BG4, font=("Segoe UI", 8),
        ).pack()

    # ── Lógica de interacción ─────────────────────────────────────────────────

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx       = sel[0]
        kind, nom = self._list_map[idx]
        if kind == "group":
            self.listbox.selection_clear(0, "end")
            return

        self._current_bone = nom
        self.bone_label_var.set(nom)

        # Restaurar valores previos o inicializar a 0
        vals = self._bone_values.get(nom, {"X": 0.0, "Y": 0.0, "Z": 0.0})
        self._set_sliders(vals["X"], vals["Y"], vals["Z"])

    def _set_sliders(self, x, y, z):
        self._block_slider = True
        vals = {"X": x, "Y": y, "Z": z}
        for axis, val in vals.items():
            self._set_axis(axis, val)
        self._block_slider = False
        self._update_code()

    def _set_axis(self, axis, val):
        """Actualiza slider + entry + grados de un eje sin disparar envío."""
        self._block_slider = True
        self._svars[axis].set(val)
        self._evars[axis].set(f"{val:.3f}")
        self._dvars[axis].set(f"{math.degrees(val):+.1f}°")
        self._block_slider = False

    def _on_slider(self, axis, val):
        if self._block_slider:
            return
        self._evars[axis].set(f"{val:.3f}")
        self._dvars[axis].set(f"{math.degrees(val):+.1f}°")
        self._update_code()
        self._schedule_send()

    def _on_entry(self, axis):
        try:
            raw = self._evars[axis].get().strip()
            # Admite expresiones simples tipo "pi/4", "3.14/2"
            val = float(eval(raw.replace("pi", str(math.pi)),
                             {"__builtins__": {}}, {}))
        except Exception:
            return
        val = max(-math.pi, min(math.pi, val))
        self._set_axis(axis, val)
        self._update_code()
        self._do_send()

    def _reset_axis(self, axis):
        self._set_axis(axis, 0.0)
        self._update_code()
        self._do_send()

    def _reset_bone(self):
        self._set_sliders(0.0, 0.0, 0.0)
        self._do_send()

    def _schedule_send(self):
        """Debounce: cancela el envío pendiente y reprograma."""
        if self._send_after_id is not None:
            self.after_cancel(self._send_after_id)
        self._send_after_id = self.after(60, self._do_send)

    def _do_send(self):
        self._send_after_id = None
        if not self._current_bone:
            return
        nombre = self._current_bone
        x = self._svars["X"].get()
        y = self._svars["Y"].get()
        z = self._svars["Z"].get()
        self._bone_values[nombre] = {"X": x, "Y": y, "Z": z}
        self._publicar(nombre, x, y, z)

    def _update_code(self):
        if not self._current_bone:
            return
        nombre = self._current_bone
        x = self._svars["X"].get()
        y = self._svars["Y"].get()
        z = self._svars["Z"].get()
        code = (
            f"lerpHueso(currentVRM, '{nombre}', "
            f"{{ x: {x:.4f}, y: {y:.4f}, z: {z:.4f} }});"
        )
        self.code_var.set(code)

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self.code_var.get())
        prev = self.status_var.get()
        self.status_var.set("📋  Copiado al portapapeles")
        self.after(2000, lambda: self.status_var.set(prev))

    def on_close(self):
        self._mqtt_client.loop_stop()
        self._mqtt_client.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = BoneEditor()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
