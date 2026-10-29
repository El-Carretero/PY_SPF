"""Mouse hold confirmation; ordinary click/invoke/keyboard cannot start RUN."""
from __future__ import annotations
import time
import tkinter as tk
from tkinter import ttk


class HoldToRunButton(ttk.Button):
    HOLD_SECONDS = 3.0
    MAX_TICK_GAP = 0.5  # A stalled GUI must not activate RUN when it resumes.

    def __init__(self, master, *, on_confirm, on_progress, **kwargs):
        self._on_confirm = on_confirm
        self._on_progress = on_progress
        self._hold_job = None
        self._hold_start = None
        self._last_tick = None
        self._mouse_down = False
        self._clock = time.monotonic
        super().__init__(master, command=self._click_only, **kwargs)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        for sequence in ('<Leave>', '<FocusOut>', '<Unmap>', '<Destroy>'):
            self.bind(sequence, self.cancel, add='+')
        for sequence in ('<KeyPress-space>', '<KeyRelease-space>', '<KeyPress-Return>', '<KeyRelease-Return>'):
            self.bind(sequence, self._click_only)

    def _click_only(self, _event=None):
        self._on_progress(None)
        return 'break'

    def _press(self, _event=None):
        if self.instate(['disabled']) or self._mouse_down:
            return 'break'
        self.focus_set()
        self._mouse_down = True
        self.state(['pressed'])
        self._hold_start = self._last_tick = self._clock()
        self._on_progress(0.0)
        self._hold_job = self.after(50, self._tick)
        return 'break'

    def _tick(self):
        self._hold_job = None
        if self._hold_start is None:
            return
        now = self._clock()
        if self.instate(['disabled']) or now - self._last_tick > self.MAX_TICK_GAP:
            self.cancel()
            return
        self._last_tick = now
        elapsed = now - self._hold_start
        if elapsed >= self.HOLD_SECONDS:
            self._hold_start = None  # Fire once; holding longer never repeats.
            self.state(['!pressed'])
            self._on_progress(None)
            self._on_confirm()
        else:
            self._on_progress(elapsed)
            self._hold_job = self.after(50, self._tick)

    def _release(self, _event=None):
        self.cancel()
        return 'break'

    def cancel(self, _event=None):
        active = self._mouse_down or self._hold_job is not None
        self._hold_start = self._last_tick = None
        self._mouse_down = False
        if self._hold_job is not None:
            try:self.after_cancel(self._hold_job)
            except tk.TclError:pass
            self._hold_job = None
        try:self.state(['!pressed'])
        except tk.TclError:pass
        if active:self._on_progress(None)
