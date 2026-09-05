"""DuBois: hunt usernames across social networks."""

from importlib.metadata import version as pkg_version, PackageNotFoundError
import pathlib
import tomli


def get_version() -> str:
    """Fetch the version number of the installed package."""
    for dist_name in ("dubois-osint", "dubois"):
        try:
            return pkg_version(dist_name)
        except PackageNotFoundError:
            continue
    pyproject_path: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        pyproject_data = tomli.load(f)
    return pyproject_data["tool"]["poetry"]["version"]

# This variable is only used to check for ImportErrors induced by users running as script rather than as module or package
import_error_test_var = None

__shortname__ = "DuBois"
__longname__ = "DuBois: Hunt Usernames Across Social Networks"
__version__ = get_version()


def search(username: str, **kwargs):
    """Library API: search one username. Never calls sys.exit.

    >>> from dubois import search
    >>> hits = search("alice", sites=["GitHub", "GitLab"], local=True)
    """
    from dubois.engine import search as _search
    return _search(username, **kwargs)
