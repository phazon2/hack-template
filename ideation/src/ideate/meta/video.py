"""Pull a video's transcript into the corpus as cited evidence.

A recorded hackathon pitch is primary evidence about what actually won: what the team led with,
how fast the demo landed, what they cut. The corpus already accepts `kind: evidence` with a
required source, so a transcript slots in beside a fetched paper with the video URL as its
citation.

Only captions are read — no audio, no frames, so no ffmpeg and no transcription key. That keeps
this cheap enough to run over a playlist. For what a demo *looks* like, frames matter more than
words, and the `/watch` plugin (github.com/bradautomates/claude-video) is the better tool: it is
interactive, reads frames as images, and needs ffmpeg. The two are complements — this one feeds
retrieval, that one feeds judgement, and anything learned from `/watch` belongs in `ideate note`.

``yt-dlp`` is an optional extra imported lazily: it is used only to resolve metadata and the
caption track URL. The caption body is fetched through the same injectable opener as every other
fetch, so the tests run without a network.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from ideate.meta.fetch import FetchError, FetchedDoc, Opener, http_opener
from ideate.models import slug

CAPTION_FORMAT = "json3"
# YouTube rate-limits datacenter IPs and answers with a bot check that clears on a retry.
RETRYABLE = ("sign in to confirm", "too many requests", "429", "temporarily unavailable")
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 5.0
MAX_TRANSCRIPT_CHARS = 40000
# A caption cue every ~15s reads as a transcript; denser stamping just burns tokens.
STAMP_EVERY_SECONDS = 15

Extractor = Callable[[str], dict]


class VideoToolMissing(RuntimeError):
    """The optional ``yt-dlp`` extra is not installed."""

    hint = 'pip install "ideate[video]"'


def ytdlp_extractor(sleep: Callable[[float], None] | None = time.sleep) -> Extractor:
    """An extractor backed by yt-dlp, retrying the bot check that rate-limited IPs get.

    Importing yt-dlp is what needs the optional extra. ``sleep`` is injectable so a test can
    exercise the retry ladder without waiting; pass ``None`` to disable backoff entirely.
    """
    try:
        import yt_dlp  # noqa: PLC0415 - lazy: the core must not require the extra
    except ImportError as e:
        raise VideoToolMissing("yt-dlp is not installed, so videos cannot be read") from e

    def _extract(url: str) -> dict:
        options = {"skip_download": True, "quiet": True, "no_warnings": True}
        last = ""
        for attempt in range(MAX_ATTEMPTS):
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:  # yt-dlp raises its own family; only the reason matters here
                last = str(e)
                if not any(marker in last.lower() for marker in RETRYABLE):
                    raise FetchError(f"could not read {url}: {last}") from e
                if attempt == MAX_ATTEMPTS - 1:
                    raise FetchError(
                        f"{url} is rate-limited after {MAX_ATTEMPTS} attempts: {last}"
                    ) from e
                if sleep is not None:
                    sleep(BACKOFF_SECONDS * (attempt + 1))
                continue
            if not isinstance(info, dict):
                raise FetchError(f"no video metadata at {url}")
            if info.get("_type") == "playlist":
                raise FetchError("that URL is a playlist; pass a single video URL")
            return info
        raise FetchError(f"could not read {url}: {last}")  # pragma: no cover - loop always returns

    return _extract


def caption_url(info: dict, lang: str = "en") -> str:
    """The best caption track URL: a human-written track if there is one, else auto-generated.

    Manual captions are what the speaker or channel actually wrote, so they beat ASR on names,
    product terms and punctuation — exactly the parts of a pitch worth quoting.
    """
    for source in ("subtitles", "automatic_captions"):
        tracks_by_lang = info.get(source) or {}
        for key in (lang, f"{lang}-orig", *(k for k in tracks_by_lang if k.startswith(lang))):
            for track in tracks_by_lang.get(key) or []:
                if track.get("ext") == CAPTION_FORMAT and track.get("url"):
                    return str(track["url"])
    available = sorted({*(info.get("subtitles") or {}), *(info.get("automatic_captions") or {})})
    raise FetchError(
        f"no {lang!r} captions for this video"
        + (f" (available: {', '.join(available[:8])})" if available else " (it has none at all)")
    )


def parse_json3(payload: bytes) -> str:
    """A json3 caption track as timestamped plain text."""
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise FetchError(f"caption track was not valid json3: {e}") from e
    lines: list[str] = []
    last_stamp = -STAMP_EVERY_SECONDS
    for event in data.get("events") or []:
        text = "".join(seg.get("utf8", "") for seg in event.get("segs") or []).strip()
        if not text or text == "[Music]":
            continue
        seconds = int(event.get("tStartMs", 0)) // 1000
        if seconds - last_stamp >= STAMP_EVERY_SECONDS:
            lines.append(f"\n[{seconds // 60:02d}:{seconds % 60:02d}] {text}")
            last_stamp = seconds
        else:
            lines.append(text)
    transcript = " ".join(lines).replace(" \n", "\n").strip()
    if not transcript:
        raise FetchError("caption track was empty")
    return transcript


def _tags(info: dict) -> list[str]:
    tags = ["video"]
    channel = info.get("channel") or info.get("uploader")
    if channel:
        tags.append(slug(str(channel)))
    for category in (info.get("categories") or [])[:2]:
        tags.append(slug(str(category)))
    return [t for t in dict.fromkeys(tags) if t]


def fetch_transcript(
    url: str,
    lang: str = "en",
    extractor: Extractor | None = None,
    opener: Opener | None = None,
) -> FetchedDoc:
    """Fetch one video's captions as a document ready for the corpus."""
    info = (extractor or ytdlp_extractor())(url)
    body = (opener or http_opener())(caption_url(info, lang))
    transcript = parse_json3(body)[:MAX_TRANSCRIPT_CHARS]

    title = str(info.get("title") or "Untitled video")
    channel = str(info.get("channel") or info.get("uploader") or "")
    duration = int(info.get("duration") or 0)
    upload = str(info.get("upload_date") or "")
    published = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    header = f"{title}" + (f" — {channel}" if channel else "")
    if duration:
        header += f" ({duration // 60}m{duration % 60:02d}s)"

    video_id = str(info.get("id") or slug(url))
    return FetchedDoc(
        id=f"video-{slug(video_id)}",
        title=title,
        text=f"{header}\n\nTranscript:\n{transcript}",
        url=str(info.get("webpage_url") or url),
        authors=[channel] if channel else [],
        published=published,
        tags=_tags(info),
    )
