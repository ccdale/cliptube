#
# Copyright (c) 2023-2024, Chris Allison
#
#     This file is part of cliptube.
#
#     cliptube is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     cliptube is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cliptube.  If not, see <http://www.gnu.org/licenses/>.
#

"""test module for the cliptube.config module"""

import os

import pytest

from cliptube.config import (
    ConfigFileNotFound,
    expandPath,
    getBBCHandlingEnabled,
    getBBCPvrDirectory,
    getClipboardConfig,
    getClipboardSettings,
    getClipboardSleepTime,
    getHistoryDays,
    readConfig,
    writeConfig,
)


def test_expandPath():
    tilde = "~/"
    home = os.path.abspath(os.path.expanduser(tilde))
    assert home == expandPath(tilde)


def test_get_bbc_handling_enabled_defaults_to_true():
    import configparser

    assert getBBCHandlingEnabled(configparser.ConfigParser()) is True


def test_get_bbc_handling_enabled_reads_setting():
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"bbc": {"enabled": "false"}})

    assert getBBCHandlingEnabled(cfg) is False


def test_get_bbc_handling_enabled_rejects_invalid_value():
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"bbc": {"enabled": "maybe"}})

    with pytest.raises(ValueError, match=r"\[bbc\] enabled"):
        getBBCHandlingEnabled(cfg)


def test_get_bbc_pvr_directory_defaults_to_builtin_path():
    import configparser

    from cliptube.pvr import DEFAULT_PVR_DIRECTORY

    assert getBBCPvrDirectory(configparser.ConfigParser()) == expandPath(
        DEFAULT_PVR_DIRECTORY
    )


def test_get_bbc_pvr_directory_uses_configured_path():
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"bbc": {"pvrdir": "~/cliptube-pvr"}})

    assert getBBCPvrDirectory(cfg) == expandPath("~/cliptube-pvr")


def test_clipboard_defaults():
    import configparser

    settings = getClipboardSettings(configparser.ConfigParser())
    assert settings.backend == "gnome"
    assert settings.selection == "clipboard"
    assert settings.sleeptime == 1
    assert settings.historydays == 365
    assert getClipboardConfig(configparser.ConfigParser()) == settings


def test_clipboard_settings_and_history_retention():
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"clipboard": {
        "backend": " AUTO ", "selection": "Both", "sleeptime": "0.25", "historydays": "0"
    }})
    settings = getClipboardSettings(cfg)
    assert (settings.backend, settings.selection, settings.sleeptime) == ("auto", "both", 0.25)
    assert getHistoryDays(cfg) == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("backend", "unknown"),
        ("selection", "secondary"),
        ("sleeptime", "zero"),
        ("sleeptime", "0"),
        ("sleeptime", "-1"),
        ("sleeptime", "nan"),
        ("sleeptime", "inf"),
        ("historydays", "-1"),
        ("historydays", "1.5"),
        ("historydays", "many"),
    ],
)
def test_clipboard_settings_reject_invalid_values(key, value):
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"clipboard": {key: value}})
    with pytest.raises(ValueError, match=rf"\[clipboard\] {key}"):
        getClipboardSettings(cfg)


def test_legacy_gnome_sleeptime_validation():
    import configparser

    cfg = configparser.ConfigParser()
    assert getClipboardSleepTime(cfg, gnome=True) == 5
    cfg.read_dict({"gnomeclipindicator": {"sleeptime": "nan"}})
    with pytest.raises(ValueError, match=r"\[gnomeclipindicator\] sleeptime"):
        getClipboardSleepTime(cfg, gnome=True)


def test_readConfig(monkeypatch):
    import configparser
    from pathlib import Path

    def read_fixture(parser, filename):
        parser.read_dict({"mediaserver": {"user": "chris"}})

    monkeypatch.setattr(Path, "exists", lambda path: True)
    monkeypatch.setattr(configparser.ConfigParser, "read", read_fixture)
    cfg = readConfig()
    assert cfg["mediaserver"]["user"] == "chris"


def test_readConfig_does_not_exist(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "exists", lambda path: False)
    junkname = "does_not_existify"
    with pytest.raises(ConfigFileNotFound):
        readConfig(overrideappname=junkname)


def test_writeConfig(monkeypatch):
    import configparser
    from unittest.mock import mock_open

    cfg = configparser.ConfigParser()
    cfg.read_dict({"testsection": {"fileval": "42"}})
    mocked_open = mock_open()
    monkeypatch.setattr("builtins.open", mocked_open)
    writeConfig(cfg)
    written = "".join(call.args[0] for call in mocked_open().write.call_args_list)
    reloaded = configparser.ConfigParser()
    reloaded.read_string(written)
    assert reloaded["testsection"]["fileval"] == "42"
