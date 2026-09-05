"""Optional wrappers for holehe / ignorant / maigret.

These stay out of the MIT core. Install extras:

    pip install dubois-osint[email]
    pip install dubois-osint[phone]
    pip install dubois-osint[deep]

holehe password-recovery probes are skipped (-NP) so we do not email the target.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Callable

from colorama import Fore, Style


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(argv: list[str], timeout: int = 180) -> int:
    try:
        completed = subprocess.run(argv, timeout=timeout)
        return int(completed.returncode)
    except FileNotFoundError:
        return 127
    except subprocess.TimeoutExpired:
        print(f"Timed out: {' '.join(argv)}", file=sys.stderr)
        return 124


def _need(cmd: str, extra: str, package: str) -> bool:
    if _which(cmd):
        return True
    print(
        f"{package} is not installed. Optional extra:\n"
        f"  pip install dubois-osint[{extra}]\n"
        f"or: pip install {package}",
        file=sys.stderr,
    )
    return False


def run_holehe(email: str, *, timeout: int = 180) -> int:
    if not _need("holehe", "email", "holehe"):
        return 2
    # -NP: do not hit password-recovery endpoints (those can notify the inbox).
    return _run(
        ["holehe", "--only-used", "--no-color", "--no-clear", "-NP", email],
        timeout=timeout,
    )


def split_phone(raw: str) -> tuple[str, str] | None:
    digits = re.sub(r"\D+", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        return "1", digits[1:]
    if len(digits) == 10:
        return "1", digits
    if 8 <= len(digits) <= 15:
        # last 10 as national if longer country prefix
        if len(digits) > 10:
            return digits[:-10], digits[-10:]
        return "", digits
    return None


def run_ignorant(phone: str, *, timeout: int = 180) -> int:
    if not _need("ignorant", "phone", "ignorant"):
        return 2
    parts = split_phone(phone)
    if parts is None:
        print(f"Could not parse phone number: {phone}", file=sys.stderr)
        return 2
    cc, number = parts
    if not cc:
        print("Give a country code, e.g. +1 5551234567", file=sys.stderr)
        return 2
    return _run(["ignorant", cc, number], timeout=timeout)


def run_maigret(username: str, *, timeout: int = 600, top: int = 300) -> int:
    if not _need("maigret", "deep", "maigret"):
        return 2
    return _run(
        ["maigret", username, "--timeout", "10", "--top-sites", str(top)],
        timeout=timeout,
    )


def print_hit(kind: str, target: str, printer: Callable[[], None] | None = None) -> None:
    print(
        Style.BRIGHT
        + Fore.GREEN
        + f"[*] {kind} "
        + Fore.WHITE
        + target
        + Style.RESET_ALL
    )
    if printer:
        printer()
