#! /usr/bin/env python3

"""DuBois CLI entry when invoked as python -m dubois."""

import sys


if __name__ == "__main__":
    python_version = sys.version.split()[0]

    if sys.version_info < (3, 9):
        print(
            f"DuBois requires Python 3.9+\n"
            f"You are using Python {python_version}, which is not supported by DuBois."
        )
        sys.exit(1)

    from dubois.cli import main
    main()
