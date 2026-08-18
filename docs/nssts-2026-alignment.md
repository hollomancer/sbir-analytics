---
Type: Explanation
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-18
Status: active
---

# NSSTS 2026 alignment

## Overview

The [National Security Science and Technology Strategy][nssts] (NSSTS), issued August 2026
by the Office of Science and Technology Policy, updates the federal list of critical and
emerging technologies (CETs) relevant to national security. This document records what the
strategy changes for this repository, what it deliberately does not change, and which
claims it does and does not license.

The strategy satisfies 42 USC 19221 (Sec. 10612 of the CHIPS and Science Act) and supports
the 2025 National Security Strategy. It is organized into four pillars — focus, resilience,
agility, and protection — plus an implementation section and two appendices.

## What the repository takes from it

Only the two appendices carry data this repository can act on.

**Appendix A** lists 14 CET areas and states that it "constitutes an update to the OSTP
list of CETs relevant to U.S. national security." The areas are:

advanced manufacturing and materials; artificial intelligence (AI) and autonomy;
biotechnology; communications and networking; directed energy; future computing
technologies; hypersonics and advanced missile technologies; information management and
cybersecurity; nuclear energy; positioning, navigation, and timing (PNT); quantum
information technologies; semiconductors and microelectronics; sensing and signature
management; space technologies.

**Appendix B** aligns those 14 areas against eight priority national security needs,
grouped under battlefield advantage (space/air/long-range strike; undersea; national
security AI and autonomy), homeland defense (border security; nuclear deterrence and
missile defense; cyber defense; biological weapons defense), and leadership in
transformative emerging technology. A parenthesised mark in the source table means the
implication "[has] yet to emerge but [is] on the horizon"; both levels are preserved as
`current` and `horizon`.

Both appendices are encoded in [`config/cet/defense_crosswalk.yaml`](../config/cet/defense_crosswalk.yaml)
under the `nssts_cet14` target taxonomy and the `nssts_mission_needs` table, versioned
`NSSTS-CET-14-2026`.

## Why this is a crosswalk, not a taxonomy replacement

NSSTS supersedes prior OSTP CET lists *for national-security scoping*. It does not
replace the canonical 21-area `NSTC-2025Q1` taxonomy this repository uses, for two
reasons.

First, the strategy scopes its list deliberately narrowly: CETs are "a subset of advanced
technologies that are or may become critically important to U.S. national security. This
is a narrower focus than listing all technologies relevant or even important to national
security." This repository classifies the full SBIR/STTR portfolio across NIH, NSF, DOE,
and other civilian agencies, where a national-security-scoped list would misclassify or
drop a large share of awards.

Second, the canonical taxonomy is versioned to support longitudinal analysis, and the
trained CET classifier and the `CET-RULES-2026Q3` screening classifier are both fitted
against it. Swapping the canonical list would invalidate existing classifications without
answering any question the crosswalk cannot.

The crosswalk follows the pattern already established for `DOD-CTA-14-2022` and
`DOD-SC-8-2022`: many-to-many, with each mapping recording `direct`, `partial`, or
`enabling` strength and a rationale.

## Substantive differences from the 2022 defense list

The 2026 list is not a renaming of `DOD-CTA-14-2022`. Three changes matter for analysis:

- **Renewable energy generation and storage is dropped.** It was a named DoD critical
  technology area in 2022. NSSTS retains `nuclear energy` only, and its resilience
  discussion reaches energy through "microgrids powered by advanced nuclear reactors."
  The canonical `renewable_energy_generation_and_storage` CET maps to no NSSTS area.
- **PNT is added** as a standalone area. The canonical 21-area taxonomy has no PNT
  entry, so PNT is reached only through `enabling` mappings from quantum information
  science, space technologies, and networked sensing.
- **AI and autonomy are merged** into one area, collapsing what the canonical taxonomy
  splits across `artificial_intelligence`, `autonomous_systems`, and
  `trusted_ai_and_autonomy`.

Four further canonical areas reach NSSTS only partially or as enablers: advanced gas
turbine engine technologies, financial technologies, human-machine interfaces, and
integrated sensing and cyber.

## Deriving mission profiles

`DefenseTaxonomyCrosswalk.mission_needs_for()` returns the priority needs a canonical CET
aligns with. Appendix B publishes alignment against the strategy's own 14 areas, not
against the canonical 21, so a canonical CET inherits a mission profile only through a
`direct` mapping by default. A `partial` or `enabling` mapping means the two areas are not
equivalent, and carrying the full mission profile across would overstate what the source
table supports. Callers that want a wider reading must opt in explicitly via `strengths`.

Consequently five canonical areas carry no mission profile: the four partial/enabling
areas above plus renewable energy. Their dollars appear in the CET rollups of the DoD
supply-chain report but not in its mission-need rollup.

## What NSSTS does not license

**The strategy does not mention SBIR, STTR, or small business innovation programs.** It
reaches small firms twice, both under Strategy Implementation: agencies should enable
"small and nontraditional entities" to access federal R&D infrastructure, and should
establish "streamlined pathways for companies, including small and non-traditional
performers" to secure CRADAs and Agreements for Commercializing Technology. Neither names
a program. Do not cite NSSTS as endorsing, prioritizing,
or evaluating SBIR/STTR, and do not present the crosswalk as evidence that the strategy
takes a position on SBIR transition rates or commercialization outcomes. The crosswalk
aligns technology areas only.

The strategy likewise sets no measurement framework, defines no outcome metric, and names
no transition benchmark. Its acquisition discussion (Pillar 3) endorses Other Transaction
Authorities and milestone-based fixed-cost contracting without reference to Phase III.

## Epistemic tier

The crosswalk is `pipelines` tier: deterministic, reproducible from the cited source, and
validated at load time for complete canonical coverage, target referential integrity, and
mission-need referential integrity. The mappings themselves are analyst judgment, recorded
with rationales so a reviewer can disagree with a specific row.

Rollups built on it are contextual overlays, not funding allocations. Because the mapping
is many-to-many, dollars repeat across targets and rows are **not additive**.

## Related documentation

- [CET configuration](../config/cet/README.md)
- [Epistemic tiers](steering/epistemic-tiers.md)
- [Research questions](research-questions.md) — Section A, national security and
  industrial base
- [DoD supply chain initial analysis](research/dod_supply_chain_initial_analysis.md)

[nssts]: https://www.whitehouse.gov/wp-content/uploads/2026/08/NSSTS-082026.pdf
