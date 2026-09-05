"""Command-line entry for DuBois."""
from __future__ import annotations

import argparse
import os
import sys
from argparse import ArgumentParser, ArgumentTypeError, RawDescriptionHelpFormatter
from json import loads as json_loads

import requests
from colorama import init

from dubois.__init__ import (
    __longname__,
    __shortname__,
    __version__,
)
from dubois.engine import sherlock
from dubois.notify import QueryNotifyPrint
from dubois.probe import check_for_parameter, multiple_usernames
from dubois.report import result_path, write_csv, write_jsonl, write_txt, write_xlsx
from dubois.sites import SitesInformation


def timeout_check(value):
    float_value = float(value)
    if float_value <= 0:
        raise ArgumentTypeError(
            f"Invalid timeout value: {value}. Timeout must be a positive number."
        )
    return float_value


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.lstrip("v").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _remote_is_newer(remote: str, local: str) -> bool:
    try:
        return _version_tuple(remote) > _version_tuple(local)
    except Exception:
        return False


def _configure_stdio() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="dubois",
        formatter_class=RawDescriptionHelpFormatter,
        description=f"{__longname__} (Version {__version__})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__shortname__} v{__version__}",
        help="Display version information and dependencies.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        "-d",
        "--debug",
        action="store_true",
        dest="verbose",
        default=False,
        help="Display extra debugging information and metrics.",
    )
    parser.add_argument(
        "--folderoutput",
        "-fo",
        dest="folderoutput",
        help="If using multiple usernames, the output of the results will be saved to this folder.",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        help="If using single username, the output of the result will be saved to this file.",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        dest="csv",
        default=False,
        help="Create Comma-Separated Values (CSV) File.",
    )
    parser.add_argument(
        "--xlsx",
        action="store_true",
        dest="xlsx",
        default=False,
        help="Create the standard file for the modern Microsoft Excel spreadsheet (xlsx).",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        dest="jsonl",
        default=False,
        help="Write one JSON object per site to a .jsonl file.",
    )
    parser.add_argument(
        "--site",
        action="append",
        metavar="SITE_NAME",
        dest="site_list",
        default=[],
        help="Limit analysis to just the listed sites. Add multiple options to specify more than one site.",
    )
    parser.add_argument(
        "--proxy",
        "-p",
        metavar="PROXY_URL",
        action="store",
        dest="proxy",
        default=None,
        help="Make requests over a proxy. e.g. socks5://127.0.0.1:1080",
    )
    parser.add_argument(
        "--dump-response",
        action="store_true",
        dest="dump_response",
        default=False,
        help="Dump the HTTP response to stdout for targeted debugging.",
    )
    parser.add_argument(
        "--json",
        "-j",
        metavar="JSON_FILE",
        dest="json_file",
        default=None,
        help="Load data from a JSON file or an online, valid, JSON file. Upstream PR numbers also accepted.",
    )
    parser.add_argument(
        "--timeout",
        action="store",
        metavar="TIMEOUT",
        dest="timeout",
        type=timeout_check,
        default=10,
        help="Time (in seconds) to wait for response to requests (Default: 10)",
    )
    parser.add_argument(
        "--workers",
        action="store",
        metavar="N",
        dest="workers",
        type=int,
        default=50,
        help="Max concurrent requests for the async engine (Default: 50).",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        dest="sync",
        default=False,
        help="Use the legacy thread-pool engine instead of asyncio.",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        dest="calibrate",
        default=False,
        help="Also request a random absent username per site; both-claimed becomes WAF.",
    )
    parser.add_argument(
        "--print-all",
        action="store_true",
        dest="print_all",
        default=False,
        help="Output sites where the username was not found.",
    )
    parser.add_argument(
        "--print-found",
        action=argparse.BooleanOptionalAction,
        dest="print_found",
        default=True,
        help="Include claimed sites in file exports (default: true). Use --no-print-found to disable.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        default=False,
        help="Don't color terminal output",
    )
    parser.add_argument(
        "username",
        nargs="+",
        metavar="USERNAMES",
        action="store",
        help="One or more usernames to check with social networks. Check similar usernames using {?} (replace to '_', '-', '.').",
    )
    parser.add_argument(
        "--browse",
        "-b",
        action="store_true",
        dest="browse",
        default=False,
        help="Browse to all results on default browser.",
    )
    parser.add_argument(
        "--local",
        "-l",
        action="store_true",
        default=False,
        help="Force the use of the local data.json file.",
    )
    parser.add_argument(
        "--nsfw",
        action="store_true",
        default=False,
        help="Include checking of NSFW sites from default list.",
    )
    parser.add_argument(
        "--txt",
        action="store_true",
        dest="output_txt",
        default=False,
        help="Enable creation of a txt file",
    )
    parser.add_argument(
        "--ignore-exclusions",
        action="store_true",
        dest="ignore_exclusions",
        default=False,
        help="Ignore upstream exclusions (may return more false positives)",
    )
    return parser


def load_sites(args) -> SitesInformation:
    if args.local:
        return SitesInformation(
            os.path.join(os.path.dirname(__file__), "resources/data.json"),
            honor_exclusions=False,
        )

    json_file_location = args.json_file
    if args.json_file and args.json_file.isnumeric():
        pull_number = args.json_file
        pull_url = f"https://api.github.com/repos/sherlock-project/sherlock/pulls/{pull_number}"
        pull_request_raw = requests.get(pull_url, timeout=10).text
        pull_request_json = json_loads(pull_request_raw)
        if "message" in pull_request_json:
            print(f"ERROR: Pull request #{pull_number} not found.")
            sys.exit(1)
        head_commit_sha = pull_request_json["head"]["sha"]
        json_file_location = (
            f"https://raw.githubusercontent.com/sherlock-project/sherlock/"
            f"{head_commit_sha}/sherlock_project/resources/data.json"
        )

    return SitesInformation(
        data_file_path=json_file_location,
        honor_exclusions=not args.ignore_exclusions,
        do_not_exclude=args.site_list,
    )


def prune_sites(sites: SitesInformation, site_list: list[str]) -> dict:
    site_data_all = {site.name: site.information for site in sites}
    if not site_list:
        return site_data_all

    lower_map = {name.lower(): name for name in site_data_all}
    site_data = {}
    site_missing = []
    for site in site_list:
        existing = lower_map.get(site.lower())
        if existing:
            site_data[existing] = site_data_all[existing]
        else:
            site_missing.append(f"'{site}'")

    if site_missing:
        print(f"Error: Desired sites not found: {', '.join(site_missing)}.")

    if not site_data:
        sys.exit(1)
    return site_data


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.proxy is not None:
        print("Using the proxy: " + args.proxy)

    if args.no_color:
        init(strip=True, convert=False)
    else:
        init(autoreset=True)

    if args.output is not None and args.folderoutput is not None:
        print("You can only use one of the output methods.")
        sys.exit(1)

    if args.output is not None and len(args.username) != 1:
        print("You can only use --output with a single username")
        sys.exit(1)

    if args.workers is not None and args.workers < 1:
        print("ERROR: --workers must be >= 1")
        sys.exit(1)

    try:
        sites = load_sites(args)
    except Exception as error:
        print(f"ERROR:  {error}")
        sys.exit(1)

    if not args.nsfw:
        sites.remove_nsfw_sites(do_not_remove=args.site_list)

    site_data = prune_sites(sites, args.site_list)

    query_notify = QueryNotifyPrint(
        result=None, verbose=args.verbose, print_all=args.print_all, browse=args.browse
    )

    engine = "sync" if args.sync else "async"

    all_usernames: list[str] = []
    for username in args.username:
        if check_for_parameter(username):
            all_usernames.extend(multiple_usernames(username))
        else:
            all_usernames.append(username)

    try:
        for username in all_usernames:
            results = sherlock(
                username,
                site_data,
                query_notify,
                dump_response=args.dump_response,
                proxy=args.proxy,
                timeout=args.timeout,
                workers=args.workers,
                calibrate=args.calibrate,
                engine=engine,
            )

            txt_path = result_path(username, args.folderoutput, ".txt", args.output)
            if args.output_txt or args.output:
                write_txt(txt_path, results)

            if args.csv:
                write_csv(
                    result_path(username, args.folderoutput, ".csv"),
                    username,
                    results,
                    print_found=args.print_found,
                    print_all=args.print_all,
                )

            if args.xlsx:
                write_xlsx(
                    result_path(username, args.folderoutput, ".xlsx"),
                    username,
                    results,
                    print_found=args.print_found,
                    print_all=args.print_all,
                )

            if args.jsonl:
                write_jsonl(
                    result_path(username, args.folderoutput, ".jsonl"),
                    username,
                    results,
                )

            print()
        query_notify.finish()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
