# Literature corpus triage — which roadmap order each document serves

**Corpus.** 51 PDFs, 2,112 pages, report-years 1990–2022,
supplied by the maintainer on 2026-09-17 after sbir.gov refused non-browser clients. Per-document
inventory with page counts, text-quality scores, and SHA-256 hashes:
[`literature-corpus-inventory.csv`](literature-corpus-inventory.csv).

## Headline

The corpus is **deep on Order 1 and thin everywhere else**. It could support extending the SBA
annual-report replication from three report-years to a **1990–2022 panel, after OCR and after the
absent table definitions are settled**. That extension is not a finished product: 19 of the 51
documents have no text layer, and the published-sample replication of [L18] (three report-years)
stays separate from any historical extension. It contributes benchmark sources to Orders 3 and 5, and
**nothing at all** to Orders 2, 4, 6, 7, and 8.

| Order | Study | Docs | Pages | Extractable now |
| ---: | --- | ---: | ---: | ---: |
| 1 | SBA annual-report tables [L18] | 46 | 1,983 | 27 |
| 3 | DoD economic-impact studies [L19] — benchmark context only | 3 | 109 | 3 |
| 5 | Agency economic-impact context — NASA (2017), NCI [L20] | 2 | 20 | 2 |
| 2, 4, 6, 7, 8 | — | 0 | 0 | 0 |

## The binding constraint is OCR, not availability

**19 of 51 documents (616 pages) have no text layer at all** — 0 extractable
characters per page. They are image-only scans and need page rendering plus vision extraction,
which is a materially different job from parsing a text layer: it cannot be validated by the
internal-identity checks that made the FY22 capture trustworthy, and every figure needs
independent verification.

The split falls along an awkward line:

- **`sttr_annual_report_series` (FY1994–FY2008, 15 docs): text layer present.** Usable now.
- **`sbir_annual_report_series` (FY1990–FY2008, 19 docs): image-only.** This is the entire
  pre-2009 SBIR-program series, including all four years (1990–1993) that exist in no other form.

So for FY1994–FY2008 the STTR half of the program is extractable and the SBIR half is not. A
combined SBIR+STTR panel before FY2009 requires OCR; an STTR-only panel does not.

**Report-years extractable without OCR (27):** 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022.

Note FY2010 and FY2011 have no standalone report; they are covered by the consolidated
FY2009–FY2011 volume, so the span has no true gap.

Text quality for the 32 documents with a text layer was scored by stopword density
(all fall in 0.18–0.28, i.e. all readable prose) and a garbage-token rate (0.01–0.05). The two
measures do not separate cleanly into tiers, so the inventory records the scores per document
rather than asserting a hard clean/noisy boundary. One caution: `STTR_1994` renders its title as
"$TTR", a title-page glyph error rather than a document-wide problem (garbage rate 0.03).

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
recorded in [source-acquisition-orders-3-5.md](source-acquisition-orders-3-5.md). The Navy (2000–2013) and USAF (FY2015) volumes are the same TechLink family at component
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
hand-label validation is gated, so these serve as published-outcome targets rather than
validation data.

## What this corpus does not advance

- **Order 2** needs the CSIS entrant/graduation analysis [L32] and GAO concentration benchmarks [L14].
- **Order 4** needs the NASEM agency patent-cost tables [L3–L6].
- **Order 6** needs the repeat-awardee outcome sources [L41].
- **Order 7** needs the AEA replication package and licensed inputs for [L9].
- **Order 8** needs data-use approval and original replication packages.

None of those are in the corpus, and none are obtainable by supplying more SBA documents.

## Recommended sequencing

1. **Decide the four undetermined FY22 definitions first.** State attribution, the
   first-time-winner lookback, amendment handling, and zero-dollar records are absent from the FY22
   source. Extending the panel before settling them multiplies the same ambiguity across
   27 years instead of resolving it once. Whether the older reports state what FY22 omits
   is itself worth checking — the earlier volumes are often more explicit about methodology.
   The Order 1 start gate requires these decisions, not only captured PDFs.
2. **Then extend Order 1 across the 27 OCR-free report-years.** The FY22 capture established the
   extraction and validation pattern; the FY2009–FY2022 volumes are structurally similar and should
   follow directly. Once the definitions are frozen, this is the highest-value extension and needs
   no new extraction capability.
3. **Treat the 19 image-only documents as a separate capability**, not a continuation. They
   would extend the panel to 1990 and complete the pre-2009 SBIR series, but the
   extraction cannot be validated the same way.
4. **Read Order 3's DoD volume for its multiplier definition** before building anything against it.
