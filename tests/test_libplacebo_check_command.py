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


# ffmpeg exits 0 with libplacebo on a CPU Vulkan device (llvmpipe/lavapipe) but the
# dithering pass renders horizontal stripes, so the probe must refuse it and keep the
# zscale fallback. A software device merely listed next to a real GPU is fine.
GPU_LISTING = b"[AVHWDeviceContext @ 0x1] GPU listing:\n    0: Some GPU (discrete) (0x1234)\n    1: llvmpipe (LLVM 19.1.7, 256 bits) (software) (0x0)\n"


@pytest.mark.parametrize(
    "selected, expected",
    [
        (b"[AVHWDeviceContext @ 0x1] Device 1 selected: llvmpipe (LLVM 19.1.7, 256 bits) (software) (0x0)\n", (False, True)),
        (b"[AVHWDeviceContext @ 0x1] Device 0 selected: Some GPU (discrete) (0x1234)\n", (True, True)),
    ],
)
def test_libplacebo_check_refuses_a_software_vulkan_device(monkeypatch: pytest.MonkeyPatch, tmp_path, selected: bytes, expected: tuple[bool, bool]) -> None:
    async def fake_run_ffmpeg(command: Any):
        args = [str(a) for a in command.compile()]
        return 0, b"", GPU_LISTING + selected if "vulkan" in args else b""

    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    meta: dict[str, Any] = {"debug": False, "is_disc": None}
    result = asyncio.run(takescreens.check_libplacebo_compatibility(1, 1, 1920, 1080, "/nonexistent/example.mkv", "10", str(tmp_path / "shot.png"), "quiet", meta))
    assert result == expected
