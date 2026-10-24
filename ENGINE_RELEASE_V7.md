# Lithographie / Engine V7 / 24 October 2026

## Delivered

- Source-specific adapters: Census Port HS6 ZIP; Comtrade monthly API; Census Schedule C HTML; GLEIF LEI JSON.
- SHA256 content-addressed input archive, append-only acquisition log, accepted and quarantined ingestion runs.
- Strict source scope checks, response length limits, exact HTTPS URL allowlist, same-host redirect restriction.
- Browser-verified Census HS 760110 extract checks against independent total, vessel, air, and container values.
- Distinct record types and code systems. No implied importer, shipment, carrier, vessel, or USACE port linkage.
- Current version per source scope, retained revisions and key-by-key revision diff. Isolated Census ZIP replay with no automatic promotion.
- A matched January 2024/2025 HS 760110 comparison using the evidence store and a four-field ggplot2 CSV.
- Repaired research HTTP page shadowed function and Playwright test server port collision.

## Included verified browser captures

| Source | Extracted records | Complete original publisher response archived? |
|---|---:|---|
| Census HS 760110, 2024-01 | 35 | No. Full ZIP scanned in browser, full matching HS6 extract transferred. |
| Census HS 760110, 2025-01 | 45 | No. Full ZIP scanned in browser, full matching HS6 extract transferred. |
| Comtrade world aggregate, HS 7601, 2025-01 | 1 | No. Browser-returned JSON. Net weight flagged estimated. |
| Census Schedule C country HTML | 4 | No. Exact four-row HTML fragment only. |

Raw Census full ZIP import remains **0**. A direct publisher download will be stored separately and pinned against recorded checksums for already audited periods.

## Reproduce

From `lithographie-next/`:

```sh
python -m pipeline.cli --vault var/evidence-vault status
python -m pipeline.cli --vault var/evidence-vault compare --hs 760110 --base 202401 --comparison 202501 --csv var/ggplot2_760110.csv
python -m unittest discover -s pipeline/tests -v
python -m unittest discover -s research/tests -v
(cd engine && python -m unittest discover -p 'test_*.py' -v)
node --test engine/test-design.js engine/test-intelligence.js engine/test-analysis.js
python engine/test-browser.py
```

`Rscript research/chart.R var/ggplot2_760110.csv var/chart.svg` requires a local R installation with ggplot2. It was **not** executed in this environment.

No deployment or GitHub push was performed.
