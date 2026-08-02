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

## Not testable here (SAM-only → `sam_probe.sh`, off-sandbox)

- **T1 §638-J&A** (self-labeling positives) and **T4 OT awards** — api.sam.gov is IP-blocked
  from the hosted sandbox (confirmed: persists with the bash sandbox disabled). Run the probe
  script from a normal network.
