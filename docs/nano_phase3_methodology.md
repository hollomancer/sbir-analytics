# Nanotechnology SBIR/STTR Phase II → Phase III Transition: Methodology Note

**Status:** Provisional — all figures subject to revision
**Audience:** NSET Subcommittee methodology review
**Repo branch:** `claude/nanotech-sbir-analysis`
**Generated:** (see git log for date)
**Confidence tags:** [HIGH] reproducible from data; [MED] depends on third-party data; [LOW] approximate/estimated; [UNVERIFIED] requires manual check against source document

---

## 1. Data Sources

| Source | Record type | Access | Known limitation |
|---|---|---|---|
| SBIR.gov `award_data.csv` | SBIR/STTR awards (all phases) | Local | Title/abstract completeness varies; some abstracts blank |
| USAspending Phase III prospect digest | Firm-level FPDS/FABS aggregates | Local CSV | Per-firm, not per-award; FPDS Phase III coding sparse outside DoD (GAO-24-106398) |
| SEC EDGAR M&A signals | 8-K Items 1.01/2.01 | `sec_edgar_scan.jsonl` (35k firms, complete) | A subsequent scan wrote a summary showing 0 detections due to HTTP 500 errors — that summary file is not representative; the JSONL is the authoritative source and has 99.9% cohort coverage |
| SEC Form D (high-confidence) | Regulation D capital raises | Local JSONL | High-confidence subset only; ~35% match rate for NSF cohort from prior analysis |
| USPTO PatentsView CPC codes | B82Y/B82B patent classes | Local extract `data/processed/uspto/b82_patents.csv` (built 2026-07-11) | Assignee→firm linkage is exact normalized-name match; renamed/subsidiary firms missed |
| NNI Table 5 (FY26 Supplement) | Agency nanotech SBIR/STTR totals | **UNVERIFIED reference** | Methodology not published; our classification will not reconcile exactly |

---

## 2. Cohort Definitions

### 2A. Keyword/Regex Cohort [HIGH confidence method]

Applied to: `Award Title + Abstract` (Phase II awards only)

Published term list (all case-insensitive, word-boundary anchored):

```
nanoparticle(s), nanomaterial(s), nanotube(s), nanowire(s), nanostructure(s),
nanophoton(ic|ics), nanoelectron(ic|ics), nanofabric(ation), nanolithograph(y|ic),
nanocrystal(s), nanopore(s), nanoscale, nanometer-scale, nanocomposite(s),
nanomedicine, nanosensor(s), nanolayer(s), nanofilm(s), nanoribb(on|ons),
nanofluid(s), nanocluster(s), nanocapsule(s), nanocoat(ing|ings), nanotechnology,
nano(scale|sized|enabled|structured), carbon nanotube(s), CNT(s), graphene,
fullerene(s), quantum dot(s), quantum confinement, nanocrystalline, nanostructured,
single/multi-wall(ed) (carbon) nanotube(s), MEMS, NEMS, atomic layer deposition,
ALD, molecular beam epitaxy, MBE, nanoimprint, electron-beam lithograph(y|ic),
EUV lithograph(y|ic), nanodrug(s), nano-drug(s), nano-carrier(s), nanocarrier(s),
nano-encapsul*, nanoencapsul*, sub-Xnm, angstrom-scale
```

**Methodological note:** MEMS is borderline (micro-, not nano-scale); included because
MEMS devices routinely involve nanoscale features and appear extensively in NNI reports.
CNT as bare acronym may match non-nanotech contexts; flagged but retained. Exclusion of
bare "nano" prevents matching "nanosecond" and "nanosat."

**Cohort size:** 2,849 Phase II awards (all years)
**NNI window (FY2020–2023, 9 agencies):** 377 awards

---

### 2B. CET Keyword Proxy Cohort [MED confidence — heuristic, not trained]

**ACCURACY DISCLAIMER [HIGH confidence in this claim]:**
The CET system in `packages/sbir-ml/sbir_ml/transition/features/cet_analyzer.py` is a
**deterministic keyword matcher, not a trained probabilistic classifier.** No precision/recall
has been published for this heuristic on nanotech classification tasks.

The system uses two conflicting keyword sets that disagree on CET area assignment:
- `cet_analyzer.py` (hardcoded): "nanotechnology" → **Advanced Manufacturing**
- `config/cet/taxonomy.yaml` (NSTC-2025Q1): "nanomaterials" → **Advanced Engineering Materials**

Both are captured here and reported separately. This disagreement is a finding, not an error.

Terms matched: `nanotechnology`, `nanomaterials`, `graphene`, `carbon fiber`
CET areas triggered: Advanced Manufacturing, Advanced Engineering Materials

**Cohort size:** 650 Phase II awards
**Overlap with keyword cohort:** 426 of 640 unique CET award IDs
(67%) also appear in the keyword cohort.
The CET cohort is **not** a subset of the keyword cohort: `carbon fiber` appears in the CET
term list but not in the keyword list, so carbon-fiber-only awards fall outside the keyword cohort.

---

### 2C. USPTO CPC B82Y/B82B Cohort [MED confidence — name-match linkage]

**Status:** EXECUTED — built from local PatentsView PVGPATDIS extract (2026-07-11).

**What B82Y/B82B covers:**
- B82Y: Specific uses or applications of nanostructures or nanotechnology (functional/application layer)
- B82B: Nanostructures formed by manipulation of individual atoms, molecules, or limited collections

**Pipeline:**
1. `scripts/data/extract_b82_patents.py` filters PatentsView `g_cpc_current` (~60M CPC rows)
   to B82 subclasses and joins assignee organizations and grant dates:
   61,517 B82 patents, 7,510 unique assignee organizations
2. Assignee organizations are matched to SBIR Phase II firm names by **exact match on
   normalized names** (`sbir_etl.utils.text_normalization.normalize_name`, suffixes stripped)
3. Firms with ≥1 matched B82 patent → all their Phase II awards enter the cohort

**Cohort size:** 6,786 Phase II awards across 481 firms

**Matching caveats [HIGH confidence these matter]:**
- Exact normalized-name matching favors precision; firms that patent under a different name
  (renames, subsidiaries, university research partners) are missed — recall is uncertain
- Generic firm names can collide across distinct entities; spot-check before citing
  firm-level claims from this cohort alone

---

## 3. Pairwise Cohort Overlap

| Pair | Set A | Set B | Intersection | Jaccard |
|---|---|---|---|---|
| Keyword ∩ CET | 2,798 | 640 | 426 | 0.141 |
| Keyword ∩ CPC | 2,798 | 6,703 | 742 | 0.085 |
| CET ∩ CPC | 640 | 6,703 | 159 | 0.022 |

**Interpretation:** Set sizes count unique award IDs: the keyword cohort's 2,849 rows
contain 2,798 unique IDs and the CET cohort's 650 rows contain 640
(SBIR.gov repeats some Contract numbers). Keyword ∩ CET Jaccard is low (0.141),
driven by the size mismatch rather than disagreement: 67% of
CET award IDs fall inside the keyword cohort, and the remainder is carbon-fiber-only matches (see §2B).
Keyword ∩ CPC Jaccard is 0.085, with 11% of CPC-cohort award IDs also in the keyword cohort — the first cross-source triangulation in this analysis. Partial overlap is expected: CPC captures firms by patenting behavior rather than award text, so text-matched awards without patents and patent-holding firms whose abstracts avoid nanotech vocabulary both legitimately exist.

---

## 4. NNI Table 5 Reconciliation

**Scope:** FY2020–FY2023, nine NNI-reporting agencies
**Caveat [UNVERIFIED]:** NNI Table 5 reference figures are approximate public summary values,
not extracted from the PDF. Methodology for OMB-identified classification not published.
Our classification method differs; exact reconciliation is not expected.

### 4A. Keyword Cohort vs NNI Table 5

| Agency | FY | Our cohort ($M) | NNI Table 5 ref ($M) [UNVERIFIED] | Delta ($M) |
|---|---|---|---|---|
| DOC/NIST | 2020 | 0.80 | 2.50 | -1.70 |
| DOC/NIST | 2021 | 0.80 | 2.70 | -1.90 |
| DOC/NIST | 2022 | 1.60 | 2.90 | -1.30 |
| DOC/NIST | 2023 | 0.00 | 3.00 | -3.00 |
| DOE | 2020 | 12.85 | 12.00 | +0.85 |
| DOE | 2021 | 25.01 | 12.50 | +12.51 |
| DOE | 2022 | 31.64 | 13.00 | +18.64 |
| DOE | 2023 | 13.64 | 15.00 | -1.36 |
| DoD | 2020 | 41.36 | 55.00 | -13.64 |
| DoD | 2021 | 36.39 | 58.00 | -21.61 |
| DoD | 2022 | 50.26 | 61.00 | -10.74 |
| DoD | 2023 | 34.76 | 65.00 | -30.24 |
| EPA | 2020 | 0.30 | 0.80 | -0.50 |
| EPA | 2021 | 0.50 | 0.85 | -0.35 |
| EPA | 2022 | 0.00 | 0.90 | -0.90 |
| EPA | 2023 | 0.00 | 1.00 | -1.00 |
| NASA | 2020 | 5.92 | 6.50 | -0.58 |
| NASA | 2021 | 6.72 | 7.00 | -0.28 |
| NASA | 2022 | 5.42 | 7.50 | -2.08 |
| NASA | 2023 | 6.10 | 8.00 | -1.90 |
| NIH/DHHS | 2020 | 33.47 | 70.00 | -36.53 |
| NIH/DHHS | 2021 | 33.67 | 74.00 | -40.33 |
| NIH/DHHS | 2022 | 43.80 | 77.00 | -33.20 |
| NIH/DHHS | 2023 | 49.05 | 80.00 | -30.95 |
| NSF | 2020 | 8.90 | 43.00 | -34.10 |
| NSF | 2021 | 2.98 | 46.00 | -43.02 |
| NSF | 2022 | 7.87 | 48.00 | -40.13 |
| NSF | 2023 | 3.99 | 50.00 | -46.01 |
| USDA | 2020 | 0.00 | 3.50 | -3.50 |
| USDA | 2021 | 0.65 | 4.00 | -3.35 |
| USDA | 2022 | 1.30 | 4.50 | -3.20 |
| USDA | 2023 | 0.00 | 5.00 | -5.00 |

### 4B. CET Proxy Cohort vs NNI Table 5

| Agency | FY | Our cohort ($M) | NNI Table 5 ref ($M) [UNVERIFIED] | Delta ($M) |
|---|---|---|---|---|
| DOC/NIST | 2020 | 0.00 | 2.50 | -2.50 |
| DOC/NIST | 2021 | 0.40 | 2.70 | -2.30 |
| DOC/NIST | 2022 | 0.00 | 2.90 | -2.90 |
| DOC/NIST | 2023 | 0.00 | 3.00 | -3.00 |
| DOE | 2020 | 5.43 | 12.00 | -6.57 |
| DOE | 2021 | 5.45 | 12.50 | -7.05 |
| DOE | 2022 | 9.26 | 13.00 | -3.74 |
| DOE | 2023 | 3.45 | 15.00 | -11.55 |
| DoD | 2020 | 9.87 | 55.00 | -45.13 |
| DoD | 2021 | 6.46 | 58.00 | -51.54 |
| DoD | 2022 | 25.11 | 61.00 | -35.89 |
| DoD | 2023 | 16.34 | 65.00 | -48.66 |
| EPA | 2020 | 0.00 | 0.80 | -0.80 |
| EPA | 2021 | 0.50 | 0.85 | -0.35 |
| EPA | 2022 | 0.00 | 0.90 | -0.90 |
| EPA | 2023 | 0.00 | 1.00 | -1.00 |
| NASA | 2020 | 2.19 | 6.50 | -4.31 |
| NASA | 2021 | 1.50 | 7.00 | -5.50 |
| NASA | 2022 | 3.86 | 7.50 | -3.64 |
| NASA | 2023 | 0.90 | 8.00 | -7.10 |
| NIH/DHHS | 2020 | 6.33 | 70.00 | -63.67 |
| NIH/DHHS | 2021 | 6.93 | 74.00 | -67.07 |
| NIH/DHHS | 2022 | 5.74 | 77.00 | -71.26 |
| NIH/DHHS | 2023 | 5.66 | 80.00 | -74.34 |
| NSF | 2020 | 3.50 | 43.00 | -39.50 |
| NSF | 2021 | 0.00 | 46.00 | -46.00 |
| NSF | 2022 | 4.94 | 48.00 | -43.06 |
| NSF | 2023 | 1.97 | 50.00 | -48.03 |
| USDA | 2020 | 0.00 | 3.50 | -3.50 |
| USDA | 2021 | 0.00 | 4.00 | -4.00 |
| USDA | 2022 | 0.65 | 4.50 | -3.85 |
| USDA | 2023 | 0.00 | 5.00 | -5.00 |

**Methodological choice note [HIGH]:** We do not tune the keyword list or CET proxy to close
the delta. The gap itself is informative: it represents awards NNI counts as nanotech that our
text-based methods miss (e.g., awards with nanotech scope stated in solicitation topic, not abstract).

---

## 5. Phase III Transition Signal Channels

⚠ **DO NOT report the union signal as "the Phase III transition rate."**
Each channel has different coverage gaps and none is authoritative.

### 5A. Keyword cohort (n=2,849)

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | 262 | 9.2% | Known undercount; DoD ~67% of coded P3 in this cohort (GAO-24-106398) |
| Any subsequent federal obligation | 919 | 32.3% | Broad; includes non-P3 task orders; per-firm not per-award |
| M&A signal — all tiers | 434 | 15.2% | Exact name match; inflated by low-conf matches (~49% of total) |
| M&A signal — medium+high only | 220 | 7.7% | More reliable; may still reflect prior EDGAR scan errors |
| M&A signal — high conf only | 54 | 1.9% | Narrowest; recommend using this tier for any cited figure |
| Form D (high-confidence) | 394 | 13.8% | Investment signal only; not direct P3 evidence |
| **Union (any positive)** | **1408** | **49.4%** | **See caution above — do not report as rate** |

### 5B. CET proxy cohort (n=650)

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | 85 | 13.1% | Known undercount |
| Any subsequent federal obligation | 226 | 34.8% | Broad; per-firm |
| M&A signal — medium+high only | 49 | 7.5% | Preferred M&A signal tier |
| M&A signal — high conf only | 13 | 2.0% | Narrowest M&A signal |
| Form D (high-confidence) | 79 | 12.2% | Investment signal only |
| **Union (any positive)** | **313** | **48.2%** | **See caution above** |

---

### 5C. CPC cohort (n=6,786)

⚠ **Grain warning:** Method C is firm-grained — every Phase II award of a matched firm enters
the cohort, so prolific multi-award firms dominate these per-award rates (one firm contributes
596 awards). Do not compare
rates against §5A/§5B, which are award-text cohorts, without accounting for grain.
§5D below de-grains the comparison.

| Channel | Signal-positive | % | Coverage caveat |
|---|---|---|---|
| FPDS-coded Phase III contract | 2592 | 38.2% | Known undercount |
| Any subsequent federal obligation | 3409 | 50.2% | Broad; per-firm |
| M&A signal — medium+high only | 1923 | 28.3% | Preferred M&A signal tier |
| M&A signal — high conf only | 160 | 2.4% | Narrowest M&A signal |
| Form D (high-confidence) | 800 | 11.8% | Investment signal only |
| **Union (any positive)** | **5215** | **76.8%** | **See caution above** |

### 5D. Firm-level triangulation (keyword × CPC)

De-graining both cohorts to firms (share of firms with ≥1 signal-positive award) removes the
prolific-firm inflation in §5C:

| Channel (firm-level) | Keyword firms | CPC firms |
|---|---|---|
| FPDS-coded Phase III | 37/1,339 (2.8%) | 12/481 (2.5%) |
| Any federal obligation | 270/1,339 (20.2%) | 46/481 (9.6%) |
| Form D (high-confidence) | 201/1,339 (15.0%) | 113/481 (23.5%) |
| M&A signal (med+high) | 82/1,339 (6.1%) | 80/481 (16.6%) |

**What this shows:**

1. **The §5C award-level FPDS gap is a grain artifact.** Firm-level FPDS-coded Phase III rates
   are indistinguishable between the cohorts (table above); the award-level gap comes from
   prolific multi-award firms dominating the CPC cohort.
2. **Patents discriminate *within* the keyword cohort.** Keyword-cohort firms holding ≥1 B82
   patent have a 6.4% firm-level FPDS-coded Phase III rate vs 2.2% for
   non-holders. Every CPC-cohort firm with FPDS-coded Phase III lies in the keyword ∩ CPC
   firm intersection (n=188).
3. **Private-market signals stay elevated for patent holders after de-graining** (Form D and
   M&A rows above) — patents correlate more with acquisition/investment outcomes than with
   government Phase III coding.
4. **The double-confirmed subset is the strongest cohort.** The 742 unique awards
   that are both text-matched and from patent-verified firms show 23.7%
   FPDS-coded Phase III — use this subset for headline claims.
5. **Coverage asymmetry:** the keyword method catches 39%
   of patent-verified nanotech firms; 14% of keyword-cohort firms hold B82 patents
   (examiner under-assignment of B82 and small-firm non-patenting both suppress this).

**Caveat:** the "any federal obligation" channel under-measures the CPC cohort — the prospect
digest joins by UEI, and the CPC cohort skews toward older prolific firms whose activity
predates UEI-era tracking.

---

## 6. Deficiency Classification (Task 4 — Primary Deliverable)

For every Phase II award in the keyword cohort without FPDS-coded Phase III evidence,
the following taxonomy classifies why transition status is indeterminate.

### 6A. Keyword cohort

| Deficiency class | N awards |
|---|---|
| DATA_GAP_FPDS_NONDOD | 182 |
| ENTITY_RESOLUTION_FAILURE | 539 |
| FIRM_ACTIVITY_ABSENT | 1298 |
| INSUFFICIENT_TIME | 214 |
| NO_FPDS_CODING | 354 |

**Taxonomy definitions:**

| Class | Definition |
|---|---|
| `ENTITY_RESOLUTION_FAILURE` | UEI absent from SBIR.gov record; cannot link award to federal procurement systems |
| `INSUFFICIENT_TIME` | Award year ≥ 2023; typical Phase III maturation requires 3–7 years; censored observation, not negative signal |
| `FIRM_ACTIVITY_ABSENT` | Firm not found in USAspending prospect digest; no contracts or grants found under this UEI |
| `DATA_GAP_FPDS_NONDOD` | Non-DoD agency where FPDS Phase III column coding is sparse (GAO-24-106398, pp. 26-29); absence is system gap, not transition failure |
| `NO_FPDS_CODING` | Firm has FPDS activity but no contract carries Phase III coding; may be uncoded transition (common) |
| `INDETERMINATE` | None of the above categories explain the gap; cause not derivable from available data |

---

## 7. Key Methodological Caveats

1. **CET is a keyword matcher, not a classifier [HIGH].** No accuracy figures exist for this heuristic
   applied to nanotech. Do not describe Method B results as "classified by CET."

2. **FPDS Phase III undercounting [HIGH].** GAO-24-106398 documents that FPDS `sbir_program` coding is
   sparse outside DoD. Absence of a Phase III-coded contract is not evidence of no transition.

3. **NNI reconciliation is not expected to close [HIGH].** NNI uses agency+OMB identification methods
   not published in the Supplement. Our text classification approach differs by design.

4. **EDGAR scan data is usable; summary file is not [HIGH].** `sec_edgar_scan.jsonl` contains
   complete results for 34,451 firms (99.9% of nanotech cohort) with 7,548 having at least one
   mention and 2,195 tagged `ma_definitive`. A subsequent scan process wrote `sec_edgar_scan.summary.json`
   showing 0 detections after hitting HTTP 500 errors on every request — that summary reflects a failed
   process, not the data. M&A signals in this analysis draw on `sec_edgar_scan.jsonl` directly,
   filtered to M&A-specific mention types. See `scripts/data/nano_ma_signal.py`.

5. **CPC cohort uses exact name matching [MED].** B82 assignee → firm linkage is an exact match on normalized names. Precision is high; recall is uncertain (renames, subsidiaries, university assignees produce false negatives). Treat CPC cohort membership as high-precision, unknown-recall.

6. **Form D is an investment signal, not a transition signal [HIGH].** A Form D filing indicates capital
   raised, which may correlate with commercialization but does not prove Phase III transition.

7. **Phase II prospect digest is per-firm [HIGH].** A single UEI can have multiple Phase II awards.
   Transition signals in the digest apply at firm level; per-award attribution is not possible
   from this data source alone.

---

## 8. Figures

- `data/analysis/nano_cohort_overlap.png` — Three-way Venn diagram (Jaccard annotations)
- `data/analysis/nano_transition_channels.png` — Transition signal by channel, by method cohort
