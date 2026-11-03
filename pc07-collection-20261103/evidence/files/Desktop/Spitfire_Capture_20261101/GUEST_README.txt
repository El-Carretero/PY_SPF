XP GUEST READ-ONLY PROBE 1.0

This helper inventories the XP guest and can send one explicitly gated Opt-out
query. It never starts SPITFIRE.EXE, clicks controls, injects keyboard input,
changes Opt-out, changes network configuration, or changes laser parameters.

BUILD
  ./build_guest_probe.sh
Uses Zig0.13.0 installed at build-tools/ziglang/zig:
  python -m pip install --target build-tools ziglang==0.13.0
  ./build-tools/ziglang/zig cc -target x86-windows-gnu ...
The script links XP MSVCRT with a custom entrypoint, avoids modern UCRT startup,
then explicitly sets our helper's PE minimum OS/subsystem to5.1 and verifies imports.
Only this newly built helper is adjusted; no vendor application is patched.
The build targets PE32/Windows subsystem5.1 and ordinary Windows DLLs.
No Python, .NET, VMware Tools, Wireshark or driver is needed in the XP guest.
Copy guest_probe.exe to an existing directory on the isolated XP guest.

READ-ONLY INVENTORY (no packets sent)
  guest_probe.exe inventory C:\capture\inventory_unique
The output directory must not exist; its parent must already exist.
Files: identity.json, processes.jsonl, windows.jsonl, network.jsonl,
desktop.bmp, timeline.jsonl. Window enumeration includes hidden windows and
controls, their IDs/rectangles/enabled state, and menu structures. Custom CVI
controls may be owner-drawn; Windows child enumeration may not expose values.
The BMP is a screenshot, not proof that a state was changed or queried.

GUARDED OPT-OUT PREFLIGHT
  guest_probe.exe preflight C:\capture\preflight_unique C:\capture\host-isolation-proof.txt
Before using preflight, independently inspect the p07 host and create the
proof below only when EVERY condition was actually verified. The helper cannot
inspect host VMware/ICS settings from inside XP. The proof is an auditable
operator/host-orchestrator assertion, not a cryptographic attestation.

Required exact proof lines (replace verified_utc with the actual UTC time):
  schema=spitfire-isolation-v1
  vm_host=20255566-p07
  vm_network=hostonly
  host_ip_forwarding=disabled
  host_ics_on_vmnet1=disabled
  host_bridge_on_vmnet1=absent
  physical_passthrough=absent
  simulator_bind=10.19.70.13:1024
  simulator_peer=10.19.70.2
  simulator_immutable=true
  guest_ip=10.19.70.2
  authorization=diagnostic-optout-query-only
  verified_utc=2026-10-31T00:00:00Z
Additional evidence paths or comments may be appended. Do not simply copy
these assertions without rechecking them. Ordinary keyboard/mouse virtual HID
does not constitute a physical laser/controller passthrough.

The local guard requires exactly one operational IPv4 interface, only guest
address10.19.70.2 on that interface, no default route or configured gateway,
and a direct route to10.19.70.13. A standard loopback self-route is permitted.
It refuses a running process named SPITFIRE.EXE and exclusively binds port1024.
It does not kill processes or reuse another application's socket.

Only after both guards pass does it send exactly one UDP datagram:
  Spectra-Physics:CMD_ECLIPSE,[1068]EMPOPTOUT?\n
Source10.19.70.2:1024; destination10.19.70.13:1024. Timeout3.5seconds.
This is DIAGNOSTIC-GENERATED traffic, not an original-program packet.
No retry, discovery, broadcast, RUN/OFF, reset, mode or setting command exists.
The response must come from10.19.70.13:1024 and contain precisely the expected
REPLY_ECLIPSE prefix and <1068>0 or <1068>1 plus whitespace. Ambiguous input fails.
The byte-exact UDP payload files are diagnostic-tx-payload.bin and
diagnostic-rx-payload.bin. They are payloads, not fabricated pcap records.
Use host packet capture to retain actual Ethernet/IP/UDP headers and timings.

EXIT CODES
  0: inventory completed, or preflight readback is1 (depending on mode)
  2: incorrect arguments
  3: output path/file error
  4: incomplete essential inventory
 20: Opt-out is0; requested Opt-out-on suite blocked, no changes made
 21: Opt-out unknown/invalid/no reply, or original process running
 22: guest network guard failed
 23: host isolation proof missing/incomplete
Preflight0 does not authorize unknown UI controls or launch any application.
An eligible later suite must still use the reviewed action allowlist and an
immutable simulator that rejects every state-changing command. Original startup
itself emits EMP:LBOBREAK1; retain that fact rather than calling it query-only.

TIME AND LIMITATIONS
Timeline UTC is from the XP guest clock; compare it against host capture time
before analysis. A frozen/incorrect XP clock must be reported. Simulator replies
are test fixtures and say nothing about a real controller. Opt-out0/unknown
blocks the requested suite. Do not edit the simulator fixture or toggle the UI
to manufacture Opt-out1. Do not use Escape: the original binds it to OFF.
