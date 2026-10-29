"""External TCP clients never receive fabricated Empower telemetry."""
import socket

from spitfire.tcp import TCPBridge


def guarded_read(panel, control):
    assert panel not in (8, 9), 'External TCP must not read Empower panels'
    assert (panel, control) != (4, 7), 'External identity must not read Empower version'
    return {(4, 16): 'external-test', (4, 6): 'board', (4, 5): 'TDG',
            (4, 4): 'head', (4, 3): 'ECU'}.get((panel, control), 0)


def test_external_legacy_temperature_reports_unavailable_without_empower_reads():
    bridge = TCPBridge(guarded_read, external=True)
    assert bridge.handle_data('TEMP_STATUS?\n') == b'nan, nan, nan, nan, -1\n'
    assert bridge.handle_data('*IDN?\n') == (
        b'Spectra-Physics, Spitfire External, 0, external-test / board / '
        b'Empower N/A (external) / TDG / head / ECU\n'
    )


def test_ecu_query_uses_fresh_snapshot_and_no_gui_defaults():
    values = {1030: 21.5, 1031: 35.25, 1084: 19.75, 1028: 1}
    bridge = TCPBridge(guarded_read, external=True, external_readbacks=lambda: dict(values))
    assert bridge.handle_data('ECU_STATUS?') == b'21.500, 35.250, 19.750, 1\n'
    values[1028] = 0
    assert bridge.handle_data('ECU_STATUS?').endswith(b', 0\n')
    # Controller omits stale values from the snapshot; old GUI values cannot leak.
    values.clear()
    assert bridge.handle_data('ECU_STATUS?') == b'nan, nan, nan, -1\n'


def test_ecu_query_invalid_and_disconnected_values_stay_unknown():
    for ecu in (0x800, float('nan'), float('inf'), 1.5, -1, 65536, 'bad', None):
        bridge = TCPBridge(guarded_read, external=True,
                           external_readbacks=lambda: {1030: float('inf'), 1031: 'bad', 1028: ecu})
        assert bridge.handle_data('ECU_STATUS?') == b'nan, nan, nan, -1\n'
    assert TCPBridge(guarded_read, external=True).handle_data('ECU_STATUS?') == b'nan, nan, nan, -1\n'
    assert TCPBridge({}).handle_data('ECU_STATUS?') == b''


def test_external_tcp_socket_still_serves_read_only_requests():
    bridge = TCPBridge(guarded_read, {(6, 50, 500): 1}, external=True,
                       external_readbacks=lambda: {1030: 20, 1031: 10, 1084: 19, 1028: 0})
    try:
        address = bridge.start('127.0.0.1', 0)
        with socket.create_connection(address, timeout=1) as client:
            for request, expected in (
                (b'TEMP_STATUS?\n', b'nan, nan, nan, nan, -1\n'),
                (b'ECU_STATUS?\n', b'20.000, 10.000, 19.000, 0\n'),
                (b'FAULTS?\n', b'0\n'),
            ):
                client.sendall(request)
                assert client.recv(512) == expected
            client.sendall(b'EMP:ON\n')
            client.settimeout(.05)
            try:
                client.recv(512)
            except socket.timeout:
                pass
            else:
                raise AssertionError('TCP must not accept an Empower control command')
    finally:
        bridge.stop()
