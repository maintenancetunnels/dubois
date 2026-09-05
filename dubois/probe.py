"""Build per-site probes from the manifest. Does not perform I/O."""
from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

from dubois.result import QueryResult, QueryStatus

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"
)

CHECK_SYMBOLS = ["_", "-", "."]

HEAD_FALLBACK_CODES = {400, 403, 405, 501}


@dataclass
class Probe:
    site_name: str
    username: str
    url_user: str
    url_probe: str
    method: str
    headers: dict[str, str]
    payload: Any
    allow_redirects: bool
    error_type: Any
    error_msg: Any
    error_code: Any
    is_control: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def interpolate_string(input_object: Any, username: str) -> Any:
    if isinstance(input_object, str):
        return input_object.replace("{}", username)
    if isinstance(input_object, dict):
        return {k: interpolate_string(v, username) for k, v in input_object.items()}
    if isinstance(input_object, list):
        return [interpolate_string(i, username) for i in input_object]
    return input_object


def encode_username(username: str) -> str:
    return quote(username, safe="._-")


def check_for_parameter(username: str) -> bool:
    """True if {?} exists in the username (expand into _ - . variants)."""
    return "{?}" in username


def multiple_usernames(username: str) -> list[str]:
    return [username.replace("{?}", symbol) for symbol in CHECK_SYMBOLS]


def hostname_is_illegal(url: str) -> bool:
    """True if interpolating the username produced a broken host (e.g. alice.)."""
    if not url:
        return True
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    host = parsed.hostname
    if not host:
        # urlparse may refuse some broken hosts; also catch empty labels via netloc
        netloc = (parsed.netloc or "").split("@")[-1].split(":")[0]
        if not netloc:
            return True
        host = netloc
    if ".." in host or host.startswith(".") or host.endswith("."):
        return True
    if any(label == "" for label in host.split(".")):
        return True
    return False


def _choose_method(net_info: dict) -> str:
    request_method = net_info.get("request_method")
    if request_method:
        method = str(request_method).upper()
        if method not in {"GET", "HEAD", "POST", "PUT"}:
            raise RuntimeError(f"Unsupported request_method for {net_info.get('url')}")
        return method
    error_type = net_info.get("errorType")
    types = error_type if isinstance(error_type, list) else [error_type]
    if types == ["status_code"] or (len(types) == 1 and types[0] == "status_code"):
        return "HEAD"
    return "GET"


def build_probe(
    site_name: str,
    net_info: dict,
    username: str,
    *,
    is_control: bool = False,
) -> Probe | QueryResult:
    """Return a Probe, or an ILLEGAL QueryResult if this username cannot be tested."""
    encoded = encode_username(username)
    url = interpolate_string(net_info["url"], encoded)
    regex_check = net_info.get("regexCheck")
    if regex_check and re.search(regex_check, username) is None:
        return QueryResult(username, site_name, url, QueryStatus.ILLEGAL)

    if hostname_is_illegal(url):
        return QueryResult(
            username,
            site_name,
            "",
            QueryStatus.ILLEGAL,
            context="Illegal URL for this username",
        )

    url_probe = net_info.get("urlProbe")
    if url_probe is None:
        url_probe = url
    else:
        url_probe = interpolate_string(url_probe, encoded)
        if hostname_is_illegal(url_probe):
            return QueryResult(
                username,
                site_name,
                "",
                QueryStatus.ILLEGAL,
                context="Illegal probe URL for this username",
            )

    headers = {"User-Agent": DEFAULT_UA}
    if "headers" in net_info and isinstance(net_info["headers"], dict):
        headers.update(net_info["headers"])

    payload = net_info.get("request_payload")
    if payload is not None:
        payload = interpolate_string(payload, username)

    error_type = net_info.get("errorType")
    allow_redirects = error_type != "response_url"
    if isinstance(error_type, list):
        allow_redirects = "response_url" not in error_type

    return Probe(
        site_name=site_name,
        username=username,
        url_user=url,
        url_probe=url_probe,
        method=_choose_method(net_info),
        headers=headers,
        payload=payload,
        allow_redirects=allow_redirects,
        error_type=error_type,
        error_msg=net_info.get("errorMsg"),
        error_code=net_info.get("errorCode"),
        is_control=is_control,
    )


def random_absent_username(net_info: dict) -> str | None:
    """Username that should not exist, still matching regexCheck when present."""
    pattern = net_info.get("regexCheck")
    alphabet = string.ascii_lowercase + string.digits
    for length in (16, 12, 8, 20, 6, 4):
        candidate = "z" + "".join(secrets.choice(alphabet) for _ in range(length - 1))
        if not pattern or re.search(pattern, candidate):
            return candidate
    # Last resort: claimed username with a suffix, then regex check
    claimed = net_info.get("username_claimed") or "user"
    for suffix in ("zzz", "qqq", "xyz"):
        candidate = f"{claimed}{suffix}"
        if not pattern or re.search(pattern, candidate):
            return candidate
    return None
