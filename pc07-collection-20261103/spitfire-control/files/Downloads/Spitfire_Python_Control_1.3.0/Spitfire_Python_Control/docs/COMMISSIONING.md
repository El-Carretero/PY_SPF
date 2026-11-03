# Hardware commissioning checklist

This software is not a safety system. The laser's physical emergency stop,
key switch, enclosure, water-flow, temperature, and other interlocks remain
authoritative.

## Phase 1 — offline

Automate the software checks with `py validate_spitfire.py offline`.
See [AUTOMATED_VALIDATION.md](AUTOMATED_VALIDATION.md) for Windows/EXE checks,
the read-only hardware workflow, report interpretation and its limits.

1. Start in **simulator** mode and exercise every screen.
2. Confirm that RUN, HV ON, motor motion, opt-outs, and resets require explicit
   confirmation.
3. In hardware-mode tests with a fake controller, verify that disarmed writes
   are limited to OFF/HV OFF/TEC OFF/motor STOP. Simulator edits deliberately
   do not require ARM.

## Phase 2 — read-only controller check

1. Physically inhibit emission and high voltage according to the laboratory's
   approved procedure.
2. Isolate the controller network; do not bridge it to a general LAN.
3. Set the local NIC to the controller subnet and confirm reachability of the
   configured address (legacy default `10.19.70.13`).
4. Select UDP mode, leave **ARM off**, and connect.
5. Verify `*IDN?`, module versions, temperature, humidity, and status replies.
6. Save a packet capture and compare the headers and command IDs in
   `PROTOCOL.md`.

## Phase 3 — controlled writes

1. Establish the controller-specific safe ranges from its service manual and
   record current setpoints before changing anything.
2. Use ARM only for a planned, witnessed test. Start with a reversible,
   non-emission setpoint.
3. Verify every write through its corresponding readback query.
4. Test SOFTWARE STANDBY, but never treat it as an emergency stop or a
   fail-safe. A failed network cannot guarantee delivery.
5. Only after the lab's laser safety owner approves the preceding results,
   proceed to output or high-voltage testing under the local SOP.

## Optional phase — raw RS-232 service diagnostics

Raw serial access is independent of the verified UDP/ECLIPSE control path and
bypasses all command validation and ARM rules.

1. Physically inhibit laser emission and high voltage before attaching a
   serial cable or USB adapter.
2. Press `Ctrl+Shift+R`, acknowledge the raw-service warning, and select the
   exact port. Merely opening the window does not open a serial device.
3. Confirm voltage levels and pinout first. RS-232, TTL UART, and differential
   serial interfaces are not electrically interchangeable.
4. Start from the documented device settings. The legacy screen value is
   `COM1`, `19200`, `8-N-1`, but it is not proof of a specific service-port
   protocol.
5. Prefer a passive receive-only capture first. For transmit tests, use HEX
   mode when byte-exact output matters and select the line ending explicitly.
6. Save the raw log with the device serial number, cable/adapter model, and
   test conditions. Disconnect the port immediately after the check.

## 1.1.1 readback checks

Verify the GUI Hz / raw PRF factor of ten and capture a complete TDG:DEL1?
reply. Confirm that the numeric delay and all three mode selectors agree
with the raw record. A write ACK must not be interpreted as measured HV OFF.
STOP cancels queued writes; already-sent commands cannot be recalled.
After a timeout, require fresh read-only replies before rearming.
