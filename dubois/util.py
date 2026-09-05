"""Small shared helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def cache_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "dubois"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "dubois"
    return Path.home() / ".cache" / "dubois"


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, ext: str = "") -> str:
    """Make a username safe to use as a Windows/Unix file stem."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        cleaned = "username"
    stem = cleaned
    reserved_check = stem.split(".")[0].upper()
    if stem.upper() in WINDOWS_RESERVED or reserved_check in WINDOWS_RESERVED:
        stem = f"_{stem}"
    if len(stem) > 200:
        stem = stem[:200]
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"{stem}{ext}"
