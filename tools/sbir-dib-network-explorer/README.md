# SBIR → DIB Network Explorer

Static, dependency-free browser explorer for direct NSF SBIR/STTR awards and
observed DoD prime and reported-subaward funding.

## Build the browser payload

Materialize the NSF lineage release first, then export its Parquet products:

```bash
uv run python scripts/data/export_sbir_dib_network_web.py
```

The exporter writes ignored `data/network.json` plus downloadable CSV evidence
tables. They contain the local analysis slice and can be regenerated from the
pinned release manifest. Pass `--legacy-subaward-only` to export the original
supplier-to-prime-family view.

## Run locally

From this directory:

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. A local web server is required because browsers
do not permit `fetch()` of the generated JSON from a `file://` page.

## Interaction model

- Distinct nodes represent agencies, NSF awards, legal entities, DoD awards,
  and CET areas.
- Search can locate any node and open its one-hop evidence neighborhood.
- Current/former status, persistence, funding instrument, match confidence,
  density, and CET-review filters change only the visible graph—not totals in
  the source tables.
- Solid edges are direct or identifier-verified observations. Dashed edges are
  name candidates, CET text classifications, or temporal associations.
- Selecting a node exposes match confidence and source identifiers. The static
  CSV links provide complete filter-independent evidence tables, and **Visible
  relationships CSV** exports the relationships under the current filters.

The CET screen combines directly sourced NSF award text with verified legal-
entity DoD funding. It is an auditable prioritization aid, not evidence that an
NSF-funded capability was used or that a supplier is critical or irreplaceable.
DoD-14/NDIS-8 policy mapping remains deferred because no authoritative mapping
is materialized in the repository.
