XP native original-application driver

Executable: guest_driver.exe (Windows XP SP3 x86 compatible imports)
Source: guest_driver.c, optout_guard.c.inc
Build: build_guest_driver.sh, xp_msvcrt.def, verify_guest_driver.py
This helper never sends UDP instrument requests. All captured instrument requests
must originate from the separately launched original Spitfire process.

Invocation:
  guest_driver.exe MODE NEW_OUTPUT_DIRECTORY HOST_ISOLATION_PROOF.txt

Modes currently implemented:
  inventory: read-only window/menu/control/process/route/screenshot inventory
  launch: original unmodified EXE at the locked vendor installation path and SHA256
  regensvc: fixed service-display sequence into the exactly identified main panel
  temperature, timing, faults, setup: reviewed CVI View-menu actions
  about: reviewed CVI Help-menu About action
  exit: reviewed File-menu Exit, with narrowly guarded main GUI-close fallback
  optout_on: authorized one-time Empower Opt-out ON through the original UI
  close: ONLY the reviewed connection-warning OK retry; never generic close

The original CVI application has no native GetMenu(). View actions require the
exact original image/hash, actual main CVI child class and 895x550 client area,
then click client (52,9). The unique visible CVIRTLVMenuWnd4194304 popup must belong to the original PID and match the
observed bounds before an allowed item is clicked at client x107 and y28/44/60/76.
The Help menu is clicked at client (90,9), then About at (107,28), requiring the
observed original-owned popup bounds [75,20,161,40] relative to main client origin.
The File menu is clicked at client (15,9), then Exit at (35,28), requiring the
observed popup bounds [3,20,77,40]. This original callback closes the UDP channel
and quits the interface; Escape is not a substitute because it sends OFF.
CVI menu windows report enabled=false even when functioning. They are therefore
verified by EnumWindows with exact class, PID, visibility and reviewed geometry;
WindowFromPoint alone skips these disabled menu windows.
Mouse down/up are separated by120ms for CVI event processing.
The intermediate popup screenshot and window inventory are retained.

optout_on requires the exact hashed image/base, read-only emp_optout=0 and
service gAccessLevel=1. It identifies the enabled visible original Temperature
Control CVI panel with client480x480, brings it to the foreground, checks window
ownership, and clicks the observed Empower switch ON half at client (255,443) once.
The adjacent TCU Opt-out is never clicked. The helper checks the state again
immediately before the click and after it, retains screenshots, and never retries.
Already-ON causes no click. An unconfirmed transition stops with exit57.
No generic mouse/keyboard command interface exists.
Escape is never sent because the original maps it to OFF.

All actions except inventory require the independent host isolation proof and
recheck one operational guest10.19.70.2 adapter with no default route/gateway and
a direct route to simulator10.19.70.13. The proof must include these exact lines:
  schema=spitfire-isolation-v1
  vm_host=20255566-p07
  vm_network=hostonly
  host_ip_forwarding=disabled
  host_ics_on_vmnet1=disabled
  host_bridge_on_vmnet1=absent
  physical_passthrough=absent
  simulator_bind=10.19.70.13:1024
  simulator_peer=10.19.70.2
  simulator_policy=queries-and-empower-optout-on-only
  guest_ip=10.19.70.2
  authorization=xp-optout-on-and-readonly-navigation
  verified_utc=<current host verification timestamp>
Never reuse assertions without independently rechecking host conditions.

Evidence in each new output directory:
  desktop-before.bmp, desktop.bmp
  windows-before.jsonl, windows.jsonl (includes client rect and screen origin)
  processes-before.jsonl, processes.jsonl
  network.jsonl, timeline.jsonl, result.json, copied host-isolation-proof.txt
  original-state-before.json, original-state.json
  launched-original.json (launch action only)
  desktop-menu-open.bmp, windows-menu-open.jsonl (custom menu action)
  desktop-optout-target.bmp, desktop-optout-clicked.bmp (optout_on)
  corresponding windows-optout-*.jsonl and original-state-optout-*.json
The executable never overwrites an existing output directory.

Exact original path:
C:\Program Files\Spectra-Physics\Spitfire\Spitfire.exe
Original SHA256 independently matched to analyzed image:
8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b
Read-only state checks first hash the file with XP CryptoAPI SHA256, require
module base0x400000, then read emp_optout at0x4141D0 and gAccessLevel at0x416DEC.
No process-memory write, remote-thread execution, DLL injection, or vendor-binary
patch exists. The local helper's own PE minimum-version header is set to5.1.

Synthetic response data never establishes physical controller or laser behavior.
State-changing commands emitted automatically by original startup must be recorded
and rejected by the isolated simulator, except the explicitly authorized
EMPOPTOUT1 change in simulator RAM.

Connection warning retry (close compatibility verb):
This mode is only for the runtime-reviewed Warning dialog whose text was
"Remote system not responding, click OK to retry". Before issuing it, the host
operator must verify simulator health and that this is the observed warning.
The helper requires original SHA/state with Empower Opt-out1; exactly one
visible enabled CVIRTLVDChild4194304 window titled Warning, client308x85,
entirely onscreen; foreground and original-process point ownership. It clicks
client(154,58) once with120ms hold, records target/clicked screenshots, and
checks that no matching warning remains after2s. It does not use OCR to verify
the custom-drawn message, does not send WM_CLOSE/ESC, does not perform fault
reset, and does not retry the click. Any remaining/reappearing warning or
missing simulator responses must be investigated separately. This special
mode is not added to the unattended reusable read-only scenario.

Main titlebar-close fallback for exit:
Only if the File menu action returns43 because no expected popup appeared and
NO menu item was clicked, exit rechecks the original image/state, exact main
class/title/client895x550 and foreground ownership. It opens the identified
process for a bounded exit wait, records a target screenshot, and posts one
WM_SYSCOMMAND/SC_CLOSE to that exact main window. It waits up to7s and reports
whether that process exited. It never sends Escape or TerminateProcess.

This fallback was enabled after static confirmation of original main panel6
ATTR_CLOSE_CTRL=2, BTN_QUIT callback QuitProgram. Original-x86 offline commit1
invoked only QuitUserInterface and queued zero device commands. The CVI runtime
close-event path and NI manual's ATTR_CLOSE_CTRL documentation establish that
system-menu Close commits that close control. This is a main GUI quit path,
not generic WM_CLOSE for arbitrary panels and not a laser OFF/reset action.
Previous c07 executable/source are retained in
  driver-before-titlebar-fallback-c07ad545.zip
