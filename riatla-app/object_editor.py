#!/usr/bin/env python3
"""
object_editor.py — Editor visual de objetos/props para Riatla
=============================================================
Mueve, rota y escala objetos en tiempo real via MQTT → riatla/objeto
mientras ves el resultado en la ventana de Electron.
Ideal para ajustar posiciones y copiar los valores exactos a renderer.js.

Uso:  python object_editor.py
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

MQTT_HOST    = os.getenv("MQTT_HOST", "192.168.1.126")
MQTT_PORT    = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER    = os.getenv("MQTT_USER")
MQTT_PASS    = os.getenv("MQTT_PASS")
TOPIC_OBJETO = "riatla/objeto"
TOPIC_ESTADO = "riatla/estado"

# ── Objetos disponibles ───────────────────────────────────────────────────────
OBJETOS = [
    "libro",
    "musica",
    "comida",
    "bebida",
    "timer",
    "dnd",
    "mando",
]

# Valores por defecto extraídos de renderer.js
DEFAULTS = {
    "libro":  {"pos": (0.2,  1.1,  0.2),  "rot": (0.0,       math.pi/4 + math.pi,  0.0),       "scale": 0.05  },
    "musica": {"pos": (0.0,  1.5,  0.0),  "rot": (0.0,       0.0,                  0.0),        "scale": 0.003 },
    "comida": {"pos": (-0.1, 1.15, 0.5),  "rot": (0.0,       math.pi/16,           -math.pi/8), "scale": 1.4   },
    "bebida": {"pos": (0.28, 1.15, 0.0),  "rot": (0.0,       math.pi/16,           -math.pi/16),"scale": 0.9   },
    "timer":  {"pos": (-0.27,1.4,  0.0),  "rot": (0.0,       math.pi/16,            math.pi/8), "scale": 0.8   },
    "dnd":    {"pos": (-0.25,1.5,  0.0),  "rot": (math.pi/8, math.pi/2,             0.0),       "scale": 0.1   },
    "mando":  {"pos": (0.135,1.13, 0.3),  "rot": (0.0,       math.pi + math.pi/8,   0.0),       "scale": 0.2   },
}

# Colores (paleta Catppuccin Mocha — igual que bone_editor)
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
PEA  = "#94e2d5"   # teal — para escala

# Colores por eje
AXIS_COLORS = {"X": RED, "Y": GRN, "Z": ACC}

# Rangos de los sliders
POS_RANGE   = 3.0     # ± metros
ROT_RANGE   = math.pi # ± radianes
SCALE_MIN   = 0.001
SCALE_MAX   = 5.0


class ObjectEditor(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Riatla — Editor de Objetos")
        self.configure(bg=BG)
        self.resizable(True, True)

        # Estado
        self._mqtt_connected  = False
        self._mqtt_client     = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._obj_values      = {}   # {nombre: {pos, rot, scale}}
        self._current_object  = None
        self._send_after_id   = None
        self._block_slider    = False

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
            else:
                self.status_var.set(f"🔴 Error rc={rc}")

        def on_disconnect(client, userdata, rc):
            self._mqtt_connected = False
            self.status_var.set("🟡 Desconectado")

        self._mqtt_client.on_connect    = on_connect
        self._mqtt_client.on_disconnect = on_disconnect

        try:
            self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            self._mqtt_client.loop_start()
        except Exception as e:
            self.status_var.set(f"🔴 {e}")

    def _publicar(self):
        if not self._mqtt_connected or not self._current_object:
            return

        nombre = self._current_object
        px, py, pz = [self._pos_svars[a].get() for a in ("X", "Y", "Z")]
        rx, ry, rz = [self._rot_svars[a].get() for a in ("X", "Y", "Z")]
        sc         =  self._scale_svar.get()

        payload = json.dumps({
            "accion":   "update",
            "objeto":   nombre,
            "position": {"x": round(px, 4), "y": round(py, 4), "z": round(pz, 4)},
            "rotation": {"x": round(rx, 4), "y": round(ry, 4), "z": round(rz, 4)},
            "scale":    round(sc, 4),
        })
        self._mqtt_client.publish(TOPIC_OBJETO, payload)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self._build_object_list(body)
        self._build_controls(body)
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG2, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📦  Editor de Objetos VRM", bg=BG2, fg=ACC,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=14)
        tk.Label(hdr, textvariable=self.status_var, bg=BG2, fg=FG,
                 font=("Segoe UI", 9)).pack(side="right", padx=14)

    def _build_object_list(self, parent):
        frame = tk.Frame(parent, bg=BG2, bd=0)
        frame.pack(side="left", fill="y", padx=(0, 10), pady=8)

        tk.Label(frame, text="Selecciona un objeto", bg=BG2, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=(6, 2))

        list_frame = tk.Frame(frame, bg=BG2)
        list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.listbox = tk.Listbox(
            list_frame,
            bg=BG2, fg=FG,
            selectbackground=ACC, selectforeground=BG2,
            font=("Consolas", 11), activestyle="none",
            width=16, height=len(OBJETOS) + 2,
            bd=0, highlightthickness=0,
        )
        self.listbox.pack(fill="both", expand=True)

        for obj in OBJETOS:
            self.listbox.insert("end", f"  {obj}")

        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Botones add/remove bajo la lista
        btn_frame = tk.Frame(frame, bg=BG2)
        btn_frame.pack(fill="x", padx=4, pady=(4, 0))

        tk.Button(
            btn_frame, text="▶ Añadir", bg=BG3, fg=GRN, bd=0,
            padx=6, pady=4, font=("Segoe UI", 8), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._add_object,
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        tk.Button(
            btn_frame, text="■ Quitar", bg=BG3, fg=RED, bd=0,
            padx=6, pady=4, font=("Segoe UI", 8), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._remove_object,
        ).pack(side="left", fill="x", expand=True)

    def _build_controls(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, pady=8)

        # Nombre del objeto activo
        self.obj_label_var = tk.StringVar(value="(ningún objeto seleccionado)")
        tk.Label(right, textvariable=self.obj_label_var, bg=BG, fg=ACC,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 6))

        # ── Posición ──────────────────────────────────────────────────────────
        self._pos_svars = {}
        self._pos_evars = {}
        self._build_section_label(right, "POSICIÓN", PEA)
        pos_frame = tk.Frame(right, bg=BG)
        pos_frame.pack(fill="x")
        for axis in ("X", "Y", "Z"):
            self._build_row(pos_frame, axis, "pos",
                            -POS_RANGE, POS_RANGE, 0.001,
                            self._pos_svars, self._pos_evars,
                            lambda val, a=axis: self._on_slider_pos(a, float(val)))

        sep1 = tk.Frame(right, bg=BG3, height=1)
        sep1.pack(fill="x", pady=8)

        # ── Rotación ──────────────────────────────────────────────────────────
        self._rot_svars = {}
        self._rot_evars = {}
        self._rot_dvars = {}
        self._build_section_label(right, "ROTACIÓN", YEL)
        rot_frame = tk.Frame(right, bg=BG)
        rot_frame.pack(fill="x")
        for axis in ("X", "Y", "Z"):
            self._build_row(rot_frame, axis, "rot",
                            -ROT_RANGE, ROT_RANGE, 0.001,
                            self._rot_svars, self._rot_evars,
                            lambda val, a=axis: self._on_slider_rot(a, float(val)),
                            show_degrees=True)

        sep2 = tk.Frame(right, bg=BG3, height=1)
        sep2.pack(fill="x", pady=8)

        # ── Escala ────────────────────────────────────────────────────────────
        self._scale_svar = tk.DoubleVar(value=1.0)
        self._scale_evar = tk.StringVar(value="1.000")
        self._build_section_label(right, "ESCALA", LIL)
        scale_frame = tk.Frame(right, bg=BG)
        scale_frame.pack(fill="x")
        self._build_scale_row(scale_frame)

        sep3 = tk.Frame(right, bg=BG3, height=1)
        sep3.pack(fill="x", pady=8)

        # ── Botones de acción ─────────────────────────────────────────────────
        self._build_buttons(right)

        # ── Código generado ───────────────────────────────────────────────────
        self._build_code_box(right)

    def _build_section_label(self, parent, text, color):
        tk.Label(parent, text=text, bg=BG, fg=color,
                 font=("Consolas", 8, "bold")).pack(anchor="w", pady=(2, 1))

    def _build_row(self, parent, axis, kind, from_, to_, res,
                   svars, evars, cmd, show_degrees=False):
        color = AXIS_COLORS[axis]
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=2)

        tk.Label(row, text=axis, bg=BG, fg=color,
                 font=("Segoe UI", 11, "bold"), width=2).pack(side="left")

        svar = tk.DoubleVar(value=0.0)
        svars[axis] = svar
        tk.Scale(
            row, variable=svar, orient="horizontal",
            from_=from_, to=to_, resolution=res,
            bg=BG, fg=FG, troughcolor=BG3,
            highlightthickness=0, bd=0, showvalue=False,
            length=300, sliderlength=14,
            command=cmd,
        ).pack(side="left", padx=4)

        evar = tk.StringVar(value="0.000")
        evars[axis] = evar
        entry = tk.Entry(
            row, textvariable=evar,
            bg=BG3, fg=FG, insertbackground=FG,
            font=("Consolas", 10), width=7,
            bd=0, highlightthickness=1,
            highlightcolor=color, highlightbackground=BG4,
            relief="flat",
        )
        entry.pack(side="left", padx=(4, 2))
        entry.bind("<Return>",   lambda e, k=kind, a=axis: self._on_entry(k, a))
        entry.bind("<FocusOut>", lambda e, k=kind, a=axis: self._on_entry(k, a))

        if show_degrees:
            dvar = tk.StringVar(value="  0.0°")
            self._rot_dvars[axis] = dvar
            tk.Label(row, textvariable=dvar, bg=BG, fg=FG2,
                     font=("Consolas", 9), width=7, anchor="w").pack(side="left")

        tk.Button(
            row, text="×0", bg=BG3, fg=FG2, bd=0,
            padx=5, pady=0, font=("Consolas", 9),
            activebackground=BG4, activeforeground=FG,
            relief="flat",
            command=lambda k=kind, a=axis: self._reset_axis(k, a),
        ).pack(side="left", padx=2)

    def _build_scale_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=2)

        tk.Label(row, text="S", bg=BG, fg=LIL,
                 font=("Segoe UI", 11, "bold"), width=2).pack(side="left")

        tk.Scale(
            row, variable=self._scale_svar, orient="horizontal",
            from_=SCALE_MIN, to=SCALE_MAX, resolution=0.001,
            bg=BG, fg=FG, troughcolor=BG3,
            highlightthickness=0, bd=0, showvalue=False,
            length=300, sliderlength=14,
            command=lambda val: self._on_slider_scale(float(val)),
        ).pack(side="left", padx=4)

        entry = tk.Entry(
            row, textvariable=self._scale_evar,
            bg=BG3, fg=FG, insertbackground=FG,
            font=("Consolas", 10), width=7,
            bd=0, highlightthickness=1,
            highlightcolor=LIL, highlightbackground=BG4,
            relief="flat",
        )
        entry.pack(side="left", padx=(4, 2))
        entry.bind("<Return>",   lambda e: self._on_entry("scale", None))
        entry.bind("<FocusOut>", lambda e: self._on_entry("scale", None))

        # Atajos de escala
        for label, val in [("×0.1", 0.1), ("×0.5", 0.5), ("×1", 1.0), ("×2", 2.0)]:
            tk.Button(
                row, text=label, bg=BG3, fg=LIL, bd=0,
                padx=5, pady=0, font=("Consolas", 8),
                activebackground=BG4, activeforeground=FG,
                relief="flat",
                command=lambda v=val: self._apply_scale_shortcut(v),
            ).pack(side="left", padx=1)

    def _build_buttons(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(4, 6))

        tk.Button(
            frame, text="⟲  Reset todo",
            bg=BG3, fg=RED, bd=0, padx=10, pady=5,
            font=("Segoe UI", 9), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._reset_all,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            frame, text="📋  Copiar config JS",
            bg=BG3, fg=GRN, bd=0, padx=10, pady=5,
            font=("Segoe UI", 9), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._copy_code,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            frame, text="↩  Restaurar defaults",
            bg=BG3, fg=YEL, bd=0, padx=10, pady=5,
            font=("Segoe UI", 9), relief="flat",
            activebackground=BG4, activeforeground=FG,
            command=self._load_defaults,
        ).pack(side="left")

    def _build_code_box(self, parent):
        box = tk.LabelFrame(
            parent, text="  Código generado (OBJECTS entry)  ",
            bg=BG, fg=FG2, font=("Segoe UI", 8),
            bd=1, relief="solid", labelanchor="nw",
        )
        box.pack(fill="x", pady=(6, 0))

        self.code_var = tk.StringVar(value="(selecciona un objeto)")
        tk.Label(
            box, textvariable=self.code_var,
            bg=BG2, fg=LIL, font=("Consolas", 9),
            anchor="w", padx=10, pady=8, justify="left",
            wraplength=580,
        ).pack(fill="x")

    def _build_footer(self):
        foot = tk.Frame(self, bg=BG2, pady=4)
        foot.pack(fill="x", side="bottom")
        tk.Label(
            foot,
            text=f"MQTT  {MQTT_HOST}:{MQTT_PORT}  →  {TOPIC_OBJETO}",
            bg=BG2, fg=BG4, font=("Segoe UI", 8),
        ).pack()

    # ── Interacción ───────────────────────────────────────────────────────────

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        nombre = OBJETOS[sel[0]]
        self._current_object = nombre
        self.obj_label_var.set(f"📦  {nombre}")

        # Cargar valores guardados o defaults
        if nombre in self._obj_values:
            v = self._obj_values[nombre]
            self._load_values(v["pos"], v["rot"], v["scale"])
        elif nombre in DEFAULTS:
            d = DEFAULTS[nombre]
            self._load_values(d["pos"], d["rot"], d["scale"])
        else:
            self._load_values((0, 0, 0), (0, 0, 0), 1.0)

    def _load_values(self, pos, rot, scale):
        self._block_slider = True
        for i, axis in enumerate(("X", "Y", "Z")):
            self._pos_svars[axis].set(pos[i])
            self._pos_evars[axis].set(f"{pos[i]:.3f}")
            self._rot_svars[axis].set(rot[i])
            self._rot_evars[axis].set(f"{rot[i]:.3f}")
            self._rot_dvars[axis].set(f"{math.degrees(rot[i]):+.1f}°")
        self._scale_svar.set(scale)
        self._scale_evar.set(f"{scale:.3f}")
        self._block_slider = False
        self._update_code()

    def _on_slider_pos(self, axis, val):
        if self._block_slider:
            return
        self._pos_evars[axis].set(f"{val:.3f}")
        self._update_code()
        self._schedule_send()

    def _on_slider_rot(self, axis, val):
        if self._block_slider:
            return
        self._rot_evars[axis].set(f"{val:.3f}")
        self._rot_dvars[axis].set(f"{math.degrees(val):+.1f}°")
        self._update_code()
        self._schedule_send()

    def _on_slider_scale(self, val):
        if self._block_slider:
            return
        self._scale_evar.set(f"{val:.3f}")
        self._update_code()
        self._schedule_send()

    def _on_entry(self, kind, axis):
        try:
            if kind == "scale":
                raw = self._scale_evar.get().strip()
                val = float(eval(raw, {"__builtins__": {}}, {}))
                val = max(SCALE_MIN, min(SCALE_MAX, val))
                self._block_slider = True
                self._scale_svar.set(val)
                self._scale_evar.set(f"{val:.3f}")
                self._block_slider = False
            elif kind == "pos":
                raw = self._pos_evars[axis].get().strip()
                val = float(eval(raw, {"__builtins__": {}}, {}))
                val = max(-POS_RANGE, min(POS_RANGE, val))
                self._block_slider = True
                self._pos_svars[axis].set(val)
                self._pos_evars[axis].set(f"{val:.3f}")
                self._block_slider = False
            elif kind == "rot":
                raw = self._rot_evars[axis].get().strip()
                val = float(eval(raw.replace("pi", str(math.pi)), {"__builtins__": {}}, {}))
                val = max(-ROT_RANGE, min(ROT_RANGE, val))
                self._block_slider = True
                self._rot_svars[axis].set(val)
                self._rot_evars[axis].set(f"{val:.3f}")
                self._rot_dvars[axis].set(f"{math.degrees(val):+.1f}°")
                self._block_slider = False
        except Exception:
            return
        self._update_code()
        self._do_send()

    def _reset_axis(self, kind, axis):
        self._block_slider = True
        if kind == "pos":
            self._pos_svars[axis].set(0.0)
            self._pos_evars[axis].set("0.000")
        elif kind == "rot":
            self._rot_svars[axis].set(0.0)
            self._rot_evars[axis].set("0.000")
            self._rot_dvars[axis].set("  0.0°")
        self._block_slider = False
        self._update_code()
        self._do_send()

    def _apply_scale_shortcut(self, val):
        self._block_slider = True
        self._scale_svar.set(val)
        self._scale_evar.set(f"{val:.3f}")
        self._block_slider = False
        self._update_code()
        self._do_send()

    def _reset_all(self):
        self._load_values((0, 0, 0), (0, 0, 0), 1.0)
        self._do_send()

    def _load_defaults(self):
        if not self._current_object or self._current_object not in DEFAULTS:
            return
        d = DEFAULTS[self._current_object]
        self._load_values(d["pos"], d["rot"], d["scale"])
        self._do_send()

    def _add_object(self):
        if not self._mqtt_connected or not self._current_object:
            return
        payload = json.dumps({"accion": "add", "objeto": self._current_object})
        self._mqtt_client.publish(TOPIC_OBJETO, payload)
        self.status_var.set(f"▶ Añadido: {self._current_object}")

    def _remove_object(self):
        if not self._mqtt_connected or not self._current_object:
            return
        payload = json.dumps({"accion": "remove", "objeto": self._current_object})
        self._mqtt_client.publish(TOPIC_OBJETO, payload)
        self.status_var.set(f"■ Quitado: {self._current_object}")

    def _schedule_send(self):
        if self._send_after_id is not None:
            self.after_cancel(self._send_after_id)
        self._send_after_id = self.after(60, self._do_send)

    def _do_send(self):
        self._send_after_id = None
        if not self._current_object:
            return
        nombre = self._current_object
        pos   = tuple(self._pos_svars[a].get() for a in ("X", "Y", "Z"))
        rot   = tuple(self._rot_svars[a].get() for a in ("X", "Y", "Z"))
        scale = self._scale_svar.get()
        self._obj_values[nombre] = {"pos": pos, "rot": rot, "scale": scale}
        self._publicar()

    def _update_code(self):
        if not self._current_object:
            return
        nombre = self._current_object
        px = self._pos_svars["X"].get()
        py = self._pos_svars["Y"].get()
        pz = self._pos_svars["Z"].get()
        rx = self._rot_svars["X"].get()
        ry = self._rot_svars["Y"].get()
        rz = self._rot_svars["Z"].get()
        sc = self._scale_svar.get()

        code = (
            f"{nombre}: {{\n"
            f"  path:     './props/{nombre}.glb',\n"
            f"  scale:    {sc:.4f},\n"
            f"  position: {{ x: {px:.4f}, y: {py:.4f}, z: {pz:.4f} }},\n"
            f"  rotation: {{ x: {rx:.4f}, y: {ry:.4f}, z: {rz:.4f} }}\n"
            f"}}"
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
    app = ObjectEditor()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()