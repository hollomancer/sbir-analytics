# Scripts

This directory contains operational commands, study-owned producers, CI
guards, and exploratory analysis scripts. Read each script's epistemic-tier
declaration before using its output.

An exploratory script is non-citable even when it runs successfully. A public
study command must be named and frozen by that study's contract. Retired
operator conveniences are preserved behind the archive tombstone and are not
an operational interface.

## Layout rules

- The `archive` subdirectory holds retired scripts. Nothing in CI, the
  Makefile, Compose, or the Dagster deployment calls them. Do not use them
  as an operational interface. Read the README in that subdirectory for the
  reason each script was archived.
- A pipeline downloader in `scripts/data/` (`download_*.py`) is a thin
  wrapper. Put the download and parse logic in `sbir_etl/extractors/`. Keep
  only argument parsing, output writing, and the call in the script.
- Do not move, rename, or edit a script that a study contract pins by
  SHA-256. Before you move a script, search `studies/` for its path. If a
  study names the path, keep the script in place.
