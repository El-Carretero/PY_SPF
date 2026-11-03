#!/bin/sh
set -eu
cd "$(dirname "$0")"
capture_zig=${CAPTURE_ZIG:-zig}
capture_lib=$("$capture_zig" env | python3 -c 'import json,sys;print(json.load(sys.stdin)["lib_dir"])')
mkdir -p ../bin ../build/capture
"$capture_zig" dlltool -m i386 -d capture_msvcrt.def -l ../build/capture/capture_msvcrt.lib
"$capture_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra -fno-builtin -nostdlib \
 -isystem "$capture_lib/libc/include/any-windows-any" -Wl,-e,capture_entry@0 -Wl,--subsystem,console \
 -o ../bin/passive_capture.exe passive_capture.c capture_protocol.c ../build/capture/capture_msvcrt.lib \
 -lkernel32 -lshell32 -ladvapi32
python3 verify_passive_capture.py
