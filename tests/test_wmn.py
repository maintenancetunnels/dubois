from dubois.wmn import wmn_to_site_info


def test_wmn_converts_presence_site():
    entry = {
        "name": "about.me",
        "uri_check": "https://about.me/{account}",
        "e_code": 200,
        "e_string": " | about.me",
        "m_string": "<title>about.me</title>",
        "m_code": 404,
        "known": ["john"],
        "cat": "social",
    }
    info = wmn_to_site_info(entry)
    assert info is not None
    assert info["url"] == "https://about.me/{}"
    assert info["urlProbe"] == "https://about.me/{}"
    assert info["errorType"] == "presence"
    assert info["errorCode"] == 404
    assert info["claimedCode"] == 200
    assert info["claimedMsg"] == " | about.me"
    assert info["source"] == "whatsmyname"
    assert info["isNSFW"] is False


def test_wmn_skips_invalid_and_marks_nsfw():
    assert wmn_to_site_info({"name": "x", "valid": False, "uri_check": "https://x/{account}"}) is None
    nsfw = wmn_to_site_info(
        {
            "name": "nsfw",
            "uri_check": "https://x.com/{account}",
            "e_code": 200,
            "e_string": "ok",
            "m_code": 404,
            "m_string": "no",
            "cat": "xx NSFW xx",
        }
    )
    assert nsfw is not None
    assert nsfw["isNSFW"] is True
