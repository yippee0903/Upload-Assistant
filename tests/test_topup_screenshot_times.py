# When tracker images are reused but more captures are needed, the extra
# timestamps must not land on the tool's own deterministic grid (start at 5%,
# even spacing for meta["screens"]), which is what the source upload most
# likely used: otherwise the top-up duplicates the reused frames.

import asyncio
from typing import Any

from src.takescreens import valid_ss_time

LENGTH, FPS, SCREENS = 2700.0, 24.0, 6


def _times(existing: int, num_screens: int) -> list[float]:
    meta: dict[str, Any] = {
        "is_disc": None,
        "category": "TV",
        "debug": False,
        "screens": SCREENS,
        "image_list": [{"img_url": f"https://img.example/{i}.png"} for i in range(existing)],
    }
    return sorted(float(t) for t in asyncio.run(valid_ss_time([], num_screens, LENGTH, FPS, meta)))


def test_full_grid_unchanged_without_reused_images() -> None:
    total_frames = int(LENGTH * FPS)
    start, end = int(total_frames * 0.05), int(total_frames * 0.9)
    interval = (end - start) // SCREENS
    assert _times(0, SCREENS) == [(start + i * interval) / FPS for i in range(SCREENS)]


def test_topup_sits_between_base_grid_points() -> None:
    base = _times(0, SCREENS)
    base_step = base[1] - base[0]
    for needed in (1, 2, 3, 4):
        topup = _times(SCREENS - needed, needed)
        assert len(topup) == needed
        for t in topup:
            assert min(abs(t - b) for b in base) >= 0.35 * base_step, (needed, t, base)
        assert min(topup) > base[0] and max(topup) < base[-1] + base_step
