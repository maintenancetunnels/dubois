from dubois.result import QueryStatus
from dubois.score import score_profile


def test_429_claimed_is_weak():
    p, reasons = score_profile(
        status=QueryStatus.CLAIMED,
        http_status=429,
        text="Steam Community :: Error",
        profile={"title": "Steam Community :: Error"},
        username="gogusrl",
    )
    assert p < 0.5
    assert any("http_429" in r or "chrome_title" in r for r in reasons)


def test_unique_bio_is_strong():
    p, reasons = score_profile(
        status=QueryStatus.CLAIMED,
        http_status=200,
        text="<html>" + ("profile " * 40) + "Dragos (gogusrl)</html>",
        profile={"title": "TypeRacer", "display_name": "Dragos (gogusrl)", "bio": "Dragos (gogusrl)"},
        username="gogusrl",
    )
    assert p >= 0.5
    assert "bio_has_username" in reasons


def test_available_near_zero():
    p, _reasons = score_profile(status=QueryStatus.AVAILABLE, http_status=404, text="not found")
    assert p < 0.1


def test_waf_near_zero():
    p, reasons = score_profile(status=QueryStatus.WAF, http_status=403, text="challenge")
    assert p < 0.1
    assert "waf" in reasons
