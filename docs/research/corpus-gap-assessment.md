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

### 1. Two image-only tables - work rather than acquisition

No OCR engine is installed (no tesseract, ocrmypdf, pdftoppm or ghostscript, and no pytesseract or
easyocr), and package metadata for them is not reachable from this environment. That does not block
the work: `pypdfium2` and PIL are present and rasterise these pages cleanly, and the extracted rows
can be checked against the tables' own internal identities - SBIR total equals Phase I plus Phase
II, likewise STTR, and combined equals SBIR plus STTR - which is the same validation every
text-layer year already passes. Passing all three identities on every row rules out most
transcription faults but not all: a swap of two state labels that preserves each row's sums, or a
compensating digit error inside one row, passes every identity. Passing is therefore necessary for
use, not sufficient - which is what the triage means by "every figure needs independent
verification". Verification against the source line, not a second model pass, is the check.

- **FY2019** states the count basis, so it belongs in the panel. Its table is an embedded image on
  one page and renders legibly. **It covers only AK through MS - 27 jurisdictions of the 53 the
  neighbouring years print.** No continuation page exists anywhere in the volume. FY2019 can
  therefore support a cell-level comparison on those 27 jurisdictions but **cannot** contribute a
  year total, so it does not close the gap in the FY2016-FY2022 run the way a complete table would.
- **FY2015** has six consecutive image-only pages following its state-table narrative, so the table
  is probably present and complete. It predates the basis statement, so it is descriptive only and
  must not enter a tolerance envelope.

### 2. SBA's table-construction methodology for the pre-FY2016 years

The single acquisition that would most improve the panel's *quality* rather than its length. It
would settle what the FY2013 and FY2014 tables count, and if their basis turns out to match the
later convention it would return two more report-years to the envelope. The corpus contains SBA's
assembly rule (FY2016 p39, that the report is a summation of individual uploaded awards) but nothing
on how the state tables themselves were constructed before the basis sentence appeared. Candidate
sources: SBA's agency data-call instructions for those years, or a methodology annex.

### 3. The sbir.gov impact reports

Listed at sbir.gov/impact/impact-reports, which returns 403 to non-browser clients (sbir.gov's own
policy, not a sandbox restriction). **Not a new file set.** The page lists the five agency
economic-impact PDFs already in the 51-document inventory (DoD 1995-2018, Navy 2000-2013, USAF
FY2015, NASA 2017, NCI 2018) and a National Academies link that is gap 4. Nothing remains to fetch
here; kept as a record that the page was checked.

### 4. Four closed-access works

Needed for roadmap orders 3 and 5, with no open-access copy in Unpaywall, Semantic Scholar, PMC or
CrossRef, and no `best_oa_pdf_url` in OpenAlex. Identifiers verified: [L1] NASEM 2026
`10.17226/29329`, [L2] NRC 2014 `10.17226/18821`, [L47] Rovito `10.1007/s10961-024-10141-2`. The two
National Academies volumes offer free PDFs from nap.edu behind a sign-in.

Not yet assigned to an order: Research Policy 54(9) 2025 `10.1016/j.respol.2025.105302`, an
incidental find with unresolved authors and an unverified OA flag, not an [L#] entry. Filed the same
way in `source-acquisition-orders-3-5.md`.

### 5. The 1990-2008 SBIR volumes, with a cheap test first

Nineteen image-only documents, 616 pages, covering nineteen report-years of deep history. The
STTR volumes of the same era carry text but have **no state-and-territory table**. The spot-check of
the SBIR volumes is done: the
[extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md#the-1990s-sbir-volumes-do-carry-state-tables---the-earlier-inference-was-wrong)
found state tables in FY1995 and FY2002 and extracted FY1995. These years predate the basis
statement by more than a decade, so their value is long-run description, not replication.

## What would not help

- **More export vintages.** Award-year counts for 2012 through 2018 are identical across all three
  vintages held (2026-05-11, 2026-08-30, 2026-09-17). Those years have stopped moving, so another
  vintage adds nothing for this panel.
- **A report-era export.** Permanently unavailable - SBIR.gov serves only the current snapshot. This
  is what keeps the published-sample outcome at `blocked` and cannot be fixed by acquisition.
- **The pre-2009 STTR volumes** for state-level work, as above.

## Suggested order

1. Done: FY2019's partial table is rasterised and read at cell level only. See the
   [extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md#fy2019-recovered-partial-and-defective-in-a-second-way)
   and `studies/sba-annual-report-tables/extension/extension_fy2019_cells.csv`.
2. Done: the 1990s SBIR volumes carry state tables, and FY1995 is extracted. See the
   [extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md#the-1990s-sbir-volumes-do-carry-state-tables---the-earlier-inference-was-wrong).
   Extracting the rest is long-run descriptive work, not replication.
3. Everything else is acquisition-bound and can wait on someone outside this environment.
