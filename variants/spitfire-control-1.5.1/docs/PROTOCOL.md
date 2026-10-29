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

The scheduler cancels queued writes on OFF/STOP, disconnect and communication failure and rechecks authorization
atomically with send. OFF commands take priority over queued queries, but
cannot recall bytes already sent or bypass the currently outstanding reply
wait (bounded by the configured timeout).

Per-module communication status uses fresh 1013/1015/1019/1028 replies and
the original decoders' bit 0x800. Opening a socket alone never proves connection.
See CHANGELOG_1_1_1.md for executable addresses and remaining limitations.


## 1.4.0 receipt and completion policy

The full explicit Clear Faults write order is 2044, 2049, 2052, 2050 in both pump profiles.
External mode permits only the EMP fault reset exception; other EMP control remains excluded.
A framed empty reply with the matching command ID is a receipt, not an ACK or evidence of execution.
Known setters require a matching target readback. A failed/missing readback cancels queued writes.
Reset completion records observations, without assuming all fault bits must clear.
Fault rereads after RESET are scheduled at 0.5, 1.5, 3.5 and 6 seconds, regardless of auto-poll.

EMP current command 2003 uses 0.1 A wire units: GUI amperes multiply by 10.
Nonnegative 1007/1009 readbacks divide by 10; negative sentinel values remain unchanged.
The raw Programmer API does not perform engineering-unit conversion.

UDP responses are source/IP/port/command-ID filtered. Packets already queued before send
are drained. The legacy protocol has no per-transaction nonce. A late reply for the SAME
command ID arriving after a new request cannot always be distinguished; this release does
not claim exactly-once delivery or full protection against that ambiguity. Writes are never
automatically replayed after timeout. Physical actuation remains outside software validation.

## 1.5.0 PC pair and output status

External RUN uses [2019] TDG:DEL 2 ON, readback 1046, then
[2019] TDG:DEL 1 ON, readback 1045. The exact wire mnemonic comes from
commands.py; this combined sequence is a new application policy, not a recovered
original combined RUN callback. STOP requests both channel OFF writes urgently.
A failed RUN requests both OFFs and never retries ON automatically.
OFF completion requires both fresh switch=OFF readbacks. A receipt timeout stays
unverified even if a later state happens to be OFF; the historical result is not
rewritten to successful acknowledgement.

1021 reports device HV state; 1042/1043 are measured voltage. Current key interlock
is 1039 bit 0x4000 and the separate fault register is 1066 bit 0x4000.
None of these alone implies that the PC channels or optical output are ON.
HV/voltage/key/PC reads continue even when optional telemetry polling is disabled.
Global RESET observation now includes these output readings, with before/after
audit snapshots including timestamps and freshness. No extra HV/PC writes are
added to the original four-command reset sequence.
