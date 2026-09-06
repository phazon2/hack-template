"""Video transcripts as corpus evidence.

A recorded winning pitch is primary evidence, so it goes through the same attribution path as
a fetched paper. Every test injects the extractor and the opener: nothing here touches YouTube.
"""

from __future__ import annotations

import json

import pytest

from ideate.meta.fetch import FetchError
from ideate.meta.video import (
    MAX_ATTEMPTS,
    caption_url,
    fetch_transcript,
    parse_json3,
    ytdlp_extractor,
)

CAPTION_URL = "https://youtube.example/api/timedtext?v=abc&fmt=json3"

INFO = {
    "id": "abc123",
    "title": "How we won the AI hackathon",
    "channel": "Some Builder",
    "upload_date": "20250114",
    "duration": 512,
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "categories": ["Science & Technology"],
    "subtitles": {"en": [{"ext": "vtt", "url": "x"}, {"ext": "json3", "url": CAPTION_URL}]},
    "automatic_captions": {"en": [{"ext": "json3", "url": "https://auto.example/track"}]},
}


def _track(*cues: tuple[int, str]) -> bytes:
    return json.dumps(
        {"events": [{"tStartMs": ms, "segs": [{"utf8": text}]} for ms, text in cues]}
    ).encode()


# --------------------------------------------------------------------------- caption selection
def test_manual_captions_beat_auto_generated():
    """A human-written track gets names and product terms right; ASR does not."""
    assert caption_url(INFO) == CAPTION_URL


def test_auto_captions_are_used_when_there_is_no_manual_track():
    info = {**INFO, "subtitles": {}}
    assert caption_url(info) == "https://auto.example/track"


def test_a_regional_variant_still_matches_the_language():
    info = {"subtitles": {"en-GB": [{"ext": "json3", "url": "https://gb.example/t"}]}}
    assert caption_url(info, "en") == "https://gb.example/t"


def test_missing_captions_name_what_is_available():
    info = {"subtitles": {"fr": [{"ext": "json3", "url": "x"}]}, "automatic_captions": {}}
    with pytest.raises(FetchError, match="available: fr"):
        caption_url(info, "en")
    with pytest.raises(FetchError, match="none at all"):
        caption_url({}, "en")


# --------------------------------------------------------------------------- transcript parsing
def test_transcript_is_stamped_periodically_not_per_cue():
    """A stamp every cue would triple the tokens for no extra meaning."""
    text = parse_json3(_track((0, "We opened with"), (3000, "the demo"), (20000, "Then the pitch")))
    assert text.startswith("[00:00] We opened with the demo")
    assert "[00:20] Then the pitch" in text
    assert text.count("[") == 2


def test_transcript_drops_music_markers_and_empty_cues():
    text = parse_json3(_track((0, "[Music]"), (1000, ""), (2000, "Real words")))
    assert "[Music]" not in text and "Real words" in text


def test_minutes_roll_over_correctly():
    assert "[02:05]" in parse_json3(_track((125000, "later in the talk")))


def test_an_empty_or_broken_track_is_an_error_not_an_empty_document():
    with pytest.raises(FetchError, match="empty"):
        parse_json3(_track())
    with pytest.raises(FetchError, match="json3"):
        parse_json3(b"not json")


# --------------------------------------------------------------------------- document assembly
def test_transcript_becomes_an_attributed_document():
    doc = fetch_transcript(
        "https://youtu.be/abc123",
        extractor=lambda _: INFO,
        opener=lambda url: _track((0, "First place out of 100 teams")) if url == CAPTION_URL else b"{}",
    )
    assert doc.id == "video-abc123"
    assert doc.title == "How we won the AI hackathon"
    assert doc.url == "https://www.youtube.com/watch?v=abc123"  # the citation
    assert doc.authors == ["Some Builder"]
    assert doc.published == "2025-01-14"
    assert "video" in doc.tags and "some-builder" in doc.tags
    assert "8m32s" in doc.text  # duration is in the header, so a reader knows the scale
    assert "First place out of 100 teams" in doc.text


def test_a_video_without_a_channel_or_date_still_produces_a_document():
    info = {"id": "x1", "title": "Untitled", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    doc = fetch_transcript("https://youtu.be/x1", extractor=lambda _: info, opener=lambda _: _track((0, "hi")))
    assert doc.authors == [] and doc.published == ""
    assert doc.url == "https://youtu.be/x1"


def test_written_transcript_carries_the_video_url_as_its_source(tmp_path):
    from ideate.knowledge.loaders import load_corpus
    from ideate.meta.fetch import write_docs

    doc = fetch_transcript(
        "https://youtu.be/abc123", extractor=lambda _: INFO, opener=lambda _: _track((0, "won"))
    )
    write_docs([doc], tmp_path / "fetched", "2026-09-06T00:00:00+00:00")
    loaded = load_corpus([tmp_path / "fetched"])
    assert len(loaded) == 1
    assert loaded[0].metadata["kind"] == "evidence"
    assert loaded[0].source == "https://www.youtube.com/watch?v=abc123"


# --------------------------------------------------------------------------- rate limiting
class _FakeYtdlp:
    """Stands in for the yt_dlp module, failing a set number of times first."""

    def __init__(self, failures: int, message: str, result: dict | None = None):
        self.remaining = failures
        self.message = message
        self.result = result if result is not None else INFO
        self.attempts = 0

    def YoutubeDL(self, options):  # noqa: N802 - mirrors the real module's name
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise RuntimeError(self.message)
        return self.result


def _extractor_with(fake, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", fake)
    return ytdlp_extractor(sleep=None)


def test_the_bot_check_is_retried_because_it_clears(monkeypatch):
    """YouTube rate-limits datacenter IPs; the same request succeeds moments later."""
    fake = _FakeYtdlp(2, "ERROR: Sign in to confirm you're not a bot")
    info = _extractor_with(fake, monkeypatch)("https://youtu.be/abc123")
    assert info["id"] == "abc123" and fake.attempts == 3


def test_a_persistent_rate_limit_is_reported_as_such(monkeypatch):
    fake = _FakeYtdlp(99, "ERROR: HTTP Error 429: Too Many Requests")
    with pytest.raises(FetchError, match="rate-limited after"):
        _extractor_with(fake, monkeypatch)("https://youtu.be/abc123")
    assert fake.attempts == MAX_ATTEMPTS


def test_a_real_failure_is_not_retried(monkeypatch):
    """Retrying a private or deleted video wastes four requests and still fails."""
    fake = _FakeYtdlp(99, "ERROR: Private video. Sign in if you've been granted access")
    with pytest.raises(FetchError, match="could not read"):
        _extractor_with(fake, monkeypatch)("https://youtu.be/abc123")
    assert fake.attempts == 1


def test_a_playlist_url_is_rejected_with_a_useful_message(monkeypatch):
    fake = _FakeYtdlp(0, "", result={"_type": "playlist", "entries": []})
    with pytest.raises(FetchError, match="playlist"):
        _extractor_with(fake, monkeypatch)("https://youtube.com/playlist?list=x")


def test_missing_yt_dlp_names_the_extra_to_install(monkeypatch):
    from ideate.meta.video import VideoToolMissing

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", None)
    with pytest.raises(VideoToolMissing) as excinfo:
        ytdlp_extractor()
    assert 'ideate[video]' in excinfo.value.hint
