from unittest.mock import MagicMock

from dubois.dorks import username_dorks
from dubois.extras import split_phone
from dubois.records import probe_courtlistener, public_record_links
from dubois.classify import classify_http
from dubois.result import QueryStatus


def test_record_links_still_exist():
    rows = public_record_links("Jane Doe")
    labels = [label for label, _url in rows]
    assert any("CourtListener" in label for label in labels)
    assert any("EDGAR" in label for label in labels)
    assert all(url.startswith("https://") for _label, url in rows)


def test_maximalist_probe_registry():
    from dubois.records_extra import PROBES

    names = {fn.__name__ for fn in PROBES}
    assert "probe_wikidata" in names
    assert "probe_fec" in names
    assert "probe_npi" in names
    assert "probe_wayback" in names
    assert "probe_icij" in names
    assert len(PROBES) >= 15


def test_wikipedia_drops_fuzzy_homophones():
    from dubois.records_extra import probe_wikipedia

    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [
        "sdushantha",
        ["Sushanth", "Susantha Chandramali", "Siddharth Dushantha"],
        ["actor", "actress", "software author"],
        [
            "https://en.wikipedia.org/wiki/Sushanth",
            "https://en.wikipedia.org/wiki/Susantha_Chandramali",
            "https://en.wikipedia.org/wiki/Siddharth_Dushantha",
        ],
    ]
    session.get.return_value = response
    hits = probe_wikipedia("sdushantha", session=session)
    titles = [hit.title for hit in hits]
    assert "Sushanth" not in titles
    assert "Susantha Chandramali" not in titles
    assert titles == ["Siddharth Dushantha"]


def test_courtlistener_probe_parses_dockets():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "count": 1,
        "results": [
            {
                "caseName": "United States v. Doe",
                "docket_absolute_url": "/docket/1/united-states-v-doe/",
                "court": "S.D.N.Y.",
                "dateFiled": "2005-01-01",
            }
        ],
    }
    session.get.return_value = response
    hits = probe_courtlistener("Doe", session=session)
    assert hits
    assert hits[0].source == "CourtListener"
    assert "United States v. Doe" in hits[0].title
    assert "courtlistener.com/docket/1/" in hits[0].url


def test_dorks_do_not_hit_the_network():
    rows = username_dorks("alice")
    assert any("google.com" in url for _label, url in rows)
    assert any("duckduckgo.com" in url for _label, url in rows)


def test_split_phone():
    assert split_phone("+1 (555) 123-4567") == ("1", "5551234567")
    assert split_phone("5551234567") == ("1", "5551234567")
    assert split_phone("12") is None


def test_presence_missing_string():
    status, _ctx = classify_http(
        status_code=200,
        text="<title>about.me</title> not a profile",
        error_type="presence",
        error_msg="<title>about.me</title>",
        error_code=404,
        claimed_msg=" | about.me",
        claimed_code=200,
    )
    assert status is QueryStatus.AVAILABLE


def test_presence_claimed_string():
    status, _ctx = classify_http(
        status_code=200,
        text="<title>alice | about.me</title>",
        error_type="presence",
        error_msg="<title>about.me</title>",
        error_code=404,
        claimed_msg=" | about.me",
        claimed_code=200,
    )
    assert status is QueryStatus.CLAIMED
