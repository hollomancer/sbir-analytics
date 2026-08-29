---
title-meta: "Observed M&A Signals among SBIR Awardees: A Lower-Bound Analysis of SEC Form D and EDGAR Full-Text Filings"
author-meta: "Conrad Hollomon"
subject: "Exploratory preprint on observed M&A signals among SBIR awardees"
keywords:
  - SBIR
  - technology transition
  - M&A
  - Form D
  - entrepreneurial finance
papersize: letter
fontsize: 11pt
geometry:
  - margin=1in
  - footskip=0.45in
linestretch: 1.08
colorlinks: true
linkcolor: black
urlcolor: blue
header-includes:
  - |
    \usepackage{fancyhdr}
    \usepackage{booktabs}
    \usepackage{longtable}
    \usepackage{microtype}
    \usepackage{setspace}
    \usepackage{titlesec}
    \usepackage{enumitem}
    \setcounter{secnumdepth}{0}
    \pagestyle{fancy}
    \fancyhf{}
    \fancyfoot[L]{\scriptsize Version 1.0.0}
    \fancyfoot[C]{\scriptsize DOI: [UNVERIFIED \textemdash{} human review]}
    \fancyfoot[R]{\scriptsize \thepage}
    \renewcommand{\footrulewidth}{0.4pt}
    \setlength{\headheight}{14pt}
    \setlist{nosep,leftmargin=*}
---

\begin{titlepage}
\centering
\vspace*{0.7in}

{\LARGE\bfseries Observed M\&A Signals among SBIR Awardees\par}
\vspace{0.2in}
{\Large A Lower-Bound Analysis of SEC Form D and EDGAR Full-Text Filings\par}

\vspace{0.65in}
{\large Conrad Hollomon\par}
\vspace{0.08in}
{\normalsize Independent researcher\par}
{\normalsize \href{mailto:hollomancer@protonmail.ch}{hollomancer@protonmail.ch}\par}

\vspace{0.45in}
{\normalsize Version 1.0.0\par}
{\normalsize August 2026\par}

\vfill
\begin{minipage}{0.84\textwidth}
\small
\textbf{Independence statement.} This work was conducted in a personal capacity and does not represent the position of any agency.

\vspace{0.14in}
\textbf{Evidence status.} This package preserves a dated, exploratory repository finding. It does not promote the analysis to validated or citable evidence under the repository's study rules.

\vspace{0.14in}
\textbf{License.} Copyright 2026 Conrad Hollomon. The paper is licensed under CC BY 4.0. Repository code remains licensed under MIT.

\vspace{0.14in}
\textbf{Deposit status.} Prepared for a human-created Zenodo record. DOI: [UNVERIFIED — human review].
\end{minipage}

\vspace{0.3in}
\thispagestyle{fancy}
\end{titlepage}
\setcounter{page}{2}

# Abstract

Public records do not provide a complete ledger of what happens to firms after SBIR awards. This descriptive study links a committed 34,460-firm SBIR denominator to two SEC-based acquisition-signal channels: Form D business-combination records and EDGAR EFTS full-text mentions. The headline measure includes high- and medium-confidence detections only. It is a lower bound on observed acquisition signals, not a census of transactions. Firms without a detected event are treated as not-yet-observed.

The committed results identify 2,790 firms with high- or medium-confidence M&A signals, an observed rate of 8.1 percent. Among 2,558 records with valid dates, the median interval from first SBIR award to the recorded M&A event is 15 years. HHS has the highest documented agency rate at 9.3 percent. DoD follows at 5.8 percent. Other agencies range from 2.9 percent to 4.6 percent.

Directional full-text review demoted 126 of 1,178 original medium-tier candidates. It promoted 541 of 1,450 lower-tier candidates. These diagnostics reduce clear text-direction errors. They do not establish a final out-of-sample false-positive rate. Coverage also depends on SEC filing visibility, name resolution, and varying filing windows. The results are descriptive. They do not support causal claims, policy recommendations, or claims about unobserved firms.

## Scope and status

This document packages committed repository findings. It adds no analysis and recomputes no value. Quantitative claims map to the committed-source ledger in Appendix B.

The canonical research inventory describes the M&A rate and timing findings as a dated research note. It says those figures are not approved for citation as evidence. [S4] This preprint preserves that warning. A Zenodo deposit would make the document discoverable. It would not validate the underlying detections.

\newpage

# Introduction

The first problem is not a missing outcome model. It is an unreliable outcome ledger. The repository README frames SBIR commercialization tracking this way. It notes repeated GAO concerns about the reliability of Phase III tracking. [S3] That concern motivates a separate public-record view. It does not establish the size of any missing statutory record.

This paper asks a narrower question. Which SBIR awardees have an observable acquisition signal in SEC records? It also asks when that signal appears after the first SBIR award. The answer is descriptive. It does not estimate what caused an acquisition. It does not measure program effectiveness. It does not recommend a policy response.

The public record creates a structural visibility problem. Some transactions generate clear SEC filings. Other transactions do not. Private buyers, corporate layers, filing exemptions, and name changes can hide otherwise real events. The observable set is therefore a floor. It cannot support a complete transaction census.

The analysis uses two detection channels. The first channel uses Form D records marked as business combinations. The second uses EDGAR EFTS full-text search and filing context. Each channel has different strengths. Form D can identify a business-combination signal without naming an acquirer. EFTS can identify the filing company and acquisition language. It can also create more text and name-matching noise.

The committed analysis assigns accepted detections to high or medium confidence. High confidence comes from a Form D business combination or an EFTS subsidiary signal. Medium confidence comes from acquisition language near the SBIR company name. Directional review separates a named target from a company that acquired something else. Lower-tier candidates remain outside the headline measure.

The denominator is also bounded. The committed findings define it as 34,460 SBIR companies in the awards database. [S1] This paper preserves that number. It does not rebuild the award file or change the company frame. The exact frozen input bytes and denominator hash are [UNVERIFIED — human review].

The central result is an observed lower bound. The committed note reports 2,790 high- or medium-confidence firm detections. It reports an 8.1 percent observed rate. [S1] A firm without a detected event is not-yet-observed. That label carries no claim about the firm's actual transaction history.

The timing result also needs restraint. The committed median is 15 years from first SBIR award to the recorded M&A event. [S1] Filing dates and mention dates do not always equal transaction dates. The paper therefore treats timing as recorded-event timing, not a precise corporate-history clock.

This framing keeps the paper within its evidence. It reports what the two SEC channels observed. It also reports the known ways those channels can fail. The result is useful as a public-record map. It is not a complete ledger.

\newpage

# Data and Methods

## Denominator construction

The committed findings document defines the denominator as 34,460 SBIR companies in the awards database. [S1] This packaging task preserves that denominator without alteration.

The repository links awardees across sources through company identifiers and normalized names. It also states that entity resolution is probabilistic. [S3] The paper does not reconstruct that process. It treats the committed company-level frame as the analysis denominator.

The exact award snapshot, transformation ledger, and byte-level denominator hash are not committed. Their status is [UNVERIFIED — human review]. The quantitative denominator remains traceable to the committed findings document.

## Two-tier detection rule

The headline measure uses only high- and medium-confidence detections. Lower-tier candidates do not count as observed M&A events.

| Accepted tier | Detection rule | Primary source |
|---|---|---|
| High | Form D business-combination flag, or EFTS subsidiary evidence | Form D XML and EDGAR EFTS |
| Medium | Acquisition language near the company name, after directional text review | EDGAR EFTS full text |

The Form D layer includes 552 companies with a business-combination flag. [S1] The final accepted set contains 1,197 high-confidence and 1,593 medium-confidence detections. [S1]

Form D and EFTS reveal different facts. Form D can identify a target-side combination signal. It often lacks the acquirer's identity. EFTS can identify the filing company and text context. It also admits customer, competitor, lease, and comparator mentions. [S1; S2]

## Directional false-positive diagnostic

The medium-tier diagnostic began with 1,178 candidates. Review classified 662 as confirmed targets and 390 as ambiguous. It demoted 126 candidates, or 11 percent. [S1]

The same review then examined 1,450 lower-tier candidates. It promoted 541 confirmed targets, or 37 percent. [S1] These promotions produced the final medium tier.

A separate upstream mention-noise screen characterized name and text collisions. It removed 670 of 7,548 companies with filing mentions, or 8.9 percent. [S2] Common error patterns included short acronyms, ordinary words, generic business terms, and containment matches.

These checks do not estimate final cohort accuracy. A final out-of-sample name-match false-positive rate is [UNVERIFIED — human review]. The paper therefore reports confidence tiers and observed signals. It does not claim event-level ground truth.

## Interpretation rule

Every result is a lower bound on detected, SEC-visible acquisition signals. A detected signal can still describe a distressed sale, asset purchase, or other non-growth transaction. [S1]

A missing signal has one meaning: not-yet-observed. It does not identify a surviving independent firm. It also does not identify a failed firm.

# Results

## Observed acquisition-signal rate

The accepted high-plus-medium set contains 2,790 firms. The committed denominator contains 34,460 firms. The documented observed rate is 8.1 percent. [S1]

| Measure | Committed result |
|---|---:|
| SBIR firm denominator | 34,460 |
| High-confidence detections | 1,197 |
| Medium-confidence detections | 1,593 |
| High-plus-medium detections | 2,790 |
| Observed high-plus-medium rate | 8.1 percent |

This rate is not a transaction census. It is the share of the committed firm frame with an accepted SEC signal.

## Agency patterns

HHS has the highest documented high-plus-medium rate at 9.3 percent. DoD follows at 5.8 percent. [S1] Other documented agencies range from 2.9 percent to 4.6 percent. [S1]

The pattern is descriptive. Agency portfolios differ by sector, firm age, filing behavior, and SEC visibility. The analysis does not isolate those factors.

## Recorded time to acquisition signal

The committed findings include 2,558 accepted records with valid dates. [S1] Their median interval is 15 years from first SBIR award to the recorded M&A event. [S1]

The documented interquartile range runs from 8 years to 24 years. The documented mean is 16.4 years. [S1] These values describe recorded dates. They do not prove the exact legal closing date for each transaction.

# Limitations

## SEC-visibility floor

SEC records do not cover every private transaction. Form D and EFTS create an observed lower bound. The repository uses the same lower-bound rule for disclosed ownership and private capital. [S4]

Not-yet-observed firms can include firms with undisclosed, private, renamed, or poorly matched events. They can also include firms with no completed transaction. The method cannot separate those groups.

## Name and identity error

Company names collide across filings. Acronyms, generic terms, corporate suffixes, and subsidiaries increase this risk. The repository applies score, containment, distinctive-word, address, and person checks. [S2]

The upstream diagnostics characterize known noise. They do not provide a final blinded accuracy estimate for the accepted M&A cohort. That final rate remains [UNVERIFIED — human review].

## Medium-tier ambiguity

The committed note estimates medium-tier precision at approximately 65 to 70 percent. It also retains 390 ambiguous records with acquisition language but unresolved direction. [S1]

The medium tier therefore improves coverage at a known cost. Results should always identify the high-plus-medium filter.

## Coverage windows

EFTS coverage begins around 2001. Form D coverage spans 2009 through 2025 in the committed note. [S1] Older events can be absent. Recent records can use current filing activity as the event date.

The note warns that the 2025-2026 spike likely reflects latest-mention dates. [S1] This issue limits recent timing interpretation.

## Denominator reproducibility

The denominator and all headline values are traceable to committed documents. The underlying award and SEC input bytes are not committed. [S3] The exact frozen input hashes are [UNVERIFIED — human review].

This package pins the repository state and source documents. It does not claim full data-level reproducibility.

## Scope of inference

The study is descriptive. It does not identify causal effects. It does not compare detected firms with a valid control group. It does not support policy recommendations.

The analysis also does not estimate missing statutory Phase III records. The GAO framing motivates the ledger problem only.

# Appendix A. Reproducibility Pin

## Repository state

| Item | Pinned value |
|---|---|
| Repository | `https://github.com/hollomancer/sbir-analytics` |
| Repository release tag | `v0.11.0` |
| Repository commit | `241fe9d763309aabc28eb6d0cf85bb536c9289e8` |
| Paper version | `1.0.0` |
| Source draft | `docs/research/sbir-ma-exit-analysis.md` |
| Source draft blob | `81cabe1175711b36ff1bce778b0e0d5b61f5dc62` |

The paper cites the repository as its code and method supplement. The repository's `CITATION.cff` names this paper as its preferred research citation.

## Packaging procedure

This task did not run an analysis pipeline. It copied and narrowed committed findings into a public-preprint format.

The Markdown source is `studies/sbir-ma-exits/paper.md`. The PDF build command is:

```bash
pandoc studies/sbir-ma-exits/paper.md \
  --pdf-engine=xelatex \
  --output studies/sbir-ma-exits/paper.pdf
```

A human must reserve the Zenodo DOI. The human must then replace the DOI footer marker and rebuild the PDF.

# Appendix B. Committed-Source Ledger

All quantitative claims in this paper map to one of these committed sources. `CLAIM_PROVENANCE.md` gives a claim-level table.

**[S1]** `docs/research/sbir-ma-exit-analysis.md`, blob `81cabe1175711b36ff1bce778b0e0d5b61f5dc62`. This source supports the denominator, confidence counts, observed rate, agency pattern, timing distribution, directional review, coverage windows, and stated precision limits.

**[S2]** `docs/research/sec-edgar-sbir-learnings.md`, blob `4b44454c550850e5983cf06e968f1c6444c31993`. This source supports the matching design, collision examples, mention-noise screen, and Form D matching limitations.

**[S3]** `README.md`, blob `08493598fd9692872071a45a631e351125e93c32`. This source supports the ledger-reliability framing, probabilistic entity-resolution warning, data-availability limit, and personal-capacity context.

**[S4]** `docs/research-questions.md`, blob `ddc056117a847987b236a5718ffd5c976cd87ec8`. This source supports the lower-bound interpretation and the exploratory, not-approved-for-citation status.

**[S5]** `specs/archive/completed-features/merger_acquisition_detection/requirements.md`, blob `934b664146f668183219062fd952d9d2b79c52a3`. This source links the implemented detection work to the dated findings document.

# Author Statement and License

Conrad Hollomon is the sole author. The author lists no employer affiliation.

This work was conducted in a personal capacity and does not represent the position of any agency.

The paper is licensed under the Creative Commons Attribution 4.0 International License. Repository code remains under the MIT License.
