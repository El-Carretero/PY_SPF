"""Load the standalone NI typefaces in process-private memory.

The legacy runtime calls AddFontResourceA on its adjacent font paths. Those
paths contain deliberately invalid, identified placeholders in this package;
the original TTF bytes are loaded here instead, without a Windows session-wide
font registration or a persistent font-file lock.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path

FONT_PLACEHOLDER = b'PY_SPF: this typeface is supplied by the process-private memory font loader.\r\n'
FONT_FACES = {'ni7seg.ttf': 'NI7SEG', 'nisystem.ttf': 'NISYSTEM'}


class PrivateNativeFonts:
    def __init__(self, originals, adjacent):
        originals, adjacent = Path(originals), Path(adjacent)
        self.gdi = C.WinDLL('gdi32', use_last_error=True)
        self.gdi.AddFontMemResourceEx.argtypes = [C.c_void_p, W.DWORD, C.c_void_p, C.POINTER(W.DWORD)]
        self.gdi.AddFontMemResourceEx.restype = W.HANDLE
        self.gdi.RemoveFontMemResourceEx.argtypes = [W.HANDLE]
        self.gdi.RemoveFontMemResourceEx.restype = W.BOOL
        self.handles = []
        self.records = []
        try:
            for name, family in FONT_FACES.items():
                if (adjacent / name).read_bytes() != FONT_PLACEHOLDER:
                    raise RuntimeError('Unexpected adjacent NI font placeholder; reinstall PY_SPF.')
                raw = (originals / name).read_bytes()
                buffer = C.create_string_buffer(raw)
                count = W.DWORD()
                handle = self.gdi.AddFontMemResourceEx(buffer, len(raw), None, C.byref(count))
                if not handle or count.value < 1:
                    raise RuntimeError('Cannot load the private NI typeface: ' + name)
                self.handles.append(handle)
                self.records.append({'file': name, 'family': family, 'faces_loaded': count.value,
                                     'sha256': hashlib.sha256(raw).hexdigest()})
        except BaseException:
            self.close()
            raise

    def verify(self):
        """Select each requested face and verify the actual GDI font bytes."""
        gdi = self.gdi
        gdi.CreateCompatibleDC.argtypes = [W.HDC]
        gdi.CreateCompatibleDC.restype = W.HDC
        gdi.CreateFontW.argtypes = [C.c_int] * 5 + [W.DWORD] * 8 + [W.LPCWSTR]
        gdi.CreateFontW.restype = W.HFONT
        gdi.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
        gdi.SelectObject.restype = W.HGDIOBJ
        gdi.GetTextFaceW.argtypes = [W.HDC, C.c_int, W.LPWSTR]
        gdi.GetTextFaceW.restype = C.c_int
        gdi.GetFontData.argtypes = [W.HDC, W.DWORD, W.DWORD, C.c_void_p, W.DWORD]
        gdi.GetFontData.restype = W.DWORD
        gdi.DeleteObject.argtypes = [W.HGDIOBJ]
        gdi.DeleteDC.argtypes = [W.HDC]
        result = []
        for row in self.records:
            dc = gdi.CreateCompatibleDC(None)
            font = gdi.CreateFontW(-16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, row['family'])
            if not dc or not font:
                if font:
                    gdi.DeleteObject(font)
                if dc:
                    gdi.DeleteDC(dc)
                raise RuntimeError('Cannot select private NI font for validation.')
            old = gdi.SelectObject(dc, font)
            try:
                face = C.create_unicode_buffer(256)
                if not gdi.GetTextFaceW(dc, len(face), face):
                    raise RuntimeError('Cannot read selected NI font face.')
                size = gdi.GetFontData(dc, 0, 0, None, 0)
                if size in (0, 0xFFFFFFFF) or size > 1024 * 1024:
                    raise RuntimeError('Cannot read selected NI font data.')
                data = C.create_string_buffer(size)
                if gdi.GetFontData(dc, 0, 0, data, size) != size:
                    raise RuntimeError('Incomplete selected NI font data.')
                digest = hashlib.sha256(data.raw).hexdigest()
                if face.value.casefold() != row['family'].casefold() or digest != row['sha256']:
                    raise RuntimeError('GDI substituted a different NI typeface: ' + row['family'])
                result.append({**row, 'selected_face': face.value, 'selected_font_sha256': digest})
            finally:
                if old:
                    gdi.SelectObject(dc, old)
                gdi.DeleteObject(font)
                gdi.DeleteDC(dc)
        return result

    def close(self):
        for handle in reversed(self.handles):
            self.gdi.RemoveFontMemResourceEx(handle)
        self.handles.clear()
