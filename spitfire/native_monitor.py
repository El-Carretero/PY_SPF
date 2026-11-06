"""Modeless CVI monitor. All equipment information comes from saved log files."""
from __future__ import annotations
import ctypes as C
import os
from pathlib import Path
import time

from .communication_monitor import CommunicationMonitor
from .monitor_presentation import event_key, format_snapshot


class NativeCommunicationMonitor:
    """Separate native panel; deliberately absent from the hardware panel map.

    ``panel``, ``controls``, ``visible``, ``last_snapshot``, ``rendered_text`` and
    ``local_action`` are also available to the packaged, device-free UI checks.
    The reader owns file IO. Every CVI operation runs on the creating UI thread.
    """
    def __init__(self, view, session_path=None, *, reader_factory=CommunicationMonitor,
                 clock=time.monotonic):
        self.view = view
        self.path = None if session_path is None else Path(session_path)
        self.reader_factory, self.clock = reader_factory, clock
        self.reader = None
        self.panel = None
        self.controls = {}
        self.visible = self.paused = self.problems_only = self.closed = False
        self.last_snapshot = {}
        self.rendered_text = ''
        self._last_refresh = float('-inf')
        self._cleared = set()
        self._painted = {}
        self._notice = ''

    def _check(self, result, operation):
        return self.view._check(result, 'communication monitor: ' + operation)

    def _attribute(self, control, attribute, value):
        self._check(self.view.varargs.SetCtrlAttribute(
            self.panel, control, attribute, self.view._argument(value)), 'control attribute')

    def _text(self, name, value):
        value = str(value)
        if self._painted.get(name) != value:
            self._check(self.view.varargs.SetCtrlVal(
                self.panel, self.controls[name], C.c_char_p(self.view._bytes(value))), 'set ' + name)
            self._painted[name] = value

    def _new(self, name, style, label, top, left, width, height):
        control = self._check(self.view.dll.NewCtrl(
            self.panel, style, self.view._bytes(label), top, left), 'new ' + name)
        self.controls[name] = control
        for attribute, value in ((533, width), (540, height)):
            self._attribute(control, attribute, value)
        return control

    def _build(self):
        self.panel = self._check(self.view.dll.NewPanel(
            0, self.view._bytes('Communication Monitor'), 80, 120, 690, 1000), 'new panel')
        self._check(self.view.varargs.SetPanelAttribute(self.panel, 570, C.c_int(13947080)), 'panel color')
        self._check(self.view.varargs.SetPanelAttribute(self.panel, 580, C.c_int(0)), 'fixed panel size')
        for name, top in (('log', 15), ('device', 44), ('freshness', 78),
                          ('traffic', 108), ('queue', 138), ('logger', 168), ('reader', 198)):
            control = self._new(name, 160, '', top, 40 if name in ('log', 'device') else 18, 958, 25)
            for attr, value in ((682, 'NIDialogMetaFont'), (686, 13), (690, 13947080), (680, 0)):
                self._attribute(control, attr, value)
        for name, top in (('log_led', 18), ('device_led', 47)):
            control = self._new(name, 264, '', top, 16, 18, 18)
            for attr, value in ((620, 0), (920, 0x40A040), (921, 0xA0A0A0), (660, 0)):
                self._attribute(control, attr, value)
        button_type = C.CFUNCTYPE(C.c_int, C.c_int, C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_int)
        for name, label, left, width in (
            ('pause', 'Pause display', 18, 130), ('filter', 'Problems only', 158, 135),
            ('clear', 'Clear display', 303, 120), ('copy', 'Copy displayed', 433, 135),
            ('folder', 'Open log folder', 578, 145), ('close', 'Close', 908, 74)):
            control = self._new(name, 205, label, 234, left, width, 28)
            for attr, value in ((642, 'NIDialogMetaFont'), (646, 11), (880, 12632256)):
                self._attribute(control, attr, value)
            def callback(panel, ctrl, event, data, event1, event2, *, action=name):
                if event == 1 and not self.closed:
                    try:
                        self.local_action(action)
                    except Exception as error:
                        self._notice = f'Local display action failed: {error}'[:400]
                return 0
            cb = button_type(callback)
            self.view._callbacks.append(cb)
            self._check(self.view.dll.InstallCtrlCallback(self.panel, control, cb, None), 'button callback')
        events = self._new('events', 171, '', 274, 18, 964, 304)
        for attr, value in ((682, 'Courier New'), (686, 12), (690, 0xffffff),
                            (680, 0), (840, 1), (551, 2), (791, 4), (760, 60000)):
            self._attribute(events, attr, value)
        for name, top, height in (('warning', 588, 50), ('path', 645, 30)):
            control = self._new(name, 160, '', top, 18, 964, height)
            for attr, value in ((682, 'NIDialogMetaFont'), (686, 11), (690, 13947080), (680, 0)):
                self._attribute(control, attr, value)
        self._attribute(self.controls['folder'], 500, int(self.path is None))
        panel_type = C.CFUNCTYPE(C.c_int, C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_int)
        def panel_callback(panel, event, data, event1, event2):
            if event == 11 and not self.closed:
                self.hide()
            return 0
        cb = panel_type(panel_callback)
        self.view._callbacks.append(cb)
        self._check(self.view.dll.InstallPanelCallback(self.panel, cb, None), 'panel callback')

    def show(self):
        if self.closed:
            return
        if self.panel is None:
            try:
                self._build()
            except Exception:
                if self.panel is not None:
                    self.view.dll.DiscardPanel(self.panel)
                self.panel = None
                self.controls.clear()
                self._painted.clear()
                raise
        if self.path is not None and self.reader is None:
            self.reader = self.reader_factory(self.path).start()
        self.visible = True
        self._check(self.view.dll.DisplayPanel(self.panel), 'display panel')
        self.refresh(force=True)

    def hide(self):
        self.visible = False
        if self.panel is not None:
            self._check(self.view.dll.HidePanel(self.panel), 'hide panel')

    def local_action(self, name):
        """Display/file-navigation actions only; never dispatch a device command."""
        if self.closed:
            return
        self._notice = ''
        if name == 'pause':
            self.paused = not self.paused
        elif name == 'filter':
            self.problems_only = not self.problems_only
        elif name == 'clear':
            self._cleared.update(event_key(record) for record in self.last_snapshot.get('events', []))
            # Old identities may be forgotten once they leave the bounded reader.
            if len(self._cleared) > 3000:
                current = {event_key(record) for record in self.last_snapshot.get('events', [])}
                self._cleared.intersection_update(current)
        elif name == 'copy':
            self._check(self.view.dll.ClipboardPutText(self.view._bytes(self.rendered_text)), 'copy text')
            self._notice = 'Displayed events copied.'
        elif name == 'folder':
            if self.path is not None:
                os.startfile(str(self.path))
        elif name == 'close':
            self.hide()
            return
        else:
            raise ValueError('Unknown local monitor action: ' + str(name))
        self.refresh(force=True)

    def refresh(self, *, force=False):
        if self.closed or not self.visible or self.panel is None:
            return
        now = self.clock()
        if not force and now - self._last_refresh < .25:
            return
        self._last_refresh = now
        if not self.paused:
            self.last_snapshot = (self.reader.snapshot() if self.reader is not None else
                                  {'status': 'disabled', 'device_status': 'unknown', 'events': []})
        presentation = format_snapshot(self.last_snapshot, problems_only=self.problems_only,
                                       cleared=self._cleared)
        for name in ('log', 'device', 'freshness', 'traffic', 'queue', 'logger', 'reader', 'events'):
            self._text(name, presentation[name])
        self.rendered_text = presentation['events']
        self._text('path', 'Session: ' + (str(self.path) if self.path is not None else 'Logging disabled'))
        notice = ('DISPLAY PAUSED. Device communication and logging continue. ' if self.paused else '')
        self._text('warning', notice + self._notice + (' ' if self._notice else '') + presentation['warning'])
        for name, value in (('log_led', presentation['log_ok']), ('device_led', presentation['device_ok'])):
            key = 'value:' + name
            if self._painted.get(key) != value:
                self._check(self.view.varargs.SetCtrlVal(self.panel, self.controls[name], C.c_int(value)), name)
                self._painted[key] = value
        for name, label in (('pause', 'Resume display' if self.paused else 'Pause display'),
                            ('filter', 'Show all' if self.problems_only else 'Problems only')):
            if self._painted.get('label:' + name) != label:
                self._attribute(self.controls[name], 641, label)
                self._painted['label:' + name] = label

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.visible = False
        if self.reader is not None:
            self.reader.close()
        if self.panel is not None:
            self.view.dll.DiscardPanel(self.panel)
            self.panel = None
