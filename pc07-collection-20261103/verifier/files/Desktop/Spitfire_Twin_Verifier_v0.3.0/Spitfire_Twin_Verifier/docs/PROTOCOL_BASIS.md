# Protocol basis and fidelity boundary

## Recovered transport

The original Spitfire GUI 1.6.0 startup path binds local UDP port 1024 and sends
to `10.19.70.13:1024`. Its visible COM1/19200 variables do not establish the
primary controller path. Command datagrams are ASCII:

```text
Spectra-Physics:CMD_ECLIPSE,[1000]*idn?\n
[1031]ECU:HUM?\n
```

Replies use:

```text
Spectra-Physics:REPLY_ECLIPSE:<1000>...\n
<1031>34.0\n
```

The recovered sender keeps datagrams at or below 1,400 bytes. Numeric IDs
correlate each reply with its request. The verifier accepts multi-command
datagrams because the original used FIFO batches; Python 1.1.3 normally sends
one outstanding command at a time.

## Deterministic fixture policy

The twin is designed to compare clients, not to emulate laser physics.

- Clients receive isolated state copies by default.
- Initial raw values are identical.
- Writes update only well-supported readback relationships.
- Uncertain service commands are acknowledged and logged but do not invent a
  physical effect.
- Environmental values do not drift with wall-clock time, preventing false
  response differences caused by test timing.
- Q-switch query 1010 uses the recovered wire unit of 10 Hz.
- Delay queries use a synthetic six-prefix-field record compatible with the
  recovered legacy decoder.

## What the report proves

It can prove that, during the captured scenario:

- both clients sent valid ECLIPSE datagrams to the twin;
- command IDs, raw command text, arguments, and batching were observed;
- the exact twin replies and transport outcomes were recorded;
- matched semantic sequences agree or differ in named ways.

It cannot prove how the closed original GUI internally decoded every reply.
That requires observing the screen or instrumenting the process. The generated
`ui_observations.csv` deliberately keeps that evidence separate.


## v0.2.0 validation and timing changes

Request text must agree with the recovered ID catalogue. Known numeric writes
require a finite argument; no-argument commands reject extra arguments. Delay
and mode commands use the documented fixture grammar. This grammar is not a
complete vendor firmware specification and may need refinement after XP traces.
Verifier-generated ERROR:VALIDATION:* replies are synthetic diagnostics.

Motor-speed, BWD, HV, oscillator-mode, fault and delay query aliases read shared
logical state. Unknown physical effects remain explicitly unmodelled. The former
invented HV-current-from-voltage relationship was removed.

A single acquisition loop applies writes in receive order and schedules replies
without sleeping. Replies remain ordered per logical client; delays do not stall
other clients. Every datagram freezes a complete profile at receive time. Reset
cancels scheduled responses and drains already buffered datagrams, then changes
the session ID. Packets that reach the server after that boundary belong to the
new session; no software can classify an in-flight packet as an old user action
without a client-provided run identifier. Pause both GUIs when changing scenarios.

A report uses exactly one snapshot including pending requests, protocol messages,
profiles, and manual observations. REPLIED means sendto succeeded; UDP cannot
prove receipt or parsing by the remote GUI. MATCH is a wire-evidence comparison,
not proof of remote receipt, firmware fidelity, GUI correctness, or physical effects.
