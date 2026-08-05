# Self-Hosted Server Status

Copy this file to `server-status.local.md` on the live host and fill it in. The
local copy is ignored by Git because it contains installation-specific paths and
point-in-time operational state.

## Installation

- Host identifier:
- Deployment checkout:
- Persistent storage root:
- Container runtime and host architecture:
- Installed version (`git describe --tags --always --dirty`):

## Current state

- Last verified:
- Data vintages and checksums:
- Materialized subsets and Dagster run IDs:
- Backup location and last successful backup:
- Enabled schedules and sensors:
- Temporary blockers or recovery notes:

Do not put passwords, API keys, bearer tokens, or other secret values in this
file. Secrets remain in the deployment checkout's mode-`0600` `.env.server`.
