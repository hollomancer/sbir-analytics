# Source Acquisition Replay — 2026-09-21

**Status:** Passed.

## Environment

- Python: 3.12.13
- HTTP client: httpx 0.28.1
- Platform: Darwin 25.6.0 arm64
- Operator: Codex primary agent under repository-maintainer authority
- Source manifest SHA-256: `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3`
- Acquisition implementation SHA-256: `66aef6ebf3d2b936c09c0cc4c0343fbb27880ccb7fa07486fbf86848e2e8831d`

## Command

Run this command from a clean checkout:

```bash
.venv/bin/python scripts/data/acquire_sba_structural_sources.py \
  --manifest studies/sba-annual-report-structural-comparison/source-manifest.json \
  --destination-root . \
  --report studies/sba-annual-report-structural-comparison/source-acquisition.json
```

The evaluated replay used an empty temporary destination. It included only the
three captured table CSVs that a clean checkout supplies.

## Verified results

| Source | Bytes | Parsed rows or pages | SHA-256 |
| --- | ---: | ---: | --- |
| SBIR.gov award export | 394,636,989 | 219,590 rows | `aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a` |
| FY2020 report | 2,505,195 | 99 pages | `f1f51abb29c71d631451868f31babf2f6f1fe3845df91e534052f1d40dece3d3` |
| FY2021 report | 2,444,751 | 95 pages | `30b4dfa9b4c2c2220fc15938d5bd1a44bee92d5aa746b8756dc7d66217c6df55` |
| FY2022 report | 2,038,536 | 94 pages | `5ba60852f1cc44b23afdbf810ecf0cff77d714d10ffc786a9b73416d7c000fd1` |

The export had 42 columns. Its ordered-header SHA-256 was
`9f4ddf95992ccfb3a641d0f98bcf3ed591b9f3d5972cfd186d3d91708cc65127`.

The command also verified the three committed captured tables before returning.
It did not substitute a source file or search for a newer export.
