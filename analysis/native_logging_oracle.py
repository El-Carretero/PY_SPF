"""Compare the original x86 data logger with Python callback/file writes.

Only _tmr_Data_Logger is executed in Unicorn. CVI control reads and CRT file
calls are intercepted; the Windows program never accesses a device or disk.
Python's append adapter writes only inside a TemporaryDirectory. Formatting
the captured native fprintf arguments uses Python's percent formatter, so this
checks the native format/arguments and call flow, not the NI CRT formatter.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from native_oracle import NativeOracle, PANEL_GLOBALS, ROOT
from spitfire.__main__ import MemoryView
from spitfire.callbacks import dispatch
from spitfire.controller import Controller


class LoggingOracle(NativeOracle):
    def run(self, values, *, event=15, open_failure=False, initial_text=""):
        self.values = values
        self.open_failure = open_failure
        self.operations = []
        self.file_text = initial_text
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        u = self.u
        u.mem_map(0x400000, 0x50000)
        u.mem_write(0x400000, self.pe.get_memory_mapped_image())
        u.mem_map(0x1000000, 0x100000)
        u.mem_map(0x2000000, 0x1000)
        u.mem_map(0xF000000, 0x1000)
        # Match the x87 initialization performed by normal CVI startup.
        u.mem_write(0x2000000, b"\xdb\xe3")
        u.emu_start(0x2000000, 0x2000002)
        esp = 0x10FF000
        u.mem_write(esp, struct.pack("<7I", 0xF000000, 6, 64, event, 0, 0, 0))
        u.reg_write(UC_X86_REG_ESP, esp)
        for panel, address in PANEL_GLOBALS.items():
            u.mem_write(address, struct.pack("<I", panel))
        handlers = {
            "_GetCtrlVal@12": self.getctrl,
            "_fopen": self.fopen,
            "_fprintf": self.fprintf,
            "_fclose": self.fclose,
        }
        addresses = {self.symbols[name]: handler for name, handler in handlers.items()}
        runtime = {address: name for name, address in self.symbols.items()
                   if name.startswith("_") and address < 0x4048F8}

        def hook(emu, address, size, data):
            if address == 0xF000000:
                emu.emu_stop()
            elif address in addresses:
                addresses[address]()
            elif address in runtime:
                raise RuntimeError("Unhandled original runtime call: " + runtime[address])

        u.hook_add(UC_HOOK_CODE, hook)
        u.emu_start(self.symbols["_tmr_Data_Logger"], 0xF000000, count=10000)
        if u.reg_read(UC_X86_REG_EIP) != 0xF000000:
            raise RuntimeError("Native instruction budget exhausted")
        return self.operations, self.file_text

    def retvalue(self, value, pop=0):
        self.ret(pop)
        self.u.reg_write(UC_X86_REG_EAX, value)

    def getctrl(self):
        _, panel, control, pointer = self.stack(4)
        key = (panel, control)
        value = self.values.get(key, 0)
        if key == (1, 3):
            data = struct.pack("<i", int(value))
            dtype = "int32"
        elif key in ((9, 2), (8, 15)):
            data = struct.pack("<f", float(value))
            dtype = "float32"
        else:
            raise RuntimeError("Unexpected native control read: " + repr(key))
        self.u.mem_write(pointer, data)
        self.operations.append({"call": "GetCtrlVal", "panel": panel,
                                "control": control, "type": dtype})
        self.ret(12)

    def fopen(self):
        _, filename, mode = self.stack(3)
        self.operations.append({"call": "fopen", "path": self.cstr(filename),
                                "mode": self.cstr(mode), "success": not self.open_failure})
        self.retvalue(0 if self.open_failure else 0x2000800)

    def fprintf(self):
        _, stream, format_pointer = self.stack(3)
        if stream != 0x2000800:
            raise RuntimeError("Unexpected native stream")
        esp = self.u.reg_read(UC_X86_REG_ESP)
        arguments = struct.unpack("<2d", self.u.mem_read(esp + 12, 16))
        format_text = self.cstr(format_pointer)
        # Capture and assert the exact format before interpreting the varargs.
        if format_text != "%.2f, %.2f\n":
            raise RuntimeError("Unexpected native fprintf format: " + repr(format_text))
        text = format_text % arguments
        self.operations.append({"call": "fprintf", "format": format_text,
                                "arguments": list(arguments), "text": text})
        self.file_text += text
        self.retvalue(len(text))

    def fclose(self):
        _, stream = self.stack(2)
        if stream != 0x2000800:
            raise RuntimeError("Unexpected native stream close")
        self.operations.append({"call": "fclose"})
        self.retvalue(0)


def compare(label, *, enabled=1, current=12.345, temperature=36.789, event=15,
            initial_text="", open_failure=False):
    values = {(1, 3): enabled, (9, 2): current, (8, 15): temperature}
    operations, native_text = LoggingOracle().run(
        values, event=event, initial_text=initial_text, open_failure=open_failure,
    )
    should_open = event == 15 and bool(enabled)
    expected_calls = []
    if event == 15:
        expected_calls.append("GetCtrlVal")
    if should_open:
        expected_calls += ["GetCtrlVal", "GetCtrlVal", "fopen"]
        if not open_failure:
            expected_calls += ["fprintf", "fclose"]
    checks = {"call_sequence": [op["call"] for op in operations] == expected_calls}
    if should_open:
        opening = next(op for op in operations if op["call"] == "fopen")
        checks["relative_path_and_append_mode"] = (
            opening["path"] == "datalog.csv" and opening["mode"] == "a+"
        )
    result = {"label": label, "event": event, "enabled": enabled,
              "sensed_current_A": current, "lbo_temperature_C": temperature,
              "initial_text": initial_text, "open_failure": open_failure,
              "native_operations": operations, "native_logical_file_text": native_text}
    if open_failure:
        # Python currently propagates file-open errors; compare no such behavior.
        result["comparison_scope"] = "Native fopen failure only; Python not compared"
        checks["failure_leaves_file_unchanged"] = native_text == initial_text
    else:
        actions = dispatch("tmr_Data_Logger", read=lambda p, c: values.get((p, c), 0),
                           event=event, panel=6, control=64)
        with tempfile.TemporaryDirectory(prefix="spitfire-logging-") as directory:
            path = Path(directory) / "datalog.csv"
            if initial_text:
                path.write_text(initial_text, encoding="ascii")
            controller = Controller(MemoryView(), data_dir=directory, tcp_port=None)
            controller.apply(actions)
            python_text = path.read_text(encoding="ascii") if path.exists() else ""
            checks["file_created_only_if_enabled"] = path.exists() == bool(initial_text or should_open)
        expected_actions = [
            {"kind": "append_file", "target": "datalog.csv", "value": op["text"]}
            for op in operations if op["call"] == "fprintf"
        ]
        python_actions = [{"kind": a.kind, "target": a.target, "value": a.value} for a in actions]
        checks["dispatch_matches_native_write"] = python_actions == expected_actions
        checks["file_text_matches"] = python_text == native_text
        result.update(python_actions=python_actions, python_logical_file_text=python_text)
    result.update(checks=checks, **{"pass": all(checks.values())})
    return result


def verify():
    cases = [
        compare("default_off", enabled=0),
        compare("normal"),
        compare("negative", current=-1.25, temperature=-9.875),
        compare("float32_rounding", current=16.055, temperature=8.045),
        compare("zero", current=0, temperature=0),
        compare("append_existing", initial_text="1.00, 20.00\n"),
        compare("native_fopen_failure", open_failure=True, initial_text="unchanged\n"),
    ]
    cases += [compare("ignored_event_" + str(event), event=event)
              for event in (1, 2, 3, 7, 11, 14, 16)]
    source = ROOT / "analysis/reference/SPITFIRE.EXE"
    result = {
        "method": "Original x86 logger in Unicorn with typed CVI reads and in-memory CRT I/O; Python dispatch plus temporary-file append",
        "limitations": "The NI CRT formatter and Windows text-mode newline translation are intercepted, not executed. Logical lines are compared. No physical hardware or Windows process is used.",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "callback_address": "0x00412e60",
        "case_count": len(cases), "passed": sum(case["pass"] for case in cases),
        "cases": cases,
    }
    (ROOT / "analysis/native_logging_results.json").write_text(json.dumps(result, indent=2) + "\n")
    failures = [case["label"] for case in cases if not case["pass"]]
    print(json.dumps({"cases": len(cases), "passed": result["passed"], "failures": failures}))
    return not failures


if __name__ == "__main__":
    sys.exit(0 if verify() else 1)
