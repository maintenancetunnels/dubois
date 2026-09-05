"""WhatsMyName site list → DuBois probe dicts.

Dataset: https://github.com/WebBreacher/WhatsMyName (CC BY-SA 4.0).
Cached locally. Sites already in the Sherlock manifest are skipped by name.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from dubois.sites import load_remote_json

WMN_URL = (
    "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
)


def _account_to_placeholder(value: str) -> str:
    return value.replace("{account}", "{}")


def wmn_to_site_info(entry: dict) -> dict | None:
    if entry.get("valid") is False:
        return None
    uri = entry.get("uri_check")
    if not isinstance(uri, str) or "{account}" not in uri:
        return None
    pretty = entry.get("uri_pretty") or uri
    parsed = urlparse(_account_to_placeholder(pretty).replace("{}", "x"))
    url_main = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else pretty
    cat = str(entry.get("cat") or "")
    payload = entry.get("post_body")
    request_payload = None
    method = "GET"
    if isinstance(payload, str) and payload.strip():
        method = "POST"
        try:
            request_payload = json.loads(_account_to_placeholder(payload))
        except json.JSONDecodeError:
            request_payload = _account_to_placeholder(payload)

    known = entry.get("known") or []
    claimed = known[0] if known else "blue"
    info: dict = {
        "url": _account_to_placeholder(pretty),
        "urlMain": url_main,
        "urlProbe": _account_to_placeholder(uri),
        "errorType": "presence",
        "username_claimed": claimed,
        "isNSFW": cat.strip().lower() in {"xx nsfw xx", "nsfw", "adult"},
        "source": "whatsmyname",
        "wmnCategory": cat,
    }
    if entry.get("m_string"):
        info["errorMsg"] = entry["m_string"]
    if entry.get("m_code") is not None:
        info["errorCode"] = entry["m_code"]
    if entry.get("e_string"):
        info["claimedMsg"] = entry["e_string"]
    if entry.get("e_code") is not None:
        info["claimedCode"] = entry["e_code"]
    headers = entry.get("headers")
    if isinstance(headers, dict):
        info["headers"] = headers
    if request_payload is not None:
        info["request_payload"] = request_payload
        info["request_method"] = method
    return info


def load_wmn_sites(*, nsfw: bool = False, timeout: float = 30) -> dict[str, dict]:
    raw = load_remote_json(WMN_URL, cache_name="wmn-data.json", timeout=timeout)
    sites_blob = raw.get("sites") if isinstance(raw, dict) else None
    if not isinstance(sites_blob, list):
        # load_remote_json pops $schema; WMN has "sites" key at top level
        raise ValueError("WhatsMyName payload missing 'sites' list")
    out: dict[str, dict] = {}
    for entry in sites_blob:
        if not isinstance(entry, dict):
            continue
        converted = wmn_to_site_info(entry)
        if converted is None:
            continue
        if converted.get("isNSFW") and not nsfw:
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        out[name] = converted
    return out


def merge_wmn(site_data: dict[str, dict], *, nsfw: bool = False) -> tuple[dict[str, dict], int]:
    """Add WMN sites whose names are not already in site_data. Returns (merged, added)."""
    existing = {name.casefold() for name in site_data}
    added = 0
    merged = dict(site_data)
    try:
        extra = load_wmn_sites(nsfw=nsfw)
    except Exception as error:
        print(f"Warning: could not load WhatsMyName list: {error}")
        return merged, 0
    for name, info in extra.items():
        if name.casefold() in existing:
            continue
        merged[name] = info
        existing.add(name.casefold())
        added += 1
    return merged, added
