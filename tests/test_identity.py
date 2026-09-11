from dubois.identity import (
    collect_aliases,
    is_chrome_text,
    label_matches_query,
    looks_like_person_name,
)


def test_chrome_from_live_hunt():
    assert is_chrome_text("Security Verification")
    assert is_chrome_text("404 Not Found")
    assert is_chrome_text("run curl against this page")
    assert is_chrome_text("The Gateway Pundit")
    assert is_chrome_text("Galaxy A07")
    assert is_chrome_text("Your Account")
    assert is_chrome_text("guest")
    assert not is_chrome_text("Siddharth Dushantha")


def test_person_name_accepts_real_aliases():
    assert looks_like_person_name("Siddharth Dushantha")
    assert looks_like_person_name("Dragos (gogusrl)")
    assert not looks_like_person_name("Security Verification")
    assert not looks_like_person_name("TryHackMe")
    assert not looks_like_person_name("Galaxy A07")
    assert not looks_like_person_name("Spotify")


def test_wikipedia_homophones_rejected():
    assert not label_matches_query("sdushantha", "Sushanth")
    assert not label_matches_query("sdushantha", "Susantha Chandramali")
    assert label_matches_query("sdushantha", "sdushantha")
    assert label_matches_query("sdushantha", "Siddharth Dushantha")
    assert label_matches_query("Jane Doe", "Jane Doe")


def test_collect_aliases_skips_chrome_titles():
    results = {
        "WAF page": {
            "p_profile": 0.83,
            "profile": {"title": "Security Verification", "display_name": "Security Verification"},
        },
        "GitHub": {
            "p_profile": 0.78,
            "profile": {"display_name": "Siddharth Dushantha", "title": "sdushantha"},
        },
        "weak": {
            "p_profile": 0.2,
            "profile": {"display_name": "Should Ignore"},
        },
    }
    assert collect_aliases("sdushantha", results) == ["Siddharth Dushantha"]
