from dubois.classify import classify_http, error_message_hits, waf_hit
from dubois.result import QueryStatus


def test_status_code_200_is_claimed():
    status, ctx = classify_http(
        status_code=200,
        text="<html>profile</html>",
        error_type="status_code",
    )
    assert status is QueryStatus.CLAIMED
    assert ctx is None


def test_status_code_404_is_available():
    status, ctx = classify_http(
        status_code=404,
        text="not found",
        error_type="status_code",
    )
    assert status is QueryStatus.AVAILABLE


def test_status_code_403_is_unknown_not_available():
    status, ctx = classify_http(
        status_code=403,
        text="forbidden",
        error_type="status_code",
    )
    assert status is QueryStatus.UNKNOWN
    assert ctx == "HTTP 403"


def test_status_code_429_is_unknown():
    status, ctx = classify_http(
        status_code=429,
        text="slow down",
        error_type="status_code",
    )
    assert status is QueryStatus.UNKNOWN
    assert "429" in ctx


def test_status_code_503_is_unknown():
    status, _ctx = classify_http(
        status_code=503,
        text="unavailable",
        error_type="status_code",
    )
    assert status is QueryStatus.UNKNOWN


def test_explicit_error_code_still_available():
    status, _ctx = classify_http(
        status_code=403,
        text="nope",
        error_type="status_code",
        error_code=[403],
    )
    assert status is QueryStatus.AVAILABLE


def test_waf_cloudflare_fingerprint():
    body = (
        ".loading-spinner{visibility:hidden}body.no-js .challenge-running"
        "{display:none}body.dark{background-color:#222;color:#d9d9d9}"
        "body.dark a{color:#fff}body.dark a:hover{color:#ee730a;text-decoration:underline}"
        "body.dark .lds-ring div{border-color:#999 transparent transparent}"
        "body.dark .font-red{color:#b20f03}body.dark"
    )
    assert waf_hit(body)
    status, ctx = classify_http(
        status_code=200,
        text=body,
        error_type="status_code",
    )
    assert status is QueryStatus.WAF
    assert ctx is not None


def test_message_literal_match_is_available():
    status, _ctx = classify_http(
        status_code=200,
        text='{"users":[]}',
        error_type="message",
        error_msg='{"users":[]}',
    )
    assert status is QueryStatus.AVAILABLE


def test_message_gitlab_empty_array():
    status, _ctx = classify_http(
        status_code=200,
        text="[]",
        error_type="message",
        error_msg="[]",
    )
    assert status is QueryStatus.AVAILABLE


def test_script_tag_does_not_trigger_short_error_msg():
    html = "<html><script>var x = 'Not Found';</script><body>Welcome back</body></html>"
    assert not error_message_hits(html, "Not Found")
    status, _ctx = classify_http(
        status_code=200,
        text=html,
        error_type="message",
        error_msg="Not Found",
    )
    assert status is QueryStatus.CLAIMED


def test_re_prefix_error_msg():
    status, _ctx = classify_http(
        status_code=200,
        text="<title>User missing</title>",
        error_type="message",
        error_msg=r"re:User\s+missing",
    )
    assert status is QueryStatus.AVAILABLE


def test_network_error_is_unknown():
    status, ctx = classify_http(
        status_code=None,
        text="",
        error_type="status_code",
        error_text="Timeout Error",
    )
    assert status is QueryStatus.UNKNOWN
    assert ctx == "Timeout Error"


def test_response_url_redirect_is_available():
    status, _ctx = classify_http(
        status_code=302,
        text="",
        error_type="response_url",
    )
    assert status is QueryStatus.AVAILABLE


def test_response_url_403_is_unknown():
    status, ctx = classify_http(
        status_code=403,
        text="nope",
        error_type="response_url",
    )
    assert status is QueryStatus.UNKNOWN
    assert "403" in ctx
