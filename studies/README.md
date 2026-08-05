# Study contracts

This directory records the epistemic status of analyses without changing the runtime
package structure. Each study lives at `studies/<study-id>/study.yaml`; CI verifies its
schema, frozen-artifact hashes, and implementation entry points.

The status vocabulary is intentionally small:

- `exploratory`: useful working analysis, not a stable result;
- `reproducible`: specified inputs and implementation can be rerun;
- `validated`: the study's stated validation design has passed;
- `citable`: approved for the claims listed in its manifest;
- `retired`: retained for provenance but superseded or no longer supported.

Promotion changes the manifest only after the study meets the next status's requirements.
A manifest does not make an analysis citable by itself, and a closed materialization gate
must name the unresolved blocker.
