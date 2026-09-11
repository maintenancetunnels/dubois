"""Pull public profile facts from a page we already fetched.

Only open-graph / JSON-LD / obvious public HTML. No login, no private APIs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse

from dubois.identity import is_chrome_text, looks_like_person_name

_OG = re.compile(
    r"""<meta\s+[^>]*property=["']og:(title|description|image|url)["'][^>]*content=["']([^"']+)["']""",
    re.I,
)
_OG_REV = re.compile(
    r"""<meta\s+[^>]*content=["']([^"']+)["'][^>]*property=["']og:(title|description|image|url)["']""",
    re.I,
)
_TWITTER = re.compile(
    r"""<meta\s+[^>]*name=["']twitter:(title|description|image)["'][^>]*content=["']([^"']+)["']""",
    re.I,
)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_DESC = re.compile(
    r"""<meta\s+[^>]*name=["']description["'][^>]*content=["']([^"']+)["']""",
    re.I,
)
_JSONLD = re.compile(
    r"""<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.I | re.S,
)
_REL_ME = re.compile(
    r"""<a\s+[^>]*rel=["'][^"']*\bme\b[^"']*["'][^>]*href=["']([^"']+)["']""",
    re.I,
)
_JSON_NAME = re.compile(r'"(?:name|displayName|full_name|username)"\s*:\s*"([^"]{1,120})"')
_JSON_BIO = re.compile(r'"(?:bio|biography|description|about)"\s*:\s*"([^"]{1,400})"')


@dataclass
class ProfileFacts:
    title: str | None = None
    display_name: str | None = None
    bio: str | None = None
    image: str | None = None
    canonical: str | None = None
    links: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "display_name": self.display_name,
            "bio": self.bio,
            "image": self.image,
            "canonical": self.canonical,
            "links": self.links,
        }

    def one_line(self) -> str:
        bits = [x for x in (self.display_name, self.bio or self.title) if x]
        if not bits:
            return ""
        text = " — ".join(dict.fromkeys(bits))
        return text[:160]


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    text = unescape(re.sub(r"\s+", " ", value)).strip()
    return text or None


def _absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        return urljoin(base, url)
    return url


def _jsonld_name_bio(blob: str) -> tuple[str | None, str | None]:
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None, None
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return None, None
    name = data.get("name")
    desc = data.get("description")
    if isinstance(name, dict):
        name = name.get("name")
    return (
        _clean(name) if isinstance(name, str) else None,
        _clean(desc) if isinstance(desc, str) else None,
    )


def extract_profile(text: str, page_url: str = "", username: str = "") -> ProfileFacts:
    facts = ProfileFacts()
    if not text:
        return facts

    og: dict[str, str] = {}
    for match in _OG.finditer(text):
        og[match.group(1).lower()] = unescape(match.group(2))
    for match in _OG_REV.finditer(text):
        og[match.group(2).lower()] = unescape(match.group(1))
    tw: dict[str, str] = {}
    for match in _TWITTER.finditer(text):
        tw[match.group(1).lower()] = unescape(match.group(2))

    title_m = _TITLE.search(text)
    desc_m = _DESC.search(text)
    facts.title = _clean(og.get("title") or tw.get("title") or (title_m.group(1) if title_m else None))
    facts.bio = _clean(og.get("description") or tw.get("description") or (desc_m.group(1) if desc_m else None))
    facts.image = _absolutize(_clean(og.get("image") or tw.get("image")), page_url)
    facts.canonical = _absolutize(_clean(og.get("url")), page_url) or page_url or None

    for match in _JSONLD.finditer(text):
        name, bio = _jsonld_name_bio(match.group(1))
        if name and not facts.display_name:
            facts.display_name = name
        if bio and not facts.bio:
            facts.bio = bio

    if not facts.display_name:
        json_name = _JSON_NAME.search(text)
        if json_name:
            facts.display_name = _clean(json_name.group(1))
    if not facts.bio:
        json_bio = _JSON_BIO.search(text)
        if json_bio:
            facts.bio = _clean(json_bio.group(1))

    if facts.title and not facts.display_name:
        # "alice (@alice) / X" or "alice | GitHub"
        head = re.split(r"\s+[|\u2013\u2014/\-]\s+", facts.title, maxsplit=1)[0]
        head = re.sub(r"\s*\(@?\w+\)\s*$", "", head).strip()
        user = username.strip().casefold()
        if looks_like_person_name(head) or (user and head.casefold() == user):
            facts.display_name = head[:80]

    if is_chrome_text(facts.title):
        facts.title = None
    if is_chrome_text(facts.display_name):
        facts.display_name = None
    if is_chrome_text(facts.bio):
        facts.bio = None

    links: list[str] = []
    if facts.canonical:
        links.append(facts.canonical)
    for match in _REL_ME.finditer(text):
        url = _absolutize(match.group(1), page_url)
        if url:
            links.append(url)
    seen = set()
    out = []
    page_host = urlparse(page_url).netloc.lower() if page_url else ""
    for url in links:
        key = url.rstrip("/").lower()
        host = urlparse(url).netloc.lower()
        if key in seen:
            continue
        if page_host and host == page_host and url.rstrip("/") == page_url.rstrip("/"):
            continue
        seen.add(key)
        out.append(url)
    facts.links = out[:12]
    return facts
