"""Packaging defaults must isolate storage without changing source-mode behavior."""
from pathlib import Path
import os
import pytest
from spitfire.frozen import absolute_path_options, prepare_user_defaults, validate_resources


def test_default_storage_is_own_user_tree_and_does_not_change_environment(tmp_path):
    before = dict(os.environ)
    args, data, session = prepare_user_defaults(['--demo'], tmp_path / 'own-app')
    assert data == (tmp_path / 'own-app').resolve()
    for option, expected in [('--config', data / 'settings/config.sp'), ('--data-dir', data / 'data'), ('--diagnostics-dir', session)]:
        assert Path(args[args.index(option) + 1]) == expected
    assert args[args.index('--backend') + 1] == 'native'
    assert session.is_relative_to(data / 'logs')
    assert not (data / 'settings/config.sp').exists()  # Do not copy C:\config.sp.
    assert dict(os.environ) == before


def test_caller_relative_overrides_are_resolved_before_private_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args, _, _ = prepare_user_defaults(['--config=chosen.sp', '--data-dir', 'data chosen', '--diagnostics-dir', 'logs chosen'], tmp_path / 'own')
    assert '--config=' + str(tmp_path / 'chosen.sp') in args
    assert args[args.index('--data-dir') + 1] == str(tmp_path / 'data chosen')
    assert args[args.index('--diagnostics-dir') + 1] == str(tmp_path / 'logs chosen')
    assert len([x for x in args if x.startswith('--config')]) == 1


def test_each_launch_has_distinct_app_log_session(tmp_path):
    _, _, a = prepare_user_defaults([], tmp_path)
    _, _, b = prepare_user_defaults([], tmp_path)
    assert a != b and a.is_dir() and b.is_dir()


def test_incomplete_payload_fails_before_shared_runtime_cache_is_considered(tmp_path):
    with pytest.raises(RuntimeError, match='Incomplete Native application payload'):
        validate_resources(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_shipped_payload_is_complete():
    validate_resources(Path(__file__).parents[1] / 'spitfire/resources')
