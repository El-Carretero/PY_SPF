Spitfire original XP capture procedure (2026-11-01 KST)

This session is authorized to enable Empower Opt-out in the isolated XP copy.
No other changing UI controls are allowed. Physical equipment is out of scope.

Host modules:
 Prepare-Host.ps1 validates hostonly VM, no bridge/ICS/IP forwarding, fixed IPs.
 host_server.py replies to original queries and applies only EMPOPTOUT1 in RAM.
 Issue-Action.ps1 issues one allowlisted action after previous completion.
 pcap_audit.py converts original Pktmon pcapng to classic pcap preserving frames.
 analyze_run.py summarizes messages and original-process/action evidence.

Guest modules:
 bootstrap.hta writes/launches the embedded local controller without OS security changes.
 controller-local.hta polls one allowlisted action at a time and uploads evidence.
 guest_driver.exe uses original vendor executable and normal Win32 UI input.
 The helper sends no UDP protocol messages. Actual requests originate in Spitfire.exe.

One-time guest launch while host HTTP service/capture is running:
 mshta http://10.19.70.13:18979/bootstrap.hta

State-changing command policy:
 Only [2036]EMPOPTOUT 1 can alter simulated state; source fixture files remain unchanged.
 Other >=2000 commands are logged, rejected, and get a matching synthetic ACK0
 to prevent the legacy scheduler stalling. ACK0 is not physical device success.
 Responses are deterministic simulated data, not firmware behavior.

No Escape, RUN/ON, OFF/STOP, HV, reset, interlock override, parameter edits.
Current screen/controls must be verified before enabling any new click action.
