from dubois.enrich import extract_profile


HTML = """
<html>
<head>
<title>alice (@alice) / GitHub</title>
<meta property="og:title" content="alice">
<meta property="og:description" content="builds things">
<meta property="og:image" content="https://example.com/a.png">
<meta property="og:url" content="https://github.com/alice">
</head>
<body>
<a rel="me" href="https://example.com/@alice">me</a>
</body>
</html>
"""


def test_extract_og_fields():
    facts = extract_profile(HTML, "https://github.com/alice")
    assert facts.display_name == "alice"
    assert facts.bio == "builds things"
    assert facts.image == "https://example.com/a.png"
    assert "https://example.com/@alice" in facts.links
    line = facts.one_line()
    assert "alice" in line
    assert "builds things" in line


def test_empty_html():
    facts = extract_profile("")
    assert facts.as_dict()["title"] is None
