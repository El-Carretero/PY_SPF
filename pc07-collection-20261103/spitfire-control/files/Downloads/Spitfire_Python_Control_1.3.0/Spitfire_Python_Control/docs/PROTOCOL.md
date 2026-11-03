# ECLIPSE protocol compatibility notes

This document records what was recovered by static analysis of the 2005
Spectra-Physics Spitfire GUI 1.6.0 package. It is an interoperability note, not
a vendor specification.

## Confirmed transport

The original `openandconfigureport` routine populates legacy-looking values
`COM1`, `19200`, and 8-bit framing, but it never calls its imported serial-port
open routine. Its actual startup path calls `Open_Udp_Port2(0x400)`, binding
local UDP port **1024**. Packets are sent to **10.19.70.13:1024**.

Both endpoints are configurable in this implementation. This matters when a
new controller, a routed lab network, or a packet-capture proxy is used.

Version 1.1 adds an operator-invoked raw RS-232 terminal for bench service
work. That terminal is a separate byte stream: it does not wrap serial bytes
in ECLIPSE packets and it does not alter the conclusion above about the legacy
GUI's primary transport.

## Command packet

Each datagram begins with the ASCII bytes:

```text
Spectra-Physics:CMD_ECLIPSE,
```

It is immediately followed by one or more LF-terminated lines:

```text
[1000]*idn?
[1031]ECU:HUM?
```

The legacy sender splits a packet before it exceeds 1,400 bytes. There is no
CRC in this layer and no NUL terminator on the wire.

## Reply packet

The receiver expects a colon, the literal `REPLY_ECLIPSE`, another colon, then
one or more CR/LF-delimited lines:

```text
Spectra-Physics:REPLY_ECLIPSE:<1000>Spectra-Physics,Spitfire,...
<1031>34.2
```

The numeric value between `<` and `>` correlates the reply with the command
ID. The remainder is preserved as text, then conservatively converted to a
number only for known numeric queries.

## Scheduler behaviour

The old application used two fixed-size FIFO queues. It sent a new batch only
after all replies to the preceding batch had arrived, and treated a 10-second
silence as a communication problem. The Python scheduler uses a worker thread,
one outstanding command at a time, explicit timeout reporting, and an audit
trail. This is slower but easier to diagnose and avoids ambiguous correlation.

## Other recovered network surface

The old executable also opened a TCP server on port 1001 with at least these
read commands: `FAULTS?`, `*IDN?`, `TDG_STATUS?`, and `EMP_STATUS?`. The Python
application does not expose an unauthenticated remote-control server by
default. This intentionally removes an unnecessary control-network attack
surface.

## Known uncertainties

- Firmware revisions may return different status-bit layouts or text.
- The `EMP:FAULT?` four-word payload is preserved losslessly. Friendly fault
  labels in the UI are an operator aid; the raw words are authoritative.
- Delay arguments and several service commands require validation against the
  specific controller firmware and laser configuration.
- The first real-controller session should occur with laser output inhibited,
  preferably through a mirrored port or packet-capture host. Compare identity
  and read-only queries before arming any write.

The complete recovered numeric catalogue is in
`src/spitfire_control/commands.py` and is also visible from the GUI's Programmer
tab.

## Version 1.1.1 corrections

The 146 command strings remain raw wire commands. The normal GUI divides
Q-switch frequency in Hz by 10 before write 2004; read 1010 is multiplied by
10 for nonnegative values. `raw_values` preserves the wire text, and the
Programmer console does not perform engineering-unit conversion.

Delay replies are compound records: the original searches OFF/NBWD/NENA and
extracts the number after six prefix fields. Modes and numeric delay are now
stored separately. Bare numeric replies are accepted without guessing modes.
Simulator compound records are synthetic fixtures, not packet captures.

UDP replies must match the configured source IP, source port, and current
request ID. Write ACKs never overwrite measured state. Matching readbacks are
queued even with automatic polling off. Unknown write acknowledgements are
reported conservatively; only OK/ACK are accepted as positive ACK text.

The scheduler cancels queued writes on DISARM/OFF and rechecks authorization
atomically with send. OFF commands take priority over queued queries, but
cannot recall bytes already sent or bypass the currently outstanding reply
wait (bounded by the configured timeout).

Per-module communication status uses fresh 1013/1015/1019/1028 replies and
the original decoders' bit 0x800. Opening a socket alone never proves connection.
See CHANGELOG_1_1_1.md for executable addresses and remaining limitations.
