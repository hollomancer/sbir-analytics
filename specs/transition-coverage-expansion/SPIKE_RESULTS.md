# Coverage-Expansion Spike Results (USASpending-testable channels)

Testable-now channels executed against USASpending (SAM-only channels §638-J&A / OT await
off-sandbox execution via `scripts/transition_coverage/sam_probe.sh`).

## T3 — Subaward channel (DEFENSIBLE characterization)

Method (artifact-resistant): recent-SBIR-era firms (first Phase II ≥ 2010); subaward within
[firstP2, lastP2+12]; **per-prime cap $5M** (kills the "$2.1B from 1 prime" artifacts);
**exclude grown-into-primes** (raw > $200M); report **breadth (# primes)** as the primary
signal, capped $ as secondary.

- Eligible recent-era firms: 89 · excluded as grown-into-primes: **4** (Control Vision, i3,
  NOU, PeopleTec) · kept small-firm transitioners: **37**.
- **Capped subaward $: $378M** across 37 firms (conservative; vs the meaningless $10.6B raw).
- Median **3 primes/firm**; **21 firms sub to ≥3 primes**.
- Breadth signature (the real signal): Rock West Composites **26 primes**, Anduril 23, STR 21,
  Blue Canyon 17 — a small firm's SBIR tech designed into many primes' systems = broad
  adoption, invisible at prime level.

**Read:** the subaward channel is real and material (~$378M conservative, 37 small firms).
Breadth (# primes) is the transition signature to use, not raw dollars. Still an
approximation (name-token match, not UEI-exact; timing gate, not tech-matched) — T3 in
`tasks.md` tightens to UEI-exact + SBIR-derivation for the production version.

## T2 — Grants/assistance channel

Across 35 civilian SBIR firms (NIH/NSF/DOE/USDA, first P2 ≥ 2010): **~$69M non-SBIR federal
grants + $33M contracts** of follow-on footprint, absent from the FPDS contract universe
(Columbia Power $19M; NIH-biotech follow-ons: MABVAX, Exemplar Genetics). "Non-SBIR" =
description without SBIR/STTR — a loose gate; T2 tightens with UEI-exact + Phase-II proximity.

## T1 — RESURRECTED via the SAM bulk extract (not the API)

The personal-key API is quota-blocked, BUT the **SAM Contract Opportunities bulk CSV extracts
are reachable from the hosted env** (served from `s3.amazonaws.com/falextracts/` via
`sam.gov/api/prod/fileextractservices` — NOT the blocked `api.sam.gov`), **no key, no quota**.

- Files: `datagov/ContractOpportunitiesFullCSV.csv` + annual archives **FY2000–FY2025**
  (~0.9–1.3 GB/yr). Object GET works (HTTP 206) even though bucket-list is 403.
- **47 columns incl. `Description` (full BODY TEXT), `Title`, `Awardee`, `AwardNumber`,
  `Award$`, `Sol#`, `NaicsCode`, `Office`, `Type`, `PostedDate`.**
- **Live test:** streamed FY2023 (1.3 GB) here and grep'd → **66 notices self-labeling as
  SBIR Phase III / §638**, e.g. *"Intent to Award Sole Source, SBIR Phase III Contract,
  Solar Powered Tent System"*, *"Notice of Sole Source Award - Air Force SBIR/STTR program"*.
  Each row has awardee + award# + description in-line.

**This is the self-labeling ground-truth source that the API couldn't deliver.** ~66/recent
year × ~8 SBIR-era years ≈ several hundred machine-extractable, self-labeled, independent
Phase III positives (with firm + contract#) — a potential upgrade to the #481 hand-collected
293. **T1 is viable; the extractor is the next build** (parse bulk CSVs across years → firm,
contract#, description, agency for every SBIR-Phase-III-self-labeled notice).

## T4 (OT) — still blocked

OT awards live only in the Contract Awards API (needs a system account; rate-limited on the
first call). Not in the opportunities bulk extract. Deprioritized.

## (superseded) T1 §638-J&A via personal-key API — blocked (kept for the record)

`sam_probe.sh` run from a normal network (api.sam.gov reachable there, HTTP 200, key valid).
Outcome kills both as personal-key API tasks:

- **Notice populations are tiny:** ptype=a (award notices) = **1,734** and ptype=u (J&A) =
  **~5** for all of 2024. Even unthrottled, §638-via-notices is a thin vein. First-pass J&A
  grep found **0** §638/SBIR citations in the 5 J&As.
- **Personal-key daily quota is far too small for body-mining:** ~15 calls exhausted it —
  `900804 "Message throttled out", nextAccessTime 2026-Aug-03 00:00 UTC` (a **daily** cap).
  Mining hundreds of per-notice description bodies is infeasible on this key.
- **Contract Awards API (OT) rate-limited on the first call** — effectively needs a **federal
  system account**, not a personal key.

**Decision: deprioritize T1/T4.** They would require a SAM **system account** (higher quota)
or the **free bulk Contract Opportunities extract** (no API quota) — and even then §638-notice
volume is modest. Not worth chasing on a personal key. The coverage story stands on the
rate-limit-free channels below.

`scripts/transition_coverage/sam_probe.sh` (v2: reachability + ptype census + award-notice
§638 grep + OT schema dump) is retained for anyone with a system-account key.
