# The libplacebo compatibility check maps a labelled filtergraph output:
# "-map [out]" is an output option and must come before the output file,
# otherwise ffmpeg reports the filter output unconnected and the check
# always fails, silently disabling libplacebo tonemapping.

import asyncio
from typing import Any

import pytest

from src import takescreens


def test_libplacebo_check_maps_the_filter_output_before_the_output_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    commands: list[list[str]] = []

    async def fake_run_ffmpeg(command: Any):
        commands.append([str(a) for a in command.compile()])
        return 0, b"", b""

    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    out = str(tmp_path / "shot_test.png")
    meta: dict[str, Any] = {"debug": False, "is_disc": None}
    asyncio.run(takescreens.check_libplacebo_compatibility(1, 1, 1920, 1080, "/nonexistent/example.mkv", "10", str(tmp_path / "shot.png"), "quiet", meta))
    cmd = next(c for c in commands if any("libplacebo=" in a for a in c))
    assert "-map" in cmd and cmd.index("-map") < cmd.index(out)
    assert cmd[cmd.index("-map") + 1] == "[out]"
