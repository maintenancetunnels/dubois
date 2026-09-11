"""Extra public-record probes. Fail soft. Keys optional."""
from __future__ import annotations

import os
from typing import Any
import requests

from dubois.identity import label_matches_query
from dubois.records import MAX_HITS, TIMEOUT, RecordHit, _q

FEC_KEY = lambda: os.environ.get("FEC_API_KEY", "").strip() or "DEMO_KEY"


def _get(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, Any]:
    try:
        resp = session.get(url, params=params or {}, headers=headers or {}, timeout=TIMEOUT)
    except requests.RequestException as error:
        return 0, str(error)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


def _note(source: str, title: str, url: str, detail: str | None = None) -> list[RecordHit]:
    return [RecordHit(source, title, url, detail)]


def probe_wikidata(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "limit": MAX_HITS,
        },
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in payload.get("search") or []:
        label = row.get("label") or query
        if not label_matches_query(query, str(label)):
            continue
        ident = row.get("id") or ""
        out.append(
            RecordHit(
                "Wikidata",
                label,
                f"https://www.wikidata.org/wiki/{ident}" if ident else "https://www.wikidata.org",
                row.get("description"),
            )
        )
    return out


def probe_wikipedia(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://en.wikipedia.org/w/api.php",
        {"action": "opensearch", "search": query, "limit": MAX_HITS, "namespace": 0, "format": "json"},
    )
    if status != 200 or not isinstance(payload, list) or len(payload) < 4:
        return []
    titles, descs, urls = payload[1], payload[2], payload[3]
    out = []
    for i, title in enumerate(titles[:MAX_HITS]):
        if not label_matches_query(query, str(title)):
            continue
        href = urls[i] if i < len(urls) else ""
        desc = descs[i] if i < len(descs) else ""
        out.append(RecordHit("Wikipedia", title, href, desc or None))
    return out


def probe_littlesis(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(session, "https://littlesis.org/api/entities/search", {"q": query})
    if status != 200 or not isinstance(payload, dict):
        return []
    data = payload.get("data") or payload.get("entities") or []
    out = []
    for row in data[:MAX_HITS]:
        attrs = row.get("attributes") if isinstance(row, dict) else None
        if isinstance(attrs, dict):
            name = attrs.get("name") or query
            ident = row.get("id") or attrs.get("id")
            blurb = attrs.get("blurb") or attrs.get("summary")
        elif isinstance(row, dict):
            name = row.get("name") or query
            ident = row.get("id")
            blurb = row.get("blurb") or row.get("description")
        else:
            continue
        href = f"https://littlesis.org/entities/{ident}" if ident else f"https://littlesis.org/search?q={_q(query)}"
        out.append(RecordHit("LittleSis", str(name), href, blurb))
    return out


def probe_propublica_nonprofits(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://projects.propublica.org/nonprofits/api/v2/search.json",
        {"q": query},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("organizations") or [])[:MAX_HITS]:
        name = row.get("name") or query
        ein = row.get("ein") or ""
        href = f"https://projects.propublica.org/nonprofits/organizations/{ein}" if ein else ""
        st = row.get("st") or row.get("state") or ""
        out.append(RecordHit("ProPublica nonprofits", name, href, f"EIN {ein} {st}".strip()))
    return out


def probe_fec(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    key = FEC_KEY()
    out: list[RecordHit] = []
    for path, label in (
        ("names/candidates/", "candidate"),
        ("names/committees/", "committee"),
    ):
        status, payload = _get(
            session,
            f"https://api.open.fec.gov/v1/{path}",
            {"q": query, "api_key": key, "per_page": MAX_HITS},
        )
        if status in (401, 403, 429):
            return _note("FEC", f"HTTP {status} (set FEC_API_KEY)", "https://www.fec.gov/data/")
        if status != 200 or not isinstance(payload, dict):
            continue
        for row in (payload.get("results") or [])[:MAX_HITS]:
            name = row.get("name") or query
            ident = row.get("id") or row.get("candidate_id") or row.get("committee_id") or ""
            href = f"https://www.fec.gov/data/candidate/{ident}/" if ident else "https://www.fec.gov/data/"
            if "committee" in label and ident:
                href = f"https://www.fec.gov/data/committee/{ident}/"
            out.append(RecordHit("FEC", f"{label}: {name}", href, ident or None))
    return out


def probe_usaspending(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    url = "https://api.usaspending.gov/api/v2/autocomplete/recipient/"
    try:
        resp = session.post(url, json={"search_text": query, "limit": MAX_HITS}, timeout=TIMEOUT)
        payload = resp.json() if resp.status_code == 200 else None
        status = resp.status_code
    except (requests.RequestException, ValueError) as error:
        return _note("USASpending", "request failed", url, str(error))
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("results") or [])[:MAX_HITS]:
        name = row.get("recipient_name") or row.get("name") or query
        ident = row.get("recipient_hash") or row.get("uei") or ""
        href = "https://www.usaspending.gov/recipient/" + str(ident) if ident else "https://www.usaspending.gov/"
        out.append(RecordHit("USASpending", name, href, ident or None))
    return out


def probe_npi(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    params: dict[str, Any] = {"version": "2.1", "limit": MAX_HITS}
    parts = query.split()
    if len(parts) >= 2:
        params["first_name"] = parts[0]
        params["last_name"] = parts[-1]
    else:
        params["organization_name"] = query
    status, payload = _get(session, "https://npiregistry.cms.hhs.gov/api/", params)
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("results") or [])[:MAX_HITS]:
        basic = row.get("basic") or {}
        name = (
            basic.get("organization_name")
            or " ".join(x for x in (basic.get("first_name"), basic.get("last_name")) if x)
            or query
        )
        npi = row.get("number") or ""
        href = f"https://npiregistry.cms.hhs.gov/provider-view/{npi}" if npi else "https://npiregistry.cms.hhs.gov/"
        tax = ""
        taxos = row.get("taxonomies") or []
        if taxos:
            tax = taxos[0].get("desc") or ""
        out.append(RecordHit("NPI registry", name, href, f"NPI {npi} {tax}".strip()))
    return out


def probe_gleif(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://api.gleif.org/api/v1/lei-records",
        {"filter[entity.legalName]": query, "page[size]": MAX_HITS},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("data") or [])[:MAX_HITS]:
        attrs = row.get("attributes") or {}
        entity = attrs.get("entity") or {}
        legal = entity.get("legalName") or {}
        name = legal.get("name") if isinstance(legal, dict) else query
        lei = attrs.get("lei") or row.get("id") or ""
        href = f"https://search.gleif.org/#/record/{lei}" if lei else "https://search.gleif.org/"
        country = (entity.get("legalAddress") or {}).get("country") if isinstance(entity.get("legalAddress"), dict) else ""
        out.append(RecordHit("GLEIF LEI", str(name or query), href, f"{lei} {country}".strip()))
    return out


def probe_epa_echo(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://echodata.epa.gov/echo/rest_services.get_facilities",
        {"output": "JSON", "p_fn": query, "p_act": "Y"},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    results = ((payload.get("Results") or {}).get("Facilities")) or []
    out = []
    for row in results[:MAX_HITS]:
        name = row.get("FAC_NAME") or query
        registry = row.get("REGISTRY_ID") or ""
        loc = ", ".join(x for x in (row.get("FAC_CITY"), row.get("FAC_STATE")) if x)
        href = f"https://echo.epa.gov/detailed-facility-report?fid={registry}" if registry else "https://echo.epa.gov/"
        out.append(RecordHit("EPA ECHO", name, href, loc or None))
    return out


def probe_cfpb(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/",
        {"search_term": query, "size": MAX_HITS},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    hits = (payload.get("hits") or {}).get("hits") or []
    out = []
    for row in hits[:MAX_HITS]:
        src = row.get("_source") or {}
        company = src.get("company") or query
        product = src.get("product") or ""
        cid = src.get("complaint_id") or row.get("_id") or ""
        href = f"https://www.consumerfinance.gov/data-research/consumer-complaints/search/detail/{cid}" if cid else ""
        out.append(RecordHit("CFPB complaints", str(company), href, product or None))
    return out


def probe_occrp_aleph(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://aleph.occrp.org/api/2/entities",
        {"q": query, "limit": MAX_HITS},
    )
    if status in (401, 403):
        return _note("OCCRP Aleph", f"HTTP {status}", f"https://aleph.occrp.org/search?q={_q(query)}")
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("results") or [])[:MAX_HITS]:
        name = row.get("name") or (row.get("properties") or {}).get("name") or query
        if isinstance(name, list):
            name = name[0] if name else query
        ident = row.get("id") or ""
        schema = row.get("schema") or ""
        href = f"https://aleph.occrp.org/entities/{ident}" if ident else f"https://aleph.occrp.org/search?q={_q(query)}"
        out.append(RecordHit("OCCRP Aleph", str(name), href, schema or None))
    return out


def probe_icij(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    url = "https://offshoreleaks.icij.org/api/v1/search"
    status, payload = _get(session, url, {"q": query, "from": 0})
    if status != 200 or not isinstance(payload, dict):
        # Reconciliation API
        try:
            resp = session.post(
                "https://offshoreleaks.icij.org/reconcile",
                json={"query": query, "limit": MAX_HITS},
                timeout=TIMEOUT,
            )
            status, payload = resp.status_code, (resp.json() if resp.status_code == 200 else None)
        except (requests.RequestException, ValueError):
            return []
    if not isinstance(payload, dict):
        return []
    results = payload.get("results") or payload.get("response") or []
    if isinstance(payload.get("result"), list):
        results = payload["result"]
    out = []
    for row in results[:MAX_HITS]:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("id") or query
        ident = row.get("id") or ""
        score = row.get("score")
        href = f"https://offshoreleaks.icij.org/nodes/{ident}" if ident else f"https://offshoreleaks.icij.org/search?q={_q(query)}"
        out.append(RecordHit("ICIJ Offshore Leaks", str(name), href, str(score) if score is not None else None))
    return out


def probe_wayback(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    out: list[RecordHit] = []
    targets = [
        f"https://x.com/{query}",
        f"https://twitter.com/{query}",
        f"https://steamcommunity.com/id/{query}/",
        f"{query}.blogspot.com",
    ]
    for target in targets:
        try:
            resp = session.get(
                "https://web.archive.org/cdx/search/cdx",
                params={"url": target, "output": "json", "limit": 3, "fl": "original,timestamp,statuscode"},
                timeout=8,
            )
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            rows = resp.json()
        except ValueError:
            continue
        if not isinstance(rows, list) or len(rows) < 2:
            continue
        for original, timestamp, code in rows[1:4]:
            snap = f"https://web.archive.org/web/{timestamp}/{original}"
            out.append(RecordHit("Wayback", f"{target} @ {timestamp}", snap, str(code)))
    return out


def probe_datagov(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://catalog.data.gov/api/3/action/package_search",
        {"q": query, "rows": MAX_HITS},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    results = ((payload.get("result") or {}).get("results")) or []
    out = []
    for row in results[:MAX_HITS]:
        title = row.get("title") or query
        ident = row.get("name") or ""
        href = f"https://catalog.data.gov/dataset/{ident}" if ident else "https://catalog.data.gov/"
        org = ((row.get("organization") or {}).get("title")) if isinstance(row.get("organization"), dict) else ""
        out.append(RecordHit("data.gov", title, href, org or None))
    return out


def probe_nominatim(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    """Public geocoder — addresses, parcels-as-places, named buildings."""
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://nominatim.openstreetmap.org/search",
        {"q": query, "format": "jsonv2", "limit": MAX_HITS, "addressdetails": 1},
    )
    if status != 200 or not isinstance(payload, list):
        return []
    out = []
    for row in payload[:MAX_HITS]:
        name = row.get("display_name") or query
        osm_type = row.get("osm_type") or ""
        osm_id = row.get("osm_id") or ""
        href = f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else row.get("licence") or ""
        out.append(RecordHit("OpenStreetMap", name, href, row.get("type")))
    return out


def probe_opencorporates_officers(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    session = session or requests.Session()
    params: dict[str, Any] = {"q": query, "per_page": MAX_HITS}
    token = os.environ.get("OPENCORPORATES_API_TOKEN", "").strip()
    if token:
        params["api_token"] = token
    status, payload = _get(session, "https://api.opencorporates.com/v0.4/officers/search", params)
    if status in (401, 403, 429):
        return _note(
            "OpenCorporates officers",
            f"HTTP {status}",
            f"https://opencorporates.com/officers?q={_q(query)}",
        )
    if status != 200 or not isinstance(payload, dict):
        return []
    officers = ((payload.get("results") or {}).get("officers")) or []
    out = []
    for wrap in officers[:MAX_HITS]:
        officer = wrap.get("officer") if isinstance(wrap, dict) else None
        if not isinstance(officer, dict):
            continue
        name = officer.get("name") or query
        href = officer.get("opencorporates_url") or f"https://opencorporates.com/officers?q={_q(query)}"
        pos = officer.get("position") or officer.get("jurisdiction_code") or ""
        out.append(RecordHit("OpenCorporates officers", name, href, pos or None))
    return out


def probe_openstates(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    key = os.environ.get("OPENSTATES_API_KEY", "").strip()
    if not key:
        return _note(
            "OpenStates",
            "API key required — set OPENSTATES_API_KEY",
            f"https://openstates.org/search/?query={_q(query)}",
        )
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://v3.openstates.org/people",
        {"name": query, "per_page": MAX_HITS},
        {"X-API-KEY": key},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("results") or [])[:MAX_HITS]:
        name = row.get("name") or query
        href = row.get("openstates_url") or ""
        jid = row.get("jurisdiction", {})
        juris = jid.get("name") if isinstance(jid, dict) else ""
        out.append(RecordHit("OpenStates", name, href, juris or None))
    return out


def probe_companies_house(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        return _note(
            "Companies House",
            "API key required — set COMPANIES_HOUSE_API_KEY",
            f"https://find-and-update.company-information.service.gov.uk/search?q={_q(query)}",
        )
    session = session or requests.Session()
    try:
        resp = session.get(
            "https://api.company-information.service.gov.uk/search/companies",
            params={"q": query, "items_per_page": MAX_HITS},
            auth=(key, ""),
            timeout=TIMEOUT,
        )
        payload = resp.json() if resp.status_code == 200 else None
        status = resp.status_code
    except (requests.RequestException, ValueError) as error:
        return _note("Companies House", "request failed", "", str(error))
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("items") or [])[:MAX_HITS]:
        title = row.get("title") or query
        number = row.get("company_number") or ""
        href = f"https://find-and-update.company-information.service.gov.uk/company/{number}" if number else ""
        out.append(RecordHit("Companies House", title, href, row.get("company_status")))
    return out


def probe_congress(query: str, *, session: requests.Session | None = None) -> list[RecordHit]:
    key = os.environ.get("CONGRESS_GOV_KEY", "").strip() or os.environ.get("DATA_GOV_API_KEY", "").strip()
    if not key:
        return _note(
            "Congress.gov",
            "API key required — set CONGRESS_GOV_KEY",
            f"https://www.congress.gov/search?q={_q(query)}",
        )
    session = session or requests.Session()
    status, payload = _get(
        session,
        "https://api.congress.gov/v3/bill",
        {"query": query, "limit": MAX_HITS, "api_key": key, "format": "json"},
    )
    if status != 200 or not isinstance(payload, dict):
        return []
    out = []
    for row in (payload.get("bills") or [])[:MAX_HITS]:
        title = row.get("title") or query
        href = (row.get("url") or "").replace("?format=json", "")
        out.append(RecordHit("Congress.gov", title, href, row.get("type")))
    return out


PROBES = [
    probe_wikidata,
    probe_wikipedia,
    probe_littlesis,
    probe_propublica_nonprofits,
    probe_fec,
    probe_usaspending,
    probe_npi,
    probe_gleif,
    probe_epa_echo,
    probe_cfpb,
    probe_occrp_aleph,
    probe_icij,
    probe_wayback,
    probe_datagov,
    probe_nominatim,
    probe_opencorporates_officers,
    probe_openstates,
    probe_companies_house,
    probe_congress,
]
