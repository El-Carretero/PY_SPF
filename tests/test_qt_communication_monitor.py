"""The Qt monitor reads a session and routes no instrument callbacks."""
import json
import os
import time
from datetime import datetime, timezone

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from spitfire.gui import SpitfireWindow


@pytest.fixture
def monitor_window(monkeypatch):
    monkeypatch.setattr('socket.socket', lambda *args, **kwargs: pytest.fail('Monitor must not create sockets'))
    app = QApplication.instance() or QApplication([])
    window = SpitfireWindow()
    callbacks = []
    window.callback.connect(lambda *args: callbacks.append(args))
    yield window, callbacks
    window.close()
    app.processEvents()


def _wait(dialog, predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        dialog.refresh()
        if predicate():
            return
        QTest.qWait(20)
    pytest.fail('Monitor did not observe saved diagnostics')


def _event(sequence, payload):
    return json.dumps({'seq': sequence, 'session_id': 'qt', 'kind': 'RX',
                       'utc': datetime.now(timezone.utc).isoformat(), 'payload': payload}) + '\n'


def test_menu_stays_available_when_hardware_menu_is_dimmed(monitor_window):
    window, callbacks = monitor_window
    window.set_menu_attribute(6, 0, 500, 1)
    assert not window.menu_actions[5].isEnabled()
    assert window.communication_monitor_action.isEnabled()
    assert window.menuBar().isEnabled()
    window.communication_monitor_action.trigger()
    monitor = window._communication_monitor
    assert monitor is not None and monitor.isVisible()
    assert 'disabled' in monitor.status.text().lower()
    assert monitor.reader is None
    assert callbacks == []
    # Recovering global access must preserve a separately dimmed command menu.
    window.set_menu_attribute(6, 5, 500, 1)
    window.set_menu_attribute(6, 0, 500, 0)
    assert not window.menu_actions[5].isEnabled()
    assert window.menu_actions[6].isEnabled()


def test_saved_events_local_controls_and_reader_shutdown(tmp_path, monitor_window):
    window, callbacks = monitor_window
    path = tmp_path / 'events.jsonl'
    path.write_text(_event(1, 'first reply'), encoding='utf-8')
    window.configure_communication_monitor(tmp_path)
    monitor = window.show_communication_monitor()
    _wait(monitor, lambda: 'first reply' in monitor.events.toPlainText())
    assert len(window.panels) == 10
    monitor.pause_button.click()
    assert monitor.paused
    with path.open('a', encoding='utf-8') as stream:
        stream.write(_event(2, 'second reply'))
    QTest.qWait(300)
    monitor.refresh()
    assert 'second reply' not in monitor.events.toPlainText()
    monitor.pause_button.click()
    _wait(monitor, lambda: 'second reply' in monitor.events.toPlainText())
    monitor.clear_button.click()
    assert 'first reply' not in monitor.events.toPlainText()
    assert 'second reply' not in monitor.events.toPlainText()
    with path.open('a', encoding='utf-8') as stream:
        stream.write(_event(3, 'third reply'))
    _wait(monitor, lambda: 'third reply' in monitor.events.toPlainText())
    monitor.filter_button.click()
    assert monitor.problems_only
    monitor.filter_button.click()
    monitor.copy_button.click()
    assert 'third reply' in QApplication.clipboard().text()
    assert callbacks == []
    reader = monitor.reader
    window.close_communication_monitor()
    assert not reader._thread.is_alive()
    assert window._communication_monitor is None


def test_monitor_render_failure_does_not_escape_into_controller_tick(tmp_path, monitor_window, monkeypatch):
    window, callbacks = monitor_window
    window.configure_communication_monitor(tmp_path)
    monitor = window.show_communication_monitor()
    monkeypatch.setattr(monitor.reader, 'snapshot', lambda: (_ for _ in ()).throw(OSError('test sharing failure')))
    window.refresh_communication_monitor()
    assert 'sharing failure' in monitor.warning.text()
    assert callbacks == []
