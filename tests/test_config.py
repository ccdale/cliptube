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


def test_readConfig():
    cfg = readConfig()
    assert cfg["mediaserver"]["user"] == "chris"


def test_readConfig_does_not_exist(capsys):
    junkname = "does_not_existify"
    with pytest.raises(ConfigFileNotFound):
        readConfig(overrideappname=junkname)


def test_writeConfig():
    cfg = readConfig()
    fv = int(cfg["testsection"]["fileval"])
    fv += 1
    cfg["testsection"]["fileval"] = str(fv)
    writeConfig(cfg)
    xfv = int(readConfig()["testsection"]["fileval"])
    assert xfv == fv
