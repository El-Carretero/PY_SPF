# Capture tool research

Research date: 2026-11-01 Asia/Seoul. This is source research, not evidence that a tool is installed or that a capture succeeded.

## XP-compatible choice

- Wireshark **1.10.14 win32** is the last release of the branch officially supporting Windows XP. Wireshark 1.12 deprecated XP; do not describe 1.12 as the last officially supported XP branch.
- Official binary: <https://www.wireshark.org/download/win32/all-versions/Wireshark-win32-1.10.14.exe>
- Expected length: **22,205,680 bytes**.
- Published SHA1: `37f74c6f3e73550904e621ae2f5ad342be5762f6`.
- Published MD5: `b818ecbd661ab30a7b50d8d990e70ac7`.
- Published RIPEMD160: `114179f7e4dd90b8556d5fff809672231109486f`.
- Signed digest manifest: <https://www.wireshark.org/download/src/all-versions/SIGNATURES-1.10.14.txt>
- Release announcement: <https://lists.wireshark.org/archives/wireshark-announce/201505/msg00000.html>
- Platform support: <https://www.wireshark.org/docs/wsug_html_chunked/ChIntroPlatforms.html>
- 1.12 XP deprecation: <https://www.wireshark.org/docs/relnotes/wireshark-1.12.0.html>

## Capture driver

- **WinPcap 4.1.3** lists XP x86/x64 among its previously supported platforms. It is no longer maintained. Npcap's currently documented minimum is Windows 7 SP1, so do not install current Npcap in XP.
- Official binary: <https://www.winpcap.org/install/bin/WinPcap_4_1_3.exe>
- Published SHA1: `e2516fcd1573e70334c8f50bee5241cdfdf48a00`.
- Published MD5: `a11a2f0cfe6d0b4c50945989db6360cd`.
- Official download and published hashes: <https://www.winpcap.org/install/index.html>
- Platform/version guidance: <https://wiki.wireshark.org/WinPcap>
- Installation verification guidance: <https://www.winpcap.org/misc/faq.htm>

## Download and integrity method

Download on the p07 host over validated HTTPS and transfer files offline through an already verified guest file channel; do not give XP Internet access. Compare the published SHA1 before execution, record length and a newly computed SHA256 for exact artifact identity, and record Authenticode signer/status on the modern host. A locally computed SHA256 by itself is not publisher verification. Saving the signed digest manifest is not the same as successfully verifying its PGP signature; report the distinction. Old SHA1/MD5 digests provide historical artifact matching, not modern collision resistance. Use a new empty staging directory so unrelated DLLs cannot affect the old WinPcap installer.

## Installation automation

Wireshark 1.10.14 source documentation explicitly supports `/S`, `/desktopicon=no`, `/quicklaunchicon=no`, and `/D=...` (last parameter; no quotes around that parameter). It explicitly states that silent installation **does not install WinPcap**. Do not use `/NCRC`, which disables the installer integrity check.

Example after digest verification:

```bat
start /wait "" Wireshark-win32-1.10.14.exe /S /desktopicon=no /quicklaunchicon=no /D=C:\Program Files\Wireshark
```

WinPcap 4.1.3 should be automated via the XP guest's own GUI-control code using exact window/process identity and observed button text. Do not assume `/S` works. Inspect each installer dialog first; click only the documented installer navigation controls, preserving evidence. Confirm `wpcap.dll`/`Packet.dll` version, `sc query npf`, `dumpcap -v`, and `dumpcap -D` afterwards. Installer exit alone is insufficient.

Version-specific source used: <https://github.com/wireshark/wireshark/blob/wireshark-1.10.14/docbook/wsug_src/WSUG_chapter_build_install.xml>

## Capture selection and validation

If the p07 host already has a working capture driver, capture the verified VMnet1 interface. XP installation is unnecessary if the host demonstrably records guest requests AND simulator responses. Use full snapshot length and an explicitly scoped filter. For dumpcap 1.10.14:

```bat
dumpcap.exe -i VERIFIED_VMNET1_INTERFACE -p -s 65535 -f "udp and host 10.19.70.2 and host 10.19.70.13 and port 1024" -P -a duration:300 -w raw.pcap
```

`-P` produces classic pcap in 1.10.14. Recheck current addresses first. Preserve dumpcap stderr/drop statistics, interface inventory and capture version. Inspect a short probe before a full run: raw request and response byte lengths and payloads must agree with application/socket-side logs; both directions must have nonzero counts. Capture from a single interface to avoid pcapng being forced by multiple-interface capture. Capture full link-layer bytes; do not manufacture IP/UDP headers from simulator socket logs and call that an original capture.

Version-specific dumpcap source: <https://github.com/wireshark/wireshark/blob/wireshark-1.10.14/doc/dumpcap.pod>

On a sufficiently recent p07 Windows host, built-in **Pktmon** is another installation-free option. First inspect its version/help, running-session state and VMnet1 component ID. Use `--pkt-size 0`, a VMnet1-specific component and scoped filter, preserve original ETL, convert with `pktmon etl2pcap`, then convert pcapng to classic pcap with `editcap -F pcap` if all frames use one encapsulation. Different stack components may record duplicate appearances of the same packet; preserve raw ETL and account for this instead of reporting duplicates as separate application requests. Do not stop someone else's Pktmon session or replace existing filters without preserving them.

Microsoft documentation: <https://learn.microsoft.com/en-us/windows-server/networking/technologies/pktmon/pktmon-syntax>, <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pktmon-start>

After capture, read it with a real parser (`capinfos`, `tshark -r`, preferably the chosen old Wireshark tools too); verify classic pcap magic, intact packet records, captured length equal to original length, expected endpoints and two nonzero direction counts. Packet counts alone do not prove no loss; reconcile simulator log payloads/times and capture drop statistics, while acknowledging UDP and timing limitations.
