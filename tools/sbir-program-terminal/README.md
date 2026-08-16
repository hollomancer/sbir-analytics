# SBIR Program Terminal

**Target epistemic tier:** `exploratory`

A dependency-free prototype for one bounded research question: the F1 unified
capital-event timeline for the Form D high-confidence cohort.

The terminal is a read-only firm dossier over canonical
`capital_events.parquet` and `capital_events_per_firm.parquet` artifacts. It
does not connect to Neo4j, Dagster, or an HTTP API, and it does not ship data.
The generated payload is gitignored and explicitly non-citable.

Its base colors reuse the conventional token values documented by
`tools/style-guide/` and implemented by `tools/sbir-dib-network-explorer/`.
That reuse does not promote those values to enforced house style.

## Build the snapshot

Materialize the capital-event artifacts, then export the browser payload:

```bash
uv run python scripts/data/build_capital_events.py
uv run python scripts/data/export_sbir_program_terminal.py
```

The exporter fails closed when either canonical artifact is absent. The
resulting `data/terminal.json` records source paths, SHA-256 digests, the latest
observed event date, epistemic tier, and the interpretation boundary.

## Run locally

From this directory:

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. Without a generated snapshot, the page displays
the materialization command and no metrics or firms.

## Prototype controls

- Press `/` to focus firm/source-record search.
- Select a firm to inspect its observed public-event timeline and source IDs.
- Filter the timeline by event type.
- Treat missing events as measurement limits, never as negative findings.

