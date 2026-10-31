"""External presentation must stay independent after legacy view mutations."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, Qt, QEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from spitfire.gui import SpitfireWindow, font
from spitfire.external_ui import HIDDEN_CONTROLS


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    view = SpitfireWindow()
    view.show()
    app.processEvents()
    yield view
    view.close()
    app.processEvents()


def test_empower_panels_are_not_constructed_or_reopened(window):
    assert 8 not in window.panels and 9 not in window.panels
    for panel in (8, 9):
        window.show_panel(panel, True)
        window.set_panel_attribute(panel, 530, 1)
    assert 8 not in window.dialogs and 9 not in window.dialogs
    assert 'Empower-independent' in window.windowTitle()
    assert all('Empower Setup' not in action.text() for action in window.menu_actions.values())


def test_empower_controls_stay_hidden_after_legacy_updates(window):
    for panel, controls in HIDDEN_CONTROLS.items():
        for control in controls:
            window.set_attribute(panel, control, 530, 1)
            assert not window.read_attribute(panel, control, 530)
    window.set_attribute(2, 9, 500, 0)
    assert window.read_attribute(2, 9, 500) == 1
    assert 'PC' in window.read_attribute(6, 10, 641)
    assert 'PC' in window.read_attribute(6, 11, 641)


def test_optout_and_hv_off_are_distinct_explicit_menu_actions(window):
    calls = []
    window.callback.connect(lambda *args: calls.append(args))
    window.menu_actions[7].trigger()
    window.menu_actions[11].trigger()
    assert [call[0] for call in calls] == ['apply_external_optout', 'external_hv_off']


def test_leaving_run_button_cancels_hold(window):
    calls = []
    window.callback.connect(lambda *args: calls.append(args))
    panel = window.panels[6]
    a = panel.controls[10]['attrs']
    center = QPoint(a['left'] + a['width']//2, a['top'] + a['height']//2 + panel.offset_y)
    QTest.mousePress(panel, Qt.LeftButton, pos=center)
    calls.clear()
    QTest.mouseMove(panel, QPoint(480, center.y()))
    assert any(call[0] == 'cancel_run_hold' for call in calls)
    QTest.mouseRelease(panel, Qt.LeftButton, pos=QPoint(480, center.y()))


def test_window_deactivation_and_panel_navigation_cancel_hold(window):
    calls = []
    window.callback.connect(lambda *args: calls.append(args))
    QApplication.sendEvent(window, QEvent(QEvent.WindowDeactivate))
    window.show_panel(5, True)
    assert sum(call[0] == 'cancel_run_hold' for call in calls) >= 2


def test_status_explains_pc_scope_and_remains_visible(window):
    assert 'PC1 + PC2' in window.external_status.text()
    window.set_external_status('RUN blocked: external pump opt-out is unknown')
    assert window.external_status.isVisible()
    assert 'unknown' in window.external_status.text()


def test_critical_text_fonts_have_ascii_glyphs(window):
    # Offscreen Windows can create valid PNGs containing only missing-glyph boxes.
    fonts = [window.external_status.font()]
    fonts.extend(font(window.panels[6].controls[cid]['attrs'], 'label_') for cid in (10, 11, 50))
    for selected in fonts:
        metrics = QFontMetrics(selected)
        assert all(metrics.inFont(char) for char in 'PC RUN STOP connected 0123456789'), selected.family()
