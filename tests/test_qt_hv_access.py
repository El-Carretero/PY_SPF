"""The exposed Qt HV switch follows controller access without optimistic edits."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from spitfire.controller import Controller
from spitfire.gui import SpitfireWindow


@pytest.fixture
def hv_window(monkeypatch):
    monkeypatch.setattr('socket.socket', lambda *a, **kw: pytest.fail('Qt access test must not open sockets'))
    app = QApplication.instance() or QApplication([])
    created = []

    def make(*, read_only=False, ready=False):
        window = SpitfireWindow()
        controller = Controller(window, demo=True, read_only=read_only, tcp_port=None, clock=lambda: 0.)
        window.attach(controller)
        window.callback.connect(controller.handle_callback)
        window.mouse_released.connect(controller.mouse_released)
        if ready:
            controller.start()
            for _ in range(220):
                controller.tick()
            assert controller.state['gui_ready']
            controller.scheduler.clear()
        emitted = []
        window.callback.connect(lambda *args: emitted.append(args))
        window.show_panel(5)
        app.processEvents()
        created.append((window, controller))
        return window, controller, emitted

    yield make
    for window, controller in created:
        controller.stop()
        window.close()
    app.processEvents()


def test_read_only_ready_hv_cannot_toggle_or_emit_even_if_undim_requested(hv_window):
    window, controller, emitted = hv_window(read_only=True, ready=True)
    window.set_attribute(5, 34, 500, 0)
    panel = window.panels[5]
    assert panel.controls[34]['attrs']['dimmed'] == 1
    assert panel.hit(QPoint(204, 340)) is None
    QTest.mouseClick(panel, Qt.LeftButton, pos=QPoint(204, 340))
    assert window.read(5, 34) == 0
    assert emitted == []
    assert list(controller.scheduler.inside) == []


def test_unready_hv_cannot_toggle_or_emit(hv_window):
    window, controller, emitted = hv_window()
    panel = window.panels[5]
    assert panel.controls[34]['attrs']['dimmed'] == 1
    QTest.mouseClick(panel, Qt.LeftButton, pos=QPoint(204, 340))
    assert window.read(5, 34) == 0
    assert emitted == []
    assert controller.transport is None
    assert list(controller.scheduler.inside) == []


def test_ready_hv_off_click_routes_the_existing_off_command(hv_window):
    window, controller, emitted = hv_window(ready=True)
    panel = window.panels[5]
    window.set_value(5, 34, 1)  # Display fixture only; never issue an HV ON command.
    assert panel.controls[34]['attrs']['dimmed'] == 0
    assert panel.hit(QPoint(204, 340)) == 34
    QTest.mouseClick(panel, Qt.LeftButton, pos=QPoint(204, 340))
    assert window.read(5, 34) == 0
    assert ('HV_switch', 0, 1, 5, 34) in emitted
    assert [(request.tag, request.parameter) for request in controller.scheduler.inside] == [(2016, ''), (1061, '')]


def test_readiness_loss_between_press_and_release_preserves_hv_readback(hv_window):
    window, controller, emitted = hv_window(ready=True)
    panel = window.panels[5]
    window.set_value(5, 34, 1)
    QTest.mousePress(panel, Qt.LeftButton, pos=QPoint(204, 340))
    controller._set_gui_ready(False)
    QTest.mouseRelease(panel, Qt.LeftButton, pos=QPoint(204, 340))
    assert window.read(5, 34) == 1
    assert panel.controls[34]['attrs']['dimmed'] == 1
    assert not any(event[0] == 'HV_switch' and event[2] == 1 for event in emitted)
    assert list(controller.scheduler.inside) == []
