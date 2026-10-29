"""Version/scenario workbench. Background workers never access Tk objects.

Static inspection is not execution; model assertions are not client equivalence.
The explicit matrix trust dialog is required because a Python subprocess is not
a security sandbox for an imported program.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .client_matrix import run_matrix
from .profiles import get_profile, inspect_client, list_profiles
from .scenarios import list_scenarios, load_scenario, run_scenario


from .evidence_report import evidence_rows, write_workbench_report

class WorkbenchPanel:
    def __init__(self, app, parent):
        self.app, self.root = app, app.root
        # A vertical viewport keeps every control reachable on 1024x768 or
        # high-DPI desktops instead of shrinking the evidence pane to zero.
        self.viewport = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=self.viewport.yview)
        self.viewport.configure(yscrollcommand=scroll.set)
        self.viewport.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.parent = ttk.Frame(self.viewport, padding=(0, 0, 8, 0))
        self.viewport_window = self.viewport.create_window((0, 0), window=self.parent, anchor="nw")
        self.parent.bind("<Configure>", self._resize_viewport)
        self.viewport.bind("<Configure>", self._resize_viewport)
        self.root.bind("<MouseWheel>", self._scroll_viewport, add="+")
        self.profiles = list_profiles()
        self.profile_choices = {f"{p['label']} [{p['id']}]": p["id"] for p in self.profiles}
        choices = list(self.profile_choices)
        left = next((k for k, v in self.profile_choices.items() if v == "xp_gui_1.6.0"), choices[0])
        right = next((k for k, v in self.profile_choices.items()
                      if get_profile(v)["label"] == app.python_label.get()), "")
        if not right:
            right = next((k for k, v in self.profile_choices.items() if v == "python_1.3.0"), choices[-1])
        self.left_profile = tk.StringVar(value=left)
        self.right_profile = tk.StringVar(value=right)
        self.status = tk.StringVar(value="1. 버전 선택 → 2. 파일 추가 → 3. 시험 실행 → 4. 보고서 저장")
        scenarios = list_scenarios()
        self.scenario_choices = {f"{s['name']} [{s['id']}]": s["id"] for s in scenarios}
        self.scenario = tk.StringVar(value=next(iter(self.scenario_choices), ""))
        self.clock = tk.StringVar(value="realtime")
        self.advance_ms = tk.StringVar(value="1000")
        self.live_status = tk.StringVar(value="실시간 장비 시나리오 없음 · 기본 응답 모델")
        self.artifacts: list[dict] = []
        self.results: list[dict] = []
        self.applied_profiles: dict = {}
        self.desired_scenario = None
        self.desired_clock = "realtime"
        self.worker_queue = queue.Queue()
        self.busy = False
        self.closed = False
        self._build()
        self._drain_results()

    def _resize_viewport(self, _event=None):
        self.viewport.itemconfigure(self.viewport_window, width=max(1, self.viewport.winfo_width()),
                                    height=max(self.parent.winfo_reqheight(), self.viewport.winfo_height()))
        self.viewport.configure(scrollregion=self.viewport.bbox("all"))

    def _scroll_viewport(self, event):
        if self.closed or not str(event.widget).startswith(str(self.parent)):
            return
        # Treeviews and text widgets retain their own native scrolling.
        if event.widget.winfo_class() in {"Treeview", "Text", "TCombobox"}:
            return
        if event.delta:
            self.viewport.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _build(self):
        ttk.Label(self.parent, text="버전과 고장 조건을 선택해 반복 검증", style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.parent, text="XP 실제 실행: 미검증  |  모델 PASS ≠ 원본과 동등  |  실제 장비로 패킷 전달 없음",
                  foreground="#8a4b00", wraplength=650).pack(anchor="w", pady=(3, 9))
        choices = tuple(self.profile_choices)
        selection = ttk.Frame(self.parent)
        selection.pack(fill="x")
        ttk.Label(selection, text="기준 프로그램").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Combobox(selection, values=choices, textvariable=self.left_profile, state="readonly", width=20).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(selection, text="비교 프로그램").grid(row=1, column=0, sticky="w", padx=(0, 6))
        ttk.Combobox(selection, values=choices, textvariable=self.right_profile, state="readonly", width=20).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(selection, text="버전 선택 적용", command=self.apply_profiles).grid(row=2, column=1, sticky="w", pady=(3, 0))
        selection.columnconfigure(1, weight=1)
        ttk.Label(self.parent, text="프로파일 선택은 표시명·판정 근거만 설정합니다. 해당 버전 프로그램을 설치하거나 실행하지 않습니다.",
                  foreground="#526170", wraplength=650).pack(anchor="w", pady=(4, 8))

        imports = ttk.LabelFrame(self.parent, text="실제 Python 코드 검사 · 여러 버전 비교", padding=8)
        imports.pack(fill="x")
        actions = ttk.Frame(imports)
        actions.pack(fill="x", pady=(0, 6))
        ttk.Button(actions, text="ZIP 추가", command=self.import_zip).pack(side="left")
        ttk.Button(actions, text="폴더 추가", command=self.import_folder).pack(side="left", padx=6)
        ttk.Button(actions, text="선택 제거", command=self.remove_artifact).pack(side="left")
        ttk.Button(imports, text="추가한 코드로 loopback 시험", command=self.run_client_matrix).pack(anchor="w", pady=(0, 6))
        self.artifact_tree = ttk.Treeview(imports, columns=("version", "profile", "hash", "path"), show="headings", height=3)
        for key, title, width in (("version", "감지 버전", 90), ("profile", "정적 검사", 180),
                                  ("hash", "SHA-256 일부", 120), ("path", "선택한 파일 / 폴더", 450)):
            self.artifact_tree.heading(key, text=title)
            self.artifact_tree.column(key, width=width, stretch=key == "path")
        self.artifact_tree.pack(fill="x")

        model = ttk.LabelFrame(self.parent, text="외부 트리거 · 펌프 · 고장 시나리오", padding=8)
        model.pack(fill="x", pady=8)
        row = ttk.Frame(model)
        row.pack(fill="x")
        ttk.Combobox(row, values=tuple(self.scenario_choices), textvariable=self.scenario,
                     state="readonly", width=20).pack(fill="x")
        scenario_actions = ttk.Frame(model)
        scenario_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(scenario_actions, text="JSON 시나리오 열기", command=self.import_scenario).pack(side="left", padx=(0, 6))
        ttk.Button(scenario_actions, text="모델 자체 시험", command=self.run_model).pack(side="left")
        live = ttk.Frame(model)
        live.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(live, text="실시간", variable=self.clock, value="realtime").pack(side="left")
        ttk.Radiobutton(live, text="수동 시간", variable=self.clock, value="manual").pack(side="left", padx=(3, 8))
        live_actions = ttk.Frame(model)
        live_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(live_actions, text="다음 장비 시작에 적용", command=self.stage_live_scenario).pack(side="left")
        ttk.Button(live_actions, text="예약 해제", command=self.clear_live_scenario).pack(side="left", padx=6)
        manual = ttk.Frame(model)
        manual.pack(fill="x", pady=(6, 0))
        ttk.Label(manual, text="절대 가상시간").pack(side="left")
        ttk.Entry(manual, textvariable=self.advance_ms, width=8).pack(side="left", padx=(6, 4))
        ttk.Button(manual, text="ms까지 이동", command=self.advance_live).pack(side="left")
        ttk.Label(model, textvariable=self.live_status, foreground="#526170", wraplength=650).pack(anchor="w", pady=(5, 0))
        ttk.Label(model, text="합성 상태 정책입니다. 실시간 모드는 클라이언트 첫 요청부터 시간 진행; 수동은 절대 시간(ms).\n"
                  "하드웨어 상태 비트의 실측 근거가 없는 조건은 UNVERIFIED로 남습니다. 모델 자체 시험은 프로그램을 실행하지 않습니다.",
                  foreground="#8a4b00", wraplength=650).pack(anchor="w", pady=(4, 0))

        tools = ttk.Frame(self.parent)
        tools.pack(fill="x", pady=(0, 6))
        ttk.Button(tools, text="시험 JSON / HTML 저장", command=self.export).pack(anchor="w")
        ttk.Label(tools, textvariable=self.status, wraplength=650).pack(fill="x", pady=(4, 0))
        self.progress = ttk.Progressbar(self.parent, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 5))
        result_tabs = ttk.Notebook(self.parent)
        result_tabs.pack(fill="both", expand=True)
        summary, details = ttk.Frame(result_tabs), ttk.Frame(result_tabs)
        result_tabs.add(summary, text="판정 요약")
        result_tabs.add(details, text="상세 JSON / 근거")
        self.result_tree = ttk.Treeview(summary, columns=("version", "test", "status", "detail"), show="headings", height=6)
        for key, title, width in (("version", "버전 / 시간", 140), ("test", "시험", 290),
                                  ("status", "판정", 120), ("detail", "범위 / 차이", 400)):
            self.result_tree.heading(key, text=title)
            self.result_tree.column(key, width=width, stretch=key in {"test", "detail"})
        self.result_tree.tag_configure("PASS", foreground="#18794e")
        self.result_tree.tag_configure("FAIL", foreground="#b42318")
        self.result_tree.tag_configure("ERROR", foreground="#b42318")
        self.result_tree.tag_configure("UNVERIFIED", foreground="#8a4b00")
        bar = ttk.Scrollbar(summary, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=bar.set)
        self.result_tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.output = scrolledtext.ScrolledText(details, height=9, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)
        self._show({"scope": "Static artifact inspection / synthetic model assertions / real Python transport loopback",
                    "xp_gui_execution": "UNVERIFIED", "physical_validation": "UNVERIFIED",
                    "guide": "XP는 실제 레이저와 분리된 Host-only VM에서 실행하고 통신 및 화면 기록 탭에서 별도로 검증하세요."})

    def _show(self, payload):
        if hasattr(self, "result_tree"):
            self.result_tree.delete(*self.result_tree.get_children())
            for row in evidence_rows(payload):
                self.result_tree.insert("", "end", values=row, tags=(row[2],))
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        self.output.configure(state="disabled")

    def _submit(self, kind, work):
        if self.busy:
            self.status.set("현재 작업이 끝난 뒤 실행하세요.")
            return False
        self.busy = True
        self.status.set(f"진행 중: {kind} · 창은 계속 사용할 수 있습니다.")
        self.progress.start(12)

        def worker():
            try:
                self.worker_queue.put((kind, True, work()))
            except Exception as exc:
                self.worker_queue.put((kind, False, {"error": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=worker, name="spitfire-workbench", daemon=True).start()
        return True

    def _drain_results(self):
        if self.closed:
            return
        try:
            while True:
                kind, success, result = self.worker_queue.get_nowait()
                self.busy = False
                self.progress.stop()
                if kind == "정적 파일 검사" and success:
                    path = result["path"]
                    self.artifacts = [a for a in self.artifacts if a["path"] != path] + [result]
                    self._refresh_artifacts()
                record = {"kind": kind, "completed_utc": datetime.now(timezone.utc).isoformat(),
                          "operation_completed": success, "result": result}
                self.results.append(record)
                self._show(record)
                self.status.set(f"{'완료' if success else '실패'}: {kind} · 상세 판정과 제한사항을 확인하세요.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_results)

    def _refresh_artifacts(self):
        self.artifact_tree.delete(*self.artifact_tree.get_children())
        for index, item in enumerate(self.artifacts):
            self.artifact_tree.insert("", "end", iid=str(index), values=(
                item.get("version", "unknown"), item.get("inspection_status", "UNVERIFIED"),
                item.get("artifact_sha256", "")[:12], item["path"]))

    def import_zip(self):
        path = filedialog.askopenfilename(parent=self.root, title="검사할 Python ZIP 선택",
                                          filetypes=[("ZIP archive", "*.zip")])
        if path:
            self._submit("정적 파일 검사", lambda: inspect_client(path))

    def import_folder(self):
        path = filedialog.askdirectory(parent=self.root, title="Python 프로젝트 폴더 선택")
        if path:
            self._submit("정적 파일 검사", lambda: inspect_client(path))

    def remove_artifact(self):
        if self.busy:
            self.status.set("작업 완료 후 목록을 수정하세요.")
            return
        selected = set(self.artifact_tree.selection())
        self.artifacts = [a for i, a in enumerate(self.artifacts) if str(i) not in selected]
        self._refresh_artifacts()

    def apply_profiles(self):
        if (self.app.server and self.app.server.running) or self.app.capture.transactions():
            messagebox.showwarning("버전 변경", "장비를 정지하고 현재 보고서를 저장한 뒤 캡처를 초기화하세요.\n기존 기록의 버전 표시를 바꾸지 않습니다.", parent=self.root)
            return
        left = get_profile(self.profile_choices[self.left_profile.get()])
        right = get_profile(self.profile_choices[self.right_profile.get()])
        if left["id"] == right["id"]:
            messagebox.showwarning("버전 변경", "기준과 비교 버전을 다르게 선택하세요.", parent=self.root)
            return
        self.app.original_label.set(left["label"])
        self.app.python_label.set(right["label"])
        self.applied_profiles = {"baseline": left, "candidate": right,
                                 "selection_is_execution_evidence": False}
        self.record_metadata()
        self.app.latest_result = None
        self.app._update_setup_text()
        self._show(self.applied_profiles)
        self.status.set("버전 표시 적용됨 · 실제 프로그램 실행·호환성은 별도 시험 필요")

    def metadata(self):
        return {"selected_client_profiles": copy.deepcopy(self.applied_profiles),
                "xp_execution_evidence": "UNVERIFIED (requires actual XP capture + GUI observations)",
                "configured_scenario": copy.deepcopy(self.desired_scenario),
                "scenario_clock": self.desired_clock}

    def record_metadata(self):
        self.app.capture.set_metadata(**self.metadata())

    def _selected_scenario(self):
        return self.scenario_choices.get(self.scenario.get(), self.scenario.get())

    def import_scenario(self):
        path = filedialog.askopenfilename(parent=self.root, title="시나리오 JSON 선택",
                                          filetypes=[("Scenario JSON", "*.json")])
        if not path:
            return
        try:
            value = load_scenario(path)
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror("시나리오", str(exc), parent=self.root)
            return
        self.scenario.set(path)
        self._show(value)
        self.status.set("시나리오 JSON 검증됨 · 아직 실행하거나 장비에 적용하지 않았습니다.")

    def run_model(self):
        selected = self._selected_scenario()
        self._submit("합성 모델 자체 시험", lambda: run_scenario(selected))

    def run_client_matrix(self):
        if self.busy:
            self.status.set("현재 작업이 끝난 뒤 실행하세요.")
            return
        if not self.artifacts:
            messagebox.showinfo("Python 코드 시험", "먼저 검사할 Python ZIP 또는 폴더를 추가하세요.", parent=self.root)
            return
        paths = [str(a["path"]) for a in self.artifacts]
        prompt = ("추가한 Python 소스 코드를 실제로 실행합니다.\n"
                  "시험 대상 UDP는 127.0.0.1이지만, 별도 프로세스는 보안 샌드박스가 아닙니다.\n"
                  "검사한 파일의 신뢰성을 확인했을 때만 실행하세요.\n"
                  "XP GUI와 실제 하드웨어는 이 시험에 포함되지 않습니다.\n\n"
                  + "\n".join(paths) + "\n\n이 코드들을 신뢰하며 실행할까요?")
        if not messagebox.askyesno("선택 코드 실행 확인", prompt, parent=self.root):
            return
        self._submit("실제 Python transport loopback", lambda: run_matrix(paths, trusted=True))

    def stage_live_scenario(self):
        if (self.app.server and self.app.server.running) or self.app.capture.transactions():
            messagebox.showwarning("시나리오 적용", "먼저 가상 장비를 정지하고 보고서 저장 후 캡처를 초기화하세요. 기존 시험 조건을 바꾸지 않습니다.", parent=self.root)
            return
        try:
            selected = load_scenario(self._selected_scenario())
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror("시나리오 적용", str(exc), parent=self.root)
            return
        self.desired_scenario = selected
        self.desired_clock = self.clock.get()
        self.record_metadata()
        self.live_status.set(f"다음 시작에 적용: {selected.get('name', selected.get('id', 'custom'))} · {self.desired_clock} · 합성 정책")

    def clear_live_scenario(self):
        if (self.app.server and self.app.server.running) or self.app.capture.transactions():
            messagebox.showwarning("시나리오 해제", "먼저 가상 장비를 정지하고 보고서 저장 후 캡처를 초기화하세요.", parent=self.root)
            return
        self.desired_scenario = None
        self.record_metadata()
        self.live_status.set("실시간 장비 시나리오 없음 · 기본 응답 모델")

    def configure_server(self, server):
        if self.desired_scenario is not None:
            server.set_scenario(copy.deepcopy(self.desired_scenario), clock=self.desired_clock)
        self.record_metadata()

    def advance_live(self):
        server = self.app.server
        if not server or not server.running or self.desired_scenario is None:
            messagebox.showinfo("시간 이동", "수동 시나리오를 예약하고 가상 장비를 먼저 시작하세요.", parent=self.root)
            return
        if self.desired_clock != "manual":
            messagebox.showwarning("시간 이동", "실시간 모드에서는 수동 이동을 할 수 없습니다.", parent=self.root)
            return
        try:
            at_ms = float(self.advance_ms.get())
            result = server.advance_scenario(at_ms)
        except (ValueError, RuntimeError, TypeError) as exc:
            messagebox.showerror("시간 이동", str(exc), parent=self.root)
            return
        self._show({"requested_absolute_ms": at_ms, "result": result, "scope": "synthetic live model"})

    def export(self):
        if self.busy:
            self.status.set("작업 완료 후 최종 결과를 저장하세요.")
            return
        try:
            directory = write_workbench_report(self.app.output_directory.get(), {
                "schema_version": 1, "scope": "version/scenario workbench evidence",
                "metadata": self.metadata(), "inspected_artifacts": copy.deepcopy(self.artifacts),
                "runs": copy.deepcopy(self.results), "physical_validation": "UNVERIFIED"})
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("보고서 저장", str(exc), parent=self.root)
            return
        self.status.set(f"보고서 저장: {directory}")
        if messagebox.askyesno("보고서 저장", f"{directory}\n\n폴더를 열까요?", parent=self.root):
            self.app._open_path(directory)

    def close(self):
        self.closed = True
