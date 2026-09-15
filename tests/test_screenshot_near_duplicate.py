# Top-up captures must not repeat the reused tracker images, whatever grid
# the source used: a capture whose perceptual hash is close to one of the
# reused images (already downloaded in tmp/<run>/) is retaken.

from pathlib import Path

from PIL import Image

from src.takescreens import near_duplicate, reused_image_hashes


def _gradient(path: Path, shift: int = 0, flip: bool = False) -> Path:
    img = Image.frombytes("L", (64, 36), bytes(((x + shift) * 4 + y * 2) % 256 for y in range(36) for x in range(64)))
    if flip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    img.save(path)
    return path


def test_same_frame_recompressed_is_a_duplicate(tmp_path: Path) -> None:
    reused = _gradient(tmp_path / "reused.png")
    capture = _gradient(tmp_path / "capture.png", shift=1)
    assert near_duplicate(str(capture), reused_image_hashes([str(reused)]))


def test_different_frame_is_not_a_duplicate(tmp_path: Path) -> None:
    reused = _gradient(tmp_path / "reused.png")
    capture = _gradient(tmp_path / "capture.png", flip=True)
    assert not near_duplicate(str(capture), reused_image_hashes([str(reused)]))


def test_missing_reused_files_are_skipped(tmp_path: Path) -> None:
    assert reused_image_hashes([str(tmp_path / "gone.png")]) == []
    assert not near_duplicate(str(_gradient(tmp_path / "c.png")), [])
