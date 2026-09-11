from dubois.cli import _remote_is_newer, _useful_alias, build_parser


def test_fork_ahead_of_upstream_is_not_an_update():
    assert _remote_is_newer("0.16.0", "0.17.0") is False
    assert _remote_is_newer("0.17.0", "0.17.0") is False
    assert _remote_is_newer("0.18.0", "0.17.0") is True


def test_print_found_can_be_disabled():
    parser = build_parser()
    args = parser.parse_args(["--no-print-found", "alice"])
    assert args.print_found is False
    args = parser.parse_args(["alice"])
    assert args.print_found is True


def test_useful_alias_rejects_chrome():
    assert _useful_alias("sdushantha", "Siddharth Dushantha") is True
    assert _useful_alias("sdushantha", "Security Verification") is False
    assert _useful_alias("sdushantha", "sdushantha") is False
    assert _useful_alias("sdushantha", "Galaxy A07") is False
