"""P(this page is a real profile). Not P(this is the same human).

Rule scores, reasons attached. Status stays Claimed/Unknown/WAF.
"""
from __future__ import annotations

import re
from typing import Any

from dubois.identity import is_chrome_text, looks_like_person_name
from dubois.result import QueryStatus

UNIQUE_NAME = re.compile(r"^.{1,80}\s*\(\s*[^)]+\s*\)\s*$")


def _clamp(value: float) -> float:
    return max(0.0, min(0.99, value))


def score_profile(
    *,
    status: QueryStatus,
    http_status: int | str | None,
    text: str = "",
    error_text: str | None = None,
    profile: dict[str, Any] | None = None,
    username: str = "",
    site_name: str = "",
) -> tuple[float, tuple[str, ...]]:
    reasons: list[str] = [f"status:{status.value}"]
    profile = profile or {}

    if status is QueryStatus.ILLEGAL:
        return 0.0, tuple(reasons + ["illegal"])
    if status is QueryStatus.AVAILABLE:
        return 0.04, tuple(reasons)
    if status is QueryStatus.WAF:
        return 0.06, tuple(reasons + ["waf"])
    if status is QueryStatus.UNKNOWN:
        p = 0.12
        if error_text:
            reasons.append(f"error:{error_text}")
            p = 0.08
        return _clamp(p), tuple(reasons)

    # Claimed — start skeptical
    p = 0.48
    code: int | None
    try:
        code = int(http_status) if http_status not in (None, "", "?") else None
    except (TypeError, ValueError):
        code = None

    if error_text:
        p = min(p, 0.14)
        reasons.append(f"error:{error_text}")
    if code is None:
        p = min(p, 0.18)
        reasons.append("no_http")
    elif code in (401, 403, 407, 429, 430) or (code >= 500):
        p = min(p, 0.16)
        reasons.append(f"http_{code}")
    elif code == 202:
        p = min(p, 0.28)
        reasons.append("http_202")
    elif 200 <= code < 300:
        p += 0.18
        reasons.append("http_2xx")

    body = text or ""
    if len(body) < 120:
        p *= 0.55
        reasons.append("thin_body")
    title = str(profile.get("title") or "")
    display = str(profile.get("display_name") or "")
    bio = str(profile.get("bio") or "")
    blob = f"{title}\n{display}\n{bio}\n{body[:4000]}"
    chrome = is_chrome_text(blob) or is_chrome_text(title) or is_chrome_text(display) or is_chrome_text(bio)
    site = site_name.strip()
    sitename_display = bool(
        display and site and display.casefold() in {site.casefold(), f"{site.casefold()} profile"}
    )

    uname = username.strip()
    if (
        uname
        and uname.casefold() in bio.casefold()
        and len(bio) > len(uname) + 3
        and not is_chrome_text(bio)
    ):
        p += 0.22
        reasons.append("bio_has_username")
    if display and uname and uname.casefold() not in display.casefold() and looks_like_person_name(display):
        if UNIQUE_NAME.search(display) or display.casefold() != title.casefold():
            p += 0.12
            reasons.append("distinct_display_name")
    if profile.get("links") and not chrome:
        p += 0.05
        reasons.append("outbound_links")

    lower_body = body.lower()
    if "challenge-running" in lower_body or "cf-browser-verification" in lower_body:
        p = min(p, 0.12)
        reasons.append("challenge_page")
    if chrome:
        p = min(p, 0.18)
        reasons.append("chrome_title")
    if sitename_display:
        p = min(p, 0.22)
        reasons.append("display_is_sitename")

    return _clamp(p), tuple(reasons)
