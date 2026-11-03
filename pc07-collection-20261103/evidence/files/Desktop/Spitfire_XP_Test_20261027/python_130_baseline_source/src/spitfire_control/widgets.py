"""Small Tk widgets used by the control console."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Indicator(ttk.Frame):
    def __init__(
        self,
        master,
        text: str,
        *,
        compact: bool = False,
        background: str = "#ffffff",
        label_style: str | None = None,
        frame_style: str = "Card.TFrame",
    ):
        super().__init__(master, style=frame_style)
        size = 12 if compact else 16
        self.canvas = tk.Canvas(self, width=size + 6, height=size + 6, highlightthickness=0, bg=background)
        self.dot = self.canvas.create_oval(3, 3, size + 3, size + 3, fill="#aab3ba", outline="#737e86", width=1)
        self.label = ttk.Label(self, text=text, style=label_style or "CardText.TLabel")
        self.canvas.pack(side="left", padx=(0, 6))
        self.label.pack(side="left")
        self.set("unknown")

    def set(self, state: str, text: str | None = None) -> None:
        colors = {
            "ok": ("#2ea35f", "#176b3b"),
            "warning": ("#e1a426", "#9a6810"),
            "fault": ("#d64545", "#8b2323"),
            "off": ("#d1d7dc", "#89959e"),
            "unknown": ("#aab3ba", "#737e86"),
        }
        fill, outline = colors.get(state, colors["unknown"])
        self.canvas.itemconfigure(self.dot, fill=fill, outline=outline)
        if text is not None:
            self.label.configure(text=text)


class MetricCard(ttk.Frame):
    def __init__(self, master, title: str, unit: str = ""):
        super().__init__(master, style="MetricCard.TFrame", padding=(12, 9))
        self._unit = unit
        ttk.Label(self, text=title, style="MetricTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(self, style="Readout.TFrame", padding=(10, 4))
        row.pack(fill="x", pady=(5, 0))
        self.value = ttk.Label(row, text="—", style="ReadoutMetric.TLabel")
        self.value.pack(side="left")
        self.unit = ttk.Label(row, text=unit, style="ReadoutUnit.TLabel")
        self.unit.pack(side="right", padx=(6, 0), pady=(8, 0))

    def set(self, value: object, *, digits: int = 2) -> None:
        if value is None or value == "":
            rendered = "—"
        elif isinstance(value, float):
            rendered = f"{value:.{digits}f}"
        else:
            rendered = str(value)
        self.value.configure(text=rendered)


class SettingRow(ttk.Frame):
    def __init__(self, master, title: str, variable: tk.Variable, unit: str, command, *, width: int = 12, readback=None, reset=None):
        super().__init__(master, style="Card.TFrame")
        ttk.Label(self, text=title, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        self.entry = ttk.Entry(self, textvariable=variable, width=width)
        self.entry.grid(row=0, column=1, padx=(12, 5))
        ttk.Label(self, text=unit, style="CardText.TLabel").grid(row=0, column=2, sticky="w")
        self.button = ttk.Button(self, text="APPLY", command=command, width=7)
        self.button.grid(row=0, column=3, padx=(12, 0))
        if readback is not None:
            rb = ttk.Frame(self, style="Card.TFrame")
            rb.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 0))
            ttk.Label(rb, text="Readback:", style="CardTitle.TLabel").pack(side="left")
            ttk.Label(rb, textvariable=readback, style="CardTitle.TLabel").pack(side="left", padx=5)
            if reset is not None:
                ttk.Button(rb, text="USE READBACK", command=reset, width=14).pack(side="right")
        self.columnconfigure(0, weight=1)


class DraftValue:
    """A user edit survives polling until it matches a readback or is reset."""
    def __init__(self, master, default="—", *, boolean=False):
        self.variable = tk.BooleanVar(master, value=default) if boolean else tk.StringVar(master, value=default)
        self.readback = tk.StringVar(master, value="—")
        self.dirty = False
        self._syncing = False
        self._latest = default
        self._known = False
        self.variable.trace_add("write", self._edited)

    def _edited(self, *_args):
        if not self._syncing:
            self.dirty = True

    def _set(self, value):
        self._syncing = True
        try:
            self.variable.set(value)
        finally:
            self._syncing = False

    @staticmethod
    def _same(left, right):
        if str(left) == str(right):
            return True
        try:
            return float(left) == float(right)
        except (ValueError, TypeError):
            return False

    def sync(self, value, display=None):
        if value is None:
            self.readback.set("—")
            return
        self._latest = value
        self._known = True
        self.readback.set(str(value) if display is None else display)
        if not self.dirty or self._same(self.variable.get(), value):
            self._set(value)
            self.dirty = False

    def reset(self):
        if self._known:
            self._set(self._latest)
            self.dirty = False

    def clear(self):
        self.dirty = False
        self._known = False
        self.readback.set("—")
        self._set(False if isinstance(self.variable, tk.BooleanVar) else "—")
