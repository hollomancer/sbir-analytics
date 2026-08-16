# SBIR Program Terminal

An exploratory, dependency-free product prototype for a decision terminal over
the SBIR/STTR program.

The prototype demonstrates a compact interaction model for:

- program-level portfolio monitoring;
- universal organization, award, agency, and technology search;
- sortable firm screening;
- organization profiles and event timelines; and
- visible provenance and evidence-status boundaries.

Its base colors reuse the conventional token values documented by
`tools/style-guide/` and implemented by `tools/sbir-dib-network-explorer/`.
That reuse does not promote those values to enforced house style; the style
guide records their standing and open conflicts.

## Data status

The committed payload at `data/demo.json` is **synthetic demonstration data**.
Names, identifiers, amounts, and events are invented and must not be cited or
used for program decisions. The prototype is exploratory-tier and is not wired
to Neo4j or a live Dagster instance.

Production integration should replace the demo payload with a versioned export
from canonical pipeline artifacts. It should preserve the payload's per-metric
`status`, `as_of`, and `source` fields so the interface never presents a
computed value as validated evidence.

## Run locally

From this directory:

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. The local server is required because the browser
loads `data/demo.json` with `fetch()`.

## Prototype controls

- Press `/` to focus universal search.
- Search by organization, award identifier, agency, or technology.
- Select a firm in the screener to open its profile.
- Filter the screener by agency or technology.
- Change the portfolio lens to update the ranked technology view.

