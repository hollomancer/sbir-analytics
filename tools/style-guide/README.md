# Interactive Style Guide (prototype)

**Target epistemic tier:** `exploratory`

Static, dependency-free browser page documenting the repository's visual
language: the network explorer's token system, the matplotlib figure palette,
the prose conventions, and the epistemic tier ladder.

## Run locally

From this directory:

```bash
python -m http.server 8080
```

Open <http://localhost:8080>. Unlike the network explorer, this page fetches
nothing and also opens correctly from a `file://` URL.

## What it is

The organizing claim is that in this repository visual form encodes epistemic
standing rather than brand — a dashed edge means a name candidate, not a style
variant — and that this idea is currently implemented four separate times in
four unrelated palettes.

Every convention on the page is labeled by how much weight it carries:

- **Enforced** — a script fails CI when you break it. Only the
  `**Target epistemic tier:**` declaration currently qualifies.
- **Conventional** — consistent across the codebase, but nothing checks it.
- **Contested** — the codebase actively disagrees with itself.

The `Known conflicts` section is the actionable part. It records, among others,
that `--technology` and `--critical` resolve to the same value, that the
per-agency figure panel is orange in two scripts and teal in a third, and that
`html_templates.py` renders a positive delta red while `html_processor.py`
renders good status green.

## Why it is exploratory

Every value on the page is transcribed by hand from source, which is the exact
failure mode the repository warns about elsewhere: a number that left its source
and stopped being checkable. Nothing regenerates it and nothing fails when it
drifts.

Promoting it to `pipelines` means generating the token table from
`tools/sbir-dib-network-explorer/styles.css` and the conflict list from a
linter over the figure scripts, so the page breaks when the code moves. Until
then it is a discussion document, not a source of truth — the stylesheet
remains authoritative.

## Related

- `tools/sbir-dib-network-explorer/` — the source of the token system
- `docs/steering/epistemic-tiers.md` — the tier contracts
- Two synced skills (`sbir-lit-refresh`, `sbir-spec-status-survey`) call an
  `apply_figure_style()` helper from a `figure-style` skill that does not exist
  on disk. A shared figure style is already assumed by the tooling; this page is
  a candidate specification for it.
