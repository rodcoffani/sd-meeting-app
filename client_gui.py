#!/usr/bin/env python3
"""
Interface gráfica de videoconferência — sd-meeting-app

Controles disponíveis:
  🎤  Mutar / desmutar microfone
  📷  Ligar / desligar câmera
  🔊  Mutar / desmutar saída de áudio
  🚪  Sair da sala (volta para login)

Tecnologias:
  Tkinter — widgets e layout (built-in, sem dependência extra)
  Pillow  — converte frames OpenCV (numpy) em PhotoImage para Tkinter
  ZeroMQ  — mesma arquitetura do client.py (PUSH/SUB/DEALER)

Uso:
  python3 client_gui.py
"""

import json
import queue
import select
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import uuid

import yaml
import zmq

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False
    print("[GUI] Pillow não instalado — vídeo desabilitado. "
          "Instale com: pip install Pillow")

try:
    import pyaudio
    _AUDIO_OK = True
except ImportError:
    _AUDIO_OK = False

try:
    import cv2
    import numpy as np
    _VIDEO_OK = True and _PIL_OK
except ImportError:
    _VIDEO_OK = False


# ---------------------------------------------------------------------------
# Paleta de cores — tema escuro
# ---------------------------------------------------------------------------

C_BG      = "#1a1a2e"   # fundo principal
C_PANEL   = "#16213e"   # painéis internos
C_SURFACE = "#0f3460"   # superfície de botões / inputs
C_ACCENT  = "#e94560"   # vermelho: muted / câmera off / sair
C_GREEN   = "#00d4aa"   # verde: conectado / ativo
C_TEXT    = "#eaeaea"   # texto principal
C_DIM     = "#7a7a8a"   # texto secundário
C_BORDER  = "#2a2a4e"   # bordas
C_SELF    = "#533483"   # borda do self-preview
C_CHAT_ME = "#00d4aa"   # cor do meu nome no chat
C_CHAT_OT = "#e8c46a"   # cor dos outros no chat

FONT_UI   = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas",  9)
FONT_TITLE= ("Segoe UI", 13, "bold")
FONT_SMALL= ("Segoe UI",  8)


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def _load_cfg() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# QoS — Texto (ACK + fila de reenvio, thread-safe)
# ---------------------------------------------------------------------------

class TextQoS:
    def __init__(self, cfg):
        q = cfg["qos"]["text"]
        self._max_retry = q["max_retry"]
        self._retry_ivl = q["retry_interval"]
        self._pending: dict[str, dict] = {}
        self._lock  = threading.Lock()
        self._out_q: queue.Queue = queue.Queue()

    def send(self, msg_dict: dict):
        mid  = msg_dict["msg_id"]
        data = json.dumps(msg_dict).encode()
        with self._lock:
            self._pending[mid] = {"data": data, "retries": 0, "ts": time.time()}
        self._out_q.put(data)

    def ack(self, msg_id: str):
        with self._lock:
            self._pending.pop(msg_id, None)

    def get_next(self, timeout: float = 0):
        try:
            return self._out_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def retry_loop(self, stop: threading.Event):
        while not stop.is_set():
            now = time.time()
            with self._lock:
                expired = []
                for mid, p in self._pending.items():
                    if now - p["ts"] >= self._retry_ivl:
                        if p["retries"] >= self._max_retry:
                            expired.append(mid)
                        else:
                            self._out_q.put(p["data"])
                            p["retries"] += 1
                            p["ts"] = now
                for mid in expired:
                    del self._pending[mid]
            stop.wait(0.05)


# ---------------------------------------------------------------------------
# QoS — Vídeo (FPS e qualidade adaptativos)
# ---------------------------------------------------------------------------

class VideoQoS:
    def __init__(self, cfg):
        q = cfg["qos"]["video"]
        self.quality     = q["jpeg_quality"]
        self.min_quality = q["min_jpeg_quality"]
        self.fps         = q["base_fps"]
        self.min_fps     = q["min_fps"]
        self.base_fps    = q["base_fps"]
        self._last       = 0.0

    def should_send(self) -> bool:
        now = time.time()
        if now - self._last >= 1.0 / self.fps:
            self._last = now
            return True
        return False

    def encode(self, frame) -> bytes | None:
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, int(self.quality)]
        )
        return buf.tobytes() if ok else None

    def degrade(self):
        self.quality = max(self.min_quality, self.quality - 10)
        self.fps     = max(self.min_fps, self.fps - 2)

    def recover(self):
        self.quality = min(70, self.quality + 5)
        self.fps     = min(self.base_fps, self.fps + 1)


# ---------------------------------------------------------------------------
# Service Discovery
# ---------------------------------------------------------------------------

class DiscoveryClient:
    def __init__(self, cfg):
        self._host = cfg["registry"]["host"]
        self._port = cfg["registry"]["port"]

    def query_room(self, room: str, timeout_ms: int = 2000) -> dict | None:
        ctx  = zmq.Context.instance()
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
        sock.connect(f"tcp://{self._host}:{self._port}")
        try:
            sock.send_string(json.dumps({"type": "query_room", "room": room}))
            resp = json.loads(sock.recv_string())
            return resp.get("broker") if resp.get("status") == "ok" else None
        except Exception:
            return None
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# Painel de vídeo reutilizável
# ---------------------------------------------------------------------------

class VideoPanel(tk.Frame):
    """Exibe frames de vídeo ou um placeholder com texto."""

    PLACEHOLDER_COLOR = "#0d0d1a"

    def __init__(self, parent, width: int, height: int, label: str = "", **kw):
        super().__init__(parent, bg=C_PANEL,
                         highlightbackground=C_BORDER, highlightthickness=1,
                         **kw)
        self.W = width
        self.H = height
        self._label_text = label
        self._photo = None
        self._placeholder = self._make_placeholder("Sem vídeo")

        self._canvas = tk.Canvas(self, width=width, height=height,
                                 bg=self.PLACEHOLDER_COLOR,
                                 highlightthickness=0)
        self._canvas.pack()
        self._img_id = self._canvas.create_image(0, 0, anchor="nw",
                                                  image=self._placeholder)
        if label:
            self._canvas.create_text(
                6, height - 6, anchor="sw",
                text=label, fill=C_DIM, font=FONT_SMALL,
            )

    def _make_placeholder(self, text: str):
        if not _PIL_OK:
            return None
        img = Image.new("RGB", (self.W, self.H), color=self.PLACEHOLDER_COLOR)
        draw = ImageDraw.Draw(img)
        draw.text((self.W // 2, self.H // 2), text,
                  fill=C_DIM, anchor="mm")
        photo = ImageTk.PhotoImage(img)
        return photo

    def show_frame(self, jpeg_bytes: bytes):
        """Atualiza com frame JPEG recebido."""
        if not _PIL_OK or not _VIDEO_OK:
            return
        try:
            arr   = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(frame_rgb).resize(
                (self.W, self.H), Image.LANCZOS
            )
            photo = ImageTk.PhotoImage(img)
            self._canvas.itemconfigure(self._img_id, image=photo)
            self._photo = photo          # evita coleta pelo GC
        except Exception:
            pass

    def show_camera_frame(self, frame):
        """Atualiza com frame numpy (BGR) da câmera local."""
        if not _PIL_OK:
            return
        try:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(rgb).resize(
                (self.W, self.H), Image.LANCZOS
            )
            photo = ImageTk.PhotoImage(img)
            self._canvas.itemconfigure(self._img_id, image=photo)
            self._photo = photo
        except Exception:
            pass

    def show_placeholder(self, text: str = "Sem vídeo"):
        ph = self._make_placeholder(text)
        if ph:
            self._canvas.itemconfigure(self._img_id, image=ph)
            self._placeholder = ph


# ---------------------------------------------------------------------------
# Aplicação principal
# ---------------------------------------------------------------------------

class ConferenceApp:

    # Dimensões dos painéis de vídeo
    REM_W, REM_H = 640, 400   # vídeo remoto principal
    SELF_W, SELF_H = 200, 150  # self-preview

    def __init__(self):
        self.cfg       = _load_cfg()
        self.client_id = str(uuid.uuid4())
        self.username  = None
        self.room      = None
        self.broker    = None

        # Estado dos controles
        self.muted        = False
        self.camera_on    = True
        self.speaker_on   = True

        # Sincronização entre threads e GUI
        self._stop    = threading.Event()
        self._gui_q:  queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._text_qos  = TextQoS(self.cfg)
        self._video_qos = VideoQoS(self.cfg) if _VIDEO_OK else None
        self._discovery = DiscoveryClient(self.cfg)

        # Audio callback buffering
        self.recv_queue = queue.Queue()  # Buffers received audio frames for output callback
        self.p = None                    # PyAudio instance
        self.audio_stream = None         # Combined input/output stream with callbacks

        # Tkinter
        self.root = tk.Tk()
        self.root.title("sd-meeting")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_login()
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Tela de login
    # ------------------------------------------------------------------

    def _build_login(self):
        self.root.geometry("420x340")
        self._login_frame = tk.Frame(self.root, bg=C_BG)
        self._login_frame.pack(fill="both", expand=True)

        # Logo / título
        tk.Label(self._login_frame, text="📹 sd-meeting",
                 font=("Segoe UI", 22, "bold"),
                 fg=C_GREEN, bg=C_BG).pack(pady=(40, 4))
        tk.Label(self._login_frame, text="Videoconferência distribuída com ZeroMQ",
                 font=FONT_SMALL, fg=C_DIM, bg=C_BG).pack(pady=(0, 30))

        form = tk.Frame(self._login_frame, bg=C_BG)
        form.pack()

        def _row(label, widget_fn, **kw):
            r = tk.Frame(form, bg=C_BG)
            r.pack(fill="x", pady=6)
            tk.Label(r, text=label, font=FONT_UI, fg=C_DIM,
                     bg=C_BG, width=10, anchor="e").pack(side="left")
            w = widget_fn(r, **kw)
            w.pack(side="left", padx=(8, 0))
            return w

        self._var_user = tk.StringVar(value="alice")
        self._var_room = tk.StringVar(value="A")

        entry_style = dict(
            bg=C_SURFACE, fg=C_TEXT,
            insertbackground=C_TEXT,
            relief="flat", font=FONT_UI,
            width=20,
        )
        self._entry_user = _row("Usuário:", tk.Entry,
                                textvariable=self._var_user, **entry_style)

        # Combobox de salas
        rooms = self.cfg["cluster"]["all_rooms"]
        room_cb = ttk.Combobox(form, textvariable=self._var_room,
                               values=rooms, width=18, state="readonly",
                               font=FONT_UI)
        r = tk.Frame(form, bg=C_BG)
        r.pack(fill="x", pady=6)
        tk.Label(r, text="Sala:", font=FONT_UI, fg=C_DIM,
                 bg=C_BG, width=10, anchor="e").pack(side="left")
        room_cb.pack(side="left", padx=(8, 0))

        # Status
        self._login_status = tk.Label(self._login_frame, text="",
                                      font=FONT_SMALL, fg=C_ACCENT, bg=C_BG)
        self._login_status.pack(pady=(16, 0))

        # Botão entrar
        btn = tk.Button(
            self._login_frame, text="  Entrar  ", font=FONT_BOLD,
            bg=C_GREEN, fg=C_BG, relief="flat", cursor="hand2",
            activebackground="#00b89a", activeforeground=C_BG,
            command=self._do_login,
        )
        btn.pack(pady=(8, 0))
        self._entry_user.bind("<Return>", lambda e: self._do_login())

    def _do_login(self):
        username = self._var_user.get().strip()
        room     = self._var_room.get().strip().upper()
        if not username:
            self._login_status.config(text="Nome de usuário obrigatório.")
            return
        if room not in self.cfg["cluster"]["all_rooms"]:
            self._login_status.config(text="Sala inválida.")
            return
        self.username = username
        self.room     = room
        self._login_status.config(text="Conectando...", fg=C_DIM)
        self.root.update()
        threading.Thread(target=self._connect_and_launch, daemon=True).start()

    def _connect_and_launch(self):
        for i in range(15):
            info = self._discovery.query_room(self.room)
            if info:
                self.broker = info
                self.root.after(0, self._switch_to_conference)
                return
            self.root.after(0, lambda i=i: self._login_status.config(
                text=f"Aguardando broker... ({i+1}/15)"))
            time.sleep(1)
        self.root.after(0, lambda: self._login_status.config(
            text="Nenhum broker disponível.", fg=C_ACCENT))

    # ------------------------------------------------------------------
    # Tela de conferência
    # ------------------------------------------------------------------

    def _switch_to_conference(self):
        try:
            self._login_frame.destroy()
            self.root.geometry(f"{self.REM_W + self.SELF_W + 260}x"
                               f"{self.REM_H + self.SELF_H + 120}")
            self._build_conference()
            self._start_zmq()
            self.root.after(33, self._poll_gui_queue)
        except Exception:
            err = traceback.format_exc()
            print(err, file=sys.stderr)
            messagebox.showerror("Erro ao entrar na sala", err)

    def _build_conference(self):
        self._conf_frame = tk.Frame(self.root, bg=C_BG)
        self._conf_frame.pack(fill="both", expand=True)

        # ── Barra superior ─────────────────────────────────────────────
        top = tk.Frame(self._conf_frame, bg=C_PANEL, height=40)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text=f"[SD-MEETING]  Sala  {self.room}",
                 font=FONT_BOLD, fg=C_GREEN, bg=C_PANEL).pack(side="left", padx=12)
        tk.Label(top, text=f"[{self.username}]",
                 font=FONT_UI, fg=C_TEXT, bg=C_PANEL).pack(side="left", padx=4)

        self._status_lbl = tk.Label(top, text="● Conectando...",
                                    font=FONT_SMALL, fg=C_ACCENT, bg=C_PANEL)
        self._status_lbl.pack(side="left", padx=16)

        tk.Button(top, text="Sair", font=FONT_BOLD,
                  bg=C_ACCENT, fg="white", relief="flat", cursor="hand2",
                  activebackground="#c73652", activeforeground="white",
                  command=self._leave).pack(side="right", padx=10, pady=5)

        # ── Área principal ─────────────────────────────────────────────
        main = tk.Frame(self._conf_frame, bg=C_BG)
        main.pack(fill="both", expand=True)

        # Coluna esquerda: vídeo
        left = tk.Frame(main, bg=C_BG)
        left.pack(side="left", fill="both", padx=6, pady=6)

        self._video_remote = VideoPanel(left, self.REM_W, self.REM_H,
                                        label="Vídeo remoto")
        self._video_remote.pack()

        self._video_self = VideoPanel(left, self.SELF_W, self.SELF_H,
                                      label=f"Você ({self.username})")
        self._video_self.pack(pady=(4, 0))

        # Coluna direita: membros + chat
        right = tk.Frame(main, bg=C_BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=6)

        # Membros
        members_frame = tk.LabelFrame(right, text=" Membros ",
                                      bg=C_PANEL, fg=C_DIM,
                                      font=FONT_SMALL, relief="flat",
                                      highlightbackground=C_BORDER,
                                      highlightthickness=1)
        members_frame.pack(fill="x", pady=(0, 6))

        self._members_list = tk.Listbox(
            members_frame, bg=C_PANEL, fg=C_TEXT,
            selectbackground=C_SURFACE, font=FONT_UI,
            relief="flat", height=5, borderwidth=0,
        )
        self._members_list.pack(fill="x", padx=4, pady=4)

        # Chat
        chat_frame = tk.LabelFrame(right, text=" Chat ",
                                   bg=C_PANEL, fg=C_DIM,
                                   font=FONT_SMALL, relief="flat",
                                   highlightbackground=C_BORDER,
                                   highlightthickness=1)
        chat_frame.pack(fill="both", expand=True)

        self._chat_area = scrolledtext.ScrolledText(
            chat_frame, bg=C_PANEL, fg=C_TEXT,
            font=FONT_MONO, relief="flat",
            state="disabled", wrap="word",
            insertbackground=C_TEXT,
        )
        self._chat_area.pack(fill="both", expand=True, padx=4, pady=4)
        self._chat_area.tag_config("me",    foreground=C_CHAT_ME)
        self._chat_area.tag_config("other", foreground=C_CHAT_OT)
        self._chat_area.tag_config("sys",   foreground=C_DIM,
                                   font=FONT_SMALL)
        self._chat_area.tag_config("ts",    foreground=C_DIM,
                                   font=FONT_SMALL)

        # Input de texto
        inp_row = tk.Frame(chat_frame, bg=C_PANEL)
        inp_row.pack(fill="x", padx=4, pady=(0, 4))

        self._chat_entry = tk.Entry(
            inp_row, bg=C_SURFACE, fg=C_TEXT,
            insertbackground=C_TEXT, font=FONT_UI,
            relief="flat",
        )
        self._chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._chat_entry.bind("<Return>", lambda e: (self._send_text(), "break"))

        tk.Button(inp_row, text="Enviar", font=FONT_BOLD,
                  bg=C_GREEN, fg=C_BG, relief="flat", cursor="hand2",
                  activebackground="#00b89a",
                  command=self._send_text).pack(side="left")

        # ── Barra de controles ─────────────────────────────────────────
        self._build_controls()

    def _build_controls(self):
        bar = tk.Frame(self._conf_frame, bg=C_SURFACE, height=54)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        def _ctrl_btn(parent, text, cmd, color=C_TEXT):
            b = tk.Button(parent, text=text, font=("Segoe UI", 11),
                          bg=C_SURFACE, fg=color, relief="flat",
                          cursor="hand2", width=13,
                          activebackground=C_BG, activeforeground=color,
                          command=cmd)
            b.pack(side="left", padx=6, pady=8)
            return b

        center = tk.Frame(bar, bg=C_SURFACE)
        center.pack(expand=True)

        self._btn_mute    = _ctrl_btn(center, "[MIC] Mutar",     self._toggle_mute)
        self._btn_camera  = _ctrl_btn(center, "[CAM] Camera",    self._toggle_camera)
        self._btn_speaker = _ctrl_btn(center, "[SPK] Audio on",  self._toggle_speaker)

        # Indicador de qualidade de vídeo
        self._quality_lbl = tk.Label(bar, text="",
                                     font=FONT_SMALL, fg=C_DIM, bg=C_SURFACE)
        self._quality_lbl.pack(side="right", padx=10)

    # ------------------------------------------------------------------
    # Controles
    # ------------------------------------------------------------------

    def _toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self._btn_mute.config(text="[MIC] Mutado", fg=C_ACCENT, bg="#2a1020")
        else:
            self._btn_mute.config(text="[MIC] Mutar",  fg=C_TEXT,   bg=C_SURFACE)

    def _toggle_camera(self):
        self.camera_on = not self.camera_on
        if self.camera_on:
            self._btn_camera.config(text="[CAM] Camera",   fg=C_TEXT,   bg=C_SURFACE)
        else:
            self._btn_camera.config(text="[CAM] Desligada",fg=C_ACCENT, bg="#2a1020")
            self._video_self.show_placeholder("📷 Câmera desligada")

    def _toggle_speaker(self):
        self.speaker_on = not self.speaker_on
        if self.speaker_on:
            self._btn_speaker.config(text="[SPK] Audio on",  fg=C_TEXT,   bg=C_SURFACE)
        else:
            self._btn_speaker.config(text="[SPK] Audio off", fg=C_ACCENT, bg="#2a1020")

    def _send_text(self):
        content = self._chat_entry.get().strip()
        if not content or not hasattr(self, "_sock_text_push"):
            return
        self._chat_entry.delete(0, "end")
        self._text_qos.send({
            "v": 1, "type": "text",
            "msg_id":    str(uuid.uuid4()),
            "room":      self.room,
            "sender_id": self.client_id,
            "username":  self.username,
            "content":   content,
            "ts":        time.time(),
        })
        # Exibe no chat local imediatamente
        self._append_chat(self.username, content, time.time(), is_me=True)

    def _leave(self):
        if messagebox.askyesno("Sair", "Deseja sair da sala?",
                               parent=self.root):
            self._stop.set()
            self._cleanup_sockets()
            self._conf_frame.destroy()
            self._build_login()
            self.root.geometry("420x340")
            self._stop.clear()
            self.broker    = None
            self.username  = None
            self.room      = None
            self._text_qos = TextQoS(self.cfg)

    def _on_close(self):
        self._stop.set()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Atualização da GUI (sempre chamado no thread principal via after)
    # ------------------------------------------------------------------

    def _poll_gui_queue(self):
        try:
            while not self._gui_q.empty():
                item = self._gui_q.get_nowait()
                t = item.get("type")
                if t == "text":
                    self._append_chat(item["username"], item["content"],
                                      item["ts"], is_me=False)
                elif t == "presence":
                    self._update_members(item["members"])
                elif t == "video_remote":
                    self._video_remote.show_frame(item["jpeg"])
                    if self._video_qos:
                        self._quality_lbl.config(
                            text=f"Q:{int(self._video_qos.quality)}% "
                                 f"{int(self._video_qos.fps)}fps"
                        )
                elif t == "video_self":
                    if self.camera_on:
                        self._video_self.show_camera_frame(item["frame"])
                elif t == "status":
                    self._status_lbl.config(text=item["msg"],
                                            fg=item.get("color", C_GREEN))
                elif t == "reconnecting":
                    self._status_lbl.config(text="⚠ Reconectando...",
                                            fg=C_ACCENT)
                    self._video_remote.show_placeholder("Reconectando...")
                    self._append_sys("Broker desconectado. Reconectando...")
                elif t == "reconnected":
                    self._status_lbl.config(text="● Conectado", fg=C_GREEN)
                    self._append_sys("Reconectado com sucesso!")
        except Exception:
            pass
        if not self._stop.is_set() or not self._gui_q.empty():
            self.root.after(33, self._poll_gui_queue)

    def _append_chat(self, username: str, content: str, ts: float,
                     is_me: bool = False):
        if not hasattr(self, "_chat_area"):
            return
        t = self._chat_area
        t.config(state="normal")
        hh = time.strftime("%H:%M:%S", time.localtime(ts))
        t.insert("end", f"[{hh}] ", "ts")
        tag = "me" if is_me else "other"
        t.insert("end", f"{username}: ", tag)
        t.insert("end", content + "\n", "")
        t.config(state="disabled")
        t.see("end")

    def _append_sys(self, msg: str):
        if not hasattr(self, "_chat_area"):
            return
        t = self._chat_area
        t.config(state="normal")
        t.insert("end", f"── {msg}\n", "sys")
        t.config(state="disabled")
        t.see("end")

    def _update_members(self, members: dict):
        if not hasattr(self, "_members_list"):
            return
        self._members_list.delete(0, "end")
        for cid, uname in members.items():
            marker = " (você)" if cid == self.client_id else ""
            self._members_list.insert("end", f"  ● {uname}{marker}")

    def _set_status(self, msg: str, color: str = C_GREEN):
        if hasattr(self, "_status_lbl"):
            self._status_lbl.config(text=msg, fg=color)

    # ------------------------------------------------------------------
    # ZeroMQ — conexão e threads
    # ------------------------------------------------------------------

    def _make_sockets(self) -> dict:
        h = self.broker["host"]
        P = self.broker["ports"]
        ctx = zmq.Context.instance()
        s = {}

        s["text_push"] = ctx.socket(zmq.PUSH)
        s["text_push"].connect(f"tcp://{h}:{P['text_pull']}")

        s["text_sub"] = ctx.socket(zmq.SUB)
        s["text_sub"].connect(f"tcp://{h}:{P['text_pub']}")
        s["text_sub"].setsockopt_string(zmq.SUBSCRIBE, f"text:{self.room}")

        s["audio_push"] = ctx.socket(zmq.PUSH)
        s["audio_push"].connect(f"tcp://{h}:{P['audio_pull']}")

        s["audio_sub"] = ctx.socket(zmq.SUB)
        s["audio_sub"].connect(f"tcp://{h}:{P['audio_pub']}")
        s["audio_sub"].setsockopt_string(zmq.SUBSCRIBE, f"audio:{self.room}")

        s["video_push"] = ctx.socket(zmq.PUSH)
        s["video_push"].connect(f"tcp://{h}:{P['video_pull']}")

        s["video_sub"] = ctx.socket(zmq.SUB)
        s["video_sub"].connect(f"tcp://{h}:{P['video_pub']}")
        s["video_sub"].setsockopt_string(zmq.SUBSCRIBE, f"video:{self.room}")

        s["ctrl"] = ctx.socket(zmq.DEALER)
        s["ctrl"].setsockopt_string(zmq.IDENTITY, self.client_id)
        s["ctrl"].connect(f"tcp://{h}:{P['control']}")

        s["hb_sub"] = ctx.socket(zmq.SUB)
        s["hb_sub"].connect(f"tcp://{h}:{P['heartbeat']}")
        s["hb_sub"].setsockopt_string(zmq.SUBSCRIBE, "hb")

        return s

    def _close_sockets(self, socks: dict):
        for sock in socks.values():
            try:
                sock.setsockopt(zmq.LINGER, 0)
                sock.close()
            except Exception:
                pass

    def _cleanup_sockets(self):
        if hasattr(self, "_socks"):
            self._close_sockets(self._socks)
            del self._socks

    def _do_zmq_login(self, ctrl: zmq.Socket) -> bool:
        msg = json.dumps({
            "v": 1, "type": "login",
            "sender_id": self.client_id,
            "username":  self.username,
            "room":      self.room,
        }).encode()
        ctrl.send(msg)
        poller = zmq.Poller()
        poller.register(ctrl, zmq.POLLIN)
        evts = dict(poller.poll(timeout=4000))
        if ctrl in evts:
            resp = json.loads(ctrl.recv())
            if resp.get("type") == "login_ack":
                members = resp.get("members", {})
                self._gui_q.put({"type": "presence", "members": members})
                self._gui_q.put({"type": "status", "msg": "● Conectado",
                                 "color": C_GREEN})
                return True
        return False

    def _start_zmq(self):
        self._stop.clear()
        self._socks = self._make_sockets()
        self._sock_text_push = self._socks["text_push"]

        if not self._do_zmq_login(self._socks["ctrl"]):
            self._gui_q.put({"type": "status",
                             "msg": "⚠ Falha no login", "color": C_ACCENT})
            return

        # Start audio stream with callbacks (replaces explicit audio threads)
        self._start_audio_stream()

        specs = [
            ("text-send",  self._th_text_send,  self._socks["text_push"]),
            ("text-recv",  self._th_text_recv,  self._socks["text_sub"]),
            ("ctrl-recv",  self._th_ctrl_recv,  self._socks["ctrl"]),
            ("audio-zmq-recv", self._th_audio_zmq_recv, self._socks["audio_sub"]),
            ("video-send", self._th_video_send, self._socks["video_push"]),
            ("video-recv", self._th_video_recv, self._socks["video_sub"]),
            ("hb-monitor", self._th_hb_monitor, self._socks["hb_sub"]),
        ]
        self._threads = []
        for name, fn, sock in specs:
            t = threading.Thread(target=fn, args=(sock,),
                                 name=name, daemon=True)
            t.start()
            self._threads.append(t)

        t = threading.Thread(target=self._text_qos.retry_loop,
                             args=(self._stop,), daemon=True)
        t.start()
        self._threads.append(t)

    def _start_audio_stream(self):
        """Initialize PyAudio streams with input/output callbacks for ZMQ integration."""
        if not _AUDIO_OK or sys.platform == "win32":
            return
        
        cfg = self.cfg["client"]["audio"]
        try:
            self.p = pyaudio.PyAudio()
        except Exception as e:
            print(f"[Audio] Failed to initialize PyAudio: {e}", file=sys.stderr)
            return
        
        try:
            # Create a bidirectional stream: input captures mic, output plays received audio
            self.audio_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=cfg["channels"],
                rate=cfg["rate"],
                input=True,
                output=True,
                frames_per_buffer=cfg["chunk"],
                stream_callback=self._audio_callback
            )
            self.audio_stream.start_stream()
        except Exception as e:
            print(f"[Audio] Failed to open stream: {e}", file=sys.stderr)
            if self.p:
                self.p.terminate()
                self.p = None
            return

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """
        Bidirectional PyAudio callback: captures input, sends to ZMQ; receives from ZMQ, outputs.
        Args:
            in_data: Captured microphone PCM bytes
            frame_count: Number of frames in in_data
            time_info: Stream timing info (unused)
            status: Stream status flags (unused)
        Returns:
            Tuple of (out_data, paContinue_flag) for output stream
        """
        # Process input: send to network if not muted
        if hasattr(self, "_socks") and hasattr(self, "_socks") and "audio_push" in self._socks:
            if not self.muted:
                try:
                    meta = json.dumps({
                        "v": 1, "type": "audio",
                        "room": self.room, "sender_id": self.client_id,
                    }).encode()
                    self._socks["audio_push"].send_multipart([meta, in_data], flags=zmq.NOBLOCK)
                except Exception:
                    pass
        
        # Process output: return buffered audio from network or silence
        out_data = b''
        if self.speaker_on:
            try:
                out_data = self.recv_queue.get_nowait()
            except queue.Empty:
                # No buffered audio; return silence
                out_data = b'\x00' * len(in_data)
        else:
            # Speaker is off; return silence
            out_data = b'\x00' * len(in_data)
        
        return (out_data, pyaudio.paContinue)

    # ------------------------------------------------------------------
    # Threads ZMQ
    # ------------------------------------------------------------------

    def _th_text_send(self, sock: zmq.Socket):
        while not self._stop.is_set():
            data = self._text_qos.get_next(timeout=0)
            if data:
                try:
                    sock.send(data, flags=zmq.NOBLOCK)
                except Exception:
                    pass
            else:
                self._stop.wait(0.05)

    def _th_text_recv(self, sock: zmq.Socket):
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        while not self._stop.is_set():
            evts = dict(poller.poll(timeout=500))
            if sock not in evts:
                continue
            frames = sock.recv_multipart()
            if len(frames) < 2:
                continue
            try:
                msg = json.loads(frames[1])
            except Exception:
                continue
            t = msg.get("type")
            if t == "text" and msg.get("sender_id") != self.client_id:
                self._gui_q.put({
                    "type":     "text",
                    "username": msg.get("username", "?"),
                    "content":  msg.get("content", ""),
                    "ts":       msg.get("ts", time.time()),
                })
            elif t == "presence":
                self._gui_q.put({
                    "type":    "presence",
                    "members": msg.get("members", {}),
                })

    def _th_ctrl_recv(self, sock: zmq.Socket):
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        while not self._stop.is_set():
            evts = dict(poller.poll(timeout=500))
            if sock not in evts:
                continue
            try:
                msg = json.loads(sock.recv())
                if msg.get("type") == "text_ack":
                    self._text_qos.ack(msg.get("msg_id", ""))
            except Exception:
                pass

    def _th_audio_zmq_recv(self, sock: zmq.Socket):
        """Lightweight thread: polls ZMQ SUB socket and queues audio frames for output callback."""
        if not _AUDIO_OK or sys.platform == "win32":
            return
        
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        
        while not self._stop.is_set():
            evts = dict(poller.poll(timeout=500))
            if sock not in evts:
                continue
            
            try:
                frames = sock.recv_multipart()
                if len(frames) < 3:
                    continue
                
                # Parse metadata
                try:
                    meta = json.loads(frames[1])
                except Exception:
                    continue
                
                # Ignore own audio
                if meta.get("sender_id") == self.client_id:
                   continue
                
                # Queue the audio frame (frames[2] is the PCM data)
                # Use non-blocking put to avoid starving the audio callback
                try:
                    self.recv_queue.put_nowait(frames[2])
                except queue.Full:
                    # Queue overflow; drop oldest frame to make room
                    try:
                        self.recv_queue.get_nowait()
                        self.recv_queue.put_nowait(frames[2])
                    except Exception:
                        pass
            
            except Exception:
                pass

    def _th_video_send(self, sock: zmq.Socket):
        if not _VIDEO_OK or self._video_qos is None:
            return
        vcfg = self.cfg["client"]["video"]
        try:
            cap = cv2.VideoCapture(vcfg["device_index"])
        except Exception:
            return
        if not cap.isOpened():
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  vcfg["frame_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, vcfg["frame_height"])
        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret:
                continue
            # Atualiza self-preview na GUI
            self._gui_q.put({"type": "video_self", "frame": frame.copy()})
            if not self.camera_on:
                time.sleep(0.05)
                continue
            if not self._video_qos.should_send():
                time.sleep(0.01)
                continue
            jpeg = self._video_qos.encode(frame)
            if jpeg is None:
                continue
            meta = json.dumps({
                "v": 1, "type": "video",
                "room": self.room, "sender_id": self.client_id,
                "quality": int(self._video_qos.quality),
            }).encode()
            try:
                sock.send_multipart([meta, jpeg], flags=zmq.NOBLOCK)
            except zmq.Again:
                self._video_qos.degrade()
        cap.release()

    def _th_video_recv(self, sock: zmq.Socket):
        if not _VIDEO_OK:
            return
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        frame_count = 0
        while not self._stop.is_set():
            evts = dict(poller.poll(timeout=500))
            if sock not in evts:
                continue
            frames = sock.recv_multipart()
            if len(frames) < 3:
                continue
            try:
                meta = json.loads(frames[1])
            except Exception:
                continue
            if meta.get("sender_id") == self.client_id:
                continue
            self._gui_q.put({"type": "video_remote", "jpeg": frames[2]})
            frame_count += 1
            if frame_count % 30 == 0 and self._video_qos:
                self._video_qos.recover()

    def _th_hb_monitor(self, sock: zmq.Socket):
        timeout  = self.cfg["cluster"]["heartbeat_timeout"]
        last_hb  = time.time()
        poller   = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        while not self._stop.is_set():
            evts = dict(poller.poll(timeout=1000))
            if sock in evts:
                try:
                    sock.recv_multipart()
                    last_hb = time.time()
                except Exception:
                    pass
            elif time.time() - last_hb > timeout:
                self._gui_q.put({"type": "reconnecting"})
                self._stop.set()
                threading.Thread(target=self._reconnect, daemon=True).start()
                return

    def _reconnect(self):
        self._cleanup_sockets()
        time.sleep(2)
        for _ in range(30):
            info = self._discovery.query_room(self.room)
            if info:
                self.broker = info
                self._start_zmq()
                self._gui_q.put({"type": "reconnected"})
                self.root.after(0, lambda: self.root.after(33, self._poll_gui_queue))
                return
            time.sleep(1)
        self._gui_q.put({"type": "status",
                         "msg": "⚠ Sem broker disponível", "color": C_ACCENT})


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not _PIL_OK:
        print("Instale Pillow para exibir vídeo:  pip install Pillow")
    ConferenceApp()
