Fresh original-XP capture runs
=============================

Start-NewRun.ps1 and Run-ReadOnlyScenario.ps1 are NEW reusable orchestration
wrappers. They have not been executed end-to-end. The historical session did
successfully run the native guest inventory, original launch, service display,
Temperature / Timing / Faults / Setup / About menus, File Exit, restart and
restart Opt-out-ON verification. A positive automatic Opt-out transition has
NOT been demonstrated: the user confirmed the actual ON transition, and the
later helper invocation found it already ON and skipped clicking. Do not infer
automatic Opt-out success from that skip. A future successful guarded action
must be assessed using its state files, actual 2036 packet, and simulator log.

Prerequisites
-------------
- Run only on 20255566-p07, in an elevated Windows PowerShell 5.1+ console.
- Keep all supplied source/executable files together; Python 3.9+ must resolve
  as python. No guest Python or Wireshark is required.
- The intended XP VM must already be running, alone, with the original program
  CLOSED. The wrappers check the known VMX, host-only adapter, no other VM,
  no bridge/ICS/IPv4 forwarding or physical device passthrough, guest/host IPs,
  and original image identity. They do not start or reconfigure the VM.
- Fixture source is the existing read-only file:
  C:\Users\Fluke\Desktop\Spitfire_LogAudit_20261030\reply-values.json
  Initial 1068 must be 0 or 1, 1067 must be INT, 1085 must be 0. That source is not
  modified. Simulator Opt-out changes exist only in that run's process RAM.
- Finish the prior run first. Active Pktmon captures/filters and occupied
  UDP 1024 or HTTP 18979 cause a stop; the wrappers never clear unrelated ones.

Run
---
1. In elevated p07 PowerShell, change directory to this bundle.
2. Default, without permission to change Opt-out:
     .\Start-NewRun.ps1
   This stops if initial fixture or original application Opt-out is OFF.
   The current saved fixture may still be 0 because prior ON changed RAM only.
3. ONLY when enabling Empower Opt-out in this isolated XP copy is authorized:
     .\Start-NewRun.ps1 -EnableOptOut
   This adds the reviewed regensvc -> Temperature -> optout_on path if OFF.
   No other setting changes are enabled. An unconfirmed ON action stops;
   there is no retry loop and the helper never toggles an already-ON switch.
4. When the host console says capture is ready, perform one bootstrap inside
   XP Start > Run:
     mshta http://10.19.70.13:18979/bootstrap.hta
   VMware Tools are absent/not assumed. The initial guest-local controller
   launch is necessary once PER FRESH RUN. All subsequent UI actions execute
   inside XP through the native helper, not through remote VMware keystrokes.
5. Leave the XP desktop alone while actions run. Do not alter network, VM,
   instrument settings or simulator files during the run.

Every run creates distinct host and guest directories using UTC timestamp and
a random suffix. Existing captures are not overwritten. The generated HTA
copies embed those fresh paths; historical bootstrap.hta/controller-local.hta
are retained unchanged in the supplied bundle. There is no need to delete
earlier XP capture directories to rerun.

Default host output parent:
  C:\Users\Fluke\Desktop\Spitfire_Original_Runs
Example options:
  .\Start-NewRun.ps1 -EnableOptOut -Base C:\SpitfireRuns -Seconds 2400
  .\Start-NewRun.ps1 -GuestReadyTimeoutSeconds 900

-Seconds is the entire simulator/controller service lifetime, including the
guest bootstrap wait and all actions. Keep it longer than the expected wait
plus the scenario (default2400s, maximum3600s). Expiry stops the run with
partial evidence; it does not extend itself or issue overlapping UI input.

Automatic sequence
------------------
Inventory -> verify no existing original -> check initial Opt-out policy ->
launch original -> wait 30s -> verify original SHA/state -> optional authorized
Opt-out-ON path -> verify ON -> reviewed user/service Temperature and service
Timing / Faults / Setup / About displays -> File Exit -> restart -> wait 30s ->
verify ON -> user Temperature display -> File Exit -> guest controller exit.

Both original application state and simulator RAM must remain ON at checks.
Escape, RUN/ON, OFF/STOP, HV, parameter edits, fault resets, other opt-outs,
interlock overrides, generic clicks and generic WM_CLOSE are not used.
The current exit driver falls back to the reviewed main SC_CLOSE path only
when its File popup guard fails before any menu item click. This GUI close
path was exercised successfully in historical action27; it does not terminate
the process forcibly or emit a device command.
On an error, the wrapper attempts only this reviewed exit action if a fully
completed action proves it is safe to queue another action. If an action times
out, it does not send overlapping UI input. scenario-result.json records if
the original may remain running; review that condition before the next run.

Capture, cleanup and evidence
-----------------------------
The host discovers the current Pktmon component ID for VMnet1 and requires it
to be unique. It checks that Pktmon is idle and has no existing filters. It
adds only a run-named UDP 1024/.2 filter and captures full frames on that
component; HTTP transfers are excluded. Both guest transmission and simulator
responses must pass the pcap audit. No original physical PC is accessed.

The wrapper removes only its own named firewall/filter rules, stops its own
capture and simulator, and retains original ETL segments. Pktmon conversion
produces original.pcapng; the strict converter produces classic original.pcap
and reparses it, preserving frame bytes and requiring both directions.
Host and XP clocks are retained separately in the timeline.

Inspect:
  run-result.json and scenario-result.json: complete/partial result and errors
  original.pcap / original.pcapng / original*.etl: original captured frames
  original.audit.json: direction counts, byte preservation, capture validation
  received/: per-action screenshots, processes, state, route and UI evidence
  analysis/: query summary, action intervals and clock-qualified timeline
  host-isolation.json, session.json, capture logs and artifact-sha256.csv

The output remains simulator evidence. Original outgoing packets are real
original-program output; responses and ACK 0 values come from the fixture.
They establish no physical laser/controller behavior. Startup writes other
than authorized EMPOPTOUT 1 are logged and rejected with synthetic ACKs.

If PowerShell script policy blocks a script, follow the site's normal script
execution policy. The wrappers do not change machine execution/security policy.
