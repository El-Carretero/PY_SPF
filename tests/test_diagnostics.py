"""Local diagnostics observe state without issuing GUI or transport requests."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from spitfire.diagnostics import SessionDiagnostics


def test_disabled_diagnostics_need_no_controller_or_files():
    diagnostics = SessionDiagnostics(None)
    diagnostics.tick()
    diagnostics.close()


def test_main_thread_samples_communication_and_timer_watchdog_is_bounded(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('spitfire.diagnostics.time.monotonic', lambda: now[0])
    arm = Mock()
    cancel = Mock()
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.dump_traceback_later', arm)
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.cancel_dump_traceback_later', cancel)
    thread = SimpleNamespace(start=Mock(), join=Mock(), is_alive=lambda: False)
    monkeypatch.setattr('spitfire.diagnostics.threading.Thread', lambda **kw: thread)

    class View:
        _read_diagnostics = {'get_ctrl_val_calls': 7, 'timer_values_skipped': 2}

        def read(self, panel, control):
            return 42

    original_log = Mock()
    communication = Mock(return_value={'controller': {'tx_packets': 12}, 'last_status_age_seconds': .5})
    controller = SimpleNamespace(view=View(), log=original_log, read_only=True,
                                 communication_diagnostics=communication,
                                 state={'connected': True, 'gui_ready': True, 'last_query_id': 1085},
                                 running=True)
    diagnostics = SessionDiagnostics(controller, tmp_path)
    assert controller.view.read(6, 8) == 42
    controller.log('TX', '[1085]STATUS?')
    original_log.assert_called_once_with('TX', '[1085]STATUS?')
    for _ in range(20):
        diagnostics.tick()
    assert arm.call_count == 1  # No watchdog thread recreation per GUI tick.
    assert communication.call_count == 1
    now[0] += 1.1
    diagnostics.tick()
    assert arm.call_count == 2
    assert communication.call_count == 2
    diagnostics._flush()
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert heartbeat['loops'] == 21
    assert heartbeat['read_only'] and heartbeat['gui_ready']
    assert heartbeat['communication']['controller']['tx_packets'] == 12
    assert heartbeat['native_reads']['timer_values_skipped'] == 2
    assert heartbeat['original_ni_gui_version'] == '1.6.0'
    assert set(heartbeat['source_sha256']) == {'native.py', 'native_ticker.py', 'controller.py', 'protocol.py'}
    events = [json.loads(row) for row in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert events[0]['payload'] == '[1085]STATUS?'
    diagnostics.close()
    assert controller.log is original_log
    assert controller.view.read(6, 8) == 42
    cancel.assert_called_once_with()
