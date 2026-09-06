"""Public-record probes.

Query public HTTP APIs and public search endpoints. No login walls, no PACER
credentials, no fee-skipping. Optional tokens raise rate limits:

    COURTLISTENER_TOKEN
    OPENSANCTIONS_API_KEY
    OPENCORPORATES_API_TOKEN
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests

from dubois.__init__ import __version__

USER_AGENT = (
    f"DuBois/{__version__} (https://github.com/maintenancetunnels/dubois; "
    "public-records probe)"
)
TIMEOUT = 20
MAX_HITS = 8


@dataclass
class RecordHit:
    source: str
    title: str
    url: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _q(value: str) -> str:
    return quote_plus(value)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.sec.gov/",
        }
    )
    contact = os.environ.get("DUBOIS_CONTACT", "").strip()
    if contact:
        session.headers["From"] = contact
    return session


def public_record_links(query: str) -> list[tuple[str, str]]:
    """Browser URLs for sources without a useful anonymous API, plus the APIs we hit."""
    q = _q(query)
    quoted = _q(f'"{query}"')
    return [
        ("CourtListener UI", f"https://www.courtlistener.com/?q={q}&type=r"),
        ("SEC EDGAR search UI", f"https://www.sec.gov/edgar/search/#/q={q}"),
        ("OpenCorporates", f"https://opencorporates.com/companies?q={q}"),
        ("OpenSanctions", f"https://www.opensanctions.org/search/?q={q}"),
        ("Congress.gov", f"https://www.congress.gov/search?q={q}"),
        ("Federal Register", f"https://www.federalregister.gov/documents/search?conditions%5Bterm%5D={q}"),
        ("Google site:.gov", f"https://www.google.com/search?q={quoted}+site%3A.gov"),
        (
            "Google courts/PACER mentions",
            f"https://www.google.com/search?q={quoted}+(site%3A.gov+OR+site%3Auscourts.gov+OR+PACER+docket)",
        ),
        (
            "Google assessor/parcel",
            f"https://www.google.com/search?q={quoted}+(assessor+OR+parcel+OR+%22property+search%22+OR+%22property+appraiser%22)",
        ),
        (
            "Google voter file / SOS",
            f"https://www.google.com/search?q={quoted}+(%22voter+registration%22+OR+%22secretary+of+state%22+site%3A.gov)",
        ),
    ]


def probe_courtlistener(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or _session()
    token = os.environ.get("COURTLISTENER_TOKEN", "").strip()
    headers = {}
    if token:
        headers["Authorization"] = f"Token {token}"
    hits: list[RecordHit] = []
    for kind, label in (
        ("r", "RECAP docket"),
        ("rd", "RECAP filing"),
        ("o", "opinion"),
        ("oa", "oral argument"),
        ("p", "judge"),
    ):
        url = "https://www.courtlistener.com/api/rest/v4/search/"
        try:
            resp = session.get(
                url,
                params={"q": query, "type": kind, "page_size": MAX_HITS},
                headers=headers,
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            hits.append(RecordHit("CourtListener", f"{label} request failed", url, str(error)))
            continue
        if resp.status_code in (401, 403):
            hits.append(
                RecordHit(
                    "CourtListener",
                    f"{label}: auth required or rate-limited ({resp.status_code})",
                    f"https://www.courtlistener.com/?q={_q(query)}&type={kind}",
                    "Set COURTLISTENER_TOKEN for higher limits.",
                )
            )
            continue
        if resp.status_code != 200:
            hits.append(
                RecordHit(
                    "CourtListener",
                    f"{label}: HTTP {resp.status_code}",
                    f"https://www.courtlistener.com/?q={_q(query)}&type={kind}",
                    None,
                )
            )
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        results = payload.get("results") or []
        count = payload.get("count") or 0
        if not results:
            continue
        for row in results[:MAX_HITS]:
            name = row.get("caseName") or row.get("case_name") or row.get("caseNameFull") or query
            path = (
                row.get("absolute_url")
                or row.get("docket_absolute_url")
                or row.get("cluster_absolute_url")
                or ""
            )
            abs_url = urljoin("https://www.courtlistener.com", path) if path else url
            court = row.get("court") or row.get("court_citation_string") or ""
            filed = row.get("dateFiled") or row.get("dateArgued") or ""
            detail = " · ".join(x for x in (court, str(filed), f"n={count}") if x)
            hits.append(RecordHit("CourtListener", f"{label}: {name}", abs_url, detail or None))
    return hits


def probe_edgar(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or _session()
    url = "https://efts.sec.gov/LATEST/search-index"
    try:
        resp = session.get(url, params={"q": f'"{query}"', "hits.size": MAX_HITS}, timeout=TIMEOUT)
    except requests.RequestException as error:
        return [RecordHit("EDGAR", "request failed", url, str(error))]
    if resp.status_code != 200:
        return [
            RecordHit(
                "EDGAR",
                f"HTTP {resp.status_code}",
                f"https://www.sec.gov/edgar/search/#/q={_q(query)}",
                None,
            )
        ]
    try:
        payload = resp.json()
    except ValueError:
        return []
    hits_block = (payload.get("hits") or {}).get("hits") or []
    out: list[RecordHit] = []
    for row in hits_block[:MAX_HITS]:
        source = row.get("_source") or {}
        display = source.get("display_names") or source.get("entity") or query
        if isinstance(display, list):
            display = display[0] if display else query
        form = source.get("form") or source.get("root_forms") or ""
        adsh = source.get("adsh") or source.get("file_num") or ""
        file_url = f"https://www.sec.gov/edgar/search/#/q={_q(query)}"
        if adsh:
            file_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=&CIK=&type=&dateb=&owner=include&count=10&search_text={_q(str(adsh))}"
        out.append(RecordHit("EDGAR", str(display), file_url, str(form) if form else None))
    return out


def probe_federal_register(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or _session()
    url = "https://www.federalregister.gov/api/v1/documents.json"
    try:
        resp = session.get(
            url,
            params={"per_page": MAX_HITS, "order": "newest", "conditions[term]": query},
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        return [RecordHit("Federal Register", "request failed", url, str(error))]
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except ValueError:
        return []
    out: list[RecordHit] = []
    for row in (payload.get("results") or [])[:MAX_HITS]:
        title = row.get("title") or query
        href = row.get("html_url") or row.get("pdf_url") or url
        agency = ""
        agencies = row.get("agencies") or []
        if agencies and isinstance(agencies[0], dict):
            agency = agencies[0].get("name") or ""
        out.append(RecordHit("Federal Register", title, href, agency or None))
    return out


def probe_opencorporates(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or _session()
    url = "https://api.opencorporates.com/v0.4/companies/search"
    params: dict[str, Any] = {"q": query, "per_page": MAX_HITS}
    token = os.environ.get("OPENCORPORATES_API_TOKEN", "").strip()
    if token:
        params["api_token"] = token
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as error:
        return [RecordHit("OpenCorporates", "request failed", url, str(error))]
    if resp.status_code in (401, 403, 429):
        return [
            RecordHit(
                "OpenCorporates",
                f"HTTP {resp.status_code} (set OPENCORPORATES_API_TOKEN or open the UI)",
                f"https://opencorporates.com/companies?q={_q(query)}",
                None,
            )
        ]
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except ValueError:
        return []
    companies = ((payload.get("results") or {}).get("companies")) or []
    out: list[RecordHit] = []
    for wrap in companies[:MAX_HITS]:
        company = wrap.get("company") if isinstance(wrap, dict) else None
        if not isinstance(company, dict):
            continue
        name = company.get("name") or query
        href = company.get("opencorporates_url") or f"https://opencorporates.com/companies?q={_q(query)}"
        juris = company.get("jurisdiction_code") or ""
        out.append(RecordHit("OpenCorporates", name, href, juris or None))
    return out


def probe_opensanctions(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or _session()
    key = os.environ.get("OPENSANCTIONS_API_KEY", "").strip()
    url = "https://api.opensanctions.org/search/default"
    headers = {}
    if key:
        headers["Authorization"] = f"ApiKey {key}"
    try:
        resp = session.get(url, params={"q": query, "limit": MAX_HITS}, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as error:
        return [RecordHit("OpenSanctions", "request failed", url, str(error))]
    if resp.status_code in (401, 403):
        return [
            RecordHit(
                "OpenSanctions",
                "API key required — set OPENSANCTIONS_API_KEY or open the UI",
                f"https://www.opensanctions.org/search/?q={_q(query)}",
                None,
            )
        ]
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except ValueError:
        return []
    out: list[RecordHit] = []
    results = payload.get("results") or payload.get("responses") or []
    if isinstance(payload.get("results"), dict):
        results = payload["results"].get("results") or []
    for row in results[:MAX_HITS]:
        if not isinstance(row, dict):
            continue
        caption = row.get("caption") or row.get("name") or (row.get("properties") or {}).get("name")
        if isinstance(caption, list):
            caption = caption[0] if caption else query
        ident = row.get("id") or ""
        href = f"https://www.opensanctions.org/entities/{ident}/" if ident else f"https://www.opensanctions.org/search/?q={_q(query)}"
        schema = row.get("schema") or ""
        out.append(RecordHit("OpenSanctions", str(caption or query), href, schema or None))
    return out


def probe_records(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    """Hit every public API we ship. Failures become notes, not crashes."""
    from dubois.records_extra import PROBES as extra_probes

    session = session or _session()
    fns = [
        probe_courtlistener,
        probe_edgar,
        probe_federal_register,
        probe_opencorporates,
        probe_opensanctions,
        *extra_probes,
    ]
    hits: list[RecordHit] = []

    def _run(fn):
        return fn(query, session=session)

    with ThreadPoolExecutor(max_workers=min(16, len(fns))) as pool:
        futures = {pool.submit(_run, fn): fn for fn in fns}
        for fut in as_completed(futures):
            fn = futures[fut]
            try:
                hits.extend(fut.result() or [])
            except Exception as error:
                hits.append(RecordHit(getattr(fn, "__name__", "probe"), "probe crashed", "", str(error)))
    return hits


def write_records_jsonl(path: str, hits: list[RecordHit]) -> None:
    import json

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for hit in hits:
            handle.write(json.dumps(hit.as_dict(), ensure_ascii=False) + "\n")


def print_records(query: str) -> list[RecordHit]:
    print(f"[*] Public-record probe for {query}")
    hits = probe_records(query)

    def _is_note(hit: RecordHit) -> bool:
        title = hit.title.lower()
        return any(
            marker in title
            for marker in ("failed", "http ", "required", "rate-limited", "crashed")
        )

    real = [h for h in hits if h.url and not _is_note(h)]
    notes = [h for h in hits if _is_note(h)]
    if real:
        for hit in real:
            extra = f"  ({hit.detail})" if hit.detail else ""
            print(f"  [+] {hit.source}: {hit.title}{extra}")
            print(f"      {hit.url}")
    else:
        print("  no API matches")
    for hit in notes:
        print(f"  [-] {hit.source}: {hit.title}")
        if hit.url:
            print(f"      {hit.url}")
    print("  also:")
    for label, url in public_record_links(query):
        print(f"    {label}")
        print(f"      {url}")
    return hits
