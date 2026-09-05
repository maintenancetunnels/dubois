"""HTTP response → QueryStatus.

403/429/5xx are UNKNOWN (or WAF), never "username available".
Only explicit error codes, 404/410, or an error message mean AVAILABLE.
"""
from __future__ import annotations

import re
from typing import Any

from dubois.result import QueryStatus
from dubois.util import as_list

# Fingerprints should stay highly targeted. Comment with target and date.
WAF_FINGERPRINTS: list[str] = [
    # 2024-05-13 Cloudflare
    ".loading-spinner{visibility:hidden}body.no-js .challenge-running{display:none}body.dark{background-color:#222;color:#d9d9d9}body.dark a{color:#fff}body.dark a:hover{color:#ee730a;text-decoration:underline}body.dark .lds-ring div{border-color:#999 transparent transparent}body.dark .font-red{color:#b20f03}body.dark",
    # 2024-11-11 Cloudflare error page
    '<span id="challenge-error-text">',
    # 2024-11-11 Cloudfront (AWS)
    "AwsWafIntegration.forceRefreshToken",
    # 2024-04-09 PerimeterX / Human Security
    '{return l.onPageView}}),Object.defineProperty(r,"perimeterxIdentifiers",{enumerable:',
]

# Conventional "this page does not exist" — never treat these as soft-fail.
NOT_FOUND_CODES = {404, 410}

# Auth walls, rate limits, upstream death — not evidence the username is free.
SOFT_FAIL_CODES = {
    401, 403, 407, 408, 409, 425, 429, 430,
    500, 502, 503, 504, 507, 511,
    520, 521, 522, 523, 524, 525, 526, 527, 530,
}

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL)


def strip_noise(text: str) -> str:
    """Drop script/style so chrome and JS do not trip errorMsg matches."""
    if not text:
        return ""
    cleaned = _SCRIPT_RE.sub(" ", text)
    cleaned = _STYLE_RE.sub(" ", cleaned)
    return cleaned


def bounded_regions(text: str) -> str:
    """Title + main + noise-stripped body. Full text is still searched as fallback."""
    if not text:
        return ""
    parts: list[str] = []
    title = _TITLE_RE.search(text)
    if title:
        parts.append(title.group(1))
    main = _MAIN_RE.search(text)
    if main:
        parts.append(strip_noise(main.group(1)))
    parts.append(strip_noise(text))
    return "\n".join(parts)


def error_message_hits(text: str, errors: Any) -> bool:
    """True if a configured error message is present (username not claimed).

    Messages are matched as literals. If a message starts with ``re:``, the rest
    is treated as a regular expression.
    """
    haystack = bounded_regions(text)
    if not haystack:
        return False
    for err in as_list(errors):
        if not err or not isinstance(err, str):
            continue
        if err.startswith("re:"):
            pattern = err[3:]
            try:
                if re.search(pattern, haystack):
                    return True
            except re.error:
                if pattern in haystack:
                    return True
        elif err in haystack:
            return True
    return False


def waf_hit(text: str) -> bool:
    if not text:
        return False
    return any(fp in text for fp in WAF_FINGERPRINTS)


def classify_http(
    *,
    status_code: int | None,
    text: str,
    error_type: Any,
    error_msg: Any = None,
    error_code: Any = None,
    error_text: str | None = None,
) -> tuple[QueryStatus, str | None]:
    """Return (status, context) for one probe response."""
    if error_text is not None:
        return QueryStatus.UNKNOWN, error_text

    if waf_hit(text):
        return QueryStatus.WAF, "Blocked by bot detection"

    types = [str(t) for t in as_list(error_type)]
    if not types:
        return QueryStatus.UNKNOWN, "No errorType configured"

    unknown_types = [t for t in types if t not in ("message", "status_code", "response_url")]
    if unknown_types and not any(t in ("message", "status_code", "response_url") for t in types):
        return QueryStatus.UNKNOWN, f"Unknown error type '{error_type}'"

    query_status = QueryStatus.UNKNOWN

    if "message" in types:
        if error_message_hits(text, error_msg):
            query_status = QueryStatus.AVAILABLE
        else:
            query_status = QueryStatus.CLAIMED

    if "status_code" in types and query_status is not QueryStatus.AVAILABLE:
        if status_code is None:
            return QueryStatus.UNKNOWN, "No HTTP status"
        error_codes = as_list(error_code)
        if error_codes and status_code in error_codes:
            query_status = QueryStatus.AVAILABLE
        elif 200 <= status_code < 300:
            query_status = QueryStatus.CLAIMED
        elif status_code in NOT_FOUND_CODES:
            query_status = QueryStatus.AVAILABLE
        elif status_code in SOFT_FAIL_CODES or status_code >= 500:
            return QueryStatus.UNKNOWN, f"HTTP {status_code}"
        else:
            # 3xx, 405, etc. without an explicit errorCode — do not invent "available"
            return QueryStatus.UNKNOWN, f"HTTP {status_code}"

    if "response_url" in types and query_status is not QueryStatus.AVAILABLE:
        if status_code is None:
            return QueryStatus.UNKNOWN, "No HTTP status"
        if 200 <= status_code < 300:
            query_status = QueryStatus.CLAIMED
        elif status_code in NOT_FOUND_CODES or 300 <= status_code < 400:
            query_status = QueryStatus.AVAILABLE
        elif status_code in SOFT_FAIL_CODES or status_code >= 500:
            return QueryStatus.UNKNOWN, f"HTTP {status_code}"
        else:
            return QueryStatus.UNKNOWN, f"HTTP {status_code}"

    return query_status, None
