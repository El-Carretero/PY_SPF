#!/bin/sh
set -eu
cd "$(dirname "$0")"
driver_zig=${DRIVER_ZIG:-zig}
driver_zig_lib=$("$driver_zig" env | python3 -c 'import json,sys; print(json.load(sys.stdin)["lib_dir"])')
"$driver_zig" dlltool -m i386 -d xp_msvcrt.def -l xp_msvcrt.lib
"$driver_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra -fno-builtin -nostdlib \
 -isystem "$driver_zig_lib/libc/include/any-windows-any" \
 -Wl,-e,probe_entry@0 -Wl,--subsystem,console -o guest_driver.exe guest_driver.c xp_msvcrt.lib \
 -lkernel32 -lws2_32 -liphlpapi -lpsapi -lgdi32 -luser32 -lshell32 -ladvapi32
python3 verify_guest_driver.py
sha256sum guest_driver.c guest_driver.exe > guest_driver.sha256
