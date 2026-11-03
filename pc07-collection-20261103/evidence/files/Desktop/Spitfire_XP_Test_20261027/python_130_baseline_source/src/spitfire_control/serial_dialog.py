"""Tk raw RS-232 service terminal."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .serial_service import RawSerialSession, SerialEvent, SerialServiceError, SerialSettings, encode_transmission


NAVY = "#173a57"
WARNING = "#fff4d6"
WARNING_TEXT = "#72520a"
TERMINAL = "#10212b"
TERMINAL_TEXT = "#d9edf2"
RX_COLOR = "#8de4ff"
TX_COLOR = "#ffd27a"
ERROR_COLOR = "#ff8585"


class RawSerialDialog:
    """A deliberately separate, byte-oriented serial diagnostics window."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        session: RawSerialSession | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.master = master
        self.session = session or RawSerialSession()
        self.on_close = on_close
        self.records: list[SerialEvent] = []
        self.rx_bytes = 0
        self.tx_bytes = 0
        self._after_id: str | None = None

        self.window = tk.Toplevel(master)
        self.window.title("Spitfire · Raw RS-232 Service Mode")
        self.window.configure(bg="#e8edf2")
        width = min(1040, max(860, self.window.winfo_screenwidth() - 40))
        height = min(680, max(560, self.window.winfo_screenheight() - 80))
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(min(860, width), min(560, height))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(3, weight=1)

        default_port = "COM1" if os.name == "nt" else "/dev/ttyUSB0"
        self.port_var = tk.StringVar(value=default_port)
        self.baud_var = tk.StringVar(value="19200")
        self.data_bits_var = tk.StringVar(value="8")
        self.parity_var = tk.StringVar(value="N")
        self.stop_bits_var = tk.StringVar(value="1")
        self.flow_var = tk.StringVar(value="None")
        self.timeout_var = tk.StringVar(value="0.10")
        self.dtr_var = tk.BooleanVar(value=False)
        self.rts_var = tk.BooleanVar(value=False)
        self.tx_mode_var = tk.StringVar(value="ASCII")
        self.terminator_var = tk.StringVar(value="CRLF")
        self.display_mode_var = tk.StringVar(value="ASCII + HEX")
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="DISCONNECTED")
        self.counter_var = tk.StringVar(value="RX 0 B  ·  TX 0 B")

        self._build()
        self.refresh_ports()
        self._after_id = self.window.after(50, self._poll)

    def _build(self) -> None:
        header = tk.Frame(self.window, bg=NAVY, padx=20, pady=13)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="RAW RS-232 SERVICE", bg=NAVY, fg="white", font=("Segoe UI Semibold", 17)).pack(side="left")
        tk.Label(header, textvariable=self.status_var, bg=NAVY, fg="#bfe9ff", font=("Consolas", 10, "bold")).pack(side="right")

        warning = tk.Label(
            self.window,
            text="SERVICE MODE  ·  Bytes are sent without ECLIPSE framing, command validation, or ARM protection.",
            bg=WARNING,
            fg=WARNING_TEXT,
            anchor="w",
            padx=20,
            pady=8,
            font=("Segoe UI", 9, "bold"),
        )
        warning.grid(row=1, column=0, sticky="ew")

        settings = ttk.LabelFrame(self.window, text="PORT SETTINGS", padding=(12, 9), style="TLabelframe")
        settings.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 8))
        fields = ttk.Frame(settings, style="Card.TFrame")
        fields.pack(fill="x")

        self.port_box = self._field(fields, "Port", self.port_var, (), 0, width=18, editable=True)
        ttk.Button(fields, text="REFRESH", width=7, command=self.refresh_ports).grid(row=1, column=1, sticky="e", padx=(0, 9))
        self._field(fields, "Baud", self.baud_var, ("1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400"), 2, width=11, editable=True)
        self._field(fields, "Data", self.data_bits_var, ("5", "6", "7", "8"), 3, width=7)
        self._field(fields, "Parity", self.parity_var, ("N", "E", "O", "M", "S"), 4, width=7)
        self._field(fields, "Stop", self.stop_bits_var, ("1", "1.5", "2"), 5, width=7)
        self._field(fields, "Flow control", self.flow_var, ("None", "XON/XOFF", "RTS/CTS", "DSR/DTR"), 6, width=12)
        self._field(fields, "Read timeout", self.timeout_var, ("0.05", "0.10", "0.25", "0.50", "1.00"), 7, width=10, editable=True)

        controls = ttk.Frame(settings, style="Card.TFrame")
        controls.pack(fill="x", pady=(9, 0))
        ttk.Checkbutton(controls, text="DTR", variable=self.dtr_var, style="Card.TCheckbutton", command=self._set_lines).pack(side="left")
        ttk.Checkbutton(controls, text="RTS", variable=self.rts_var, style="Card.TCheckbutton", command=self._set_lines).pack(side="left", padx=(10, 0))
        ttk.Label(controls, text="Legacy service default: COM1 · 19200 · 8-N-1", style="CardTitle.TLabel").pack(side="left", padx=18)
        self.connect_button = ttk.Button(controls, text="CONNECT", style="Accent.TButton", command=self.toggle_connection)
        self.connect_button.pack(side="right")

        terminal_card = ttk.LabelFrame(self.window, text="BYTE MONITOR", padding=(10, 8), style="TLabelframe")
        terminal_card.grid(row=3, column=0, sticky="nsew", padx=16, pady=8)
        toolbar = ttk.Frame(terminal_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 7))
        ttk.Label(toolbar, text="View", style="CardText.TLabel").pack(side="left")
        display = ttk.Combobox(toolbar, textvariable=self.display_mode_var, values=("ASCII + HEX", "ASCII", "HEX"), state="readonly", width=13)
        display.pack(side="left", padx=(7, 14))
        ttk.Checkbutton(toolbar, text="Auto scroll", variable=self.autoscroll_var, style="Card.TCheckbutton").pack(side="left")
        ttk.Label(toolbar, textvariable=self.counter_var, style="CardTitle.TLabel").pack(side="right", padx=(10, 0))
        ttk.Button(toolbar, text="Save log", command=self.save_log).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side="right")

        body = tk.Frame(terminal_card, bg=TERMINAL)
        body.pack(fill="both", expand=True)
        self.terminal = tk.Text(
            body,
            bg=TERMINAL,
            fg=TERMINAL_TEXT,
            insertbackground="white",
            selectbackground="#31586b",
            relief="flat",
            padx=12,
            pady=10,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
        )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.terminal.yview)
        xscroll = ttk.Scrollbar(terminal_card, orient="horizontal", command=self.terminal.xview)
        self.terminal.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.terminal.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(fill="x")
        self.terminal.tag_configure("rx", foreground=RX_COLOR)
        self.terminal.tag_configure("tx", foreground=TX_COLOR)
        self.terminal.tag_configure("status", foreground="#9fb0b9")
        self.terminal.tag_configure("error", foreground=ERROR_COLOR)

        transmit = ttk.LabelFrame(self.window, text="TRANSMIT", padding=(12, 9), style="TLabelframe")
        transmit.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 14))
        ttk.Label(transmit, text="Format", style="CardText.TLabel").pack(side="left")
        ttk.Combobox(transmit, textvariable=self.tx_mode_var, values=("ASCII", "HEX"), state="readonly", width=7).pack(side="left", padx=(6, 10))
        ttk.Label(transmit, text="Ending", style="CardText.TLabel").pack(side="left")
        ttk.Combobox(transmit, textvariable=self.terminator_var, values=("NONE", "CR", "LF", "CRLF"), state="readonly", width=7).pack(side="left", padx=(6, 10))
        self.tx_entry = ttk.Entry(transmit)
        self.tx_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.tx_entry.bind("<Return>", self.send)
        self.send_button = ttk.Button(transmit, text="SEND", style="Accent.TButton", command=self.send, state="disabled")
        self.send_button.pack(side="right")

    @staticmethod
    def _field(parent: ttk.Frame, label: str, variable: tk.StringVar, values: tuple[str, ...], column: int, *, width: int, editable: bool = False) -> ttk.Combobox:
        ttk.Label(parent, text=label, style="CardTitle.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 9))
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="normal" if editable else "readonly", width=width)
        box.grid(row=1, column=column, sticky="w", padx=(0, 9))
        return box

    def refresh_ports(self) -> None:
        ports = self.session.list_ports()
        current = self.port_var.get().strip()
        if current and current not in ports:
            ports.insert(0, current)
        self.port_box.configure(values=ports)
        if ports and not current:
            self.port_var.set(ports[0])

    def _settings(self) -> SerialSettings:
        try:
            stopbits = float(self.stop_bits_var.get())
            flow = self.flow_var.get()
            return SerialSettings(
                port=self.port_var.get().strip(),
                baudrate=int(self.baud_var.get()),
                bytesize=int(self.data_bits_var.get()),
                parity=self.parity_var.get(),
                stopbits=stopbits,
                timeout=float(self.timeout_var.get()),
                xonxoff=flow == "XON/XOFF",
                rtscts=flow == "RTS/CTS",
                dsrdtr=flow == "DSR/DTR",
                dtr=self.dtr_var.get(),
                rts=self.rts_var.get(),
            )
        except ValueError as exc:
            raise SerialServiceError("Port 설정의 숫자 값을 확인하십시오.") from exc

    def toggle_connection(self) -> None:
        if self.session.connected:
            self.session.close()
            self._set_connected(False)
            return
        try:
            self.session.connect(self._settings())
        except SerialServiceError as exc:
            messagebox.showerror("RS-232 연결 실패", str(exc), parent=self.window)
            return
        self._set_connected(True)
        self.tx_entry.focus_set()

    def _set_connected(self, connected: bool) -> None:
        self.status_var.set("CONNECTED" if connected else "DISCONNECTED")
        self.connect_button.configure(text="DISCONNECT" if connected else "CONNECT", style="Danger.TButton" if connected else "Accent.TButton")
        self.send_button.configure(state="normal" if connected else "disabled")

    def _set_lines(self) -> None:
        try:
            self.session.set_control_lines(dtr=self.dtr_var.get(), rts=self.rts_var.get())
        except SerialServiceError as exc:
            messagebox.showerror("Control line 오류", str(exc), parent=self.window)

    def send(self, _event: tk.Event | None = None) -> str:
        try:
            data = encode_transmission(self.tx_entry.get(), self.tx_mode_var.get(), self.terminator_var.get())
            self.session.send(data)
        except SerialServiceError as exc:
            messagebox.showwarning("전송 실패", str(exc), parent=self.window)
            return "break"
        self.tx_entry.selection_range(0, "end")
        return "break"

    def _poll(self) -> None:
        try:
            while True:
                event = self.session.events.get_nowait()
                self.records.append(event)
                if len(self.records) > 20_000:
                    del self.records[:2_000]
                if event.kind == "rx":
                    self.rx_bytes += len(event.data)
                elif event.kind == "tx":
                    self.tx_bytes += len(event.data)
                elif event.kind == "error":
                    self._set_connected(False)
                elif event.kind == "status":
                    self._set_connected(event.message.startswith("CONNECTED"))
                self._append_event(event)

        except queue.Empty:
            pass
        self.counter_var.set(f"RX {self.rx_bytes:,} B  ·  TX {self.tx_bytes:,} B")
        if self.window.winfo_exists():
            self._after_id = self.window.after(50, self._poll)

    def _append_event(self, event: SerialEvent) -> None:
        stamp = event.timestamp.astimezone().strftime("%H:%M:%S.%f")[:-3]
        if event.kind in ("rx", "tx"):
            direction = event.kind.upper()
            line = f"{stamp}  {direction:<2}  {self._render_bytes(event.data)}\n"
            tag = event.kind
        else:
            line = f"{stamp}  {event.kind.upper():<6}  {event.message}\n"
            tag = "error" if event.kind == "error" else "status"
        self.terminal.configure(state="normal")
        self.terminal.insert("end", line, tag)
        line_count = int(self.terminal.index("end-1c").split(".")[0])
        if line_count > 10_000:
            self.terminal.delete("1.0", "1001.0")
        self.terminal.configure(state="disabled")
        if self.autoscroll_var.get():
            self.terminal.see("end")

    def _render_bytes(self, data: bytes) -> str:
        ascii_view = "".join(chr(byte) if 32 <= byte <= 126 else {9: "\\t", 10: "\\n", 13: "\\r"}.get(byte, ".") for byte in data)
        hex_view = " ".join(f"{byte:02X}" for byte in data)
        mode = self.display_mode_var.get()
        if mode == "ASCII":
            return ascii_view
        if mode == "HEX":
            return hex_view
        return f"{hex_view:<48} | {ascii_view}"

    def clear(self) -> None:
        self.records.clear()
        self.rx_bytes = self.tx_bytes = 0
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")

    def save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="RS-232 log 저장",
            initialfile=f"spitfire_rs232_{datetime.now():%Y%m%d_%H%M%S}.log",
            defaultextension=".log",
            filetypes=(("Text log", "*.log"), ("All files", "*.*")),
        )
        if not path:
            return
        lines = ["# timestamp_utc  direction  hex  ascii"]
        for event in self.records:
            if event.data:
                hex_view = event.data.hex(" ").upper()
                ascii_view = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in event.data)
                lines.append(f"{event.timestamp.isoformat()}  {event.kind.upper()}  {hex_view}  {ascii_view}")
            else:
                lines.append(f"{event.timestamp.isoformat()}  {event.kind.upper()}  {event.message}")
        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc), parent=self.window)

    def show(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        if self._after_id is not None:
            try:
                self.window.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self.session.close()
        try:
            self.window.destroy()
        finally:
            if self.on_close is not None:
                self.on_close()
