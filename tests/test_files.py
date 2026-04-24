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
import tempfile
from unittest.mock import patch

from cliptube.config import expandPath
from cliptube.files import dirFileList, getOutputDirectory, getOutputFileName, homeDir


def test_homeDir():
    homed = homeDir()
    tilde = "~/"
    assert expandPath(tilde) == homed


def test_getOutputFileName():
    cfg = {
        "youtube": {
            "filenumber": "5",
            "videodir": "/mnt/nas/youtube/subs",
            "playlistdir": "/mnt/nas/youtube/playlists",
            "iplayerdir": "/mnt/nas/youtube/iplayer",
        },
        "iplayer": {
            "iplayerdir": "/mnt/nas/youtube/iplayer",
        },
    }
    with patch("cliptube.files.writeConfig") as mock_write:
        ofn = getOutputFileName(cfg, vtype="v")
        assert ofn == f"{expandPath('/mnt/nas/youtube/subs')}/05"
        ofn = getOutputFileName(cfg, vtype="p")
        assert ofn == f"{expandPath('/mnt/nas/youtube/playlists')}/06"
        ofn = getOutputFileName(cfg, vtype="i")
        assert ofn == f"{expandPath('/mnt/nas/youtube/iplayer')}/07"
        assert cfg["youtube"]["filenumber"] == "8"
        assert mock_write.call_count == 3


def test_getOutputDirectory():
    cfg = {
        "youtube": {
            "videodir": "/mnt/nas/youtube/subs",
            "playlistdir": "/mnt/nas/youtube/playlists",
            "iplayerdir": "/mnt/nas/youtube/iplayer",
        },
        "iplayer": {
            "iplayerdir": "/mnt/nas/youtube/iplayer",
        },
    }
    assert getOutputDirectory(cfg, vtype="v") == expandPath("/mnt/nas/youtube/subs")
    assert getOutputDirectory(cfg, vtype="p") == expandPath(
        "/mnt/nas/youtube/playlists"
    )
    assert getOutputDirectory(cfg, vtype="i") == expandPath("/mnt/nas/youtube/iplayer")


def test_dirFileList():
    with tempfile.TemporaryDirectory() as tmpd:
        # path = expandPath("~/.testme")
        # os.mkdir(path)
        with open("/".join([tmpd, "testfile"]), "w") as f:
            f.write("test")
        with open("/".join([tmpd, "test.err"]), "w") as f:
            f.write("test")
        fns = dirFileList(tmpd)
        assert len(fns) == 2
        assert "testfile" in fns
        assert "test.err" in fns
        fns = dirFileList(tmpd, filterext="err")
        assert len(fns) == 1
        assert "test.err" not in fns
        assert "testfile" in fns
        # os.remove("/".join([path, "testfile"]))
        # os.remove("/".join([path, "test.err"]))
        # os.rmdir(path)
