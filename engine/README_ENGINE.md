# LITHOGRAPHIE / Intelligence evidence pass

Version: 2026-10-24. Canonical app: `Lithographie_Research_Workbench.html`.

## Added to the application

**Intelligence** is the new default workspace. It compares U.S. monthly trade totals for HS 7601, 7602, 7604, 7606 and 7607, imports and exports, January–March 2024 versus January–March 2025. The dashboard derives aggregate Q1 value, HS category share and year-over-year change from the monthly world observations. Select one commodity for a matched-month time series, underlying records, and source links. The Origins tab compares a **sample of top-seven import partners per month** for HS 7601 and HS 7606 only. Missing partners are not filled with zero, and YoY partner changes are shown only for six-month-complete partner samples.

The original graph and geography views are retained. They continue to use their existing annual / port snapshots and do **not** automatically substitute these monthly observations.

## Evidence stored

| Layer | Records | Limit |
| --- | ---: | --- |
| Comtrade annual world totals | 9 | Original selected cohort set |
| Comtrade annual partner observations | 481 | Original preview cohorts |
| Comtrade monthly world totals | 60 | 5 HS codes × 2 directions × 6 months |
| Comtrade monthly top-partner observations | 84 | 7 per month × 2 HS codes × 6 months; not a complete census |
| USDOT / USACE principal ports | 40 | 2023 all commodities, not HS-linked |
| GLEIF legal entity records | 3 | Legal entities only |
| Verified bills of lading | 0 | No company-shipment edges |

Rows have source URLs. `monthly-snapshot.json` captures the validated compact values from public UN Comtrade preview queries retrieved on 2026-10-24. Quantity estimation flags are the API's `isQtyEstimated` flag, **not** verification that `netWgt` itself is estimated. Missing or zero net weights are treated as unavailable. The 2025-03 preview result hit 500 rows, but the world-total observations were present.

## Schema

`lithographie.sqlite` contains normalized sources, trade observations, port records, legal entities, empty shipment-evidence and company-link tables, and a searchable FTS5 index. The `quarter_world` view totals monthly world rows **without** double counting partner observations. Commodity codes and report periods are part of the observation identity. The schema does not create an unverified join from companies to trade/ports/vessels.

## Reproduce and test

Use Python 3.11+ and Node 18+. The database build needs BeautifulSoup.

```sh
python build_intelligence.py
python build_database.py
node --test test-intelligence.js
python test-database.py
python test-browser.py
```

The browser test uses Playwright and Chromium; it loads the standalone HTML via `page.set_content` because the test environment blocks Chromium direct navigation. Open the HTML itself normally in a desktop browser.

## Next work and new source pipeline

The parent `README.md` is the current engineering record. The new scripts `census_port_hs6.py`, `flow_contracts.py`, `comtrade_audit.py`, `db_safety.py`, and `build_manifest.py` support source acquisition, reproducibility and bounded aggregate comparisons. Official Census Port HS6 archives are **not included** in this release; therefore port-to-HS6 corridors remain unavailable until complete, unfiltered source months are ingested. The browser workbench still uses its embedded research snapshot, not live SQLite data. See `evidence-manifest.json` for exact row coverage and expected archive URLs.
