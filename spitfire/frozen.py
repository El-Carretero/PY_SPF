"""Process-local defaults for the standalone Windows distribution.

This module changes no machine/user environment, network configuration, Python
installation or shared NI runtime. Source/python -m spitfire behavior is unchanged.
"""
from __future__ import annotations
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import sys
import traceback
import uuid

APP_DIRECTORY = 'PY_SPF_1.0'
APP_MUTEX = r'Local\PY_SPF.Native1_0.A772B846AB4E487BA1DD03E19D5880E9'
PATH_OPTIONS = {'--config', '--data-dir', '--diagnostics-dir', '--output', '--snapshot', '--render-dir'}
_REQUIRED = ('SPITFIRE.UIR', 'SERVER.UIR', 'gui_spec.json', 'cvi_attributes.json',
             'callback_bindings.json', 'runtime/cvirte.dll', 'runtime/cvintwrk.dll',
             'runtime/bin/cvirte.rsc', 'runtime/bin/msgrte.txt', 'runtime/bin/cvierror.txt',
             'runtime/fonts/ni7seg.ttf', 'runtime/fonts/nisystem.ttf')
_mutex_handle = None
_log_streams = []


def local_app_data():
    """Use the Windows known folder, not an inherited Python/venv setting."""
    if sys.platform != 'win32':
        raise RuntimeError('The standalone Native application requires Windows.')
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    function = shell.SHGetFolderPathW
    function.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                         ctypes.c_uint32, ctypes.c_wchar_p]
    function.restype = ctypes.c_long
    path = ctypes.create_unicode_buffer(32768)
    result = function(None, 0x1C, None, 0, path)  # CSIDL_LOCAL_APPDATA, current user
    if result < 0:
        raise OSError(result, 'Cannot locate the current user LocalAppData folder')
    return Path(path.value)


def has_option(argv, option):
    return any(value == option or value.startswith(option + '=') for value in argv)


def absolute_path_options(argv):
    """Resolve caller-relative paths before switching only this process's CWD."""
    result = list(argv)
    for index, value in enumerate(result):
        name, separator, tail = value.partition('=')
        if name not in PATH_OPTIONS:
            continue
        if separator:
            result[index] = name + '=' + str(Path(tail).expanduser().resolve())
        elif index + 1 < len(result):
            result[index + 1] = str(Path(result[index + 1]).expanduser().resolve())
    return result


def prepare_user_defaults(argv, user_data):
    """Create only this application's directories and add omitted path defaults."""
    argv = absolute_path_options(argv)
    user_data = Path(user_data).resolve()
    for folder in ('settings', 'data', 'logs'):
        (user_data / folder).mkdir(parents=True, exist_ok=True)
    session = user_data / 'logs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    session.mkdir()
    for flag, value in (('--config', user_data / 'settings' / 'config.sp'),
                        ('--data-dir', user_data / 'data'),
                        ('--diagnostics-dir', session)):
        if not has_option(argv, flag):
            argv += [flag, str(value)]
    if not has_option(argv, '--backend'):
        argv += ['--backend', 'native']
    return argv, user_data, session


def validate_resources(resources):
    """Reject incomplete packages before CVI can fall back to a shared cache."""
    resources = Path(resources)
    missing = [name for name in _REQUIRED if not (resources / name).is_file()]
    if missing:
        raise RuntimeError('Incomplete Native application payload: ' + ', '.join(missing))
    return resources


def _streams(session):
    # --windowed PyInstaller has stdout/stderr=None. CVI's required shutdown path
    # flushes both before ExitProcess, so bind valid, app-owned streams first.
    for name in ('stdout', 'stderr'):
        stream = (session / (name + '.log')).open('a', encoding='utf-8', buffering=1)
        _log_streams.append(stream)
        if getattr(sys, name) is None:
            setattr(sys, name, stream)
    # Ensure failures in native.run (which catches/prints exceptions) are visible
    # in an installed windowed process's private error log.


def _acquire_mutex():
    global _mutex_handle
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateMutexW
    create.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    create.restype = ctypes.c_void_p
    _mutex_handle = create(None, False, APP_MUTEX)
    if not _mutex_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        close = kernel.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close(_mutex_handle)
        _mutex_handle = None
        raise RuntimeError('PY_SPF 1.2 is already running. Close that instance before starting another.')


def _error_dialog(message):
    if sys.platform == 'win32':
        ctypes.WinDLL('user32').MessageBoxW(None, str(message), 'PY_SPF 1.2', 0x10)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A bounded self-test has a separate parser; its only transport is the
    # in-memory simulator, and it never calls the live entry point.
    self_test = '--self-test-native' in argv
    try:
        if sys.platform != 'win32' or struct.calcsize('P') != 4:
            raise RuntimeError('PY_SPF Native requires 32-bit Windows execution.')
        if getattr(sys, 'frozen', False):
            acp = ctypes.WinDLL('kernel32').GetACP()
            if acp != 65001:
                raise RuntimeError('PY_SPF requires Windows 10 version 1903 or newer (private UTF-8 process support).')
        data = local_app_data() / APP_DIRECTORY
        if self_test:
            # Do not add ordinary application flags to the bounded test parser.
            test_argv = absolute_path_options([a for a in argv if a != '--self-test-native'])
            _, data, session = prepare_user_defaults([], data)
        else:
            argv, data, session = prepare_user_defaults(argv, data)
        _streams(session)
        _acquire_mutex()
        from .native import RESOURCES
        validate_resources(RESOURCES)
        # Only the child process changes its inherited environment or CWD.
        # Frozen import resolution does not use a user's Python/venv install.
        for name in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONUSERBASE'):
            os.environ.pop(name, None)
        os.chdir(data)
        (session / 'launcher.json').write_text(json.dumps({
            'application': 'PY_SPF 1.2 Native', 'pid': os.getpid(),
            'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable,
            'user_data': str(data), 'session': str(session), 'mutex': APP_MUTEX,
            'self_test': self_test}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if self_test:
            from .packaged_check import main as check
            return check(test_argv, default_output=session / 'native-check.json')
        from .__main__ import arguments, main as application_main
        options = arguments(argv)
        if options.backend not in ('native', 'auto'):
            raise RuntimeError('This installer contains the Native GUI only. Use --backend native.')
        options.data_dir.mkdir(parents=True, exist_ok=True)
        return application_main(argv)
    except Exception as exc:
        traceback.print_exc()
        # Tests receive an output file/exit status rather than a blocking dialog.
        if not self_test and '--headless' not in argv:
            _error_dialog(str(exc))
        return 1
