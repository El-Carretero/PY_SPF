#!/bin/sh
set -eu
cd "$(dirname "$0")"
provision_zig=${DRIVER_ZIG:-zig}
provision_zig_lib=$("$provision_zig" env | python3 -c 'import json,sys; print(json.load(sys.stdin)["lib_dir"])')
mkdir -p ../bin ../build
"$provision_zig" dlltool -m i386 -d provision_msvcrt.def -l ../build/provision_msvcrt.lib
"$provision_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra -fno-builtin -nostdlib \
 -isystem "$provision_zig_lib/libc/include/any-windows-any" \
 -Wl,-e,provision_entry@0 -Wl,--subsystem,windows -Wl,--major-os-version,5 -Wl,--minor-os-version,1 \
 -Wl,--major-subsystem-version,5 -Wl,--minor-subsystem-version,1 \
 -o ../bin/provision_winpcap.exe provision_winpcap.c ../build/provision_msvcrt.lib \
 -lkernel32 -luser32 -lshell32 -ladvapi32
