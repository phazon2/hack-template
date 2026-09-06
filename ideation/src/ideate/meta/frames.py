"""Extract frames from a video so an agent can look at it.

Captions say what someone *said*; frames show what the judges actually *saw* — the opening
shot, how fast the aha lands, whether the UI reads at a glance. That is most of what makes a
demo win, and none of it is in the transcript.

This produces JPEG files and a timestamped index. It deliberately stops there: reading the
frames is the agent's job (they render as images), and the interesting judgement — what the
first five seconds communicate — is not something to bury in a helper.

``ffmpeg`` comes from the ``imageio-ffmpeg`` wheel, so the ``frames`` extra needs no system
package and no root. Nothing here reaches the network; feed it a local file that was fetched
separately.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_FRAMES = 24
DEFAULT_WIDTH = 512
# Below this a "video" is almost always an error page saved with a video extension.
MIN_VIDEO_BYTES = 10_000


class FramesToolMissing(RuntimeError):
    """The optional ``imageio-ffmpeg`` extra is not installed."""

    hint = 'pip install "ideate[frames]"'


class FrameError(RuntimeError):
    """Frame extraction failed: unreadable container, bad range, or ffmpeg refused."""


@dataclass
class Frame:
    """One extracted still and the moment it came from."""

    path: Path
    seconds: float

    @property
    def stamp(self) -> str:
        total = int(self.seconds)
        return f"{total // 60:02d}:{total % 60:02d}"


def ffmpeg_exe() -> str:
    """Path to a bundled ffmpeg binary."""
    try:
        import imageio_ffmpeg  # noqa: PLC0415 - lazy: the core must not require the extra
    except ImportError as e:
        raise FramesToolMissing("imageio-ffmpeg is not installed, so frames cannot be extracted") from e
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(path: str | Path, exe: str | None = None) -> float:
    """Duration in seconds, or 0.0 when the container does not report one."""
    binary = exe or ffmpeg_exe()
    result = subprocess.run(  # noqa: S603 - fixed binary, no shell
        [binary, "-i", str(path)], capture_output=True, text=True, check=False
    )
    for line in result.stderr.splitlines():
        if "Duration:" not in line:
            continue
        stamp = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
        try:
            hours, minutes, seconds = stamp.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except ValueError:
            return 0.0
    return 0.0


def plan_fps(duration: float, max_frames: int = DEFAULT_MAX_FRAMES) -> float:
    """Frames per second that fills the budget over ``duration`` without overshooting it.

    Every frame is an image and images dominate token cost, so the budget is the real
    constraint: a fixed fps would return four frames of a 20-second clip and four hundred of a
    conference talk.
    """
    if duration <= 0:
        return 1.0
    return max(max_frames / duration, 0.02)


def extract_frames(
    path: str | Path,
    out_dir: str | Path,
    *,
    max_frames: int = DEFAULT_MAX_FRAMES,
    start: float | None = None,
    end: float | None = None,
    width: int = DEFAULT_WIDTH,
    exe: str | None = None,
) -> list[Frame]:
    """Sample evenly spaced frames from ``path`` into ``out_dir``, newest budget first."""
    source = Path(path)
    if not source.is_file():
        raise FrameError(f"no such video file: {source}")
    if source.stat().st_size < MIN_VIDEO_BYTES:
        raise FrameError(f"{source} is too small to be a video ({source.stat().st_size} bytes)")
    if start is not None and end is not None and end <= start:
        raise FrameError(f"end ({end}s) must be after start ({start}s)")

    binary = exe or ffmpeg_exe()
    duration = probe_duration(source, binary)
    window = duration
    if start is not None or end is not None:
        window = (end if end is not None else duration) - (start or 0.0)
    fps = plan_fps(window, max_frames)

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    for stale in target.glob("frame_*.jpg"):
        stale.unlink()

    command = [binary, "-hide_banner", "-loglevel", "error"]
    if start is not None:
        command += ["-ss", str(start)]
    if end is not None:
        command += ["-to", str(end)]
    command += [
        "-i", str(source),
        "-vf", f"fps={fps:.6f},scale={width}:-2",
        "-frames:v", str(max_frames),
        "-q:v", "3",
        str(target / "frame_%03d.jpg"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    frames = sorted(target.glob("frame_*.jpg"))
    if not frames:
        detail = (result.stderr or "").strip().splitlines()
        raise FrameError(f"ffmpeg produced no frames: {detail[-1] if detail else 'no error reported'}")
    offset = start or 0.0
    return [Frame(path=p, seconds=offset + i / fps) for i, p in enumerate(frames)]


def render_index(frames: list[Frame], title: str = "") -> str:
    """A listing an agent can act on: one line per frame, with the moment it shows."""
    header = f"{len(frames)} frame(s)" + (f" from {title}" if title else "")
    lines = [f"{header}. Read them in order; each is a still at that timestamp.", ""]
    lines += [f"[{frame.stamp}] {frame.path}" for frame in frames]
    return "\n".join(lines)
