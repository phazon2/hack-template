"""Frame extraction: what the judges saw, not what the presenter said.

The extractor shells out to ffmpeg, so the tests either inject a fake binary path or generate
a real two-second clip with ffmpeg itself and check the frames that come back. Nothing here
touches the network.
"""

from __future__ import annotations

import subprocess

import pytest

from ideate.meta.frames import (
    DEFAULT_MAX_FRAMES,
    Frame,
    FrameError,
    FramesToolMissing,
    extract_frames,
    ffmpeg_exe,
    plan_fps,
    probe_duration,
    render_index,
)

ffmpeg = pytest.importorskip("imageio_ffmpeg", reason="the frames extra is not installed")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A real two-second test clip, so extraction is exercised against actual video."""
    path = tmp_path_factory.mktemp("clip") / "test.mp4"
    subprocess.run(
        [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


# --------------------------------------------------------------------------- budget
def test_fps_fills_the_budget_rather_than_being_fixed():
    """Images dominate token cost, so the frame budget is the constraint, not a fixed rate."""
    assert plan_fps(24, max_frames=24) == pytest.approx(1.0)
    assert plan_fps(600, max_frames=24) == pytest.approx(0.04)  # a 10-minute talk stays in budget
    assert plan_fps(2, max_frames=24) == pytest.approx(12.0)  # a 2-second clip gets dense coverage


def test_fps_has_a_floor_so_a_very_long_video_still_yields_frames():
    assert plan_fps(100_000, max_frames=24) == 0.02


def test_unknown_duration_falls_back_to_one_per_second():
    assert plan_fps(0) == 1.0


# --------------------------------------------------------------------------- extraction
def test_frames_are_extracted_with_timestamps(clip, tmp_path):
    frames = extract_frames(clip, tmp_path / "out", max_frames=4)
    assert 1 <= len(frames) <= 4
    assert all(f.path.exists() and f.path.stat().st_size > 0 for f in frames)
    assert [f.seconds for f in frames] == sorted(f.seconds for f in frames)
    assert frames[0].stamp == "00:00"


def test_a_window_shifts_the_timestamps_to_real_positions(clip, tmp_path):
    """A frame from a --start window must report where it is in the video, not in the window."""
    frames = extract_frames(clip, tmp_path / "out", max_frames=3, start=1.0)
    assert frames and frames[0].seconds >= 1.0


def test_extraction_clears_frames_from_a_previous_run(clip, tmp_path):
    out = tmp_path / "out"
    first = extract_frames(clip, out, max_frames=8)
    second = extract_frames(clip, out, max_frames=2)
    assert len(second) <= 2
    assert len(list(out.glob("frame_*.jpg"))) == len(second) < len(first)


def test_probe_reads_the_duration(clip):
    assert probe_duration(clip) == pytest.approx(2.0, abs=0.5)


# --------------------------------------------------------------------------- refusals
def test_a_missing_file_is_named(tmp_path):
    with pytest.raises(FrameError, match="no such video file"):
        extract_frames(tmp_path / "absent.mp4", tmp_path / "out")


def test_a_tiny_file_is_rejected_as_not_a_video(tmp_path):
    """A saved error page with a .mp4 name is the common case; say so instead of failing in ffmpeg."""
    fake = tmp_path / "v.mp4"
    fake.write_bytes(b"<html>404</html>")
    with pytest.raises(FrameError, match="too small to be a video"):
        extract_frames(fake, tmp_path / "out")


def test_a_backwards_window_is_rejected_before_ffmpeg_runs(clip, tmp_path):
    with pytest.raises(FrameError, match="must be after start"):
        extract_frames(clip, tmp_path / "out", start=5.0, end=2.0)


def test_an_unreadable_container_reports_ffmpeg_rather_than_an_empty_list(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00" * 20_000)  # big enough to pass the size gate, not a video
    with pytest.raises(FrameError, match="no frames"):
        extract_frames(broken, tmp_path / "out")


def test_missing_extra_names_what_to_install(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    with pytest.raises(FramesToolMissing) as excinfo:
        ffmpeg_exe()
    assert "ideate[frames]" in excinfo.value.hint


# --------------------------------------------------------------------------- index
def test_the_index_tells_an_agent_what_to_do_with_the_frames(tmp_path):
    frames = [Frame(path=tmp_path / "frame_001.jpg", seconds=0.0), Frame(path=tmp_path / "frame_002.jpg", seconds=95.0)]
    text = render_index(frames, "demo.mp4")
    assert "2 frame(s) from demo.mp4" in text
    assert "Read them in order" in text
    assert "[01:35]" in text  # minutes roll over


def test_default_budget_is_stated_once():
    assert DEFAULT_MAX_FRAMES == 24
