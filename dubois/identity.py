"""String hygiene for profiles, aliases, and record labels."""
from __future__ import annotations

import re
from html import unescape
from typing import Any

CHROME_RE = re.compile(
    r"(security\s+verification|just\s+a\s+moment|attention\s+required|"
    r"access\s+denied|cf-error|checking\s+your\s+browser|enable\s+javascript|"
    r"please\s+wait|pardon\s+our\s+interruption|challenge-running|"
    r"steam\s+community\s*::\s*error|internet\s+archive|wayback\s+machine|"
    r"\b404\b|not\s+found|does(?:n'?t|\s+not)\s+exist|your\s+account|"
    r"have\s+fun,\s+meet\s+people|for\s+sale\s+domain|trending\s+gists|"
    r"xanga\s+2\.0|galaxy\s+a\d|checkout\s+.+\s+aws|"
    r"run\s+curl\s+against\s+this\s+page|making\s+sure\s+you'?re\s+not\s+a\s+bot|"
    r"\bcaptcha\b|\batlassian\b|gateway\s+pundit|situs\s+slot|utip\s+devient|"
    r"pagetitle:|<!\[CDATA\[|nothing\s+here|error\s*$)",
    re.I,
)

GENERIC_LABELS = frozenset(
    {
        "guest",
        "username",
        "profile",
        "home",
        "error",
        "official",
        "about",
        "login",
        "log in",
        "sign in",
        "your account",
        "undefined",
        "none",
        "n/a",
        "profilepage",
        "all",
        "target",
        "english",
        "linux",
        "rock",
        "acholi",
    }
)

_LEADING_STOP = frozenset(
    {
        "the",
        "official",
        "welcome",
        "checkout",
        "join",
        "meet",
        "page",
        "error",
        "stories",
        "security",
        "please",
        "nothing",
        "for",
    }
)

MAX_ALIASES = 5
_WORD = re.compile(r"[A-Za-z][A-Za-z.'\-]*$")


def _fold(value: str) -> str:
    return unescape(re.sub(r"\s+", " ", value or "")).strip().casefold()


def is_chrome_text(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    raw = unescape(re.sub(r"\s+", " ", str(text))).strip()
    if _fold(raw) in GENERIC_LABELS:
        return True
    return CHROME_RE.search(raw) is not None


def looks_like_person_name(text: str | None) -> bool:
    """First Last, or 'Dragos (handle)'. Not site chrome, not one-word brands."""
    if not text:
        return False
    cleaned = unescape(re.sub(r"\s+", " ", str(text))).strip()
    if not cleaned or is_chrome_text(cleaned):
        return False
    if any(ch.isdigit() for ch in cleaned):
        return False
    core = re.sub(r"\s*\([^)]{1,40}\)\s*$", "", cleaned).strip()
    if not core or is_chrome_text(core):
        return False
    words = core.split()
    if not 1 <= len(words) <= 5:
        return False
    if not all(_WORD.match(word) for word in words):
        return False
    if words[0].casefold() in _LEADING_STOP:
        return False
    if len(words) < 2 and "(" not in cleaned:
        return False
    return True


def label_matches_query(query: str, label: str) -> bool:
    """Keep exact / token / high-overlap labels. Drop Wikipedia homophones."""
    q = _fold(query)
    t = _fold(label)
    if not q or not t:
        return False
    if q == t:
        return True
    tokens = re.split(r"[\s_\-/]+", t)
    if q in tokens:
        return True
    for tok in tokens:
        if _tokens_related(q, tok):
            return True
    if " " in q:
        q_tokens = q.split()
        return all(any(_tokens_related(qt, tok) for tok in tokens) for qt in q_tokens)
    return False


def _tokens_related(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        if len(shorter) < 5:
            return False
        return len(shorter) / len(longer) >= 0.85 or longer.startswith(shorter) or longer.endswith(shorter)
    return False


def collect_aliases(username: str, results: dict[str, dict[str, Any]]) -> list[str]:
    """Real display names only. Never page titles, never chrome."""
    seen = {username.casefold()}
    found: list[str] = []
    for data in results.values():
        if float(data.get("p_profile") or 0) < 0.5:
            continue
        profile = data.get("profile") or {}
        raw = profile.get("display_name")
        if not looks_like_person_name(raw):
            continue
        name = str(raw).strip()
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
        if len(found) >= MAX_ALIASES:
            break
    return found
