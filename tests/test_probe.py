from dubois.probe import (
    build_probe,
    check_for_parameter,
    encode_username,
    hostname_is_illegal,
    interpolate_string,
    multiple_usernames,
)
from dubois.result import QueryResult, QueryStatus
from dubois import search


def test_wildcard_helpers():
    assert check_for_parameter("test{?}test") is True
    assert multiple_usernames("test{?}test") == ["test_test", "test-test", "test.test"]


def test_trailing_dot_hostname_is_illegal():
    url = interpolate_string("https://{}.empretienda.com.ar", encode_username("alice."))
    assert hostname_is_illegal(url)


def test_path_trailing_dot_is_legal():
    url = interpolate_string("https://example.com/{}", encode_username("alice."))
    assert not hostname_is_illegal(url)


def test_build_probe_rejects_broken_host():
    net_info = {
        "url": "https://{}.empretienda.com.ar",
        "urlMain": "https://empretienda.com",
        "errorType": "status_code",
        "username_claimed": "blue",
    }
    built = build_probe("Empretienda", net_info, "alice.")
    assert isinstance(built, QueryResult)
    assert built.status is QueryStatus.ILLEGAL


def test_search_does_not_hit_network_for_illegal_host():
    data = {
        "Empretienda": {
            "url": "https://{}.empretienda.com.ar",
            "urlMain": "https://empretienda.com",
            "errorType": "status_code",
            "username_claimed": "blue",
        }
    }
    results = search("alice.", site_data=data, engine="sync")
    assert results["Empretienda"]["status"].status is QueryStatus.ILLEGAL


def test_regex_illegal_without_network():
    data = {
        "GitHub": {
            "url": "https://www.github.com/{}",
            "urlMain": "https://www.github.com/",
            "errorType": "status_code",
            "regexCheck": r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$",
            "username_claimed": "blue",
        }
    }
    results = search("*#$Y&*JRE", site_data=data, engine="sync")
    assert results["GitHub"]["status"].status is QueryStatus.ILLEGAL


def test_does_not_mutate_site_data():
    data = {
        "GitHub": {
            "url": "https://www.github.com/{}",
            "urlMain": "https://www.github.com/",
            "errorType": "status_code",
            "regexCheck": r"^[a-zA-Z0-9]+$",
            "username_claimed": "blue",
        }
    }
    snapshot = {k: dict(v) for k, v in data.items()}
    search("!!!", site_data=data, engine="sync")
    assert data == snapshot
