"""Search-engine dorks. We print URLs. We do not scrape Google."""
from __future__ import annotations

from urllib.parse import quote_plus


def _q(value: str) -> str:
    return quote_plus(value)


def username_dorks(username: str, *, extra_names: list[str] | None = None) -> list[tuple[str, str]]:
    names = [username, *(extra_names or [])]
    names = list(dict.fromkeys(n for n in names if n and n.strip()))
    rows: list[tuple[str, str]] = []
    for name in names:
        q = _q(name)
        quoted = _q(f'"{name}"')
        rows.extend(
            [
                (f"Google exact: {name}", f"https://www.google.com/search?q={quoted}"),
                (f"Google inurl: {name}", f"https://www.google.com/search?q=inurl%3A{q}"),
                (
                    f"Google profiles: {name}",
                    f"https://www.google.com/search?q={quoted}+(site%3Agithub.com+OR+site%3Alinkedin.com+OR+site%3Atwitter.com+OR+site%3Ax.com+OR+site%3Ainstagram.com)",
                ),
                (f"DuckDuckGo: {name}", f"https://duckduckgo.com/?q={quoted}"),
                (f"Yandex: {name}", f"https://yandex.com/search/?text={quoted}"),
                (f"Bing: {name}", f"https://www.bing.com/search?q={quoted}"),
            ]
        )
    return rows


def email_dorks(email: str) -> list[tuple[str, str]]:
    q = _q(f'"{email}"')
    return [
        (f"Google email: {email}", f"https://www.google.com/search?q={q}"),
        (f"DuckDuckGo email: {email}", f"https://duckduckgo.com/?q={q}"),
        (
            "Have I Been Pwned",
            f"https://haveibeenpwned.com/account/{_q(email)}",
        ),
    ]


def print_dorks(rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    print("Search URLs (open these yourself; DuBois does not scrape search engines):")
    for label, url in rows:
        print(f"  {label}")
        print(f"    {url}")
