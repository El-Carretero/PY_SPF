"""Modeless Qt presentation of saved communication diagnostics only."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from .communication_monitor import CommunicationMonitor
from .monitor_presentation import event_key, format_snapshot


class QtCommunicationMonitor(QDialog):
    """Local display controls never enter the device callback/command path."""

    def __init__(self, session_path, parent=None, *, reader_factory=CommunicationMonitor):
        super().__init__(parent)
        self.setWindowTitle('Communication Monitor')
        self.resize(880, 580)
        self.setModal(False)
        self.setStyleSheet('QDialog { background-color: #d4d0c8; }')
        self.session_path = Path(session_path) if session_path is not None else None
        self.reader = reader_factory(self.session_path) if self.session_path is not None else None
        self.paused = False
        self.problems_only = False
        self._cleared = set()
        self._last_snapshot = None
        self._rendered = ''
        self._disposed = False
        layout = QVBoxLayout(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.warning = QLabel(self)
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.PlainText)
        layout.addWidget(self.warning)
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.PlainText)
        layout.addWidget(self.details)
        self.events = QPlainTextEdit(self)
        self.events.setReadOnly(True)
        self.events.setMaximumBlockCount(350)
        self.events.setStyleSheet('QPlainTextEdit { background: white; color: black; font-family: Consolas, monospace; font-size: 10pt; }')
        layout.addWidget(self.events, 1)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.pause_button = QPushButton('Pause display', self)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.filter_button = QPushButton('Problems only', self)
        self.filter_button.setCheckable(True)
        self.filter_button.toggled.connect(self.set_problems_only)
        self.clear_button = QPushButton('Clear view', self)
        self.clear_button.clicked.connect(self.clear_view)
        self.copy_button = QPushButton('Copy', self)
        self.copy_button.clicked.connect(self.copy_display)
        self.folder_button = QPushButton('Open log folder', self)
        self.folder_button.clicked.connect(self.open_folder)
        self.folder_button.setEnabled(self.session_path is not None)
        for button in (self.pause_button, self.filter_button, self.clear_button,
                       self.copy_button, self.folder_button):
            buttons.addWidget(button)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event):
        if not self._disposed:
            if self.reader is not None:
                self.reader.start()
            self.timer.start()
            self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self, *, presentation_only=False):
        if self._disposed or (self.paused and not presentation_only):
            return
        if self.reader is None:
            self.status.setText('Log monitoring disabled')
            self.warning.setText('Enable session diagnostics to view saved communication logs.')
            self.details.setText('No active log session was supplied.')
            return
        try:
            if not presentation_only or self._last_snapshot is None:
                self._last_snapshot = self.reader.snapshot()
            result = format_snapshot(self._last_snapshot,
                                     problems_only=self.problems_only,
                                     cleared=self._cleared)
            self.status.setText(f"Log: {result['log']}    Device: {result['device']}")
            self.warning.setText(result['warning'])
            self.details.setText('\n'.join(str(result[key]) for key in
                                          ('freshness', 'traffic', 'queue', 'logger', 'reader')))
            rendered = result['events']
            if rendered != self._rendered:
                self._rendered = rendered
                self.events.setPlainText(rendered)
                scrollbar = self.events.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
        except Exception as error:
            # A display/file-reader failure must never stop controller ticks.
            self.warning.setText(f'Monitor display error: {type(error).__name__}: {error}')

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText('Resume display' if self.paused else 'Pause display')
        if not self.paused:
            self.refresh()

    def set_problems_only(self, enabled):
        self.problems_only = bool(enabled)
        self.refresh(presentation_only=True)

    def clear_view(self):
        if self._last_snapshot is not None:
            self._cleared = {event_key(record) for record in self._last_snapshot.get('events', [])}
        self.refresh(presentation_only=True)

    def copy_display(self):
        QApplication.clipboard().setText('\n'.join((self.status.text(), self.warning.text(),
                                                   self.details.text(), self._rendered)))

    def open_folder(self):
        if self.session_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session_path.resolve())))

    def dispose(self):
        self._disposed = True
        self.timer.stop()
        if self.reader is not None:
            self.reader.close()
        self.hide()
