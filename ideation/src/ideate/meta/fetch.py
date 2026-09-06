"""Fetch external material into the corpus as `kind: evidence`, with provenance.

Ingestion (``meta/ingest.py``) takes what is already on disk. This takes what is not: an arXiv
search or a URL. Everything written here carries the source URL, the retrieval date and a
content hash, because `kind: evidence` is the one corpus kind whose front matter *requires* a
source — an unattributed claim in the knowledge base is exactly what the evidence rules forbid.

Network access happens only when a fetcher is called. Every function takes an injectable
``opener`` so the tests exercise the parsing and the file writing without a network.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from ideate.models import sha256_hex, slug

ARXIV_API = "https://export.arxiv.org/api/query"
USER_AGENT = "ideate/0.1 (hackathon ideation system; +https://github.com/phazon2/hack-template)"
ATOM = "{http://www.w3.org/2005/Atom}"
DEFAULT_TIMEOUT = 30.0
MAX_TEXT_CHARS = 20000

Opener = Callable[[str], bytes]


class FetchError(RuntimeError):
    """A fetch failed: unreachable, rejected, empty, or unparseable."""


@dataclass
class FetchedDoc:
    """One fetched item, ready to be written as a corpus document."""

    id: str
    title: str
    text: str
    url: str
    authors: list[str]
    published: str
    tags: list[str]

    @property
    def fingerprint(self) -> str:
        return sha256_hex(self.text)


def http_opener(timeout: float = DEFAULT_TIMEOUT) -> Opener:
    """A real network opener. Only this function reaches the network."""

    def _open(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit http(s) only
                return response.read()
        except Exception as e:  # urllib raises a wide family; the caller only needs the reason
            raise FetchError(f"could not fetch {url}: {e}") from e

    return _open


def _require_http(url: str) -> None:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError(f"only http(s) URLs can be fetched, got {url!r}")


# --------------------------------------------------------------------------- arXiv
FIELD_PREFIXES = ("ti:", "abs:", "au:", "cat:", "all:", "id:", "jr:", "co:", "rn:")


def build_arxiv_query(query: str) -> str:
    """Scope a bare phrase to abstracts, ANDed.

    arXiv defaults a bare phrase to a loose OR across every field, which returns papers that
    share one common word and nothing else. A gap phrase is a topic, so AND its terms over the
    abstract. A query that already names fields (``ti:``, ``cat:`` ...) is passed through.
    """
    text = query.strip()
    # Word-boundary match, so a stray colon inside a term ("covid:19") is not read as a field.
    if re.search(r"\b(?:" + "|".join(p.rstrip(":") for p in FIELD_PREFIXES) + r"):", text, re.I):
        return text
    terms = [t for t in re.split(r"[^A-Za-z0-9+#.-]+", text) if len(t) > 1]
    if not terms:
        raise FetchError(f"arXiv query has no usable terms: {query!r}")
    return " AND ".join(f'abs:"{t}"' for t in terms)


def arxiv_query_url(query: str, max_results: int = 5) -> str:
    """The arXiv API URL for ``query``, scoped by :func:`build_arxiv_query`."""
    if not query.strip():
        raise FetchError("arXiv query is empty")
    params = urllib.parse.urlencode(
        {
            "search_query": build_arxiv_query(query),
            "start": 0,
            "max_results": max(1, min(int(max_results), 50)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    return f"{ARXIV_API}?{params}"


def parse_arxiv(payload: bytes) -> list[FetchedDoc]:
    """Parse an arXiv Atom feed into documents (abstracts, not full texts)."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as e:
        raise FetchError(f"arXiv returned unparseable XML: {e}") from e
    docs: list[FetchedDoc] = []
    for entry in root.findall(f"{ATOM}entry"):
        url = (entry.findtext(f"{ATOM}id") or "").strip()
        title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
        summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
        if not (url and title and summary):
            continue
        authors = [
            " ".join((a.findtext(f"{ATOM}name") or "").split())
            for a in entry.findall(f"{ATOM}author")
            if (a.findtext(f"{ATOM}name") or "").strip()
        ]
        published = (entry.findtext(f"{ATOM}published") or "")[:10]
        categories = [
            c.get("term", "") for c in entry.findall(f"{ATOM}category") if c.get("term")
        ]
        arxiv_id = url.rstrip("/").split("/")[-1]
        docs.append(
            FetchedDoc(
                id=f"arxiv-{slug(arxiv_id)}",
                title=title,
                text=f"{title}\n\n{summary}",
                url=url,
                authors=authors,
                published=published,
                tags=["arxiv", *categories[:4]],
            )
        )
    if not docs:
        raise FetchError("arXiv returned no usable entries for that query")
    return docs


MIN_ANDED_TERMS = 1


def arxiv_query_ladder(query: str) -> list[str]:
    """Progressively looser queries: all terms ANDed, then fewer, ending with the broadest.

    ANDing every term over abstracts is precise but often matches nothing — no single abstract
    contains all four of "hackathon judging criteria evaluation". Dropping the trailing terms
    trades precision for a non-empty result. The last rung is the leading term alone, which is
    normally the topic anchor, so a search always ends on-topic rather than empty. An explicit
    field query is the caller's own; it is never relaxed.
    """
    text = query.strip()
    if re.search(r"\b(?:" + "|".join(p.rstrip(":") for p in FIELD_PREFIXES) + r"):", text, re.I):
        return [text]
    terms = [t for t in re.split(r"[^A-Za-z0-9+#.-]+", text) if len(t) > 1]
    if not terms:
        raise FetchError(f"arXiv query has no usable terms: {query!r}")
    ladder = [
        " AND ".join(f'abs:"{t}"' for t in terms[:n])
        for n in range(len(terms), MIN_ANDED_TERMS - 1, -1)
    ]
    return ladder or [f'abs:"{terms[0]}"']


def fetch_arxiv(query: str, max_results: int = 5, opener: Opener | None = None) -> list[FetchedDoc]:
    """Search arXiv and return matching abstracts, relaxing the query until something matches."""
    open_url = opener or http_opener()
    last: FetchError | None = None
    for candidate in arxiv_query_ladder(query):
        url = arxiv_query_url(candidate, max_results)
        try:
            return parse_arxiv(open_url(url))
        except FetchError as e:
            last = e  # only "no usable entries" is worth relaxing for; a transport error repeats
            if "no usable entries" not in str(e):
                raise
    raise FetchError(f"arXiv found nothing for {query!r} even after relaxing the query") from last


# --------------------------------------------------------------------------- plain URLs
class _TextExtractor(HTMLParser):
    """Visible text only: script, style, nav and template content is dropped."""

    SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "form"}
    BREAK = {"p", "div", "br", "li", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        elif data.strip():
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        # Collapse runs of blank lines so the chunker sees real paragraphs.
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        return re.sub(r"\n\s*\n\s*", "\n\n", joined).strip()


def parse_page(payload: bytes, url: str) -> FetchedDoc:
    """Extract a readable document from an HTML (or plain text) page."""
    raw = payload.decode("utf-8", errors="replace")
    if "<" in raw and ">" in raw:
        parser = _TextExtractor()
        parser.feed(raw)
        text, title = parser.text(), " ".join(parser.title.split())
    else:
        text, title = raw.strip(), ""
    if not text:
        raise FetchError(f"no readable text at {url}")
    host = urllib.parse.urlparse(url).netloc
    title = title or f"Page at {host}"
    return FetchedDoc(
        id=f"web-{slug(host + '-' + urllib.parse.urlparse(url).path)[:32] or 'page'}-{sha256_hex(url)[:8]}",
        title=title,
        text=text[:MAX_TEXT_CHARS],
        url=url,
        authors=[],
        published="",
        tags=["web", slug(host)],
    )


def fetch_url(url: str, opener: Opener | None = None) -> FetchedDoc:
    """Fetch one http(s) page and extract its readable text."""
    _require_http(url)
    return parse_page((opener or http_opener())(url), url)


# --------------------------------------------------------------------------- writing
def write_docs(docs: list[FetchedDoc], directory: str | Path, retrieved_at: str) -> list[Path]:
    """Write documents as `kind: evidence` markdown with source, date and hash front matter."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for doc in docs:
        path = target / f"{doc.id}.md"
        front = [
            "---",
            f"title: {doc.title}",
            f"tags: {', '.join(doc.tags)}",
            "kind: evidence",
            f"source: {doc.url}",
            f"retrieved: {retrieved_at}",
            f"content_sha256: {doc.fingerprint}",
        ]
        if doc.authors:
            front.append(f"authors: {', '.join(doc.authors)}")
        if doc.published:
            front.append(f"published: {doc.published}")
        front.append("---")
        path.write_text("\n".join(front) + "\n\n" + doc.text.strip() + "\n", encoding="utf-8")
        written.append(path)
    return written
