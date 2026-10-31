"""Native preconditions and resource handling; no NI library is loaded."""
from types import SimpleNamespace

import pytest

from spitfire import native


@pytest.mark.parametrize(('platform', 'pointer_bytes'), [('linux', 4), ('win32', 8)])
def test_unsupported_platform_or_architecture_fails_before_loading_dll(monkeypatch, platform, pointer_bytes):
    monkeypatch.setattr(native, 'sys', SimpleNamespace(platform=platform))
    monkeypatch.setattr(native, 'struct', SimpleNamespace(calcsize=lambda _: pointer_bytes))
    def forbidden(*args, **kwargs):
        pytest.fail('Native runtime loading must not be reached')
    monkeypatch.setattr(native, '_prepare_runtime', forbidden)
    with pytest.raises(RuntimeError, match='32-bit Windows Python'):
        native.NativeGui()


def test_resource_preparation_without_any_ni_dll(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    monkeypatch.setattr(native, 'RESOURCES', tmp_path)
    assert native._prepare_runtime() == runtime
    assert (runtime / 'bin').is_dir()
    assert (runtime / 'fonts').is_dir()
    assert not list(runtime.rglob('*.dll'))
