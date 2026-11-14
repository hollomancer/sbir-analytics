# Source acquisition — roadmap Orders 3 and 5 (blockers B5, B6)

Records what these two orders need, the verified identifier for each, and the retrieval routes
already exhausted. Written so the next attempt starts from the remaining route rather than
repeating the search.

**Automated retrieval failed for every item below, and not because of the analysis environment's
network policy.** DOI resolution returned HTTP 200 for all of them — the landing pages are
reachable. Each is closed at the publisher, with no open-access location in Unpaywall, Semantic
Scholar, PubMed Central, or CrossRef text-and-data-mining links. Full text would require scraping a
publisher landing page, which was not attempted.

## Order 3 — NASEM DoD follow-on multiplier

Order 3 replicates the ratio of non-SBIR DoD obligations to SBIR/STTR obligations (>4:1 for
2012–2020). **Neither source is in the 51-document corpus.** The three agency economic-impact PDFs
that were previously filed here are `[L19]`-family output/sales ROI studies measuring a different
quantity; see `literature-corpus-triage.md`.

| Ref | Work | Identifier | Type | Status |
| --- | --- | --- | --- | --- |
| `[L1]` | NASEM (2026), *Review of the SBIR and STTR Programs at the Department of Defense* | `10.17226/29329` | book | closed |
| `[L2]` | NRC (2014), *SBIR at the Department of Defense* | `10.17226/18821` | book | closed |

Both are National Academies Press volumes. NAP distributes report PDFs at no cost but behind an
account and download gate on its own site, so acquisition is a browser action rather than an API
call. `[L1]` has **zero citing works** in OpenAlex as of 2026-09-17, consistent with its 2026
publication date, so there is no secondary source that restates its definitions yet.

**What Order 3 actually needs from them** is not the headline ratio, which the bibliography already
carries, but the denominator rules: which DoD obligations count as non-SBIR, whether the denominator
is extramural R/R&D or total RDT&E, and the firm-matching basis. A replication cannot be specified
from the ratio alone.

## Order 5 — agency transition and commercialization

| Ref | Work | Identifier | Type | Status |
| --- | --- | --- | --- | --- |
| `[L47]` | Rovito, Kamp, & Etemadi, *Exploring Department of the Navy SBIR Phase III awards and corresponding public sector commercialization success factors* | `10.1007/s10961-024-10141-2` | article | closed |

*The Journal of Technology Transfer*, **vol. 50, issue 4, pp. 1363–1395**; online 2024-09-24,
issue-dated 2025. The bibliography's `(2025)` is the issue year and is correct as a citation; the
2024 date is online-first. The volume, issue and page range above confirm the existing entry.

Springer subscription content. Acquisition route is institutional access.

The corpus contributes only economic-impact context to this order — the NASA (2017) study and the
NCI two-pager `[L20]` — not transition or Phase III outcome data.

## Retrieval routes tried

For each of `10.17226/29329`, `10.17226/18821`, `10.1007/s10961-024-10141-2`:

| Route | Result |
| --- | --- |
| Unpaywall | no OA location |
| Semantic Scholar | no open-access PDF (HTTP 404 for the two NAP volumes) |
| PubMed Central | no PMCID |
| CrossRef TDM | no accessible TDM link |
| DOI resolution | HTTP 200, landing page only |
| OpenAlex `best_oa_pdf_url` | null for all |

OpenAlex abstracts are also unavailable: the abstract is withheld where a work's license is not
declared, which applies to all three.

## Incidental find, not yet an `[L#]` entry

Searching citations of `[L2]` surfaced a directly relevant open-listed work:

- *A new approach to measuring invention commercialization: An application to the SBIR program.*
  *Research Policy*, vol. 54, issue 9, article 105302, 2025-08-13. DOI
  `10.1016/j.respol.2025.105302`. OpenAlex reports 7 citations.

This addresses commercialization measurement for SBIR directly, which is the subject of question
area A. Two cautions before it is cited. First, OpenAlex marks it `is_oa: true` with `oa_status:
hybrid`, but its `oa_url` is the DOI redirect and Unpaywall reports no OA location, so full text was
**not** retrievable — treat the open-access flag as unverified. Second, **author names were not
resolved**: the connector returned a three-author record with null display names, and no author is
named here rather than guessing. Resolve the authors from the DOI before adding an `[L#]` entry.
