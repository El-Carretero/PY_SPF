#!/bin/sh
set -eu
cd "$(dirname "$0")"
probe_zig=./build-tools/ziglang/zig
"$probe_zig" dlltool -m i386 -d xp_msvcrt.def -l xp_msvcrt.lib
"$probe_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra \
  -fno-builtin -nostdlib \
  -isystem ./build-tools/ziglang/lib/libc/include/any-windows-any \
  -Wl,-e,probe_entry@0 -Wl,--subsystem,console \
  -o guest_probe.exe guest_probe.c xp_msvcrt.lib \
  -lkernel32 -lws2_32 -liphlpapi -lpsapi -lgdi32 -luser32 -lshell32
python3 verify_guest_pe.py
sha256sum guest_probe.c guest_probe.exe > guest_probe.sha256
