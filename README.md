# DuBois

Downstream fork of [Sherlock](https://github.com/sherlock-project/sherlock). Same job: hunt a username across 400+ sites. Honest classifier, async engine, Windows-first.

Upstream still owns the site manifest. DuBois consumes it.

**Repo:** https://github.com/maintenancetunnels/dubois

## Install

```
pip install -e .
```

From a clone:

```
git clone https://github.com/maintenancetunnels/dubois.git
cd dubois
pip install -e .
```

## CLI

```
dubois user123
dubois --local --site GitHub --site GitLab ppfeister
dubois --calibrate --jsonl someuser
dubois --sync --workers 20 someuser
```

```
dubois --help
```

## Library

```python
from dubois import search

hits = search("alice", sites=["GitHub", "GitLab"], local=True)
```

Distribution name on disk is `dubois-osint` so it does not collide with the unrelated PyPI package `dubois`. The command and the import are both `dubois`.
