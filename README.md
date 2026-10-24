# Lithographie

U.S. trade research with source-aware ingestion and reproducible comparisons.

## Run

Requires Python 3.11+ and `beautifulsoup4`. Node 18+ is used for JavaScript tests. `R` with `ggplot2` is optional for chart rendering.

```sh
python -m pip install beautifulsoup4
python engine/build_database.py
python -m pipeline.cli --vault var/evidence-vault bootstrap
python -m pipeline.cli --vault var/evidence-vault compare --hs 760110 --base 202401 --comparison 202501 --csv var/ggplot2.csv
python research/app.py
```

Open `http://127.0.0.1:8765/` for the Census comparison, or open `Lithographie_Research_Workbench.html` for the standalone visualization snapshot. The snapshot is **not** connected to live ingestion.

## Sources

- `pipeline/`: allowlisted Census ZIP, Census HTML, Comtrade JSON and GLEIF JSON adapters; immutable input store; quarantine, revision and reconciliation rules.
- `engine/`: Census fixed-width parser, existing Comtrade/port snapshot and coverage contracts.
- `research/`: matched-month analysis, reproducible rows, and ggplot2 renderer.
- `research/data/`: **80 browser-verified HS 760110 observations** from complete January 2024 and 2025 scans, with original source hashes and explicit limits. The original full ZIP bytes are **not** in this repository.

The Census observations are customs aggregates, not shipments. Comtrade world statistics, port tonnage and GLEIF entities stay separate; none establishes company-to-port or carrier relationships. Missing observations are not zero. Quarter rankings require three complete months.

## Test

```sh
python -m unittest discover -s pipeline/tests
python -m unittest discover -s research/tests
(cd engine && python -m unittest discover -p 'test_*.py')
node --test engine/test-*.js
python engine/test-browser.py  # Optional: requires Playwright and Chromium
```

Details: [`pipeline/README.md`](pipeline/README.md), [`FRONTEND_DECISION.md`](FRONTEND_DECISION.md), [`ENGINE_RELEASE_V7.md`](ENGINE_RELEASE_V7.md).

## Publish

The repository root includes `index.html` for a static GitHub Pages preview.
It opens the self-contained HTML workbench, which is a **fixed evidence snapshot**, not a live data service.
To publish the static preview, select **Settings → Pages → Deploy from a branch → main / (root)** after the repository is created.

`research/app.py` is a separate Python HTTP application. GitHub Pages cannot run it, fetch source archives, or execute R; deploy that service separately when persistent hosting and verified-source refreshes are ready.
