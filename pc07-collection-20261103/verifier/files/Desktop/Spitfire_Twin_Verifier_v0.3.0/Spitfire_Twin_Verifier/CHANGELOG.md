# Changelog

## 0.2.0 — 2026-09-17

- Compare polling values, errors and transitions while compressing identical repetition.
- Separate content, numeric meaning, framing, transport health and manual GUI observations.
- Include malformed/unassigned traffic and pending datagrams in verdicts; never pass identical send errors.
- Export comparison and JSONL from one immutable session snapshot; cached GUI results cannot leak into reports.
- Replace global sleeping worker with ordered request processing and scheduled per-client replies.
- Record receive/send timestamps and total latency; cancel old scheduled work at session reset.
- Validate ID/text agreement and arguments; share state across query aliases; mark unmodelled effects.
- Distinguish request loss from reply loss; reply override/loss follows command execution.
- Freeze full profiles per datagram and keep profile/scenario history; retain logical state across reconnects.
- Add scenario and manual observation tab, visible diagnostic history, source test launcher.
- Fix PyInstaller entry point and add build error checks plus frozen CLI self-test.

## 0.1.0 — 2026-09-17

- Added a network-visible virtual Spitfire at a configurable IPv4/UDP endpoint.
- Added all 146 commands recovered from Spitfire GUI 1.6.0.
- Added deterministic isolated state for XP and Python clients.
- Added Q-switch scaling-compatible raw values and compound Delay records.
- Added live Tk traffic inspection with raw packet hex.
- Added semantic sequence alignment, polling-count comparison, and reports.
- Added controlled response override, error, drop, delay, CRLF, and bad-header tests.
- Added safe loopback demo, headless mode, Windows launchers, reversible Host-only
  network scripts, and optional PyInstaller build script.
