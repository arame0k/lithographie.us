# Ponytail review · 2026-10-24

Changed only shared code where a failing regression test proved a defect:

- Census HTML parsing reads rows only from the country-code table, not adjacent layout tables.
- Census ZIP import and acceptance log commit together; failure rolls back both.
- Incomplete quarters expose coverage counts, but not ranked port corridors.
- Imported air and vessel values cannot exceed the record's reported total.
- Parser version is 3. An already imported ZIP cannot be silently relabelled as freshly parsed; use isolated replay.
- The repository excludes local raw objects, generated databases, caches and browser screenshots. CI runs the existing core tests.
- Browser tests now use the installed Chromium or an explicit `CHROMIUM_PATH`, not a Linux-only path.

No new UI library or data abstraction was added. The existing standalone workbench and ggplot2 renderer were retained. Full Census publisher ZIPs and shipment records are still absent.

- Added minimal static `index.html` and release gate for GitHub Pages; it labels the snapshot correctly and does not present the Python service as hosted on Pages.

- Removed an unused precomputed ggplot CSV that represented absent port-country records as zeros; the verified comparison exporter leaves them blank.
- Fixed SVG output to use base R graphics without a hidden `svglite` dependency; added its release test and a CI ggplot2 render gate.
