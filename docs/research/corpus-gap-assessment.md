# What the corpus still needs

Assessment of the supplied document corpus against the analyses that depend on it, written after
extending the annual-report replication from three report-years to six. Ranked by what each item
unlocks, not by effort.

## What is already held

51 documents, 2,112 pages:

| Series | Documents | Text layer |
| --- | ---: | --- |
| SBA consolidated annual reports, FY2009-FY2022 | 12 | 10 clean, 2 OCR-noisy |
| SBIR annual reports, 1990-2008 | 19 | **all image-only** (616 pages) |
| STTR annual reports, 1994-2008 | 15 | 13 clean, 2 OCR-noisy |
| Agency economic-impact studies | 5 | 4 clean, 1 OCR-noisy |

The consolidated series has **no year gaps** from FY2009 to FY2022 (FY2010 and FY2011 sit inside the
FYs 2009-2011 volume). State-and-territory tables exist from FY2012 onward: FY2012 prints a state
total only, FY2013-FY2022 print the full jurisdiction-by-program-by-phase grid.

## Ranked gaps

### 1. The FY2023 and FY2024 annual reports - highest value

The corpus stops at FY2022. The pinned export already holds **6,325 awards for award-year 2023 and
6,412 for 2024**, so the data side is ready and only the published tables are missing. Both years
would fall inside the stated-basis era, taking the usable panel from six report-years to **eight**,
and they sit at report ages 2 and 3 - the youngest end, where post-publication drift should be
smallest and where the committed one-sided +3% band has the most headroom. The band's tightest
observation is FY2016 at +2.92%, so the informative test is whether young years stay near the
bottom of the band as FY2022 (+0.85%) does.

**Access:** sbir.gov returns HTTP 403 to non-browser clients, so this needs a browser download, the
same route by which the FY2020-FY2022 volumes arrived. Nothing else in this list has a better
value-to-effort ratio.

### 2. Two image-only tables - work rather than acquisition

No OCR engine is installed (no tesseract, ocrmypdf, pdftoppm or ghostscript, and no pytesseract or
easyocr), and package metadata for them is not reachable from this environment. That does not block
the work: `pypdfium2` and PIL are present and rasterise these pages cleanly, and the extracted rows
can be checked against the tables' own internal identities - SBIR total equals Phase I plus Phase
II, likewise STTR, and combined equals SBIR plus STTR - which is the same validation every
text-layer year already passes. An extraction that satisfies all three identities on every row is
trustworthy without a second opinion.

- **FY2019** states the count basis, so it belongs in the panel. Its table is an embedded image on
  one page and renders legibly. **It covers only AK through MS - 27 jurisdictions of the 53 the
  neighbouring years print.** No continuation page exists anywhere in the volume. FY2019 can
  therefore support a cell-level comparison on those 27 jurisdictions but **cannot** contribute a
  year total, so it does not close the gap in the FY2016-FY2022 run the way a complete table would.
- **FY2015** has six consecutive image-only pages following its state-table narrative, so the table
  is probably present and complete. It predates the basis statement, so it is descriptive only and
  must not enter a tolerance envelope.

### 3. SBA's table-construction methodology for the pre-FY2016 years

The single acquisition that would most improve the panel's *quality* rather than its length. It
would settle what the FY2013 and FY2014 tables count, and if their basis turns out to match the
later convention it would return two more report-years to the envelope. The corpus contains SBA's
assembly rule (FY2016 p39, that the report is a summation of individual uploaded awards) but nothing
on how the state tables themselves were constructed before the basis sentence appeared. Candidate
sources: SBA's agency data-call instructions for those years, or a methodology annex.

### 4. The sbir.gov impact reports

Listed at sbir.gov/impact/impact-reports and confirmed unreachable: `data.www.sbir.gov`, the host
that serves the award export with a clean 200, returns 403 on the `/impact/` path. That is
sbir.gov's own content policy, not a sandbox restriction, so no network grant changes it. These bear
on the commercialization questions rather than on this study, and need a browser download.

### 5. Four closed-access works

Needed for roadmap orders 3 and 5, with no open-access copy in Unpaywall, Semantic Scholar, PMC or
CrossRef, and no `best_oa_pdf_url` in OpenAlex. Identifiers verified: NASEM 2026
`10.17226/29329`, NRC 2014 `10.17226/18821`, Rovito `10.1007/s10961-024-10141-2`, and Research
Policy 54(9) 2025 `10.1016/j.respol.2025.105302`. The two National Academies volumes offer free PDFs
from nap.edu behind a sign-in. Recorded in `source-acquisition-orders-3-5.md`.

### 6. The 1990-2008 SBIR volumes, with a cheap test first

Nineteen image-only documents, 616 pages, covering nineteen report-years of deep history. **Do not
commit to extracting all of them yet.** The STTR volumes of the same era do carry text, and probing
all fifteen found **no state-and-territory table in any of them** - no page even mentions awards by
state. Whether the SBIR volumes of that era print such a table is therefore unknown rather than
assumed. Rasterising two or three of them and looking is a few minutes of work and decides whether
the remaining 600-odd pages are worth extracting. Either way these years predate the basis statement
by more than a decade, so their value is long-run description, not replication.

## What would not help

- **More export vintages.** Award-year counts for 2012 through 2018 are identical across all three
  vintages held (2026-05-11, 2026-08-30, 2026-09-17). Those years have stopped moving, so another
  vintage adds nothing for this panel.
- **A report-era export.** Permanently unavailable - SBIR.gov serves only the current snapshot. This
  is what keeps the published-sample outcome at `blocked` and cannot be fixed by acquisition.
- **The pre-2009 STTR volumes** for state-level work, as above.

## Suggested order

1. Ask for the FY2023 and FY2024 reports - two years of panel for one browser download.
2. Rasterise and read FY2019's partial table; add its 27 jurisdictions at cell level only.
3. Spot-check two or three 1990s SBIR volumes for a state table before committing to the rest.
4. Everything else is acquisition-bound and can wait on someone outside this environment.
