"""Exercise the real serial event loop with a pseudo-terminal, no instrument."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

from emulator import CAPTURED, commands


@unittest.skipUnless(os.name == 'posix', 'PTY transport test uses POSIX pseudo-terminals')
class SerialEndpointTest(unittest.TestCase):
    def test_serial_daemon_replies_to_fragmented_request_and_stops(self):
        import pty
        import serial
        master, slave = pty.openpty()
        name = os.ttyname(slave)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name('emulator.py')),
                                     '--serial', name, '--output', tmp, '--duration', '8'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                # Poll for the daemon's port configuration, without consuming data.
                import termios
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    attrs = termios.tcgetattr(slave)
                    if not attrs[3] & termios.ICANON and attrs[4] == termios.B19200:
                        break
                    time.sleep(.02)
                else:
                    self.fail('Serial endpoint did not configure 19200 baud raw mode')
                request = commands.query_firmware()
                os.write(master, request[:3]);time.sleep(.02);os.write(master, request[3:])
                reply = b''
                deadline = time.monotonic() + 3
                while len(reply) < 12 and time.monotonic() < deadline:
                    if select.select([master], [], [], .2)[0]:
                        reply += os.read(master, 100)
                self.assertEqual(reply, CAPTURED['firmware'])
                (output / 'STOP').touch()
                stdout, stderr = proc.communicate(timeout=3)
                self.assertEqual(proc.returncode, 0, stderr.decode())
                rows = [json.loads(line) for line in (output / 'traffic.jsonl').read_text().splitlines()]
                self.assertEqual(rows[-1]['opcode'], 0x42)
            finally:
                if proc.poll() is None:proc.terminate();proc.communicate(timeout=3)
                os.close(master);os.close(slave)


if __name__ == '__main__':unittest.main()
