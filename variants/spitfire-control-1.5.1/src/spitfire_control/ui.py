"""Tk-based operator console.

Tk is deliberately used instead of a vendor-specific UI runtime.  It ships
with normal Windows and python.org Python distributions, keeping deployment on
instrument PCs small and predictable.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
import queue
import math
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from . import __version__
from .commands import COMMANDS, FAULT_QUERY_IDS, FAST_POLL_IDS, Risk, get_command
from .config import AppConfig
from .profiles import EXTERNAL_REQUIRED_READS, filter_queries, query_allowed
from .controller import ControllerEvent, LaserController
from .serial_dialog import RawSerialDialog
from .state import DeviceState, FAULT_LABELS
from .commands import engineering_argument, FAST_POLL_IDS, HV_POLL_IDS
from .transport import SimulatorTransport, UdpSettings, UdpTransport
from .widgets import DraftValue, Indicator, MetricCard, SettingRow, set_if_changed
from .hold_button import HoldToRunButton


BG = "#e8edf2"
PANEL = "#f4f7f9"
CARD = "#ffffff"
TEXT = "#1b2a35"
MUTED = "#60717e"
ACCENT = "#1e6f9f"
NAVY = "#173a57"
BORDER = "#bac6ce"
RED = "#b5363d"
GREEN = "#287f4e"
AMBER = "#d39a21"
READOUT = "#10212b"
READOUT_TEXT = "#8ce9ff"


class SpitfireApp:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        self.controller: LaserController | None = None
        self.state = DeviceState(pump_mode=config.pump_mode)
        self.value_vars: dict[int, tk.StringVar] = {}
        self.drafts: dict[int, DraftValue] = {}
        self.delay_drafts: dict[tuple[int, str], DraftValue] = {}
        self.metric_cards: dict[int, list[MetricCard]] = {}
        self.subsystem_indicators: dict[str, Indicator] = {}
        self.fault_indicators: list[Indicator] = []
        self.service_unlocked = False
        self.rs232_warning_acknowledged = False
        self.raw_serial_dialog: RawSerialDialog | None = None
        self._last_data_log_second: str | None = None
        self._profile_widget_states: dict[ttk.Widget, str] = {}
        self.override_widgets: dict[int, ttk.Checkbutton] = {}
        self._closed = False
        self._after_jobs: set[str] = set()
        self._log_batch: list[str] | None = None
        self._fault_last: dict[int, bool] = {}
        self._fault_last_stamp = {}
        self._fault_raw_last: dict[int, tuple[object, str, object]] = {}

        self.connection_text = tk.StringVar(value="연결 준비 중")
        self.mode_text = tk.StringVar(value="")
        self.external_status_text = tk.StringVar(value="Empower opt-out: not confirmed")
        self.external_timing_text = tk.StringVar(value="EXTERNAL PUMP · timing readbacks unavailable")
        self.auto_poll_var = tk.BooleanVar(value=config.auto_poll)
        self.hv_monitor_var = tk.BooleanVar(value=config.monitor_hv)
        self.data_log_var = tk.BooleanVar(value=False)
        self.data_log_path = tk.StringVar(value="")

        self._configure_window()
        self._configure_styles()
        self._build_menu()
        self._build_layout()
        self._apply_pump_profile()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind('<Unmap>', lambda event: self.run_button.cancel(), add='+')
        self.root.bind('<Escape>', lambda event: self.run_button.cancel(), add='+')
        self.notebook.bind('<<NotebookTabChanged>>', lambda event: self.run_button.cancel(), add='+')
        self._schedule(80, self._drain_events)
        self._schedule(150, self.connect)

    def _schedule(self, delay_ms: int, callback) -> None:
        if self._closed:
            return
        token = None
        def invoke():
            self._after_jobs.discard(token)
            if not self._closed:
                callback()
        token = self.root.after(delay_ms, invoke)
        self._after_jobs.add(token)

    def _configure_window(self) -> None:
        self.root.title(f"Spitfire Python Control {__version__}")
        self.root.configure(bg=BG)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1440, max(640, screen_width - 60))
        height = min(920, max(560, screen_height - 80))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(900, width), min(650, height))

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.root.option_add("*Font", "{Segoe UI} 10")
        style.configure(".", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=PANEL)
        style.configure("Page.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("MetricCard.TFrame", background=CARD, relief="solid", borderwidth=1)
        style.configure("Readout.TFrame", background=READOUT, relief="sunken", borderwidth=1)
        style.configure("Header.TFrame", background=NAVY)
        style.configure("Status.TFrame", background="#dbe3e8")
        style.configure("Module.TFrame", background="#edf3f6", relief="solid", borderwidth=1)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Header.TLabel", background=NAVY, foreground="white")
        style.configure("HeaderMuted.TLabel", background=NAVY, foreground="#b9d5e5")
        style.configure("Status.TLabel", background="#dbe3e8", foreground="#435561", font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 21), foreground=TEXT)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground=MUTED)
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 12), foreground=TEXT)
        style.configure("CardTitle.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("CardText.TLabel", background=CARD, foreground=TEXT)
        style.configure("ModuleTitle.TLabel", background="#edf3f6", foreground=NAVY, font=("Segoe UI Semibold", 9))
        style.configure("MetricTitle.TLabel", background=CARD, foreground="#536775", font=("Segoe UI Semibold", 8))
        style.configure("ReadoutMetric.TLabel", background=READOUT, foreground=READOUT_TEXT, font=("Consolas", 21, "bold"))
        style.configure("ReadoutUnit.TLabel", background=READOUT, foreground="#9db4c0", font=("Segoe UI", 8))
        style.configure("Metric.TLabel", background=CARD, foreground=NAVY, font=("Segoe UI Semibold", 25))
        style.configure("Unit.TLabel", background=CARD, foreground=MUTED)
        style.configure("TButton", background="#e3eaee", foreground=TEXT, padding=(10, 7), borderwidth=1, relief="solid")
        style.map("TButton", background=[("active", "#d2dee5"), ("disabled", "#eef1f3")], foreground=[("disabled", "#98a3aa")])
        style.configure("Header.TButton", background="#2b5875", foreground="white", padding=(11, 6), borderwidth=0)
        style.map("Header.TButton", background=[("active", "#397494")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#2787bb")])
        style.configure("Danger.TButton", background=RED, foreground="white", font=("Segoe UI Semibold", 10))
        style.map("Danger.TButton", background=[("active", "#d24a50")])
        style.configure("Safe.TButton", background=GREEN, foreground="white", font=("Segoe UI Semibold", 10))
        style.map("Safe.TButton", background=[("active", "#359a63")])
        style.configure("Stop.TButton", background=RED, foreground="white", font=("Segoe UI Semibold", 14), padding=(12, 13))
        style.map("Stop.TButton", background=[("active", "#d24a50")])
        style.configure("Run.TButton", background=GREEN, foreground="white", font=("Segoe UI Semibold", 14), padding=(12, 13))
        style.map("Run.TButton", background=[("active", "#359a63")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("Card.TCheckbutton", background=CARD, foreground=TEXT)
        style.map("Card.TCheckbutton", background=[("active", CARD)])
        style.configure("Header.TCheckbutton", background=NAVY, foreground="white")
        style.map("Header.TCheckbutton", background=[("active", NAVY)], foreground=[("active", "white")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#d9e2e7", foreground="#455966", padding=(14, 9), borderwidth=1)
        style.map("TNotebook.Tab", background=[("selected", CARD), ("active", "#edf2f5")], foreground=[("selected", NAVY)], expand=[("selected", (0, 0, 0, 2))])
        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background="#dce5ea", foreground=TEXT)
        style.map("Treeview", background=[("selected", "#cce7f5")], foreground=[("selected", TEXT)])
        style.configure("TEntry", fieldbackground="white", foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.configure("TCombobox", fieldbackground="white", background="#dce5ea", foreground=TEXT, arrowcolor=NAVY)
        style.map("TCombobox", fieldbackground=[("readonly", "white")], selectbackground=[("readonly", "white")], selectforeground=[("readonly", TEXT)])
        style.configure("TLabelframe", background=CARD, foreground=NAVY, bordercolor=BORDER, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=CARD, foreground=NAVY, font=("Segoe UI Semibold", 10))

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = self.file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Connection Settings...", command=self.show_connection_settings)
        file_menu.add_command(label="Export Snapshot...", command=self.export_snapshot)
        file_menu.add_command(label="External timing...", command=self.show_external_timing)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = self.view_menu = tk.Menu(menu, tearoff=False)
        for index, label in enumerate(("Spitfire", "Empower Setup", "Timing and High Voltage", "Temperature Control", "Active Faults", "Programmer", "Empower Service")):
            view_menu.add_command(label=label, command=lambda i=index: self.notebook.select(i))
        menu.add_cascade(label="View", menu=view_menu)
        service_menu = self.service_menu = tk.Menu(menu, tearoff=False)
        service_menu.add_command(label="Raw RS-232 Terminal", accelerator="Ctrl+Shift+R", command=self.open_raw_serial_service)
        menu.add_cascade(label="Service", menu=service_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Safety & Protocol", command=self.show_safety_info)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)
        self.root.bind_all("<Control-Shift-KeyPress-R>", self._raw_serial_shortcut, add="+")

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg=NAVY, padx=20, pady=12)
        header.pack(fill="x")
        title_group = tk.Frame(header, bg=NAVY)
        title_group.pack(side="left")
        tk.Label(title_group, text="SPITFIRE", bg=NAVY, fg="white", font=("Segoe UI Semibold", 20)).pack(side="left")
        tk.Label(title_group, text="  LASER CONTROL CONSOLE", bg=NAVY, fg="#a9ccdf", font=("Segoe UI", 10, "bold")).pack(side="left", pady=(7, 0))

        right = ttk.Frame(header, style="Header.TFrame")
        right.pack(side="right")
        self.connection_indicator = Indicator(right, "", background=NAVY, label_style="Header.TLabel", frame_style="Header.TFrame")
        self.connection_indicator.label.configure(width=17)
        self.connection_indicator.pack(side="left", padx=(0, 16))
        ttk.Button(right, text="CONNECTION", style="Header.TButton", command=self.show_connection_settings).pack(side="left", padx=(0, 10))

        separator = tk.Frame(self.root, height=4, bg="#2b94c3")
        separator.pack(fill="x")
        self.external_banner = ttk.Frame(self.root, padding=(14, 3))
        banner_text = ttk.Frame(self.external_banner)
        banner_text.pack(side="left", fill="x", expand=True)
        ttk.Label(banner_text, textvariable=self.external_timing_text,
                  font=("Segoe UI Semibold", 9), width=1).pack(fill="x")
        ttk.Label(banner_text, textvariable=self.external_status_text, style="Muted.TLabel",
                  font=("Segoe UI", 9), width=1).pack(fill="x")
        self.opt_out_button = ttk.Button(self.external_banner, text="APPLY EMPOWER OPT-OUT",
                                         command=self._apply_external_opt_out)
        self.opt_out_button.pack(side="right", padx=(8, 0))
        ttk.Button(self.external_banner, text="REFRESH",
                   command=lambda: self._query(EXTERNAL_REQUIRED_READS)).pack(side="right")
        self.notebook = ttk.Notebook(self.root)
        self.overview = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.empower = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.timing = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.temperature = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.faults = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.diagnostics = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        self.service = ttk.Frame(self.notebook, style="Page.TFrame", padding=12)
        for page, label in ((self.overview, "SPITFIRE"), (self.empower, "EMPOWER"), (self.timing, "TIMING / HV"), (self.temperature, "TEMPERATURE"), (self.faults, "FAULTS"), (self.diagnostics, "PROGRAMMER"), (self.service, "SERVICE")):
            self.notebook.add(page, text=label)
        self._build_overview()
        self._build_empower()
        self._build_timing()
        self._build_temperature()
        self._build_faults()
        self._build_diagnostics()
        self._build_service_locked()

        footer = ttk.Frame(self.root, style="Status.TFrame", padding=(16, 6))
        footer.pack(fill="x", side="bottom")
        ttk.Label(footer, textvariable=self.connection_text, style="Status.TLabel", width=1).pack(side="left", fill="x", expand=True)
        self.raw_service_hint = ttk.Label(footer, text="Ctrl+Shift+R · RAW RS-232 SERVICE", style="Status.TLabel")
        self.raw_service_hint.pack(side="left", padx=(24, 0))
        ttk.Label(footer, textvariable=self.mode_text, style="Status.TLabel").pack(side="right")
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(10, 8))

    def _walk_widgets(self, parent):
        for widget in parent.winfo_children():
            yield widget
            yield from self._walk_widgets(widget)

    def _card(self, parent, title: str, *, padding: int = 14) -> ttk.LabelFrame:
        return ttk.LabelFrame(parent, text=title, padding=padding, style="TLabelframe")

    def _metric(self, parent, command_id: int, title: str, unit: str, column: int, *, digits: int = 2) -> None:
        card = MetricCard(parent, title, unit)
        card.grid(row=0, column=column, sticky="nsew", padx=5)
        card._digits = digits  # type: ignore[attr-defined]
        parent.columnconfigure(column, weight=1, uniform="metrics")
        self.metric_cards.setdefault(command_id, []).append(card)

    def _build_overview(self) -> None:
        self.overview.columnconfigure(0, weight=5, uniform="overview")
        self.overview.columnconfigure(1, weight=3, uniform="overview")
        self.overview.rowconfigure(2, weight=1)
        metrics = ttk.Frame(self.overview, style="Page.TFrame")
        metrics.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._metric(metrics, 1008, "OUTPUT POWER", "W", 0)
        self._metric(metrics, 1007, "DIODE CURRENT", "A", 1)
        self._metric(metrics, 1065, "OSCILLATOR", "MHz", 2, digits=3)
        self._metric(metrics, 1030, "XTAL TEMPERATURE", "°C", 3)
        self._metric(metrics, 1031, "HUMIDITY", "%RH", 4)

        status = self._card(self.overview, "SYSTEM COMMUNICATION")
        status.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 12))
        row = ttk.Frame(status, style="Card.TFrame")
        row.pack(fill="x")
        for name in ("MAIN", "EMPOWER", "TDG", "TCU", "COMPRESSOR"):
            module = ttk.Frame(row, style="Module.TFrame", padding=(7, 6))
            module.pack(side="left", fill="x", expand=True, padx=(0, 6) if name != "COMPRESSOR" else 0)
            ttk.Label(module, text=name, style="ModuleTitle.TLabel").pack(anchor="center")
            ind = Indicator(module, "COMM", compact=True, background="#edf3f6", label_style="ModuleTitle.TLabel", frame_style="Module.TFrame")
            ind.pack(anchor="center", pady=(5, 0))
            self.subsystem_indicators[name] = ind

        safety = self._card(self.overview, "LASER OUTPUT", padding=10)
        safety.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 12))
        buttons = ttk.Frame(safety, style="Card.TFrame")
        buttons.pack(fill="x")
        self.stop_button = ttk.Button(buttons, text="STOP", style="Stop.TButton", command=self.software_standby)
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.run_button = HoldToRunButton(buttons, text="RUN", style="Run.TButton",
                                              on_confirm=self._run_laser, on_progress=self._run_hold_progress)
        self.stop_button.bind('<ButtonPress-1>', self._stop_pressed)
        self.stop_button.bind('<ButtonRelease-1>', lambda event: 'break')
        self.stop_button.bind('<KeyPress-space>', self._stop_pressed)
        self.stop_button.bind('<KeyPress-Return>', self._stop_pressed)
        self.stop_button.bind('<KeyRelease-space>', lambda event: 'break')
        self.stop_button.bind('<KeyRelease-Return>', lambda event: 'break')
        self.run_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.output_scope_label = ttk.Label(safety, text="Software command · physical E-stop remains authoritative", style="CardTitle.TLabel")
        self.output_scope_label.configure(width=1, anchor="w")
        self.output_scope_label.pack(fill="x", pady=(7, 0))
        self.output_readbacks = tk.StringVar(value="Device HV: unknown · Key interlock: unknown\nHV1: unknown · HV2: unknown\nPC1: unknown · PC2: unknown")
        ttk.Label(safety, textvariable=self.output_readbacks, style="CardText.TLabel", justify="left", width=1).pack(fill="x", pady=(6, 0))
        self.output_result = tk.StringVar(value="No PC output command requested")
        ttk.Label(safety, textvariable=self.output_result, style="CardTitle.TLabel", width=1).pack(fill="x", pady=(3, 0))
        output_tools = ttk.Frame(safety, style="Card.TFrame")
        output_tools.pack(fill="x", pady=(6, 0))
        self.timing_settings_button = ttk.Button(output_tools, text="Open timing / HV settings", command=self._open_timing_settings)
        self.timing_settings_button.pack(side="left", fill="x", expand=True)
        self.hv_off_button = ttk.Button(output_tools, text="HV OFF", style="Safe.TButton", command=lambda: self.issue(2016))
        self.hv_off_button.pack(side="left", padx=(6, 0))

        details = self._card(self.overview, "READBACKS")
        details.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        grid = ttk.Frame(details, style="Card.TFrame")
        grid.pack(fill="both", expand=True)
        items = (
            (1013, "Empower status"), (1015, "Head status"), (1019, "TDG status"),
            (1028, "TCU status"), (1021, "High voltage"), (1085, "Overall status"),
            (1038, "Controller ID"), (1035, "Empower version"), (1036, "TDG version"),
            (1037, "TCU version"), (1034, "Head version"), (1089, "Communication status"),
        )
        for index, (command_id, label) in enumerate(items):
            row_no = index % 6
            base_column = (index // 6) * 2
            ttk.Label(grid, text=label, style="CardTitle.TLabel").grid(row=row_no, column=base_column, sticky="w", pady=5)
            var = self._var(command_id)
            ttk.Label(grid, textvariable=var, style="CardText.TLabel", width=12).grid(row=row_no, column=base_column + 1, sticky="ew", padx=(12, 18), pady=5)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

        motor = self._card(self.overview, "AMPLIFIER MOTOR", padding=10)
        motor.grid(row=2, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(motor, text="CAUTION · Motor commands move the amplifier optics.", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        speed = self._edit_var(1060)
        self._setting_row(motor, "Speed", speed, "%", lambda: self._issue_from_var(2014, speed, "모터 속도 변경", numeric=True)).pack(fill="x", pady=5)
        buttons = ttk.Frame(motor, style="Card.TFrame")
        buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="◀ REVERSE", command=lambda: self.issue(2009, confirm="Amplifier motor를 REVERSE로 구동할까요?")).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(buttons, text="■ STOP", style="Safe.TButton", command=lambda: self.issue(2013)).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(buttons, text="FORWARD ▶", command=lambda: self.issue(2010, confirm="Amplifier motor를 FORWARD로 구동할까요?")).pack(side="left", expand=True, fill="x", padx=(4, 0))
        jog = ttk.Frame(motor, style="Card.TFrame")
        jog.pack(fill="x")
        ttk.Button(jog, text="JOG REV", command=lambda: self.issue(2012, confirm="짧은 reverse jog를 실행할까요?")).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(jog, text="JOG FWD", command=lambda: self.issue(2011, confirm="짧은 forward jog를 실행할까요?")).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _build_empower(self) -> None:
        self.empower.columnconfigure(0, weight=3)
        self.empower.columnconfigure(1, weight=2)
        setpoints = self._card(self.empower, "EMPOWER SETUP")
        setpoints.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        rows = (
            (1009, 2003, "Diode current setpoint", "A"),
            (1010, 2004, "Q-switch frequency", "Hz"),
            (1011, 2007, "Pulse width", "ns"),
        )
        for query_id, write_id, label, unit in rows:
            variable = self._edit_var(query_id)
            self._setting_row(setpoints, label, variable, unit, lambda wid=write_id, var=variable, name=label: self._issue_from_var(wid, var, name, numeric=True)).pack(fill="x", pady=8)
        source_frame = ttk.Frame(setpoints, style="Card.TFrame")
        source_frame.pack(fill="x", pady=8)
        ttk.Label(source_frame, text="Q-switch source", style="CardText.TLabel").pack(side="left")
        self.qsw_source = self._edit_var(1012)
        ttk.Combobox(source_frame, textvariable=self.qsw_source, values=("0", "1"), state="readonly", width=10).pack(side="left", padx=(20, 8))
        ttk.Button(source_frame, text="APPLY", command=lambda: self.issue(2008, self.qsw_source.get(), confirm="Q-switch SOURCE 변경은 레이저를 손상시킬 수 있습니다. 계속할까요?")).pack(side="left")
        ttk.Label(source_frame, textvariable=self.drafts[1012].readback, style="CardTitle.TLabel").pack(side="left", padx=10)
        ttk.Label(setpoints, text="WARNING · Change SOURCE only when it matches the controller and laser configuration.", style="CardTitle.TLabel", wraplength=600).pack(anchor="w", pady=(18, 0))

        readback = self._card(self.empower, "LIVE READBACK")
        readback.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        for command_id, title, unit in ((1007, "Sensed current", "A"), (1008, "Output power", "W"), (1077, "LBO temperature", "°C")):
            frame = ttk.Frame(readback, style="Card.TFrame")
            frame.pack(fill="x", pady=10)
            ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w")
            line = ttk.Frame(frame, style="Card.TFrame")
            line.pack(anchor="w")
            ttk.Label(line, textvariable=self._var(command_id), style="Metric.TLabel").pack(side="left")
            ttk.Label(line, text=unit, style="Unit.TLabel").pack(side="left", padx=7, pady=(10, 0))
        ttk.Separator(readback).pack(fill="x", pady=13)
        self.emp_opt_var = self._edit_var(1068, boolean=True)
        ttk.Checkbutton(readback, text="Empower opt-out (service)", variable=self.emp_opt_var, style="Card.TCheckbutton", command=lambda: self._toggle_option(2036, 1068, self.emp_opt_var, "Empower opt-out")).pack(anchor="w")
        ttk.Button(readback, text="Empower faults refresh", command=lambda: self._query((1014, 1013))).pack(anchor="w", pady=(15, 0))

    def _build_timing(self) -> None:
        self.timing.columnconfigure(0, weight=1)
        self.timing.columnconfigure(1, weight=1)
        hv = self._card(self.timing, "HIGH VOLTAGE", padding=10)
        hv.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 10))
        self.hv_indicator = Indicator(hv, "HV state unknown")
        self.hv_indicator.pack(anchor="w", pady=(0, 7))
        for query_id, write_id, label in ((1040, 2025, "HV channel 1 setpoint"), (1041, 2026, "HV channel 2 setpoint")):
            var = self._edit_var(query_id)
            self._setting_row(hv, label, var, "V", lambda wid=write_id, value=var, name=label: self._issue_from_var(wid, value, name, numeric=True)).pack(fill="x", pady=3)
        hbuttons = ttk.Frame(hv, style="Card.TFrame")
        hbuttons.pack(fill="x", pady=(9, 4))
        ttk.Button(hbuttons, text="HV ON", style="Danger.TButton", command=lambda: self.issue(2017, confirm="HIGH VOLTAGE를 켤까요? 실제 장비와 인터록 상태를 확인하십시오.")).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(hbuttons, text="HV OFF", style="Safe.TButton", command=lambda: self.issue(2016)).pack(side="left", expand=True, fill="x", padx=(5, 0))
        readbacks = ttk.Frame(hv, style="Card.TFrame")
        readbacks.pack(fill="x", pady=4)
        for col, (cid, label, unit) in enumerate(((1042, "HV1", "V"), (1055, "I1", ""), (1043, "HV2", "V"), (1056, "I2", ""))):
            sub = ttk.Frame(readbacks, style="Card.TFrame")
            sub.grid(row=0, column=col, sticky="ew")
            ttk.Label(sub, text=f"{label} ({unit})" if unit else label, style="CardTitle.TLabel").pack()
            ttk.Label(sub, textvariable=self._var(cid), style="CardText.TLabel").pack()
            readbacks.columnconfigure(col, weight=1)
        ttk.Checkbutton(hv, text="Extra HV current monitoring (voltage always monitored)", variable=self.hv_monitor_var, style="Card.TCheckbutton", command=self._apply_poll_options).pack(anchor="w", pady=(4, 0))

        timing = self._card(self.timing, "TRIGGER & OSCILLATOR", padding=10)
        timing.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10))
        trigger_freq = self._edit_var(1053)
        self._setting_row(timing, "Internal amplifier rate", trigger_freq, "Hz", lambda: self._issue_from_var(2032, trigger_freq, "Trigger frequency", numeric=True)).pack(fill="x", pady=3)
        divisor = self._edit_var(1025)
        self._setting_row(timing, "Divisor", divisor, "", lambda: self._issue_from_var(2020, divisor, "Divisor", numeric=True)).pack(fill="x", pady=3)
        self.trigger_mode = self._edit_var(1051)
        self.osc_mode = self._edit_var(1050)
        for label, variable, cid in (("Amplifier trigger", self.trigger_mode, 2031), ("Oscillator sync", self.osc_mode, 2030)):
            row = ttk.Frame(timing, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, style="CardText.TLabel").pack(side="left")
            ttk.Combobox(row, textvariable=variable, values=("INT", "EXT"), state="readonly", width=8).pack(side="left", padx=(20, 8))
            ttk.Button(row, text="APPLY", command=lambda c=cid, v=variable, n=label: self.issue(c, v.get(), confirm=f"{n} source를 변경할까요?")).pack(side="left")
            qid = 1051 if cid == 2031 else 1050
            ttk.Label(row, textvariable=self.drafts[qid].readback, style="CardTitle.TLabel").pack(side="left", padx=10)
        opmode_row = ttk.Frame(timing, style="Card.TFrame")
        opmode_row.pack(fill="x", pady=3)
        ttk.Label(opmode_row, text="Operation mode", style="CardText.TLabel").pack(side="left")
        self.operation_mode = self._edit_var(1080)
        ttk.Combobox(opmode_row, textvariable=self.operation_mode, values=("CONT", "COUNT", "COUNT 1"), state="readonly", width=9).pack(side="left", padx=(20, 8))
        ttk.Button(opmode_row, text="APPLY", command=lambda: self.issue(2048, self.operation_mode.get(), confirm="TDG operation mode를 변경할까요?")).pack(side="left")
        ttk.Label(opmode_row, textvariable=self.drafts[1080].readback, style="CardTitle.TLabel").pack(side="left", padx=10)
        actions = ttk.Frame(timing, style="Card.TFrame")
        actions.pack(fill="x", pady=(7, 0))
        ttk.Button(actions, text="Measured oscillator → setpoint", command=self._oscillator_to_measured).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="RESET BWD", command=lambda: self.issue(2018, confirm="BWD fault/interlock를 reset할까요?")).pack(side="left")

        delays = self._card(self.timing, "CHANNEL DELAYS", padding=10)
        delays.grid(row=1, column=0, columnspan=2, sticky="nsew")
        ttk.Label(delays, text="Five legacy delay channels · units and accepted ranges are enforced by controller firmware.", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))
        dgrid = ttk.Frame(delays, style="Card.TFrame")
        dgrid.pack(fill="x")
        for index, query_id in enumerate((1045, 1046, 1047, 1048, 1049), start=1):
            cell = ttk.Frame(dgrid, style="Card.TFrame")
            cell.grid(row=0, column=index - 1, sticky="ew", padx=5)
            ttk.Label(cell, text=f"CH {index}", style="CardTitle.TLabel").pack(anchor="w")
            var = self._edit_var(query_id)
            ttk.Entry(cell, textvariable=var, width=12).pack(fill="x", pady=5)
            ttk.Label(cell, textvariable=self.drafts[query_id].readback, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Button(cell, text="APPLY DELAY", command=lambda i=index, v=var: self._apply_delay(i, v)).pack(fill="x")
            for option_label, choices in (("Switch", ("off", "on")), ("BWD", ("BWD", "NBWD")), ("Enable", ("ENA", "NENA"))):
                field = {"Switch": "switch", "BWD": "bwd", "Enable": "enable"}[option_label]
                draft = DraftValue(self.root)
                self.delay_drafts[(index, field)] = draft
                option = draft.variable
                line = ttk.Frame(cell, style="Card.TFrame")
                line.pack(fill="x", pady=(5, 0))
                ttk.Label(line, text=option_label, style="CardTitle.TLabel").pack(side="left")
                box = ttk.Combobox(line, textvariable=option, values=choices, state="readonly", width=7)
                box.pack(side="right")
                box.bind("<<ComboboxSelected>>", lambda _event, i=index, v=option: self._apply_channel_mode(i, v.get()))
            dgrid.columnconfigure(index - 1, weight=1)
        # Fit the complete panel plus external profile banner on instrument PCs.
        # Widget padding preserves each button's color and safety-related style.
        for widget in self._walk_widgets(self.timing):
            if isinstance(widget, ttk.Button):
                widget.configure(padding=(8, 2))

    def _build_temperature(self) -> None:
        self.temperature.columnconfigure(0, weight=3)
        self.temperature.columnconfigure(1, weight=2)
        metrics = ttk.Frame(self.temperature, style="Page.TFrame")
        metrics.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._metric(metrics, 1030, "XTAL TEMP", "°C", 0)
        self._metric(metrics, 1084, "TEC TEMP", "°C", 1)
        self._metric(metrics, 1031, "HUMIDITY", "%RH", 2)
        self._metric(metrics, 1032, "SET TEMP", "°C", 3)
        control = self._card(self.temperature, "TEMPERATURE CONTROL")
        control.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        temp_var = self._edit_var(1032)
        self._setting_row(control, "Temperature setpoint", temp_var, "°C", lambda: self._issue_from_var(2021, temp_var, "Temperature setpoint", numeric=True)).pack(fill="x", pady=6)
        buttons = ttk.Frame(control, style="Card.TFrame")
        buttons.pack(fill="x", pady=15)
        self.tec_on_button = ttk.Button(buttons, text="TEC ON", command=lambda: self.issue(2022, confirm="TEC를 켤까요?"))
        self.tec_on_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.tec_off_button = ttk.Button(buttons, text="TEC OFF", style="Safe.TButton", command=lambda: self.issue(2023))
        self.tec_off_button.pack(side="left", expand=True, fill="x", padx=(5, 0))
        self.tec_indicator = Indicator(control, "TEC state unknown")
        self.tec_indicator.pack(anchor="w")
        self.tec_result = tk.StringVar(value="No TEC command requested")
        ttk.Label(control, textvariable=self.tec_result, style="CardTitle.TLabel", width=1).pack(fill="x", pady=4)
        ttk.Button(control, text="REFRESH STATUS", command=lambda: self._query((1028, 1029, 1030, 1031, 1032, 1084))).pack(anchor="w")

        overrides = self._card(self.temperature, "SERVICE OVERRIDES")
        overrides.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(overrides, text="CAUTION · Interlock overrides and opt-outs can reduce equipment protection.", style="CardTitle.TLabel", wraplength=390).pack(anchor="w", pady=(0, 12))
        self.humidity_override_var = self._edit_var(1044, boolean=True)
        self.ecu_opt_var = self._edit_var(1033, boolean=True)
        self.comp_opt_var = self._edit_var(1069, boolean=True)
        self.empower_opt_temp_var = self._edit_var(1068, boolean=True)
        self.tdg_fault_override_var = self._edit_var(1087, boolean=True)
        options = (
            ("Humidity error override", self.humidity_override_var, 2029),
            ("TCU opt-out", self.ecu_opt_var, 2024),
            ("Compressor opt-out", self.comp_opt_var, 2035),
            ("Empower opt-out", self.empower_opt_temp_var, 2036),
            ("TDG error override", self.tdg_fault_override_var, 2053),
        )
        for label, var, cid in options:
            check = ttk.Checkbutton(overrides, text=label, variable=var, style="Card.TCheckbutton", command=lambda c=cid, v=var, n=label: self._toggle_option(c, {2029: 1044, 2024: 1033, 2035: 1069, 2036: 1068, 2053: 1087}[c], v, n))
            check.pack(anchor="w", pady=6)
            self.override_widgets[cid] = check

    def _build_faults(self) -> None:
        top = ttk.Frame(self.faults, style="Page.TFrame")
        top.pack(fill="x", pady=(0, 10))
        self.fault_summary = Indicator(top, "Fault data not received")
        self.fault_summary.pack(side="left", fill="x", expand=True)
        self.fault_summary.label.configure(width=1)
        self.fault_summary.label.pack_configure(fill="x", expand=True)
        ttk.Button(top, text="REFRESH", command=lambda: self._query(FAULT_QUERY_IDS)).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="CLEAR FAULTS", style="Danger.TButton", command=self._clear_faults).pack(side="right")
        raw = self._card(self.faults, "FAULT READBACKS")
        raw.pack(fill="x", pady=(0, 10))
        self.fault_raw_var = tk.StringVar(value="—")
        ttk.Label(raw, textvariable=self.fault_raw_var, style="Metric.TLabel", width=1).pack(fill="x")
        self.fault_health_raw_var = tk.StringVar(value="TDG — | TCU — | COM — | BWD —")
        ttk.Label(raw, textvariable=self.fault_health_raw_var, style="CardTitle.TLabel", width=1).pack(fill="x", pady=(3, 0))
        self.fault_diagnostic_var = tk.StringVar()
        ttk.Label(raw, textvariable=self.fault_diagnostic_var, style="CardTitle.TLabel",
                  width=1).pack(fill="x", pady=(5, 0))
        ttk.Label(raw, text="* Last confirmed fault value; current data unavailable/stale.",
                  style="CardTitle.TLabel", width=1).pack(fill="x")
        grid = self._card(self.faults, "FAULT INDICATORS")
        grid.pack(fill="both", expand=True)
        for index, label in enumerate(FAULT_LABELS):
            indicator = Indicator(grid, label, compact=True)
            indicator.grid(row=index % 7, column=index // 7, sticky="w", padx=10, pady=7)
            self.fault_indicators.append(indicator)
        for column in range(4):
            grid.columnconfigure(column, weight=1, uniform="faults")

    def _build_diagnostics(self) -> None:
        self.diagnostics.columnconfigure(0, weight=2)
        self.diagnostics.columnconfigure(1, weight=3)
        self.diagnostics.rowconfigure(0, weight=1)
        command = self._card(self.diagnostics, "COMMAND CONSOLE")
        command.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(command, text="Only recovered command IDs can be sent. Hardware writes require fresh readbacks.", style="CardTitle.TLabel", wraplength=420).pack(anchor="w", pady=(0, 10))
        choices = [f"{cid} · {spec.text}" for cid, spec in sorted(COMMANDS.items())]
        self.console_command = tk.StringVar(value=choices[0])
        combo = ttk.Combobox(command, textvariable=self.console_command, values=choices, state="readonly")
        combo.pack(fill="x", pady=5)
        self.console_arg = tk.StringVar()
        ttk.Entry(command, textvariable=self.console_arg).pack(fill="x", pady=5)
        ttk.Button(command, text="SEND", style="Accent.TButton", command=self._console_send).pack(fill="x", pady=5)
        ttk.Separator(command).pack(fill="x", pady=15)
        ttk.Checkbutton(command, text="Automatic polling", variable=self.auto_poll_var, style="Card.TCheckbutton", command=self._apply_poll_options).pack(anchor="w", pady=4)
        ttk.Label(command, text="Connection check stays on. Temperature / humidity: 2× poll cycle.",
                  style="CardTitle.TLabel", wraplength=400).pack(anchor="w")
        ttk.Checkbutton(command, text="CSV state logging", variable=self.data_log_var, style="Card.TCheckbutton", command=self._toggle_data_log).pack(anchor="w", pady=4)
        ttk.Label(command, textvariable=self.data_log_path, style="CardTitle.TLabel", wraplength=400).pack(anchor="w", pady=(4, 12))
        ttk.Button(command, text="QUERY PRIMARY READBACKS", command=lambda: self._query(FAST_POLL_IDS)).pack(anchor="w")

        log_frame = self._card(self.diagnostics, "WIRE LOG")
        log_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.log_text = tk.Text(log_frame, bg=READOUT, fg="#d4e4ea", insertbackground="white", relief="flat", font=("Consolas", 9), wrap="none", height=20)
        yscroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=yscroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

    def _build_service_locked(self) -> None:
        for child in self.service.winfo_children():
            child.destroy()
        panel = self._card(self.service, "EMPOWER SERVICE · LOCKED")
        panel.pack(fill="both", expand=True)
        ttk.Label(
            panel,
            text="Values on this panel can change protection limits and calibration.\n"
                 "Unlock only with device-specific service data and an approved procedure.",
            style="CardText.TLabel",
            justify="left",
        ).pack(anchor="center", pady=(80, 20))
        ttk.Button(panel, text="UNLOCK EMPOWER SERVICE", style="Danger.TButton", command=self._unlock_service).pack()

    def _unlock_service(self) -> None:
        if self.config.pump_mode == "external":
            return
        phrase = simpledialog.askstring(
            "Service unlock",
            "Service limit 변경은 laser를 손상시키거나 보호 기능을 무력화할 수 있습니다.\n"
            "계속하려면 SERVICE MODE 를 입력하십시오.",
            parent=self.root,
        )
        if phrase != "SERVICE MODE":
            return
        self.service_unlocked = True
        self._build_service_controls()
        self._query((1071, 1072, 1073, 1074, 1075, 1076, 1077, 1078))

    def _build_service_controls(self) -> None:
        if self.config.pump_mode == "external":
            return
        for child in self.service.winfo_children():
            child.destroy()
        warning = self._card(self.service, "EMPOWER SERVICE · UNLOCKED")
        warning.pack(fill="x", pady=(0, 10))
        ttk.Label(warning, text="Each set commits EMP:SECRETSCOMT and queries the readback.", style="CardTitle.TLabel").pack(anchor="w")
        content = ttk.Frame(self.service, style="Page.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        limits = self._card(content, "CALIBRATION & LIMITS")
        limits.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        settings = (
            (1071, 2038, "Max current", "A"),
            (1072, 2039, "Max power", "mW"),
            (1073, 2040, "Intercept", "mW"),
            (1074, 2041, "Slope", "mW/V"),
            (1076, 2043, "Under-temperature limit", "°C"),
            (1075, 2042, "Over-temperature limit", "°C"),
        )
        for query_id, write_id, label, unit in settings:
            var = self._edit_var(query_id)
            self._setting_row(limits, label, var, unit, lambda q=query_id, w=write_id, v=var, n=label: self._apply_service_value(q, w, v, n)).pack(fill="x", pady=6)
        live = self._card(content, "LBO & SERVICE ACTIONS")
        live.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(live, text="LBO temperature", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(live, textvariable=self._var(1077), style="Metric.TLabel").pack(anchor="w")
        self.lbo_break_var = self._edit_var(1078, boolean=True)
        ttk.Checkbutton(live, text="LBO stability fault break", variable=self.lbo_break_var, style="Card.TCheckbutton", command=lambda: self._toggle_option(2047, 1078, self.lbo_break_var, "LBO stability fault")).pack(anchor="w", pady=12)
        ttk.Button(live, text="Service readback refresh", command=lambda: self._query((1071, 1072, 1073, 1074, 1075, 1076, 1077, 1078))).pack(anchor="w")
        ttk.Button(live, text="LOCK SERVICE", command=self._lock_service).pack(anchor="w", pady=(8, 0))
        for widget in self._walk_widgets(self.service):
            if isinstance(widget, ttk.Button):
                widget.configure(padding=(10, 5))

    def _lock_service(self) -> None:
        self.service_unlocked = False
        self._build_service_locked()

    def _apply_service_value(self, query_id: int, write_id: int, variable: tk.StringVar, label: str) -> None:
        value = variable.get().strip()
        try:
            if not math.isfinite(float(value)):
                raise ValueError
        except ValueError:
            messagebox.showwarning("잘못된 값", f"{label}: 숫자를 입력하십시오.", parent=self.root)
            return
        if self.config.mode == "udp" and (not self.controller or not self.controller.running or not self.controller.state.link_fresh()):
            messagebox.showwarning("명령 차단", "Service write requires a recent controller connection.", parent=self.root)
            return
        if self.config.mode == "udp" and not messagebox.askyesno("SERVICE WRITE", f"{label}을(를) {value}(으)로 변경하고 commit할까요?", icon="warning", parent=self.root):
            return
        if self.issue(write_id, value):
            self.issue(2045)
            self._query((query_id,))

    def _edit_var(self, command_id: int, *, boolean: bool = False):
        if command_id not in self.drafts:
            self.drafts[command_id] = DraftValue(self.root, False if boolean else "—", boolean=boolean)
        return self.drafts[command_id].variable

    def _setting_row(self, parent, title, variable, unit, command, **kwargs):
        draft = next(d for d in self.drafts.values() if d.variable is variable)
        return SettingRow(parent, title, variable, unit, command,
                          readback=draft.readback, reset=draft.reset, **kwargs)

    def _var(self, command_id: int, default: str = "—") -> tk.StringVar:
        if command_id not in self.value_vars:
            self.value_vars[command_id] = tk.StringVar(value=default)
        return self.value_vars[command_id]

    def _apply_pump_profile(self) -> None:
        external = self.config.pump_mode == "external"
        if external:
            self.external_banner.pack(fill="x", before=self.notebook)
            if self.raw_serial_dialog is not None:
                self.raw_serial_dialog.close()
            self._lock_service()
        else:
            self.external_banner.pack_forget()
        for page, menu_index in ((self.empower, 1), (self.service, 6)):
            if external and self.notebook.select() == str(page):
                self.notebook.select(self.overview)
            self.notebook.tab(page, state="disabled" if external else "normal")
            self.view_menu.entryconfigure(menu_index, state="disabled" if external else "normal")
            def visit(parent):
                for widget in parent.winfo_children():
                    if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton)):
                        if external:
                            self._profile_widget_states.setdefault(widget, str(widget.cget("state")))
                            widget.configure(state="disabled")
                        elif widget in self._profile_widget_states:
                            widget.configure(state=self._profile_widget_states.pop(widget))
                    visit(widget)
            visit(page)
        for widget in self.override_widgets.values():
            widget.configure(state="disabled" if external else "normal")
        self.service_menu.entryconfigure(0, state="disabled" if external else "normal")
        self.file_menu.entryconfigure(2, state="normal" if external else "disabled")
        self.raw_service_hint.configure(text="External pump: separate controls" if external else "Ctrl+Shift+R · RAW RS-232 SERVICE")
        self.run_button.cancel()
        self.stop_button.configure(text="STOP")
        self.run_button.configure(text="RUN", style="Run.TButton")
        self._run_hold_progress(None)

    def _configuration_change_reason(self) -> str:
        if self.controller is None or not self.controller.running:
            return ""
        state = self.controller.state
        if state.transport_open and state.high_voltage is not False:
            return "A fresh HV OFF readback is required before changing modes. Refresh HV state or disconnect."
        return ""

    def _apply_external_opt_out(self) -> None:
        if self.config.pump_mode != "external" or self.controller is None or not self.controller.running:
            return
        state = self.controller.state
        if state.high_voltage is not False:
            self._query((1021, 1068))
            messagebox.showwarning("HV state required", "Confirm a fresh TDG HV OFF readback before applying Empower opt-out.", parent=self.root)
            return
        self.issue(2036, 1, confirm="Set controller Empower opt-out to 1? This does not start or verify the external pump.")

    def _make_controller(self) -> LaserController:
        if self.config.mode == "udp":
            transport = UdpTransport(UdpSettings(
                remote_host=self.config.remote_host,
                remote_port=self.config.remote_port,
                local_host=self.config.local_host,
                local_port=self.config.local_port,
            ))
        else:
            transport = SimulatorTransport(empower_present=self.config.pump_mode != "external")
        return LaserController(
            transport,
            timeout=self.config.timeout_seconds,
            poll_interval=self.config.poll_interval_seconds,
            auto_poll=self.auto_poll_var.get(),
            monitor_hv=self.hv_monitor_var.get(),
            log_directory=self.config.log_directory,
            pump_mode=self.config.pump_mode,
            external_seed_mhz=self.config.external_seed_mhz,
            external_seed_tolerance_mhz=self.config.external_seed_tolerance_mhz,
            external_pump_hz=self.config.external_pump_hz,
        )

    def connect(self) -> None:
        self.run_button.cancel()
        self._fault_last.clear()
        self._fault_last_stamp.clear()
        self._fault_raw_last.clear()
        if self.controller:
            self.controller.stop()
        self.state = DeviceState(pump_mode=self.config.pump_mode)
        for draft in (*self.drafts.values(), *self.delay_drafts.values()):
            draft.clear()
        self._apply_pump_profile()
        self._refresh_ui()
        self.controller = self._make_controller()
        self.mode_text.set(("SIMULATOR" if self.config.mode != "udp" else "UDP") + " · " + ("EXTERNAL PUMP" if self.config.pump_mode == "external" else "EMPOWER"))
        self.connection_text.set("연결 중...")
        self.connection_indicator.set("warning", "연결 중")
        self.controller.start()

    def disconnect(self) -> None:
        self.run_button.cancel()
        if self.controller:
            self.controller.stop()
            self.state = self.controller.state
        else:
            self.state = DeviceState(pump_mode=self.config.pump_mode)
        self._refresh_ui()
        self.connection_indicator.set("off", "연결 끊김")
        self.connection_text.set("Disconnected")

    def issue(self, command_id: int, argument: object | None = None, *, confirm: str | None = None, raw: bool = False) -> bool:
        if not self.controller or not self.controller.running:
            messagebox.showerror("전송 불가", "Controller transport가 연결되어 있지 않습니다.", parent=self.root)
            return False
        spec = get_command(command_id)
        if confirm and self.config.mode == "udp":
            if not messagebox.askyesno("실제 하드웨어 명령 확인", confirm, icon="warning", parent=self.root):
                return False
        try:
            self.controller.submit(command_id, argument if raw else engineering_argument(command_id, argument))
        except (PermissionError, ValueError) as exc:
            messagebox.showwarning("명령 차단", str(exc), parent=self.root)
            return False
        if spec.writable:
            self.connection_text.set(f"Queued [{command_id}] {spec.text}")

        return True

    def _issue_from_var(self, command_id: int, variable: tk.StringVar, label: str, *, numeric: bool = False) -> None:
        value = variable.get().strip()
        if not value or value == "—":
            messagebox.showwarning("값 필요", f"{label} 값을 입력하십시오.", parent=self.root)
            return
        if numeric:
            try:
                number = float(value)
            except ValueError:
                messagebox.showwarning("잘못된 값", f"{label}: 숫자를 입력하십시오.", parent=self.root)
                return
            if not (-1_000_000 <= number <= 1_000_000):
                messagebox.showwarning("범위 초과", "비정상적으로 큰 값이므로 전송하지 않았습니다.", parent=self.root)
                return
        self.issue(command_id, value, confirm=f"{label}을(를) {value}(으)로 변경할까요?")

    def _apply_delay(self, channel: int, variable: tk.StringVar) -> None:
        value = variable.get().strip()
        try:
            if not math.isfinite(float(value)):
                raise ValueError
        except ValueError:
            messagebox.showwarning("잘못된 값", "Delay는 숫자여야 합니다.", parent=self.root)
            return
        # The original uses one write command and places the channel selector in
        # the argument.  Read IDs 1045..1049 verify channels 1..5 afterwards.
        self.issue(2019, f"{channel} {value}", confirm=f"Channel {channel} delay를 {value}(으)로 설정할까요?")

    def _toggle_option(self, command_id, query_id, variable, label):
        if not self.issue(command_id, int(variable.get()), confirm=f"{label} 상태를 변경할까요?"):
            self.drafts[query_id].reset()

    def _apply_channel_mode(self, channel: int, value: str) -> None:
        if not self.issue(2019, f"{channel} {value}", confirm=f"Channel {channel} mode를 {value}(으)로 변경할까요?"):
            field = "switch" if value.upper() in {"ON", "OFF"} else ("bwd" if value in {"BWD", "NBWD"} else "enable")
            self.delay_drafts[(channel, field)].reset()

    def _oscillator_to_measured(self) -> None:
        value = self.state.value(1065)
        if not self.state.is_fresh(1065) or not isinstance(value, (int, float)):
            messagebox.showwarning("측정값 없음", "먼저 measured oscillator frequency를 조회하십시오.", parent=self.root)
            self._query((1065,))
            return
        self.issue(2046, value, confirm=f"측정 oscillator 주파수 {value}를 setpoint로 복사할까요?")

    def _open_timing_settings(self) -> None:
        self.notebook.select(self.timing)

    def _run_laser(self) -> None:
        if self.config.pump_mode == "external":
            if not self.controller or not self.controller.running:
                messagebox.showwarning("RUN unavailable", "Connect before RUN.", parent=self.root)
                return
            try:
                self.controller.run_pc_outputs()
            except (ValueError, PermissionError) as exc:
                messagebox.showwarning("RUN unavailable", str(exc), parent=self.root)
                return
            self.connection_text.set("PC RUN requested; channel readback confirmation pending")
            return
        self.issue(2027)

    def _run_hold_progress(self, elapsed) -> None:
        scope = "PC1+PC2 only" if self.config.pump_mode == "external" else "laser command"
        message = f"Hold RUN 3 s · {scope}" if elapsed is None else f"Keep holding RUN: {elapsed:.1f} / 3.0 s"
        self.output_scope_label.configure(text=message)

    def _stop_pressed(self, _event=None):
        self.software_standby()
        return 'break'

    def software_standby(self) -> None:
        self.run_button.cancel()
        if not self.controller or not self.controller.running:
            return
        if self.config.pump_mode == "external":
            try:
                self.controller.stop_pc_outputs()
            except (ValueError, PermissionError) as exc:
                messagebox.showwarning("STOP unavailable", str(exc), parent=self.root)
                return
            self.connection_text.set("PC1/PC2 OFF requested; HV, external pump and seed are not stopped")
        else:
            self.issue(2028)
            self.issue(2016)
            self.connection_text.set("Software standby requested · physical E-stop remains authoritative")

    def _clear_faults(self) -> None:
        if not self.controller or not self.controller.running:
            messagebox.showwarning("Fault reset unavailable", "Connect before fault reset.", parent=self.root)
            return
        if self.config.mode == "udp":
            state = self.controller.state
            if not state.link_fresh():
                messagebox.showwarning("Fault reset unavailable", "A recent controller readback is required. " + state.last_error, parent=self.root)
                return
            if not messagebox.askyesno("FAULT RESET",
                    "EMP → TCU → TDG → global RESET 후 fault·HV·PC 상태를 다시 조회합니다.\n"
                    "Keyswitch가 ON이면 Fault Reset 후 HV가 활성화될 수 있습니다.\n"
                    "RESET은 RUN/STOP 명령이 아닙니다. 계속할까요?",
                    icon="warning", parent=self.root):
                return
        try:
            self.controller.clear_faults()
        except (PermissionError, ValueError) as exc:
            messagebox.showwarning("Fault reset unavailable", str(exc), parent=self.root)
            return
        self.connection_text.set("Fault reset queued · delayed readback pending")

    def _query(self, command_ids) -> None:
        if not self.controller or not self.controller.running:
            return
        try:
            self.controller.query_now(filter_queries(tuple(command_ids), self.config.pump_mode))
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("조회 오류", str(exc), parent=self.root)

    def _console_send(self) -> None:
        try:
            command_id = int(self.console_command.get().split("·", 1)[0].strip())
        except ValueError:
            return
        spec = get_command(command_id)
        argument = self.console_arg.get().strip() or None
        prompt = None
        if spec.writable and spec.risk != Risk.CONFIG:
            prompt = f"[{command_id}] {spec.text} 명령을 실제 controller에 전송할까요?"
        self.issue(command_id, argument, confirm=prompt, raw=True)

    def _apply_poll_options(self) -> None:
        if self.controller:
            self.controller.auto_poll = self.auto_poll_var.get()
            self.controller.monitor_hv = self.hv_monitor_var.get()
        self.config.auto_poll = self.auto_poll_var.get()
        self.config.monitor_hv = self.hv_monitor_var.get()
        self.config.save()

    def _toggle_data_log(self) -> None:
        if self.data_log_var.get() and not self.data_log_path.get():
            directory = Path(self.config.log_directory).expanduser() if self.config.log_directory else Path.cwd() / "logs"
            path = directory / f"spitfire_data_{datetime.now():%Y%m%d_%H%M%S}.csv"
            self.data_log_path.set(str(path))
        if not self.data_log_var.get():
            self._last_data_log_second = None

    def _write_data_log(self, state: DeviceState) -> None:
        if not self.data_log_var.get() or not self.data_log_path.get():
            return
        second = datetime.now().isoformat(timespec="seconds")
        if second == self._last_data_log_second:
            return
        self._last_data_log_second = second
        path = Path(self.data_log_path.get())
        fields = (1007, 1008, 1010, 1011, 1013, 1019, 1021, 1030, 1031, 1032, 1042, 1043, 1055, 1056, 1065, 1077, 1084, 1085)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                if new:
                    writer.writerow(("local_time", "transport", "pump_mode") + tuple(f"id_{cid}" for cid in fields))
                writer.writerow((second, state.transport_name, state.pump_mode) + tuple(state.raw_values.get(cid, "") for cid in fields))
        except OSError as exc:
            self.data_log_var.set(False)
            self._append_log(f"DATA LOG ERROR: {exc}")

    def _drain_events(self) -> None:
        deadline = time.monotonic() + 0.008
        self._log_batch = []
        try:
            if self.controller:
                for _ in range(256):
                    try:event = self.controller.events.get_nowait()
                    except queue.Empty:break
                    self._handle_event(event, render=False)
                    if time.monotonic() >= deadline:break
            # Use the latest snapshot, not a backlog of old UI snapshots.
            if isinstance(self.controller, LaserController):
                self.state = self.controller.state
            self._refresh_ui()
            self._write_data_log(self.state)
        finally:
            lines, self._log_batch = self._log_batch, None
            if lines:self._insert_log(''.join(lines))
        self._schedule(80, self._drain_events)

    def _handle_event(self, event: ControllerEvent, *, render: bool = True) -> None:
        if event.kind == "command" and event.result:
            result = event.result
            labels = {"queued":"대기", "sent":"전송", "receipt":"수신·적용 미확인",
                      "acknowledged":"ACK·적용 미확인", "confirmed":"설정 조회 일치",
                      "observed":"상태 재조회 완료", "unverified":"적용 미확인",
                      "rejected":"응답 거부", "mismatch":"설정 불일치",
                      "timeout":"통신 실패·적용 불명", "cancelled":"전송 취소"}
            self.connection_text.set(f"#{result.token} [{result.command_id}] {labels.get(result.status,result.status)}")
            if result.command_id in (2022, 2023):
                self.tec_result.set(f"TEC {'ON' if result.command_id == 2022 else 'OFF'}: {labels.get(result.status,result.status)}")
            self._append_log(event.message)
        elif event.kind == "output" and event.output:
            operation = event.output
            descriptions = {
                "pending": "pending · channel readback required",
                "stopping": "stopping · PC OFF confirmation pending",
                "confirmed": "PC1+PC2 " + ("ON" if operation.action == "RUN" else "OFF") + " confirmed",
                "failed": "failed · both PC OFF confirmed",
                "unverified": "unverified · check channel readbacks",
            }
            self.output_result.set(f"Last {operation.action}: {descriptions.get(operation.status, operation.status)}")
            self.connection_text.set(event.message)
            self._append_log(event.message)
        elif event.kind == "log":
            self._append_log(event.message)
        elif event.kind == "error":
            self.connection_text.set(event.message)
            self.connection_indicator.set("fault", "통신 오류")
            self._append_log(f"ERROR {event.message}")
        elif event.kind == "connection":
            if event.state and event.state.connected:
                self.connection_indicator.set("ok", event.state.transport_name)
                self.connection_text.set(event.message)
            else:
                self.connection_indicator.set("fault" if event.message != "Disconnected" else "off", "연결 실패" if event.message != "Disconnected" else "연결 끊김")
                self.connection_text.set(event.message)
        if event.state:
            self.state = event.state
            self._remember_fault_state(event.state)
            if render:
                self._refresh_ui()
                self._write_data_log(event.state)

    def _append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"{stamp}  {message}\n"
        if self._log_batch is not None:self._log_batch.append(line)
        else:self._insert_log(line)

    def _insert_log(self, text: str) -> None:
        follow = self.log_text.yview()[1] >= 0.995
        self.log_text.insert("end", text)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 1000:self.log_text.delete("1.0", f"{line_count-999}.0")
        if follow:self.log_text.see("end")

    def _remember_fault_state(self, state: DeviceState) -> None:
        for cid in (1014, 1066, 1088, 1089, 1039):
            previous = self._fault_raw_last.get(cid)
            if state.is_fresh(cid) and (previous is None or state.updated_at[cid] >= previous[2]):
                self._fault_raw_last[cid] = (state.value(cid), state.raw_values[cid], state.updated_at[cid])
        for index in range(len(FAULT_LABELS)):
            value = state.fault_state(index)
            stamp = state.last_reply_at
            previous = self._fault_last_stamp.get(index)
            if value is not None and stamp is not None and (previous is None or stamp >= previous):
                self._fault_last[index] = value
                self._fault_last_stamp[index] = stamp

    @staticmethod
    def _render(value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _bool_value(value: object) -> bool | None:
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"1", "ON", "TRUE", "EXT", "YES"}:
                return True
            if normalized in {"0", "OFF", "FALSE", "INT", "NO"}:
                return False
        return None

    def _refresh_ui(self) -> None:
        self._remember_fault_state(self.state)
        external = self.config.pump_mode == "external"
        if external:
            confirmed = self.state.external_opt_out_confirmed
            seed = self.state.value(1065) if self.state.is_fresh(1065) else None
            set_if_changed(self.external_timing_text, 
                f"EXTERNAL PUMP · seed {self._render(seed)} MHz · expected pump {self._render(self.config.external_pump_hz)} Hz (unmeasured)"
            )
            reason = self.state.external_enable_reason()
            if confirmed:
                status = "Opt-out confirmed - " + (reason or "TDG enable checks passed; optical sync unverified")
            elif self.state.is_fresh(1068) and self.state.value(1068) == 0:
                status = "Empower opt-out is OFF; apply explicitly with fresh HV OFF"
            else:
                status = "Empower opt-out unavailable / unconfirmed; REFRESH required"
            set_if_changed(self.external_status_text, status)
            self.opt_out_button.configure(state="normal" if self.controller is not None and self.controller.running and self.state.high_voltage is False else "disabled")
        live = set(FAST_POLL_IDS + HV_POLL_IDS + FAULT_QUERY_IDS)
        if external:
            live.update(EXTERNAL_REQUIRED_READS)
        for cid, variable in self.value_vars.items():
            if external and not query_allowed(cid, self.config.pump_mode):
                set_if_changed(variable, "N/A")
                continue
            value = self.state.value(cid)
            if not self.state.link_fresh() or (cid in live and not self.state.is_fresh(cid)):
                value = None
            # Preserve current suffixes such as MA without guessing their SI scale.
            if cid in {1055, 1056} and value is not None:
                set_if_changed(variable, self.state.raw_values.get(cid, self._render(value)).strip())
            else:
                set_if_changed(variable, self._render(value))
        for cid, cards in self.metric_cards.items():
            if external and not query_allowed(cid, self.config.pump_mode):
                for card in cards:
                    card.set("N/A")
                continue
            value = self.state.value(cid) if self.state.link_fresh() else None
            if cid in live and not self.state.is_fresh(cid):
                value = None
            for card in cards:
                card.set(value, digits=getattr(card, "_digits", 2))
        for cid, draft in self.drafts.items():
            if external and not query_allowed(cid, self.config.pump_mode):
                set_if_changed(draft.readback, "N/A")
                continue
            value = self.state.value(cid) if self.state.link_fresh() else None
            if external and cid in EXTERNAL_REQUIRED_READS and not self.state.is_fresh(cid):
                value = None
            if value is not None:
                if cid in (1050, 1051):
                    oscillator_external = self._bool_value(value)
                    value = None if oscillator_external is None else ("EXT" if oscillator_external else "INT")
                elif cid == 1080:
                    value = {0: "CONT", 1: "COUNT", 2: "COUNT 1"}.get(value)
                elif isinstance(draft.variable, tk.BooleanVar):
                    value = self._bool_value(value)
                else:
                    value = self._render(value)
            draft.sync(value)
        for (channel, field), draft in self.delay_drafts.items():
            status = self.state.delays.get(channel)
            value = getattr(status, field) if status and self.state.link_fresh() and (1044 + channel) not in self.state.invalid_ids and (1044 + channel) not in self.state.pending_readbacks else None
            if external and channel in (1, 2) and not self.state.is_fresh(1044 + channel):
                value = None
            if value is not None and field == "switch":
                value = value.lower()
            draft.sync(value)
        for name, indicator in self.subsystem_indicators.items():
            indicator.set(self.state.communication_state(name), "N/A" if external and name == "EMPOWER" else "COMM")
        if self.state.link_fresh():
            self.connection_indicator.set("ok", self.state.transport_name)
        elif self.state.transport_open:
            self.connection_indicator.set("fault" if self.state.last_reply_at else "unknown", "No fresh readback")
        else:
            self.connection_indicator.set("off", "Disconnected")
        hv = self.state.high_voltage
        self.hv_indicator.set("fault" if hv else ("off" if hv is False else "unknown"),
                              "Device HV ON" if hv else ("Device HV OFF" if hv is False else "Device HV unknown / stale"))
        key = self.state.key_interlock
        key_text = "asserted" if key is True else "clear" if key is False else "unknown/stale"
        def measured_voltage(cid):
            value = self.state.value(cid)
            return f"{value:g} V" if self.state.is_fresh(cid) and isinstance(value, (int, float)) else "unknown/stale"
        set_if_changed(self.output_readbacks, 
            f"Device HV: {'ON' if hv is True else 'OFF' if hv is False else 'unknown/stale'} · Key interlock: {key_text}\n"
            f"HV1: {measured_voltage(1042)} · HV2: {measured_voltage(1043)}\n"
            f"PC1: {self.state.pc_output(1) or 'unknown/stale'} · PC2: {self.state.pc_output(2) or 'unknown/stale'}"
        )
        tec = self.state.tec_enabled
        self.tec_indicator.set("ok" if tec is True else "off" if tec is False else "unknown",
                               "TEC reported ON" if tec is True else "TEC reported OFF" if tec is False else "TEC unknown/stale")
        words = self.state.fault_words if self.state.is_fresh(1014) else ()
        fault_raw = "Empower N/A" if external else " ".join(str(word) for word in words) if words else "Empower —"
        if not external and not words and 1014 in self._fault_raw_last:
            fault_raw = self._fault_raw_last[1014][1] + " [last/stale]"
        set_if_changed(self.fault_raw_var, fault_raw)
        def raw_status(cid):
            if self.state.is_fresh(cid):return self.state.raw_values.get(cid, "—")
            previous = self._fault_raw_last.get(cid)
            return (previous[1] + " [last/stale]") if previous else "—"
        set_if_changed(self.fault_health_raw_var, " | ".join(
            f"{name} {raw_status(cid)}" for name, cid in (("TDG", 1066), ("TCU", 1088), ("COM", 1089), ("BWD", 1039))
        ))
        def bit_status(cid, mask):
            if not self.state.is_fresh(cid):
                return "unknown/stale"
            return "SET" if int(self.state.value(cid)) & mask else "clear"
        pc_link = "reply received" if self.state.link_fresh() else "no fresh reply"
        set_if_changed(self.fault_diagnostic_var, 
            f"PC link: {pc_link}. Controller Main comm flag: {bit_status(1089, 0x01)}.\n"
            f"TDG Key bit: current {bit_status(1039, 0x4000)} / fault register {bit_status(1066, 0x4000)}. "
            "Reset requests a new fault readback; it does not force flags clear."
        )
        active, known = self.state.fault_active, self.state.faults_known
        remembered_active = any(
            int(self._fault_raw_last[cid][0]) & mask for cid, mask in
            ((1066, 0xffffffff), (1088, 0x14), (1089, ~0x04 if external else 0xffffffff), (1039, 0x00330000))
            if cid in self._fault_raw_last and not self.state.is_fresh(cid))
        if not external and not self.state.is_fresh(1014) and 1014 in self._fault_raw_last:
            remembered_active = remembered_active or any(self._fault_raw_last[1014][0])
        if not known and remembered_active:
            self.fault_summary.set("fault", "Last reported FAULT · current data unavailable/stale")
        else:
            self.fault_summary.set("fault" if active else ("ok" if known else "unknown"),
                "REPORTED SYSTEM FAULT" if active else "No reported faults; external pump unmonitored" if external and known
                else "No reported faults" if known else "Fault data unavailable/stale")
        for index, indicator in enumerate(self.fault_indicators):
            if external and FAULT_LABELS[index].startswith("Empower"):
                indicator.set("off", FAULT_LABELS[index] + " (N/A)")
                continue
            fault = self.state.fault_state(index)
            last = self._fault_last.get(index)
            if fault is None and last is not None:
                indicator.set("fault" if last else "warning", FAULT_LABELS[index] + " *")
            else:
                indicator.set("unknown" if fault is None else "fault" if fault else "ok", FAULT_LABELS[index])

    def _raw_serial_shortcut(self, _event: tk.Event | None = None) -> str:
        self.open_raw_serial_service()
        return "break"

    def open_raw_serial_service(self) -> None:
        if self.config.pump_mode == "external":
            messagebox.showinfo("External pump mode", "Raw RS-232 service is unavailable in External Pump mode.", parent=self.root)
            return
        if self.raw_serial_dialog is not None:
            try:
                if self.raw_serial_dialog.window.winfo_exists():
                    self.raw_serial_dialog.show()
                    return
            except tk.TclError:
                self.raw_serial_dialog = None
        if not self.rs232_warning_acknowledged:
            accepted = messagebox.askyesno(
                "Raw RS-232 service mode",
                "Raw RS-232는 command ID, ECLIPSE framing, 상태 검사를 우회하고 입력한 byte를 그대로 전송합니다.\n\n"
                "출력이 물리적으로 차단된 점검 환경에서만 사용하십시오. 서비스 터미널을 열까요?",
                icon="warning",
                parent=self.root,
            )
            if not accepted:
                return
            self.rs232_warning_acknowledged = True
        self.raw_serial_dialog = RawSerialDialog(self.root, on_close=self._raw_serial_closed)
        self.raw_serial_dialog.show()

    def _raw_serial_closed(self) -> None:
        self.raw_serial_dialog = None

    def _apply_external_sources(self) -> bool:
        if self.config.pump_mode != "external" or self.controller is None or not self.controller.running:
            return False
        if self.controller.state.high_voltage is not False:
            self._query((1021, 1050, 1051))
            messagebox.showwarning("HV state required", "Confirm a fresh HV OFF readback before changing timing sources.", parent=self.root)
            return False
        if self.config.mode == "udp" and not messagebox.askyesno("EXT SOURCES",
                "Set oscillator sync and amplifier trigger to EXT?", parent=self.root):
            return False
        try:
            self.controller.submit_batch(((2030,"EXT"),(2031,"EXT")), origin="Apply EXT sources")
        except (PermissionError, ValueError) as exc:
            messagebox.showwarning("명령 차단", str(exc), parent=self.root)
            return False
        self.connection_text.set("EXT sources queued · both readbacks pending")
        return True

    def _save_external_timing(self, values: dict[str, str], parent=None) -> bool:
        if self.config.pump_mode != "external":
            return False
        reason = self._configuration_change_reason()
        if reason:
            messagebox.showwarning("Timing profile change blocked", reason, parent=parent or self.root)
            return False
        try:
            candidate = replace(
                self.config,
                external_seed_mhz=float(values["external_seed_mhz"]),
                external_seed_tolerance_mhz=float(values["external_seed_tolerance_mhz"]),
                external_pump_hz=float(values["external_pump_hz"]),
            )
            candidate.save()
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Timing profile not saved", str(exc), parent=parent or self.root)
            return False
        self.config = candidate
        self.connect()
        return True

    def show_external_timing(self) -> None:
        if self.config.pump_mode != "external":
            return
        window = tk.Toplevel(self.root)
        window.title("External timing profile")
        window.configure(bg=PANEL)
        window.transient(self.root)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        fields = (
            ("Expected seed (MHz)", "external_seed_mhz"),
            ("Allowed seed deviation (± MHz)", "external_seed_tolerance_mhz"),
            ("Expected pump rate (Hz; reference only)", "external_pump_hz"),
        )
        values = {}
        for row, (label, key) in enumerate(fields):
            values[key] = tk.StringVar(value=str(getattr(self.config, key)))
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=values[key], width=20).grid(row=row, column=1, sticky="ew", padx=(15, 0), pady=6)
        ttk.Label(frame, text=(
            "Pump rate is a planning value; the TDG does not provide a verified pump-rate readback here.\n"
            "Saving changes the software checks and reconnects without replaying writes. It does not write timing or enable HV.\n"
            "Optical pump/seed timing must be verified separately."
        ), wraplength=540, style="Muted.TLabel").grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(12, 18))
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields)+1, column=0, columnspan=2, sticky="e")
        def save():
            if self._save_external_timing({key: variable.get() for key, variable in values.items()}, window):
                window.destroy()
        ttk.Button(buttons, text="APPLY EXT SOURCES", command=self._apply_external_sources).pack(side="left", padx=5)
        ttk.Button(buttons, text="CANCEL", command=window.destroy).pack(side="left", padx=5)
        ttk.Button(buttons, text="SAVE & RECONNECT", style="Accent.TButton", command=save).pack(side="left", padx=5)
        frame.columnconfigure(1, weight=1)
        window.update_idletasks()
        window.geometry(f"590x{window.winfo_reqheight()}")

    def show_connection_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Connection settings")
        window.configure(bg=PANEL)
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        values = {
            "mode": tk.StringVar(value=self.config.mode),
            "pump_mode": tk.StringVar(value=self.config.pump_mode),
            "remote_host": tk.StringVar(value=self.config.remote_host),
            "remote_port": tk.StringVar(value=str(self.config.remote_port)),
            "local_host": tk.StringVar(value=self.config.local_host),
            "local_port": tk.StringVar(value=str(self.config.local_port)),
            "timeout": tk.StringVar(value=str(self.config.timeout_seconds)),
            "poll": tk.StringVar(value=str(self.config.poll_interval_seconds)),
        }
        labels = (("Transport", "mode"), ("Pump configuration", "pump_mode"), ("Remote host", "remote_host"), ("Remote UDP port", "remote_port"), ("Local bind host", "local_host"), ("Local UDP port", "local_port"), ("Timeout (s)", "timeout"), ("Poll cycle (s)", "poll"))
        for row, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6)
            if key == "mode":
                widget = ttk.Combobox(frame, textvariable=values[key], values=("simulator", "udp"), state="readonly", width=28)
            elif key == "pump_mode":
                widget = ttk.Combobox(frame, textvariable=values[key], values=("empower", "external"), state="readonly", width=28)
            else:
                widget = ttk.Entry(frame, textvariable=values[key], width=31)
            widget.grid(row=row, column=1, sticky="ew", padx=(15, 0), pady=6)
        ttk.Label(frame, text="External pump is controlled separately. Mode changes never apply opt-out or enable outputs.\nLegacy UDP defaults: 10.19.70.13:1024, local :1024.", style="Muted.TLabel").grid(row=len(labels), column=0, columnspan=2, sticky="w", pady=(12, 18))

        def apply() -> None:
            reason = self._configuration_change_reason()
            if reason:
                messagebox.showwarning("Connection change blocked", reason, parent=window)
                return
            try:
                remote_port = int(values["remote_port"].get())
                local_port = int(values["local_port"].get())
                timeout = float(values["timeout"].get())
                poll = float(values["poll"].get())
                if not 1 <= remote_port <= 65535 or not 0 <= local_port <= 65535 or not math.isfinite(timeout) or not math.isfinite(poll) or timeout <= 0 or poll < 0.2:
                    raise ValueError
            except ValueError:
                messagebox.showerror("잘못된 설정", "포트, timeout, poll 값을 확인하십시오.", parent=window)
                return
            try:
                candidate = replace(
                    self.config,
                    mode=values["mode"].get(),
                    pump_mode=values["pump_mode"].get(),
                    remote_host=values["remote_host"].get().strip(),
                    remote_port=remote_port,
                    local_host=values["local_host"].get().strip(),
                    local_port=local_port,
                    timeout_seconds=timeout,
                    poll_interval_seconds=poll,
                )
                candidate.save()
            except (OSError, ValueError, TypeError) as exc:
                messagebox.showerror("Settings not saved", str(exc), parent=window)
                return
            # Change the live profile only after the complete candidate is saved.
            self.config = candidate
            window.destroy()
            self.connect()

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(labels) + 1, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="DISCONNECT", command=self.disconnect).pack(side="left", padx=5)
        ttk.Button(buttons, text="CANCEL", command=window.destroy).pack(side="left", padx=5)
        ttk.Button(buttons, text="SAVE & CONNECT", style="Accent.TButton", command=apply).pack(side="left", padx=5)
        frame.columnconfigure(1, weight=1)
        window.update_idletasks()
        window.geometry(f"560x{window.winfo_reqheight()}")

    def export_snapshot(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.root, title="상태 내보내기", defaultextension=".csv", filetypes=(("CSV", "*.csv"),))
        if not path:
            return
        try:
            with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(("transport", "pump_mode", "command_id", "command", "value", "updated_utc"))
                for command_id, raw in sorted(self.state.raw_values.items()):
                    writer.writerow((self.state.transport_name, self.state.pump_mode, command_id, COMMANDS.get(command_id).text if command_id in COMMANDS else "", raw, self.state.updated_at.get(command_id, "")))
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc), parent=self.root)

    def show_safety_info(self) -> None:
        messagebox.showinfo(
            "Safety & protocol",
            "이 프로그램은 소프트웨어 호환 구현이며 안전 인터록이 아닙니다.\n\n"
            "• 기본 모드는 simulator이며 네트워크 패킷을 보내지 않습니다.\n"
            "• UDP writes require recent readbacks and command-specific checks.\n"
            "• 물리적 E-stop, key switch, enclosure interlock가 항상 우선합니다.\n"
            "• 최초 실제 연결은 출력이 차단된 bench 조건에서 packet capture와 함께 검증하십시오.\n\n"
            "Protocol: UDP/1024, Spectra-Physics CMD_ECLIPSE/REPLY_ECLIPSE framing.",
            parent=self.root,
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "Spitfire Python Control",
            f"Spitfire Python Control {__version__}\n"
            "Clean-room Python reimplementation of the 1.6.0 operator GUI.\n\n"
            "Original vendor contact embedded in the legacy UI:\nservice@spectra-physics.com",
            parent=self.root,
        )

    def close(self) -> None:
        if self._closed:
            return
        self.run_button.cancel()
        self._closed = True
        for token in self._after_jobs:
            try:
                self.root.after_cancel(token)
            except tk.TclError:
                pass
        self._after_jobs.clear()
        if self.raw_serial_dialog is not None:
            self.raw_serial_dialog.close()
        if self.controller:
            self.controller.stop()
        try:
            self.config.save()
        finally:
            self.root.destroy()
