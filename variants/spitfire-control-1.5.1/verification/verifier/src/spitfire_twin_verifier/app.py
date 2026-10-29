"""Tk desktop application for side-by-side Spitfire verification."""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .catalog import COMMANDS
from .compare import ComparisonResult, compare_transactions
from .config import AppConfig
from .demo import run_loopback_demo
from .model import VirtualSpitfire
from .network import local_ipv4_addresses, setup_text, validate_ipv4
from .records import CaptureMessage, CaptureStore, Transaction
from .report import write_report
from .server import ServerError, VirtualDeviceServer


class VerifierApp:
    def __init__(self, root: tk.Tk, config: AppConfig | None = None):
        self.root = root
        self.config = config or AppConfig.load()
        self.capture = CaptureStore()
        self.device = VirtualSpitfire(isolated_clients=self.config.isolated_clients)
        self.server: VirtualDeviceServer | None = None
        self.latest_result: ComparisonResult | None = None
        self.event_queue: queue.Queue[Transaction | CaptureMessage] = queue.Queue()
        self.capture.add_listener(self.event_queue.put)
        self._traffic_items: dict[str, Transaction] = {}
        self._client_keys: dict[str, str] = {}

        root.title(f"Spitfire Twin Verifier {__version__}")
        usable_width = max(800, root.winfo_screenwidth() - 64)
        usable_height = max(560, root.winfo_screenheight() - 96)
        root.geometry(f"{min(1380, usable_width)}x{min(860, usable_height)}+24+24")
        root.minsize(min(1024, usable_width), min(700, usable_height))
        self._style()
        self._variables()
        self._build()
        self._update_setup_text()
        self._poll_events()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names() and sys.platform == "win32":
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Good.TLabel", foreground="#18794e", font=("Segoe UI", 10, "bold"))
        style.configure("Bad.TLabel", foreground="#b42318", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _variables(self) -> None:
        c = self.config
        self.bind_ip = tk.StringVar(value=c.bind_ip)
        self.bind_port = tk.StringVar(value=str(c.bind_port))
        self.original_ip = tk.StringVar(value=c.original_ip)
        self.python_ip = tk.StringVar(value=c.python_ip)
        self.original_label = tk.StringVar(value=c.original_label)
        self.python_label = tk.StringVar(value=c.python_label)
        self.output_directory = tk.StringVar(value=c.output_directory)
        self.isolated = tk.BooleanVar(value=c.isolated_clients)
        self.ignore_polling = tk.BooleanVar(value=True)
        self.server_status = tk.StringVar(value="정지됨")
        self.original_status = tk.StringVar(value="아직 패킷 없음")
        self.python_status = tk.StringVar(value="아직 패킷 없음")
        self.capture_summary = tk.StringVar(value="트랜잭션 0개")
        self.compare_summary = tk.StringVar(value="두 프로그램의 패킷을 받은 뒤 비교를 생성하세요.")
        self.profile_summary = tk.StringVar(value="Nominal: 응답 변형 없음")
        self.state_client = tk.StringVar(value="")
        self.scenario_name = tk.StringVar(value="A. 시작 및 기본 조회")
        self.observation_field = tk.StringVar(value="Q-switch 주파수")
        self.observation_expected = tk.StringVar(value="1250 Hz")
        self.observation_original = tk.StringVar()
        self.observation_python = tk.StringVar()
        self.observation_notes = tk.StringVar()
        self.scenario_status = tk.StringVar(value="시나리오를 시작한 뒤 XP → Python 순서로 같은 조작을 수행하세요.")

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Spitfire Twin Verifier", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="XP 원본 ↔ 가상 장비 ↔ 여러 Python 버전", foreground="#526170").pack(side="left", padx=16, pady=(7, 0))
        self.main_start_button = ttk.Button(header, text="가상 장비 시작", style="Accent.TButton", command=self.toggle_server)
        self.main_start_button.pack(side="right")

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self.dashboard = ttk.Frame(self.notebook, padding=14)
        self.traffic_tab = ttk.Frame(self.notebook, padding=10)
        self.compare_tab = ttk.Frame(self.notebook, padding=10)
        self.device_tab = ttk.Frame(self.notebook, padding=12)
        self.setup_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.dashboard, text="1. 대시보드")
        self.notebook.add(self.traffic_tab, text="2. 실시간 통신")
        self.notebook.add(self.compare_tab, text="3. 차이 비교")
        self.notebook.add(self.device_tab, text="4. 가상 장비 / 응답 실험")
        self.notebook.add(self.setup_tab, text="5. 네트워크 설정")
        self._build_dashboard()
        self._build_traffic()
        self._build_compare()
        self._build_device()
        self._build_setup()
        self.scenario_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.scenario_tab, text="6. 시나리오 / 화면 기록")
        self._build_scenario()
        self.diagnostics_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.diagnostics_tab, text="7. 오류 / 시험 이력")
        self.diagnostics = scrolledtext.ScrolledText(self.diagnostics_tab, wrap="word", font=("Consolas", 10))
        self.diagnostics.pack(fill="both", expand=True)
        self.diagnostics.configure(state="disabled")
        from .workbench_ui import WorkbenchPanel
        self.workbench_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.insert(0, self.workbench_tab, text="버전·시나리오")
        self.workbench = WorkbenchPanel(self, self.workbench_tab)
        self.notebook.select(self.workbench_tab)

    def _entry_row(self, parent, row: int, label: str, variable: tk.Variable, width=22) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _build_dashboard(self) -> None:
        paned = ttk.Panedwindow(self.dashboard, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left, right = ttk.Frame(paned, padding=10), ttk.Frame(paned, padding=10)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        ttk.Label(left, text="가상 장비 주소", style="Section.TLabel").pack(anchor="w")
        form = ttk.Frame(left)
        form.pack(fill="x", pady=8)
        self._entry_row(form, 0, "장비 Bind IPv4", self.bind_ip)
        self._entry_row(form, 1, "UDP Port", self.bind_port)
        self._entry_row(form, 2, "XP VM IPv4", self.original_ip)
        self._entry_row(form, 3, "Windows/Python IPv4", self.python_ip)
        form.columnconfigure(1, weight=1)
        ttk.Checkbutton(form, text="클라이언트별 상태 분리 (비교용 권장)", variable=self.isolated).grid(row=4, column=0, columnspan=2, sticky="w", pady=8)

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=8)
        self.dashboard_start = ttk.Button(actions, text="가상 장비 시작", style="Accent.TButton", command=self.toggle_server)
        self.dashboard_start.pack(side="left")
        ttk.Button(actions, text="캡처 초기화", command=self.clear_capture).pack(side="left", padx=6)
        ttk.Button(actions, text="안전한 데모 실행", command=self.run_demo).pack(side="left")

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Label(left, text="빠른 사용 순서", style="Section.TLabel").pack(anchor="w")
        instructions = (
            "① [네트워크 설정] 탭의 주소를 XP VM과 Windows에 한 번 설정\n"
            "② 가상 장비 시작 → XP 원본 GUI 실행\n"
            "③ Python GUI의 Remote=.13, Local=.1을 지정해 실행\n"
            "④ 두 GUI에서 같은 버튼/설정값을 순서대로 조작\n"
            "⑤ [차이 비교] 탭에서 비교 생성 및 HTML 저장"
        )
        ttk.Label(left, text=instructions, justify="left").pack(anchor="w", pady=8)

        ttk.Label(right, text="상태", style="Section.TLabel").pack(anchor="w")
        status = ttk.Frame(right)
        status.pack(fill="x", pady=8)
        ttk.Label(status, text="가상 장비").grid(row=0, column=0, sticky="w", pady=6)
        self.server_status_label = ttk.Label(status, textvariable=self.server_status, style="Bad.TLabel")
        self.server_status_label.grid(row=0, column=1, sticky="e")
        ttk.Label(status, text="XP 원본").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Label(status, textvariable=self.original_status).grid(row=1, column=1, sticky="e")
        ttk.Label(status, text="Python GUI").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Label(status, textvariable=self.python_status).grid(row=2, column=1, sticky="e")
        ttk.Label(status, text="현재 캡처").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Label(status, textvariable=self.capture_summary).grid(row=3, column=1, sticky="e")
        status.columnconfigure(1, weight=1)

        ttk.Separator(right).pack(fill="x", pady=12)
        ttk.Label(right, text="안전 경계", style="Section.TLabel").pack(anchor="w")
        warning = (
            "이 서버는 수신한 패킷을 실제 장비로 전달하지 않습니다.\n"
            "실제 레이저 제어망과 분리된 Host-only 네트워크에서 사용하세요.\n"
            "프로그램 화면 해석은 자동 판정 범위가 아니므로 보고서의\n"
            "ui_observations.csv에 육안 관찰값을 함께 기록할 수 있습니다."
        )
        ttk.Label(right, text=warning, foreground="#8a4b00", justify="left", wraplength=430).pack(anchor="w", pady=8)

    def _build_traffic(self) -> None:
        toolbar = ttk.Frame(self.traffic_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, textvariable=self.capture_summary, style="Section.TLabel").pack(side="left")
        ttk.Button(toolbar, text="캡처 JSONL 저장", command=self.save_capture).pack(side="right")
        ttk.Button(toolbar, text="선택 패킷 상세", command=self.show_packet_detail).pack(side="right", padx=6)
        columns = ("seq", "time", "client", "id", "kind", "command", "response", "latency", "status")
        self.traffic_tree = ttk.Treeview(self.traffic_tab, columns=columns, show="headings", selectmode="browse")
        labels = {"seq": "#", "time": "UTC", "client": "클라이언트", "id": "ID", "kind": "종류",
                  "command": "보낸 명령", "response": "가상 장비 응답", "latency": "ms", "status": "상태"}
        widths = {"seq": 55, "time": 105, "client": 145, "id": 60, "kind": 55,
                  "command": 275, "response": 230, "latency": 70, "status": 85}
        for column in columns:
            self.traffic_tree.heading(column, text=labels[column])
            self.traffic_tree.column(column, width=widths[column], stretch=column in {"command", "response", "client"})
        scroll_y = ttk.Scrollbar(self.traffic_tab, orient="vertical", command=self.traffic_tree.yview)
        scroll_x = ttk.Scrollbar(self.traffic_tab, orient="horizontal", command=self.traffic_tree.xview)
        self.traffic_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.traffic_tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.traffic_tree.bind("<Double-1>", lambda _event: self.show_packet_detail())

    def _build_compare(self) -> None:
        toolbar = ttk.Frame(self.compare_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(toolbar, text="동일 폴링 반복만 압축 (응답·오류는 비교)", variable=self.ignore_polling).pack(side="left")
        ttk.Button(toolbar, text="비교 생성", style="Accent.TButton", command=self.generate_comparison).pack(side="right")
        ttk.Button(toolbar, text="HTML/JSON 보고서 저장", command=self.export_report).pack(side="right", padx=6)
        ttk.Label(self.compare_tab, textvariable=self.compare_summary, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        columns = ("status", "id", "original", "python", "original_reply", "python_reply", "note")
        self.compare_tree = ttk.Treeview(self.compare_tab, columns=columns, show="headings")
        headers = ("판정", "ID", "XP 원본 명령", "Python 명령", "XP 응답", "Python 응답", "설명")
        widths = (115, 60, 230, 230, 150, 150, 260)
        for column, header, width in zip(columns, headers, widths):
            self.compare_tree.heading(column, text=header)
            self.compare_tree.column(column, width=width, stretch=column in {"original", "python", "note"})
        self.compare_tree.tag_configure("MATCH", foreground="#18794e")
        self.compare_tree.tag_configure("DIFF", foreground="#b42318")
        ybar = ttk.Scrollbar(self.compare_tab, orient="vertical", command=self.compare_tree.yview)
        self.compare_tree.configure(yscrollcommand=ybar.set)
        self.compare_tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")

    def _build_device(self) -> None:
        paned = ttk.Panedwindow(self.device_tab, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left, right = ttk.Frame(paned, padding=8), ttk.Frame(paned, padding=8)
        paned.add(left, weight=2)
        paned.add(right, weight=3)
        ttk.Label(left, text="동일 응답 조건 주입", style="Section.TLabel").pack(anchor="w")
        ttk.Label(left, text="두 클라이언트에 같은 조건을 적용해 오류 처리 차이를 관찰합니다.", wraplength=360).pack(anchor="w", pady=(2, 10))
        form = ttk.Frame(left)
        form.pack(fill="x")
        self.inject_id = tk.StringVar(value="1010")
        self.inject_value = tk.StringVar(value="")
        self.inject_delay = tk.StringVar(value="0")
        self.inject_error = tk.BooleanVar(value=False)
        self.inject_drop = tk.BooleanVar(value=False)
        self.inject_request_drop = tk.BooleanVar(value=False)
        self.inject_crlf = tk.BooleanVar(value=False)
        self.inject_bad_header = tk.BooleanVar(value=False)
        self._entry_row(form, 0, "Command ID", self.inject_id)
        self._entry_row(form, 1, "강제 응답 (빈칸=없음)", self.inject_value)
        self._entry_row(form, 2, "응답 지연 ms", self.inject_delay)
        ttk.Checkbutton(form, text="ERROR:INJECTED 반환", variable=self.inject_error).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(form, text="응답 유실 (명령 실행 후 응답만 누락)", variable=self.inject_drop).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(form, text="CRLF 줄끝 사용", variable=self.inject_crlf).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(form, text="잘못된 reply header", variable=self.inject_bad_header).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(form, text="요청 유실 (명령 실행 안 함)", variable=self.inject_request_drop).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)
        form.columnconfigure(1, weight=1)
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="조건 적용", command=self.apply_profile).pack(side="left")
        ttk.Button(actions, text="모두 해제", command=self.clear_profile).pack(side="left", padx=6)
        ttk.Label(left, textvariable=self.profile_summary, foreground="#8a4b00", wraplength=390).pack(anchor="w", pady=6)

        ttk.Separator(left).pack(fill="x", pady=12)
        ttk.Label(left, text="클라이언트 상태", style="Section.TLabel").pack(anchor="w")
        client_box = ttk.Combobox(left, textvariable=self.state_client, state="readonly", values=[])
        client_box.pack(fill="x", pady=6)
        client_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_state())
        ttk.Button(left, text="상태 새로고침", command=self.refresh_state).pack(anchor="w")
        self.state_client_box = client_box

        ttk.Label(right, text="가상 장비 Query 값", style="Section.TLabel").pack(anchor="w")
        self.state_tree = ttk.Treeview(right, columns=("id", "command", "value"), show="headings")
        for column, header, width in (("id", "ID", 65), ("command", "Query", 240), ("value", "현재 raw 값", 220)):
            self.state_tree.heading(column, text=header)
            self.state_tree.column(column, width=width, stretch=column != "id")
        self.state_tree.pack(fill="both", expand=True, pady=6)

    def _build_setup(self) -> None:
        toolbar = ttk.Frame(self.setup_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="현재 주소로 안내 갱신", command=self._update_setup_text).pack(side="left")
        ttk.Button(toolbar, text="클립보드 복사", command=self.copy_setup).pack(side="left", padx=6)
        ttk.Label(toolbar, text="감지된 로컬 IPv4: " + ", ".join(local_ipv4_addresses()), foreground="#526170").pack(side="right")
        self.setup_text_widget = scrolledtext.ScrolledText(self.setup_tab, wrap="word", font=("Consolas", 10))
        self.setup_text_widget.pack(fill="both", expand=True)

    def _build_scenario(self) -> None:
        ttk.Label(self.scenario_tab, text="같은 단계에서 두 프로그램을 비교", style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.scenario_tab, text="시작 → XP 조작 → Python 같은 조작 → 화면값 기록 → 단계 종료. 새 시험은 캡처 초기화 후 시작합니다.").pack(anchor="w", pady=8)
        choices = ("A. 시작 및 기본 조회", "B. Q-switch 1250 Hz", "C. Delay channel 1 12.5",
                   "D. OFF / HV OFF / STOP", "E. 오류 응답 및 복구")
        ttk.Combobox(self.scenario_tab, textvariable=self.scenario_name, values=choices, width=60).pack(anchor="w", pady=6)
        actions = ttk.Frame(self.scenario_tab)
        actions.pack(anchor="w", pady=6)
        ttk.Button(actions, text="시나리오 시작", command=self.start_scenario).pack(side="left")
        ttk.Button(actions, text="단계 종료", command=self.finish_scenario).pack(side="left", padx=6)
        form = ttk.Frame(self.scenario_tab)
        form.pack(fill="x", pady=12)
        for row, label, variable in ((0, "화면 항목", self.observation_field), (1, "기대값 (선택)", self.observation_expected),
                                     (2, "XP 실제 표시", self.observation_original), (3, "Python 실제 표시", self.observation_python),
                                     (4, "메모", self.observation_notes)):
            self._entry_row(form, row, label, variable, width=60)
        form.columnconfigure(1, weight=1)
        ttk.Button(self.scenario_tab, text="관찰값 기록", command=self.record_observation).pack(anchor="w")
        ttk.Label(self.scenario_tab, textvariable=self.scenario_status, wraplength=950).pack(anchor="w", pady=10)
        ttk.Label(self.scenario_tab, text="화면 확인은 사람이 입력한 관찰입니다. wire 판정과 별도로 보고서에 저장됩니다.").pack(anchor="w")

    def start_scenario(self) -> None:
        name = self.scenario_name.get().strip()
        if not name:
            return
        self.capture.mark_scenario(name)
        self.latest_result = None
        self.scenario_status.set(f"진행 중: {name} — XP와 Python에서 같은 순서로 조작하세요.")

    def finish_scenario(self) -> None:
        name = self.capture.scenario
        self.capture.message("SCENARIO_END", name or "unnamed")
        self.capture.mark_scenario("")
        self.scenario_status.set(f"종료: {name}. [비교 생성]으로 현재 결과를 확인하세요.")

    def record_observation(self) -> None:
        item = {"scenario": self.capture.scenario or self.scenario_name.get().strip(),
                "field": self.observation_field.get().strip(), "expected": self.observation_expected.get().strip(),
                "original": self.observation_original.get().strip(), "python": self.observation_python.get().strip(),
                "notes": self.observation_notes.get().strip()}
        if not item["field"] or not item["original"] or not item["python"]:
            messagebox.showerror("화면 관찰", "항목과 양쪽 실제 표시값을 입력하세요.", parent=self.root)
            return
        item["same"] = str(item["original"] == item["python"] and (not item["expected"] or item["original"] == item["expected"]))
        with self.capture.locked():
            observations = self.capture.snapshot().metadata.get("ui_observations", [])
            observations.append(item)
            self.capture.set_metadata(ui_observations=observations)
            self.capture.message("OBSERVATION", item["field"], details=item)
        self.latest_result = None
        self.scenario_status.set(f"화면 관찰 {len(observations)}개 기록됨 · 이번 항목 일치: {item['same']}")

    def _collect_config(self) -> AppConfig:
        bind_ip = validate_ipv4(self.bind_ip.get(), field="Bind IPv4")
        original_ip = validate_ipv4(self.original_ip.get(), field="XP IPv4")
        python_ip = validate_ipv4(self.python_ip.get(), field="Python IPv4")
        if len({bind_ip, original_ip, python_ip}) != 3:
            raise ValueError("장비, XP, Python IPv4는 서로 달라야 합니다.")
        if self.original_label.get().strip() == self.python_label.get().strip():
            raise ValueError("XP/Python 이름은 서로 달라야 합니다.")
        port = int(self.bind_port.get())
        if not 1 <= port <= 65535:
            raise ValueError("UDP port must be 1..65535")
        return AppConfig(bind_ip, port, original_ip, python_ip,
                         self.original_label.get().strip() or "XP Original 1.6.0",
                         self.python_label.get().strip() or "Python 1.3.0",
                         self.isolated.get(), self.output_directory.get().strip() or "verification_reports")

    def toggle_server(self) -> None:
        if self.server and self.server.running:
            self.server.stop()
            self.server = None
            self._set_running(False)
            return
        if self.server is not None:
            self.server.stop()
            self.server = None
        try:
            self.config = self._collect_config()
            self.config.save()
            if self.capture.transactions() and not messagebox.askyesno("새 세션", "새 장비 세션을 시작하면 현재 캡처가 초기화됩니다. 필요한 보고서를 저장했습니까?", parent=self.root):
                return
            profile = self.device.get_profile()
            self.device = VirtualSpitfire(isolated_clients=self.config.isolated_clients)
            self.device.set_profile(profile)
            self.clear_capture()
            labels = {self.config.original_ip: self.config.original_label,
                      self.config.python_ip: self.config.python_label}
            self.server = VirtualDeviceServer(self.config.bind_ip, self.config.bind_port,
                                              self.device, self.capture, labels)
            if hasattr(self, "workbench"):
                self.workbench.configure_server(self.server)
            self.server.start()
        except (ValueError, OSError, ServerError) as exc:
            self.server = None
            messagebox.showerror("가상 장비 시작 실패", str(exc), parent=self.root)
            return
        self._set_running(True)

    def _set_running(self, running: bool) -> None:
        text = "가상 장비 정지" if running else "가상 장비 시작"
        self.main_start_button.configure(text=text)
        self.dashboard_start.configure(text=text)
        self.server_status.set("수신 대기 중" if running else "정지됨")
        self.server_status_label.configure(style="Good.TLabel" if running else "Bad.TLabel")

    def _poll_events(self) -> None:
        changed = False
        try:
            for _ in range(300):
                item = self.event_queue.get_nowait()
                if item.session_id != self.capture.session_id:
                    continue
                self.latest_result = None
                if isinstance(item, Transaction):
                    self._append_transaction(item)
                    changed = True
                else:
                    self.diagnostics.configure(state="normal")
                    self.diagnostics.insert("end", f"{item.timestamp_utc} [{item.level}] {item.client_label} {item.message} {item.details_json}\n")
                    self.diagnostics.see("end")
                    self.diagnostics.configure(state="disabled")
                    if item.level in {"ERROR", "PROTOCOL", "UNASSIGNED"}:
                        self.compare_summary.set(f"{item.level}: {item.message} — [오류 / 시험 이력] 확인")
        except queue.Empty:
            pass
        if changed:
            self._update_counters()
        self.root.after(100, self._poll_events)

    def _append_transaction(self, item: Transaction) -> None:
        clock = item.timestamp_utc.split("T")[-1].replace("+00:00", "")
        row_id = self.traffic_tree.insert("", "end", values=(
            item.sequence, clock, item.client_label, item.command_id,
            "WRITE" if item.writable else "READ", item.command,
            item.response_value if item.response_value is not None else "<dropped>",
            f"{item.latency_ms:.1f}", item.status,
        ))
        self._traffic_items[row_id] = item
        self.traffic_tree.see(row_id)
        self._client_keys[item.client_label] = item.client_key
        values = sorted(self._client_keys)
        self.state_client_box.configure(values=values)
        if not self.state_client.get() and values:
            self.state_client.set(values[0])

    def _update_counters(self) -> None:
        items = self.capture.transactions()
        counts = Counter(item.client_label for item in items)
        self.original_status.set(f"{counts[self.original_label.get()]}개 수신")
        self.python_status.set(f"{counts[self.python_label.get()]}개 수신")
        writes = sum(item.writable for item in items)
        self.capture_summary.set(f"트랜잭션 {len(items)}개 · 쓰기 {writes}개")

    def clear_capture(self) -> None:
        if self.server and self.server.running:
            self.server.reset_session()
        else:
            self.capture.clear()
            self.device.reset()
            self.capture.set_metadata(response_profile=self.device.get_profile().to_dict())
        # Old events are filtered by session_id in _poll_events; do not discard new events.
        if hasattr(self, "diagnostics"):
            self.diagnostics.configure(state="normal")
            self.diagnostics.delete("1.0", "end")
            self.diagnostics.configure(state="disabled")
        self.latest_result = None
        self._traffic_items.clear()
        self._client_keys.clear()
        self.traffic_tree.delete(*self.traffic_tree.get_children())
        self.compare_tree.delete(*self.compare_tree.get_children())
        self.state_tree.delete(*self.state_tree.get_children())
        self.state_client_box.configure(values=[])
        self.state_client.set("")
        self.original_status.set("아직 패킷 없음")
        self.python_status.set("아직 패킷 없음")
        self.capture_summary.set("트랜잭션 0개")
        self.compare_summary.set("캡처를 초기화했습니다.")
        if hasattr(self, "workbench"):
            self.workbench.record_metadata()

    def run_demo(self) -> None:
        if self.server and self.server.running:
            if not messagebox.askyesno("데모", "실행 중인 가상 장비를 정지하고 loopback 데모를 실행할까요?", parent=self.root):
                return
            self.server.stop()
            self.server = None
            self._set_running(False)
        if self.capture.transactions() and not messagebox.askyesno("데모", "현재 캡처를 지우고 안전한 loopback 데모를 실행할까요?", parent=self.root):
            return
        self.clear_capture()
        try:
            self.device = run_loopback_demo(self.capture, self.original_label.get(), self.python_label.get())
            self.root.after(200, self.generate_comparison)
            self.notebook.select(self.compare_tab)
        except Exception as exc:
            messagebox.showerror("데모 실패", str(exc), parent=self.root)

    def generate_comparison(self) -> None:
        self.latest_result = compare_transactions(
            self.capture.snapshot(), self.original_label.get(), self.python_label.get(),
            ignore_polling=self.ignore_polling.get(),
        )
        result = self.latest_result
        self.compare_tree.delete(*self.compare_tree.get_children())
        for row in result.rows:
            tag = "MATCH" if row.status == "MATCH" else "DIFF"
            self.compare_tree.insert("", "end", values=(row.status, row.command_id or "—",
                row.original_command or "—", row.python_command or "—",
                row.original_response or "—", row.python_response or "—", row.note), tags=(tag,))
        self.compare_summary.set(
            f"Wire {result.verdict} · 시퀀스 {result.sequence_similarity:.1%} · "
            f"완전 일치 {result.matched} · 차이 {result.differences} · "
            f"전송 {result.transport_health} · 화면 {result.gui_verdict} · 처리 중 {result.pending_datagrams}"
        )

    def _metadata(self) -> dict:
        return {"scope": "fixture wire evidence; manual GUI observations are separate"}

    def export_report(self) -> None:
        snapshot = self.capture.snapshot()
        result = compare_transactions(snapshot, self.original_label.get(), self.python_label.get(),
                                      ignore_polling=self.ignore_polling.get())
        self.latest_result = result
        root = Path(self.output_directory.get()).expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        try:
            directory = write_report(root, result, snapshot, self._metadata())
        except OSError as exc:
            messagebox.showerror("보고서 저장 실패", str(exc), parent=self.root)
            return
        self.compare_summary.set(f"{result.verdict} · 스냅샷 {len(snapshot.transactions)}개 · 보고서 저장: {directory}")
        if messagebox.askyesno("보고서 저장 완료", f"{directory}\n\n폴더를 열까요?", parent=self.root):
            self._open_path(directory)

    def save_capture(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.root, title="캡처 저장", defaultextension=".jsonl",
                                            filetypes=[("JSON Lines", "*.jsonl"), ("All files", "*.*")])
        if path:
            try:
                self.capture.save_jsonl(Path(path))
            except OSError as exc:
                messagebox.showerror("저장 실패", str(exc), parent=self.root)

    def show_packet_detail(self) -> None:
        selection = self.traffic_tree.selection()
        if not selection:
            messagebox.showinfo("패킷 상세", "통신 행을 먼저 선택하세요.", parent=self.root)
            return
        item = self._traffic_items.get(selection[0])
        if item is None:
            return
        window = tk.Toplevel(self.root)
        window.title(f"Transaction #{item.sequence}")
        window.geometry("820x600")
        text = scrolledtext.ScrolledText(window, wrap="word", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        detail = (
            f"Client: {item.client_label} ({item.source_ip}:{item.source_port})\n"
            f"UTC: {item.timestamp_utc}\nCommand ID: {item.command_id}\n"
            f"Command: {item.command}\nArgument: {item.argument!r}\n"
            f"Response: {item.response_value!r}\nStatus: {item.status}\nLatency: {item.latency_ms:.3f} ms\n\n"
            f"REQUEST HEX\n{item.request_hex}\n\nRESPONSE HEX\n{item.response_hex or '<none>'}\n"
        )
        text.insert("1.0", detail)
        text.configure(state="disabled")

    def apply_profile(self) -> None:
        try:
            command_id = int(self.inject_id.get())
            if command_id not in COMMANDS:
                raise ValueError("Command ID must be one of the recovered 1000..1089 or 2000..2055 IDs")
            delay = int(self.inject_delay.get() or "0")
            if not 0 <= delay <= 60_000:
                raise ValueError("delay must be 0..60000 ms")
        except ValueError as exc:
            messagebox.showerror("응답 조건", str(exc), parent=self.root)
            return
        profile = self.device.get_profile()
        value = self.inject_value.get()
        if value:
            try:
                value.encode("ascii", "strict")
            except UnicodeEncodeError:
                messagebox.showerror("응답 조건", "강제 응답은 ASCII여야 합니다.", parent=self.root)
                return
            profile.overrides[command_id] = value
        else:
            profile.overrides.pop(command_id, None)
        (profile.error_ids.add if self.inject_error.get() else profile.error_ids.discard)(command_id)
        (profile.drop_ids.add if self.inject_drop.get() else profile.drop_ids.discard)(command_id)
        (profile.request_drop_ids.add if self.inject_request_drop.get() else profile.request_drop_ids.discard)(command_id)
        if delay:
            profile.delay_ms[command_id] = delay
        else:
            profile.delay_ms.pop(command_id, None)
        profile.line_ending = "\r\n" if self.inject_crlf.get() else "\n"
        profile.malformed_reply_header = self.inject_bad_header.get()
        profile.name = "Custom response lab"
        self._commit_profile(profile)
        self._update_profile_summary()

    def clear_profile(self) -> None:
        from .model import ResponseProfile
        self._commit_profile(ResponseProfile())
        self.inject_value.set("")
        self.inject_delay.set("0")
        self.inject_error.set(False)
        self.inject_drop.set(False)
        self.inject_request_drop.set(False)
        self.inject_crlf.set(False)
        self.inject_bad_header.set(False)
        self._update_profile_summary()

    def _commit_profile(self, profile) -> None:
        if self.server and self.server.running:
            self.server.set_profile(profile)
        else:
            self.device.set_profile(profile)
            self.capture.set_metadata(response_profile=profile.to_dict())
            self.capture.message("PROFILE", "response conditions updated", details=profile.to_dict())
        self.latest_result = None

    def _update_profile_summary(self) -> None:
        p = self.device.get_profile()
        self.profile_summary.set(
            f"{p.name}: override={sorted(p.overrides)}, error={sorted(p.error_ids)}, "
            f"reply_drop={sorted(p.drop_ids)}, request_drop={sorted(p.request_drop_ids)}, delay={p.delay_ms}, "
            f"line={'CRLF' if p.line_ending == chr(13)+chr(10) else 'LF'}, bad_header={p.malformed_reply_header}"
        )

    def refresh_state(self) -> None:
        label = self.state_client.get()
        key = self._client_keys.get(label)
        self.state_tree.delete(*self.state_tree.get_children())
        if not key:
            return
        for command_id, value in sorted(self.device.snapshot(key).items()):
            spec = COMMANDS.get(command_id)
            if spec and not spec.writable:
                self.state_tree.insert("", "end", values=(command_id, spec.text, value))

    def _update_setup_text(self) -> None:
        try:
            text = setup_text(self.bind_ip.get(), self.original_ip.get(), self.python_ip.get(), int(self.bind_port.get()))
        except ValueError:
            text = "주소 또는 포트를 먼저 올바르게 입력하세요."
        if hasattr(self, "setup_text_widget"):
            self.setup_text_widget.configure(state="normal")
            self.setup_text_widget.delete("1.0", "end")
            self.setup_text_widget.insert("1.0", text)
            self.setup_text_widget.configure(state="disabled")

    def copy_setup(self) -> None:
        self._update_setup_text()
        text = self.setup_text_widget.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError:
            pass

    def close(self) -> None:
        if hasattr(self, "workbench"):
            if self.workbench.busy:
                messagebox.showwarning("시험 진행 중", "실행 중인 코드 시험이 끝난 뒤 종료하세요. 중간에 닫으면 시험 근거가 유실될 수 있습니다.", parent=self.root)
                return
            self.workbench.close()
        if self.server:
            self.server.stop()
        try:
            self.config = self._collect_config()
            self.config.save()
        except (ValueError, OSError):
            pass
        self.root.destroy()


def launch(config: AppConfig | None = None) -> None:
    root = tk.Tk()
    VerifierApp(root, config)
    root.mainloop()
