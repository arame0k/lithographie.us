# Lithographie

U.S. trade intelligence built on public records, verified sources, and reproducible analysis.

## Setup

Requires Python 3.11+, `beautifulsoup4`, and Node 18+ for testing. R and ggplot2 are used for chart rendering.

```sh
python -m pip install beautifulsoup4
python engine/build_database.py
python -m pipeline.cli --vault var/evidence-vault bootstrap
python -m pipeline.cli --vault var/evidence-vault compare --hs 760110 --base 202401 --comparison 202501 --csv var/ggplot2.csv
python research/app.py
```

Open `http://127.0.0.1:8765/` for the research app. `Lithographie_Research_Workbench.html` is a standalone preview for now.

## Data

The engine collects, cleans, and reconciles records from Census, Comtrade, and other public sources through APIs, bulk downloads, and scraping.

- `pipeline/` — Acquisition, validation, provenance, and revisions.
- `engine/` — Parsing, normalization, and data integrity.
- `research/` — Analysis, comparisons, and ggplot2.
- `research/data/` — approx 80 verified aluminum import/export observations from January 2024 and 2025.

Original Census ZIP archives are not included.

Customs aggregates are not individual shipments. Sources remain separate until their relationships are established. 
Missing data is not 0. Incomplete periods cannot support complete rankings.

## Tests

```sh
python -m unittest discover -s pipeline/tests
python -m unittest discover -s research/tests
(cd engine && python -m unittest discover -p 'test_*.py')
node --test engine/test-*.js
```

Optional browser tests: `python engine/test-browser.py`

## Deployment

`index.html` provides a static GitHub Pages preview. Enable it under **Settings → Pages**, using `main / (root)`.

The research server runs separately. GitHub Pages cannot execute Python, ingest new records, or render R charts.

Additional documentation is available in `pipeline/README.md`, `FRONTEND_DECISION.md`, and `ENGINE_RELEASE_V7.md`. (names will be changed
