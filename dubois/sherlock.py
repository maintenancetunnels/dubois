#! /usr/bin/env python3

"""Compatibility module for the historical Sherlock import path.

Implementation lives in classify/probe/engine/cli.
`from dubois.sherlock import sherlock` still works.
"""

import sys

try:
    from dubois.__init__ import import_error_test_var  # noqa: F401
except ImportError:
    print("Run DuBois with `dubois` or `python -m dubois`.")
    sys.exit(1)

from dubois.cli import main, timeout_check  # noqa: F401
from dubois.engine import (  # noqa: F401
    DuboisFuturesSession,
    get_response,
    search,
    sherlock,
)
from dubois.probe import (  # noqa: F401
    check_for_parameter,
    interpolate_string,
    multiple_usernames,
)

if __name__ == "__main__":
    main()
