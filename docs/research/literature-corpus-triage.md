# Literature corpus triage — which roadmap order each document serves

**Corpus.** 51 PDFs, 2,112 pages, report-years 1990–2022,
supplied by the maintainer on 2026-09-17 after sbir.gov refused non-browser clients. Per-document
inventory with page counts, text-quality scores, and SHA-256 hashes:
[`literature-corpus-inventory.csv`](literature-corpus-inventory.csv).

## Headline

The corpus is **deep on Order 1 and thin everywhere else**. It does not support a 1990–2022
replication panel. The [extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md) finds extractable state tables in eight
report-years, and six of them usable for the replication (FY2016–FY2022, less FY2019). The image-only
pre-2009 SBIR volumes carry state tables, but they support long-run description only, not the
replication. The published-sample replication of [L18] (three report-years) stays separate from
any extension. The corpus contributes benchmark sources to Orders 3 and 5, and **nothing at all**
to Orders 2, 4, 6, 7, and 8.

| Order | Study | Docs | Pages | Text layer |
| ---: | --- | ---: | ---: | ---: |
| 1 | SBA annual-report tables [L18] | 46 | 1,983 | 27 |
| 3 | DoD economic-impact studies [L19] — benchmark context only | 3 | 109 | 3 |
| 5 | Agency economic-impact context — NASA (2017), NCI [L20] | 2 | 20 | 2 |
| 2, 4, 6, 7, 8 | — | 0 | 0 | 0 |

## The binding constraint is OCR, not availability

**19 of 51 documents (616 pages) have no text layer at all** — 0 extractable
characters per page. They are image-only scans and need page rendering plus vision extraction,
which is a materially different job from parsing a text layer. The internal-identity checks used
for the FY22 capture remain necessary, but they are not sufficient for image extraction: every
figure also needs independent verification against the rendered source line.

The split falls along an awkward line:

- **`sttr_annual_report_series` (FY1994–FY2008, 15 docs): text layer present.** Usable now.
- **`sbir_annual_report_series` (FY1990–FY2008, 19 docs): image-only.** This is the entire
  pre-2009 SBIR-program series, including all four years (1990–1993) that exist in no other form.

So for FY1994–FY2008 the STTR volumes carry text and the SBIR volumes do not. No STTR volume of
that era prints a state table, so a text layer does not give a pre-2009 state panel. The SBIR
volumes do print one, but only after OCR, and only for the SBIR program.

**Report-years whose document has a text layer (27):** 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022.
A text layer does not mean the state table is in it. The FY2015 and FY2019 state tables are
embedded images; see [corpus-gap-assessment.md](corpus-gap-assessment.md) and the
[extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md).

Note FY2010 and FY2011 have no standalone report; they are covered by the consolidated
FY2009–FY2011 volume, so the span has no true gap.

Text quality for the 32 documents with a text layer was scored by stopword density
(all fall in 0.18–0.28, i.e. all readable prose) and a garbage-token rate (0.01–0.05). The
inventory's `tier` column and the gap assessment's text-layer table do draw a clean/noisy line
(27 `clean_digital`, 5 `ocr_noisy`). The two measures do not separate cleanly, so treat that line
as a working label and use the per-document scores when the distinction matters. One caution:
`STTR_1994` renders its title as "$TTR", a title-page glyph error rather than a document-wide
problem (garbage rate 0.03).

## Order 3 — DoD follow-on multiplier benchmarks

Three documents, all with text layers, all agency-run economic impact studies:

| Document | Span | Pages |
| --- | --- | ---: |
| DoD SBIR Economic Impacts | 1995–2018 | 50 |
| USAF SBIR/STTR Economic Impact Study | FY2015 | 36 |
| Navy SBIR/STTR National Economic Impacts | 2000–2013 | 23 |

**These are [L19]-family studies, and they do not measure the quantity Order 3 replicates.** The
DoD volume is [L19] itself — TechLink / Montana State, *National Economic Impacts from the DOD
SBIR/STTR Programs, 1995–2018* — reporting 22:1 total-output ROI and 8.4:1 sales ROI. Order 3
replicates the NASEM ratio of non-SBIR DoD obligations to SBIR/STTR obligations, >4:1 for 2012–2020
([L1], with [L2] as the earlier baseline). Output ROI and an obligations ratio are different
estimands with different denominators, and neither is a decomposition of the other.

**Order 3 therefore has no corpus document.** [L1] and [L2] are not in this corpus and must still be
recovered. Their DOIs, the retrieval routes already exhausted, and the remaining acquisition route are
recorded in [source-acquisition-orders-3-5.md](source-acquisition-orders-3-5.md). A standing
assessment of what the corpus still needs, ranked by what each acquisition unlocks, is in
[corpus-gap-assessment.md](corpus-gap-assessment.md). The Navy (2000–2013) and USAF (FY2015) volumes are the same TechLink family at component
level, so they are internally comparable to the DoD volume but equally not NASEM inputs. Treat all
three as [L19] economic-impact benchmarks.
Note that the roadmap flags Order 3's validation spec as still `exploratory` in the registry, so
these are benchmark inputs, not a licence to promote the multiplier's evidence status.

## Order 5 — agency transition and commercialization outcomes

| Document | Year | Pages |
| --- | --- | ---: |
| NASA SBIR/STTR Economic Impact Report | 2017 | 16 |
| NCI SBIR Economic Impact Analysis | 2018 | 4 |

Both are short and agency-specific. The NCI document is a two-pager and will not carry a
replicable table set on its own. The roadmap notes label validity is unresolved for Order 5 and
hand-label validation is gated. Neither document is an Order 5 transition source; treat both as
economic-impact context only, not as published-outcome targets or validation data.

## What this corpus does not advance

- **Order 2** needs the CSIS entrant/graduation analysis [L32] and GAO concentration benchmarks [L14].
- **Order 4** needs the NASEM agency patent-cost tables [L3–L6].
- **Order 6** needs the repeat-awardee outcome sources [L41].
- **Order 7** needs the AEA replication package and licensed inputs for [L9].
- **Order 8** needs data-use approval and original replication packages.

None of those are in the corpus, and none are obtainable by supplying more SBA documents.

## Recommended sequencing

1. **The four undetermined FY22 definitions are settled.** State attribution, the
   first-time-winner lookback, amendment handling, and zero-dollar records are closed in
   [`definition-decisions.md`](../../studies/sba-annual-report-tables/definition-decisions.md),
   at the evidence levels recorded there. `sources.yaml` records `gate_satisfied: true`. Do not
   redo them; read that record before changing any of the four.
2. **The Order 1 extension is recorded.**
   [`extension-to-eight-years.md`](../../studies/sba-annual-report-tables/extension-to-eight-years.md)
   finds eight report-years with extractable state tables (FY2013, FY2014, FY2016-FY2018,
   FY2020-FY2022) and six usable on a stated count basis (FY2016-FY2022, less FY2019). FY2019 was
   recovered from its image at cell level only. Most of the 27 text-layer documents have no state
   table, so the panel does not extend to all of them. Next work follows the
   [gap assessment](corpus-gap-assessment.md).
3. **Treat the 19 image-only documents as a separate capability**, not a continuation. The
   [extension record](../../studies/sba-annual-report-tables/extension-to-eight-years.md#the-1990s-sbir-volumes-do-carry-state-tables---the-earlier-inference-was-wrong)
   found that they carry state tables and extracted FY1995. They cannot extend the replication
   panel: they are SBIR-only and state no count basis. Their value is long-run description. The
   two additive identities are a necessary check on them, not a sufficient one.
4. **Read [L1] and [L2] for the NASEM obligations-ratio definition** before building anything
   against Order 3. The DoD TechLink volume in the corpus is an [L19]-family ROI study; its 22:1
   output ratio is not the quantity Order 3 replicates, and reading it for that definition would
   repeat the mapping error corrected above.
