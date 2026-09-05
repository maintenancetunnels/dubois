from dubois.dorks import username_dorks
from dubois.extras import split_phone
from dubois.records import public_record_links
from dubois.classify import classify_http
from dubois.result import QueryStatus


def test_records_are_links_not_fetches():
    rows = public_record_links("Jane Doe")
    labels = [label for label, _url in rows]
    assert any("CourtListener" in label for label in labels)
    assert any("EDGAR" in label for label in labels)
    assert all(url.startswith("https://") for _label, url in rows)


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
