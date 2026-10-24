# Lithographie / acquisition engine V7

Four source classes are supported: Census fixed-width ZIP, UN Comtrade JSON, GLEIF JSON, and Census Schedule C HTML. The pipeline retains exact **received input bytes**, their SHA256 digests, accepted records, validation failures, ingestion scopes and revisions. HTTP inputs require registered HTTPS URLs. APIs, geographic references, company identities and customs aggregates never merge implicitly.

## Execute

From the project root:

```sh
python -m pipeline.cli --vault var/evidence-vault sources
python -m pipeline.cli --vault var/evidence-vault bootstrap
python -m pipeline.cli --vault var/evidence-vault status
python -m pipeline.cli --vault var/evidence-vault compare --hs 760110 --base 202401 --comparison 202501 --csv var/ggplot2-760110.csv
python -m unittest discover -s pipeline/tests -v
```

`bootstrap` loads 80 Census HS 760110 port-country observations from earlier browser-based complete ZIP scans, 1 Comtrade 7601 world observation returned by the public preview API, and 4 country-code records copied from the Census HTML page. Browser captures are explicitly labelled: **publisher ZIP and full HTML/HTTP response bytes are not present**. The source ZIP hashes were reported by the browser scan and checked against a separate total-and-mode manifest. Do not use browser capture files as a proof of having downloaded complete raw sources.

Production acquisition requires network access:

```sh
python -m pipeline.cli --vault var/evidence-vault fetch --source census_port_hs6_imports --period 202501
python -m pipeline.cli --vault var/evidence-vault fetch --source comtrade_world_monthly --period 202501 --hs 7601 --flow M
python -m pipeline.cli --vault var/evidence-vault fetch --source census_country_codes
python -m pipeline.cli --vault var/evidence-vault fetch --source gleif_lei_record --lei 506700GE1G29325QX363
```

The first two must be obtained directly from the publisher in a network-enabled environment and tested for completeness. The public Comtrade **preview** is limited to 500 records and is permitted here only for a single, strictly scoped world-partner observation. Large partner listings from that endpoint are **not complete population extracts**. Reported quantity estimation flags are preserved, not silently set to measured values.

The `compare` command builds matched-month, same-HS6 customs port aggregate comparisons. It emits a typed CSV for `research/chart.R` (ggplot2), with empty values for missing port-country observations, never fabricated zeros. An original publisher ZIP takes priority over a browser-scanned extract **only after both monthly archives exist, are accepted and agree with the browser evidence when both are present**. Full-quarter plots remain blocked until all three monthly archives are present.

## Guardrails

- API responses, scraped references and full bulk data use separate observation types. US Census Schedule C is **not** UN M49. Legal entities from GLEIF are **not** importers by default.
- Source revisions are kept. `export` uses only the current accepted revision per scope; older versions remain available for audit.
- The immutable raw store is content-addressed. An invalid source stays available but is marked quarantined; it cannot enter comparisons.
- Browser extracts describe a **complete HS6 subset within a scanned ZIP**, not complete trade data across all HS codes.
- This environment could not retrieve ZIP bytes through its network stack. The real publisher archives are still needed for the full ingestion test, and R/ggplot2 is not installed here to render SVG.
