# Frontend decision — 2026-10-24

## Current

Keep the offline research workbench as a standalone HTML snapshot. Its sources and period are fixed; client-side interaction does not fetch new evidence. Preserve offline operation.

## Hypermedia

The [htmx alternatives](https://htmx.org/essays/alternatives/) essay argues for hypermedia as a model, not one mandatory library. That distinction applies here.

When the engine serves real, auditable query results, return source-labelled HTML fragments from a server. Keep query inputs and URLs authoritative and bookmarking reliable. Start with **native forms and fetch** for a small number of endpoints. Evaluate **fixi.js** if partial page replacement becomes repetitive, or **Unpoly** if navigation, history and layered views justify it. Do not add a client framework to solve an evidence problem.

## Visual contract

- White surfaces, gray rules, restrained blue selection.
- Squares and rectangles for data and controls. Triangles for direction and disclosure, not for implying shipments.
- One typographic hierarchy: IBM Plex Sans for primary content, IBM Plex Mono for measurements and source keys.
- On research views, concise evidence labels. Full limits live in the Evidence register and record inspector.
- Never display partner samples as population rankings or Customs port observations as bill-of-lading routes.

## No change to underlying data

This pass changes presentation only. It does not acquire or verify new source archives and does not change data coverage.
