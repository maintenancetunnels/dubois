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
dubois --calibrate --jsonl --dorks --records someuser
dubois --whatsmyname someuser
dubois --email name@example.com
dubois --phone +15551234567
dubois --deep someuser
```

Claimed hits now parse public Open Graph / JSON-LD (name, bio, avatar). `--no-enrich` turns that off.

`--email` / `--phone` / `--deep` wrap **holehe**, **ignorant**, and **maigret** if installed:

```
pip install dubois-osint[email]
pip install dubois-osint[phone]
pip install dubois-osint[deep]
pip install dubois-osint[full]
```

holehe is run with `-NP` so password-recovery probes (which can notify the inbox) stay off.

## Public records

**DuBois does not scrape courts, assessors, or voter rolls.** Those sites are often public in a browser and forbidden to harvest in bulk. `--records` prints official search URLs (CourtListener, SEC EDGAR, OpenCorporates, site:.gov dorks) for you to open. `--dorks` prints search-engine URLs; it does not scrape Google.

```
dubois --help
```

## Library

```python
from dubois import search

hits = search("alice", sites=["GitHub", "GitLab"], local=True)
```

Distribution name on disk is `dubois-osint` so it does not collide with the unrelated PyPI package `dubois`. The command and the import are both `dubois`.
