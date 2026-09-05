"""DuBois Sites Information Module

Load and cache the site manifest.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

import requests

from dubois.util import cache_dir

MANIFEST_URL = "https://data.sherlockproject.xyz"
EXCLUSIONS_URL = (
    "https://raw.githubusercontent.com/sherlock-project/sherlock/"
    "refs/heads/exclusions/false_positive_exclusions.txt"
)


class SiteInformation:
    def __init__(
        self,
        name,
        url_home,
        url_username_format,
        username_claimed,
        information,
        is_nsfw,
        username_unclaimed=None,
    ):
        self.name = name
        self.url_home = url_home
        self.url_username_format = url_username_format
        self.username_claimed = username_claimed
        self.username_unclaimed = username_unclaimed or secrets.token_urlsafe(32)
        self.information = information
        self.is_nsfw = is_nsfw

    def __str__(self) -> str:
        return f"{self.name} ({self.url_home})"


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "data.schema.json"


def validate_manifest(site_data: dict) -> None:
    """Validate against the bundled schema when jsonschema is installed."""
    try:
        import jsonschema
    except ImportError:
        return
    schema_file = _schema_path()
    if not schema_file.is_file():
        return
    with schema_file.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=site_data, schema=schema)


def _load_json_payload(raw: dict) -> dict:
    payload = dict(raw)
    payload.pop("$schema", None)
    return payload


def _read_cached_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def load_remote_json(url: str, *, cache_name: str, timeout: float = 30) -> dict:
    """GET JSON with ETag cache. Falls back to the last good cache on failure."""
    dest = cache_dir()
    dest.mkdir(parents=True, exist_ok=True)
    cache_file = dest / cache_name
    etag_file = dest / f"{cache_name}.etag"
    headers = {}
    if etag_file.is_file() and cache_file.is_file():
        headers["If-None-Match"] = etag_file.read_text(encoding="utf-8").strip()

    try:
        response = requests.get(url=url, headers=headers, timeout=timeout)
    except Exception as error:
        cached = _read_cached_json(cache_file)
        if cached is not None:
            return _load_json_payload(cached)
        raise FileNotFoundError(
            f"Problem while attempting to access data file URL '{url}':  {error}"
        ) from error

    if response.status_code == 304:
        cached = _read_cached_json(cache_file)
        if cached is not None:
            return _load_json_payload(cached)

    if response.status_code != 200:
        cached = _read_cached_json(cache_file)
        if cached is not None:
            return _load_json_payload(cached)
        raise FileNotFoundError(
            f"Bad response while accessing data file URL '{url}'."
        )

    try:
        site_data = response.json()
    except Exception as error:
        cached = _read_cached_json(cache_file)
        if cached is not None:
            return _load_json_payload(cached)
        raise ValueError(
            f"Problem parsing json contents at '{url}':  {error}."
        ) from error

    try:
        cache_file.write_text(
            json.dumps(site_data, ensure_ascii=False),
            encoding="utf-8",
        )
        etag = response.headers.get("ETag")
        if etag:
            etag_file.write_text(etag, encoding="utf-8")
    except OSError:
        pass

    return _load_json_payload(site_data)


def load_exclusions(timeout: float = 10) -> list[str]:
    dest = cache_dir()
    dest.mkdir(parents=True, exist_ok=True)
    cache_file = dest / "exclusions.txt"
    try:
        response = requests.get(url=EXCLUSIONS_URL, timeout=timeout)
        if response.status_code == 200:
            text = response.text
            try:
                cache_file.write_text(text, encoding="utf-8")
            except OSError:
                pass
            return [line.strip() for line in text.splitlines() if line.strip()]
    except Exception:
        pass
    if cache_file.is_file():
        try:
            return [
                line.strip()
                for line in cache_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            return []
    return []


class SitesInformation:
    def __init__(
        self,
        data_file_path: str | None = None,
        honor_exclusions: bool = True,
        do_not_exclude: list[str] | None = None,
    ):
        do_not_exclude = list(do_not_exclude or [])
        validate_remote = False

        if not data_file_path:
            data_file_path = MANIFEST_URL

        if data_file_path.lower().startswith("http"):
            site_data = load_remote_json(data_file_path, cache_name="data.json")
            validate_remote = True
        else:
            try:
                with open(data_file_path, "r", encoding="utf-8") as file:
                    try:
                        site_data = json.load(file)
                    except Exception as error:
                        raise ValueError(
                            f"Problem parsing json contents at '{data_file_path}':  {error}."
                        ) from error
            except FileNotFoundError as error:
                raise FileNotFoundError(
                    f"Problem while attempting to access data file '{data_file_path}'."
                ) from error
            site_data = _load_json_payload(site_data)

        if validate_remote:
            try:
                validate_manifest(site_data)
            except Exception as error:
                print(f"Warning: remote manifest failed schema validation: {error}")

        if honor_exclusions:
            try:
                exclusions = load_exclusions()
                skip = {name.casefold() for name in do_not_exclude}
                for exclusion in exclusions:
                    if exclusion.casefold() in skip:
                        continue
                    site_data.pop(exclusion, None)
            except Exception:
                print("Warning: Could not load exclusions, continuing without them.")

        self.sites = {}
        for site_name in site_data:
            try:
                self.sites[site_name] = SiteInformation(
                    site_name,
                    site_data[site_name]["urlMain"],
                    site_data[site_name]["url"],
                    site_data[site_name]["username_claimed"],
                    site_data[site_name],
                    site_data[site_name].get("isNSFW", False),
                )
            except KeyError as error:
                raise ValueError(
                    f"Problem parsing json contents at '{data_file_path}':  Missing attribute {error}."
                ) from error
            except TypeError:
                print(
                    f"Encountered TypeError parsing json contents for target "
                    f"'{site_name}' at {data_file_path}\nSkipping target.\n"
                )

    def remove_nsfw_sites(self, do_not_remove: list | None = None):
        do_not_remove = [site.casefold() for site in (do_not_remove or [])]
        sites = {}
        for site in self.sites:
            if self.sites[site].is_nsfw and site.casefold() not in do_not_remove:
                continue
            sites[site] = self.sites[site]
        self.sites = sites

    def site_name_list(self):
        return sorted([site.name for site in self], key=str.lower)

    def __iter__(self):
        for site_name in self.sites:
            yield self.sites[site_name]

    def __len__(self):
        return len(self.sites)
