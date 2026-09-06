"""Discover hackathon galleries and read their winners.

A submission gallery with winners labelled is the best evidence this system can get: the same
event, the same judges, the same rules, with the outcome attached. Everything else — advice
videos, papers, our own reasoning — is a claim about what wins. A gallery is a record of what
did.

Devpost exposes a public JSON index of events, so galleries can be found rather than supplied.
The catch is yield: most events that have *ended* have not yet *announced*, and an unannounced
gallery carries no labels. Sweeping is therefore cheap per event and low-hit; a link to a known
announced event is worth many sweeps.

Only public listing pages are read, one request per event, with the shared opener. Nothing here
logs in, and no page behind an account is touched.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field

from ideate.meta.fetch import FetchError, FetchedDoc, Opener, http_opener
from ideate.models import slug

DEVPOST_API = "https://devpost.com/api/hackathons"
WINNER_LABEL = "Winner"
GALLERY_PATH = "/project-gallery"
# Below this a gallery page is a shell: the listing never rendered, so there is nothing to read.
MIN_GALLERY_CHARS = 800


@dataclass
class Submission:
    """One project as its gallery lists it."""

    name: str
    tagline: str
    won: bool


@dataclass
class Gallery:
    """A hackathon's submission gallery, with winners separated."""

    title: str
    url: str
    submissions: list[Submission] = field(default_factory=list)

    @property
    def winners(self) -> list[Submission]:
        return [s for s in self.submissions if s.won]

    @property
    def others(self) -> list[Submission]:
        return [s for s in self.submissions if not s.won]

    @property
    def has_outcomes(self) -> bool:
        return bool(self.winners)


def gallery_url(event_url: str) -> str:
    """The gallery page for an event's base URL."""
    return event_url.rstrip("/") + GALLERY_PATH


def discover(
    query: str = "",
    page: int = 1,
    status: str = "ended",
    order_by: str = "prize-amount",
    opener: Opener | None = None,
) -> list[dict]:
    """Public Devpost event index: title and URL per event, newest page first."""
    params = {"status[]": status, "order_by": order_by, "page": page}
    if query:
        params["search"] = query
    url = f"{DEVPOST_API}?{urllib.parse.urlencode(params)}"
    payload = (opener or http_opener())(url)
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise FetchError(f"Devpost index was not JSON: {e}") from e
    return [h for h in (data.get("hackathons") or []) if h.get("url")]


def parse_gallery(text: str, title: str, url: str) -> Gallery:
    """Read a gallery page's text into submissions, marking the ones labelled Winner.

    The page lists each project as a name line, a tagline line, and — for winners — a line
    reading exactly "Winner". Anything after the result count is pagination furniture.
    """
    body = text.split("Filter submissions", 1)[-1]
    for tail in (" of ", "\n1 – "):
        if tail in body:
            body = body.rsplit("1 – ", 1)[0] if "1 – " in body else body
            break
    lines = [line.strip() for line in body.splitlines() if line.strip()]

    submissions: list[Submission] = []
    i = 0
    while i < len(lines) - 1:
        if lines[i] == WINNER_LABEL:  # a stray label with no project above it
            i += 1
            continue
        name, tagline = lines[i], lines[i + 1]
        if tagline == WINNER_LABEL:  # a project with no tagline
            submissions.append(Submission(name=name, tagline="", won=True))
            i += 2
            continue
        won = i + 2 < len(lines) and lines[i + 2] == WINNER_LABEL
        submissions.append(Submission(name=name, tagline=tagline, won=won))
        i += 3 if won else 2
    return Gallery(title=title, url=url, submissions=submissions)


def fetch_gallery(event_url: str, title: str = "", opener: Opener | None = None) -> Gallery:
    """Fetch and parse one event's gallery."""
    from ideate.meta.fetch import fetch_url  # local: avoids a cycle at import time

    url = gallery_url(event_url)
    doc = fetch_url(url, opener=opener)
    if len(doc.text) < MIN_GALLERY_CHARS:
        raise FetchError(f"{url} rendered no listing ({len(doc.text)} chars); it may need a browser")
    return parse_gallery(doc.text, title or doc.title, url)


def sweep(
    query: str = "",
    pages: int = 1,
    limit: int = 20,
    opener: Opener | None = None,
) -> tuple[list[Gallery], list[tuple[str, str]]]:
    """Discover events and return the galleries that actually carry outcomes.

    Returns the galleries with winners and a list of (title, reason) for the ones skipped, so a
    low hit rate is visible rather than looking like an empty result.
    """
    events: list[dict] = []
    for page in range(1, max(1, pages) + 1):
        try:
            events.extend(discover(query, page=page, opener=opener))
        except FetchError:
            break
    found: list[Gallery] = []
    skipped: list[tuple[str, str]] = []
    for event in events[:limit]:
        title = str(event.get("title") or "")
        try:
            gallery = fetch_gallery(str(event["url"]), title, opener=opener)
        except FetchError as e:
            skipped.append((title, str(e)[:80]))
            continue
        if gallery.has_outcomes:
            found.append(gallery)
        else:
            skipped.append((title, "no winners announced"))
    return found, skipped


def as_document(gallery: Gallery) -> FetchedDoc:
    """A gallery as a corpus document: winners and non-winners kept apart and labelled.

    The separation is the whole value. A list of winners teaches what winning text looks like;
    winners *beside* the projects that did not win at the same event is what lets a reader see
    which differences actually tracked the outcome.
    """
    if not gallery.has_outcomes:
        raise FetchError(f"{gallery.url} has no announced winners; nothing to record")
    lines = [
        f"{gallery.title} — submission gallery",
        "",
        f"{len(gallery.winners)} project(s) labelled Winner, {len(gallery.others)} listed without "
        "that label on the same page. The unlabelled ones are the gallery's own neighbours, not a "
        "fair sample of everything that did not win.",
        "",
        "WINNERS",
    ]
    lines += [f"- {s.name}: {s.tagline}" for s in gallery.winners]
    if gallery.others:
        lines += ["", "LISTED WITHOUT A WINNER LABEL"]
        lines += [f"- {s.name}: {s.tagline}" for s in gallery.others]
    return FetchedDoc(
        id=f"gallery-{slug(urllib.parse.urlparse(gallery.url).netloc)}",
        title=f"{gallery.title}: winners and neighbours",
        text="\n".join(lines),
        url=gallery.url,
        authors=[],
        published="",
        tags=["gallery", "winners", "evidence"],
    )
