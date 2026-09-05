"""Public-records *search links*, not a scraper.

Can we scrape county courts, assessors, voter rolls? Technically some pages
are public. Should we? No.

- PACER and most state court portals forbid bulk harvesting in their terms.
- Home addresses, DOB, and case parties at scale is skip-tracing, not
  username OSINT, and piles up CFAA / ToS / privacy risk.
- DuBois will not fetch those sites.

What we will do:
- Print official search URLs the investigator opens in a browser.
- Point at documented APIs (CourtListener, SEC EDGAR, OpenCorporates) as
  *links*. No silent bulk pull of dockets or property rolls.
"""
from __future__ import annotations

from urllib.parse import quote_plus


def _q(value: str) -> str:
    return quote_plus(value)


def public_record_links(query: str) -> list[tuple[str, str]]:
    """Human-opened search pages for a name, email, or handle."""
    q = _q(query)
    quoted = _q(f'"{query}"')
    return [
        ("CourtListener (federal PACER-derived, official API/UI)", f"https://www.courtlistener.com/?q={q}&type=r"),
        ("CourtListener oral arguments", f"https://www.courtlistener.com/?q={q}&type=oa"),
        ("SEC EDGAR full-text", f"https://www.sec.gov/edgar/search/#/q={q}"),
        ("OpenCorporates companies", f"https://opencorporates.com/companies?q={q}"),
        ("OpenSanctions", f"https://www.opensanctions.org/search/?q={q}"),
        ("Congress.gov", f"https://www.congress.gov/search?q={q}"),
        ("Federal Register", f"https://www.federalregister.gov/documents/search?conditions%5Bterm%5D={q}"),
        ("Google: site:.gov", f"https://www.google.com/search?q={quoted}+site%3A.gov"),
        ("Google: site:.us courts", f"https://www.google.com/search?q={quoted}+(site%3A.gov+OR+site%3Auscourts.gov)+court"),
        (
            "Google: property/assessor (you click through)",
            f"https://www.google.com/search?q={quoted}+(assessor+OR+%22property+search%22+OR+parcel)",
        ),
    ]


def print_records(query: str) -> None:
    print(
        "Public-record search links — DuBois does not scrape these. "
        "Open what is in scope for your case."
    )
    for label, url in public_record_links(query):
        print(f"  {label}")
        print(f"    {url}")
