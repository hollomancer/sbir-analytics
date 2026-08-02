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

## Full-sweep consolidated set + cross-validation vs #481 (FY2015–2025)

`consolidate_selflabeled.py` over all 11 years → committed artifacts in `collected/`:
- **66 firm-named positives** (55 award + 11 intent — intent recovered via Description
  firm-parsing, `firm_from_notice`), **59/66 (89%) resolve to a real SBIR firm** (self-label
  precision), **18 agree with #481** (independent methods converging → confidence),
  **48 net-new** (expands #481's 293 by ~16%).
- **130 Sources Sought** forward-opportunity records (`..._forward_feed.csv`) — addresses
  #481's open forward-validation gap.

**Detector check (FY2020–24 pilot, n=21):** frozen detector on the rich notice text scored
p@1 0.429 / p@3 0.714 — indistinguishable from the 0.467 baseline. **The set improves the
LABELS, not the detector's score** (notice text is FAR procurement boilerplate, not
abstract-matching tech content).

**Does it improve the detector as-is? No evidence.** Frozen detector (word-TFIDF dominant
signal) on the rich self-labeled notices: **p@1 0.429, p@3 0.714 (n=21)** — indistinguishable
from the 0.467 baseline. The same-firm rich-vs-terse head-to-head was impossible (0 SAM award#s
matched `phase3_universe`). Root cause: the notice Descriptions are long but mostly **FAR
procurement boilerplate**, not tech content that matches the abstract — length ≠ discriminating
text, and decoys share the boilerplate. **Value is in the LABELS (validated + expanded ground
truth), not a detector lift.**

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

**Built:** `scripts/phase3_benchmark/extract_phase3_selflabeled.py` (reuses
`pull_gsa_archive`'s streaming/columns; swaps seed-attribution for a self-label regex;
tested, ruff-clean).

**Actual yield (FY2023+FY2024), classified by `notice_class` — richer than first written:**
the extractor tags each self-labeled notice, and the pre-award notices are *signal*, not noise:

| class | FY23+24 | what it is |
|---|---|---|
| `award` | 12 | confirmed Phase III (firm + contract#) — **retrospective positive** |
| `intent_sole_source` | 15 | pre-award intent *naming the firm* — **near-certain forward positive** |
| `sources_sought` | 43 | open Phase III need — **forward-opportunity feed (the packet's real input)** |
| `other` | 26 | self-labeled but no firm/award |

- **Firm-named positives = award + intent = 27 over 2 yrs (~13–14/yr) → ~100–130 across SBIR-era
  years** — e.g. Advanced Strategic Insight `W50S6N-23-P-0011`; North Star Scientific "Phase III
  Basic Ordering Agreement"; Progeny Systems `N6134023C0007`. (Corrects an earlier award-only
  "~6/yr" undercount — the intent-to-sole-source notices are firm-named positives too.)
- **Sources Sought = a forward Phase III opportunity feed** — directly addresses the
  forward/open-solicitation validation gap #481 left explicitly open.

**Value (right-sized):** a **self-labeled, SAM-sourced, provenance-diverse** independent set —
~100–130 firm-named positives (cross-validation complement to #481's 293) **plus** a standing
forward-opportunity feed. Run the full sweep with `--years 2015 … 2025`.

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
