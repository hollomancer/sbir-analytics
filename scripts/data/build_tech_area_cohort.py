#!/usr/bin/env python3
"""
Build a technology-area Phase II cohort from a transition-report area config.

v1 (specs/tech-area-transition-report): Method A keyword cohort + Method B
CET/taxonomy triangulation + overlap stats. Optional shared-signal enrichment
when prospect-digest / Form D / M&A artifacts are present.

Usage:
  python scripts/data/build_tech_area_cohort.py --area quantum_information_science
  python scripts/data/build_tech_area_cohort.py --area hypersonics
  python scripts/data/build_tech_area_cohort.py --area nanotechnology
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
CONFIG_DIR = REPO / "config" / "transition_reports"
TAXONOMY_PATH = REPO / "config" / "cet" / "taxonomy.yaml"
REPORTS = DATA / "reports"


def load_taxonomy() -> dict[str, dict]:
    raw = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {a["cet_id"]: a for a in raw.get("cet_areas", [])}


def load_area_config(area_id: str) -> dict:
    path = CONFIG_DIR / f"{area_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No area config at {path}. Add config/transition_reports/{area_id}.yaml"
        )
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if cfg.get("area_id") and cfg["area_id"] != area_id:
        raise ValueError(f"area_id in {path} is {cfg['area_id']!r}, expected {area_id!r}")
    cfg["area_id"] = area_id
    if not cfg.get("display_name"):
        raise ValueError(f"{path} missing display_name")
    return cfg


def _safe_float(v: str) -> float:
    try:
        return float(v.replace("$", "").replace(",", "")) if v else 0.0
    except ValueError:
        return 0.0


def _safe_int(v: str) -> int:
    try:
        return int(float(v.replace("$", "").replace(",", ""))) if v else 0
    except ValueError:
        return 0


def load_phase2_awards(awards_csv: Path) -> list[dict]:
    rows = []
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("Phase", "").strip() != "Phase II":
                continue
            rows.append(
                {
                    "award_id": row.get("Contract", "").strip()
                    or row.get("Agency Tracking Number", "").strip(),
                    "agency": row.get("Agency", "").strip(),
                    "branch": row.get("Branch", "").strip(),
                    "program": row.get("Program", "").strip(),
                    "company": row.get("Company", "").strip(),
                    "uei": row.get("UEI", "").strip(),
                    "duns": row.get("Duns", "").strip(),
                    "award_year": _safe_int(row.get("Award Year", "")),
                    "award_amount": _safe_float(row.get("Award Amount", "")),
                    "title": row.get("Award Title", "").strip(),
                    "abstract": row.get("Abstract", "").strip(),
                    "proposal_award_date": row.get("Proposal Award Date", "").strip(),
                    "contract_end_date": row.get("Contract End Date", "").strip(),
                    "solicitation_year": _safe_int(row.get("Solicitation Year", "")),
                }
            )
    return rows


def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            raise ValueError(f"invalid regex in keyword pack: {p!r} ({e})") from e
    return compiled


def _phrase_to_pattern(phrase: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)


def resolve_method_a(
    cfg: dict, taxonomy: dict[str, dict]
) -> tuple[list[re.Pattern], list[re.Pattern], list[re.Pattern], str]:
    """Return (core_positives, soft_positives, negatives, source_label).

    Soft positives only admit an award when corroborated (see build_keyword_cohort).
    """
    pack = cfg.get("keyword_pack") or {}
    core: list[re.Pattern] = []
    soft: list[re.Pattern] = []
    negatives: list[re.Pattern] = []
    source = "keyword_pack"

    if pack.get("patterns") or pack.get("soft_patterns"):
        core = _compile_patterns(list(pack.get("patterns") or []))
        soft = _compile_patterns(list(pack.get("soft_patterns") or []))
        negatives.extend(_compile_patterns(list(pack.get("negative_patterns") or [])))
    else:
        cet_id = cfg.get("cet_id")
        if not cet_id or cet_id not in taxonomy:
            raise ValueError(
                f"area {cfg['area_id']}: no keyword_pack.patterns and no usable cet_id"
            )
        core = [_phrase_to_pattern(k) for k in taxonomy[cet_id].get("keywords") or []]
        source = "taxonomy"
        negatives.extend(
            [_phrase_to_pattern(k) for k in taxonomy[cet_id].get("negative_keywords") or []]
        )

    cet_id = cfg.get("cet_id")
    if cet_id and cet_id in taxonomy:
        for k in taxonomy[cet_id].get("negative_keywords") or []:
            negatives.append(_phrase_to_pattern(k))

    if not core and not soft:
        raise ValueError(f"area {cfg['area_id']}: empty Method A pattern list")
    return core, soft, negatives, source


def resolve_method_b(
    cfg: dict, taxonomy: dict[str, dict]
) -> tuple[dict[re.Pattern, str], str]:
    if cfg.get("method_b_terms"):
        compiled = {
            _phrase_to_pattern(k): v for k, v in dict(cfg["method_b_terms"]).items()
        }
        return compiled, "method_b_terms"
    cet_id = cfg.get("cet_id")
    if cet_id and cet_id in taxonomy:
        name = taxonomy[cet_id].get("name") or cet_id
        compiled = {
            _phrase_to_pattern(k): name for k in taxonomy[cet_id].get("keywords") or []
        }
        return compiled, "taxonomy"
    return {}, "absent"


def _collect_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    hits = []
    for pat in patterns:
        m = pat.search(text)
        if m:
            hits.append(m.group(0).lower())
    return hits


def build_keyword_cohort(
    awards: list[dict],
    core: list[re.Pattern],
    soft: list[re.Pattern],
    negatives: list[re.Pattern],
    source: str,
    soft_requires: str = "title_or_multi",
) -> list[dict]:
    """Method A with optional soft-pattern corroboration and a negative veto.

    Admission:
      - A core hit always admits. A specific, high-precision positive (qubit,
        ``quantum information``, scramjet) is strong enough that a co-occurring
        negative term does not veto it — e.g. a genuine qubit award that also
        mentions ``quantum well`` in passing stays in.
      - A soft-only award admits only when it clears ``soft_requires`` **and** no
        negative pattern fires. Negatives veto soft-only admissions, which is where
        market-name-drop contamination enters (a ``quantum computing`` title-drop
        over a quantum-dot materials abstract). This is the load-bearing use of the
        taxonomy / pack negatives; without it they are inert.

    soft_requires:
      - ``title_or_multi`` (default): soft-only admits if soft term is in the title
        or ≥2 distinct soft hits appear (quantum market-name-drop filter).
      - ``core_cooccur``: soft-only never admits; soft hits only tag awards that
        already matched a core pattern (hypersonics TPS/Mach rule).
    """
    if soft_requires not in ("title_or_multi", "core_cooccur"):
        raise ValueError(f"unknown soft_requires={soft_requires!r}")
    cohort = []
    for aw in awards:
        title = aw["title"]
        text = " ".join([title, aw["abstract"]])
        core_hits = _collect_hits(text, core)
        soft_hits = _collect_hits(text, soft)
        if core_hits:
            admitted_by = "core"
            pos = core_hits + soft_hits
        elif soft_hits and soft_requires == "title_or_multi":
            soft_in_title = _collect_hits(title, soft)
            if not (soft_in_title or len(set(soft_hits)) >= 2):
                continue
            # Negative veto: a soft-only admit with a negative hit is contamination
            # (market-name-drop over off-target work). Core admits are never vetoed.
            if any(p.search(text) for p in negatives):
                continue
            admitted_by = "soft_corroborated"
            pos = soft_hits
        else:
            # soft_requires == core_cooccur and no core → reject soft-only
            continue
        rec = dict(aw)
        rec["cohort_keyword"] = True
        rec["keyword_matches"] = "|".join(sorted(set(pos))[:10])
        rec["keyword_source"] = source
        rec["admitted_by"] = admitted_by
        cohort.append(rec)
    return cohort


def build_method_b_cohort(
    awards: list[dict], compiled: dict[re.Pattern, str], source: str
) -> list[dict]:
    if not compiled:
        return []
    cohort = []
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        hits: dict[str, str] = {}
        for pat, label in compiled.items():
            m = pat.search(text)
            if m:
                hits[m.group(0).lower()] = label
        if not hits:
            continue
        rec = dict(aw)
        rec["cohort_cet"] = True
        rec["cet_terms_matched"] = "|".join(sorted(hits.keys()))
        rec["cet_areas_matched"] = "|".join(sorted(set(hits.values())))
        rec["cet_method_note"] = f"METHOD_B_SOURCE={source}"
        cohort.append(rec)
    return cohort


def overlap_stats(a_ids: set[str], b_ids: set[str]) -> dict:
    inter = a_ids & b_ids
    union = a_ids | b_ids
    return {
        "method_a_n": len(a_ids),
        "method_b_n": len(b_ids),
        "intersection_n": len(inter),
        "union_n": len(union),
        "containment_a_in_b": (len(inter) / len(a_ids)) if a_ids else None,
        "containment_b_in_a": (len(inter) / len(b_ids)) if b_ids else None,
        "jaccard": (len(inter) / len(union)) if union else None,
    }


def _norm_firm(company: str) -> str:
    """Firm identity key for unique-firm counts (mirror the findings-report grain)."""
    try:
        sys.path.insert(0, str(REPO))
        from sbir_etl.utils.text_normalization import normalize_name

        return normalize_name(company, remove_suffixes=True) or ""
    except Exception:
        return (company or "").strip().upper()


def dedupe_by_award_id(cohort: list[dict]) -> list[dict]:
    """Drop true duplicate rows (keep first); rows with no award_id are kept.

    ``award_id`` alone is not a unique key: SBIR.gov reuses the same base ID
    across genuinely different awards — DOE Phase II continuations/renewals in
    a later year, and cases where a different company (successor/awardee
    change) carries the same contract number. Deduping on bare ``award_id``
    silently drops real, distinct awards (verified against real data: 2 of 3
    QIS "duplicates" and all 3 of 3 hypersonics "duplicates" were genuinely
    different awards with different company/year/dollar values, not repeats).

    Key on (award_id, company, award_year, award_amount) instead — a row is a
    true duplicate only if all four agree. Overlap stats already dedupe on
    unique award_id sets for Jaccard/containment (a different, coarser
    question — "how many distinct IDs are in each method" — where the
    same-ID-different-award cases don't matter); composition tables need this
    finer key so dollar sums and agency counts don't drop real award dollars.
    """
    seen: set[tuple[str, str, str, str]] = set()
    out = []
    for r in cohort:
        aid = r.get("award_id") or ""
        key = (aid, r.get("company") or "", r.get("award_year") or "", r.get("award_amount") or "")
        if aid and key in seen:
            continue
        if aid:
            seen.add(key)
        out.append(r)
    return out


def aggregate_composition(cohort: list[dict], censor_year: int = 2023) -> dict:
    """Recompute the Finding 1 / Finding 2 composition tables from the cohort.

    Operates on award_id-deduplicated rows so agency counts, dollar sums, and firm
    counts are unique-based (not row-based). Emits the agency mix, program split,
    decade distribution, recency censoring, firm concentration, and no-UEI share —
    the load-bearing numbers hand-authored into the findings reports today.
    """
    rows = dedupe_by_award_id(cohort)
    n = len(rows)

    by_agency: dict[str, dict] = {}
    for r in rows:
        a = r.get("agency", "") or "(unknown)"
        bucket = by_agency.setdefault(
            a, {"awards": 0, "phase2_dollars": 0.0, "_firms": set()}
        )
        bucket["awards"] += 1
        bucket["phase2_dollars"] += float(r.get("award_amount") or 0.0)
        bucket["_firms"].add(_norm_firm(r.get("company", "")))
    agency_table = {
        a: {
            "awards": b["awards"],
            "share_pct": round(100 * b["awards"] / n, 1) if n else 0.0,
            "phase2_dollars_m": round(b["phase2_dollars"] / 1e6, 1),
            "unique_firms": len(b["_firms"]),
        }
        for a, b in sorted(by_agency.items(), key=lambda kv: -kv[1]["awards"])
    }

    prog = Counter((r.get("program", "") or "").upper() for r in rows)
    sbir_n, sttr_n = prog.get("SBIR", 0), prog.get("STTR", 0)

    decades: Counter = Counter()
    mature = censored = 0
    for r in rows:
        yr = int(r.get("award_year") or 0)
        if yr:
            decades[f"{(yr // 10) * 10}s"] += 1
            if yr >= censor_year:
                censored += 1
            else:
                mature += 1

    firm_counts = Counter(_norm_firm(r.get("company", "")) for r in rows)
    top10 = firm_counts.most_common(10)
    top10_share = round(100 * sum(c for _, c in top10) / n, 1) if n else 0.0

    no_uei = sum(1 for r in rows if not (r.get("uei") or "").strip())

    return {
        "n_unique_awards": n,
        "n_rows_pre_dedupe": len(cohort),
        "duplicate_award_id_rows": len(cohort) - n,
        "totals": {
            "awards": n,
            "phase2_dollars_m": round(
                sum(float(r.get("award_amount") or 0.0) for r in rows) / 1e6, 1
            ),
            "unique_firms": len({_norm_firm(r.get("company", "")) for r in rows}),
        },
        "by_agency": agency_table,
        "program_split": {
            "SBIR": sbir_n,
            "STTR": sttr_n,
            "sttr_pct": round(100 * sttr_n / n, 1) if n else 0.0,
        },
        "by_decade": dict(sorted(decades.items())),
        "censoring": {
            "censor_year": censor_year,
            "mature_awards": mature,
            "censored_awards": censored,
        },
        "firm_concentration": {
            "top10_award_share_pct": top10_share,
            "top_firms": [{"firm": f, "awards": c} for f, c in top10],
        },
        "entity_resolution": {
            "no_uei_awards": no_uei,
            "no_uei_pct": round(100 * no_uei / n, 1) if n else 0.0,
        },
    }


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_methodology_stub(
    cfg: dict,
    out: Path,
    stats: dict,
    signals_absent: list[str],
    channel_summary: dict | None,
) -> None:
    j = stats.get("jaccard")
    c = stats.get("containment_a_in_b")
    lines = [
        f"# {cfg['display_name']} — Phase II cohort methodology stub",
        "",
        f"**area_id:** `{cfg['area_id']}`  ",
        f"**cet_id:** `{cfg.get('cet_id')}`  ",
        f"**Generated by:** `scripts/data/build_tech_area_cohort.py`",
        "",
        "## Cohort sizes",
        "",
        f"- Method A (keyword): **{stats['method_a_n']:,}** awards",
        f"- Method B (CET/taxonomy): **{stats['method_b_n']:,}** awards",
        f"- Intersection: **{stats['intersection_n']:,}**",
        f"- Jaccard: **{j:.3f}**" if j is not None else "- Jaccard: n/a",
        f"- Containment A⊆B: **{c:.3f}**" if c is not None else "- Containment A⊆B: n/a",
        "",
        "## Caveats",
        "",
        "- Union of transition channels is **not** a transition rate.",
        "- FPDS Phase III coding is sparse outside DoD (GAO-24-106398).",
        "- Method B is a deterministic keyword heuristic, not a trained classifier.",
        "",
    ]
    if signals_absent:
        lines += [
            "## Signal inputs absent this run",
            "",
            *[f"- `{s}`" for s in signals_absent],
            "",
            "Channel rates were **not** computed from empty inputs.",
            "",
        ]
    if channel_summary:
        lines += ["## Transition channels (keyword cohort)", ""]
        for k, v in channel_summary.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def signal_paths() -> dict[str, Path]:
    return {
        "prospect_digest": DATA / "processed" / "sbir_phase3" / "fy25_phase3_prospect_digest.csv",
        "ma_enrichment": DATA / "enriched_sbir_ma_events.jsonl",
        "form_d_high_conf": DATA / "form_d_high_conf_cohort.jsonl",
    }


def try_enrich(kw_cohort: list[dict], *, require_signals: bool = False):
    """Enrich with shared transition signals when artifacts exist."""
    import sys

    sys.path.insert(0, str(REPO))
    from sbir_etl.utils.transition_signals import enrich_from_artifacts

    return enrich_from_artifacts(kw_cohort, REPO, require_signals=require_signals)


def contamination_spotcheck(
    kw_cohort: list[dict],
    core: list[re.Pattern],
    soft: list[re.Pattern],
    negatives: list[re.Pattern],
    sample: int = 20,
) -> dict:
    """Count Method-A awards that also match negatives; sample for review."""
    positives = core + soft
    both = []
    for r in kw_cohort:
        text = " ".join([r["title"], r["abstract"]])
        neg_hits = [p.pattern for p in negatives if p.search(text)]
        if neg_hits:
            both.append(
                {
                    "award_id": r["award_id"],
                    "company": r["company"],
                    "keyword_matches": r["keyword_matches"],
                    "admitted_by": r.get("admitted_by", ""),
                    "negative_patterns": neg_hits[:3],
                    "title": r["title"][:120],
                }
            )
    pure_neg_admitted = 0
    for r in kw_cohort:
        text = " ".join([r["title"], r["abstract"]])
        if any(p.search(text) for p in negatives) and not any(
            p.search(text) for p in positives
        ):
            pure_neg_admitted += 1
    by = Counter(r.get("admitted_by", "") for r in kw_cohort)
    return {
        "method_a_with_negative_cooccurrence": len(both),
        "pure_negative_admissions": pure_neg_admitted,
        "admitted_by": dict(by),
        "sample": both[:sample],
    }


_NEGATORS = frozenset(
    {
        "no",
        "not",
        "without",
        "non",
        "neither",
        "nor",
        "lacks",
        "lacking",
        "absent",
        "excludes",
        "excluding",
        "except",
        "avoid",
        "avoids",
        "avoiding",
        "rather",
    }
)
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']*")


def negation_spotcheck(
    kw_cohort: list[dict],
    core: list[re.Pattern],
    soft: list[re.Pattern],
    window: int = 4,
    sample: int = 15,
) -> dict:
    """Flag admitted awards where a positive is negated in context.

    Regex matching cannot read negation: ``does not involve quantum information``
    still fires the ``quantum information`` positive. This does not change admission
    (a diagnostic, not a veto); it quantifies a known false-positive class the
    negative-cooccurrence spot-check misses. A positive match is flagged when a
    negator token appears within ``window`` words immediately before it.
    """
    positives = core + soft
    flagged = []
    for r in kw_cohort:
        text = " ".join([r["title"], r["abstract"]])
        negated: list[str] = []
        for pat in positives:
            for m in pat.finditer(text):
                pre_tokens = _WORD_RE.findall(text[: m.start()].lower())[-window:]
                if any(tok in _NEGATORS for tok in pre_tokens):
                    negated.append(m.group(0).lower())
        if negated:
            flagged.append(
                {
                    "award_id": r["award_id"],
                    "company": r["company"],
                    "admitted_by": r.get("admitted_by", ""),
                    "negated_positive": sorted(set(negated))[:3],
                    "title": r["title"][:120],
                }
            )
    return {
        "method_a_with_negated_positive": len(flagged),
        "sample": flagged[:sample],
    }


def quantum_dot_only_false_positives(
    awards: list[dict], core: list[re.Pattern], soft: list[re.Pattern]
) -> int:
    """Awards that mention quantum dot/well but no Method-A positive — should be excluded."""
    positives = core + soft
    neg_only = [
        re.compile(r"\bquantum dots?\b", re.I),
        re.compile(r"\bquantum wells?\b", re.I),
    ]
    n = 0
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        if any(p.search(text) for p in neg_only) and not any(
            p.search(text) for p in positives
        ):
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True, help="area_id under config/transition_reports/")
    parser.add_argument(
        "--awards",
        default=str(DATA / "raw" / "sbir" / "award_data.csv"),
        help="SBIR.gov award_data.csv path",
    )
    parser.add_argument(
        "--sample-negatives",
        type=int,
        default=15,
        help="Include N co-occurring negative samples in overlap_summary.json",
    )
    args = parser.parse_args()

    cfg = load_area_config(args.area)
    taxonomy = load_taxonomy()
    awards_csv = Path(args.awards)
    if not awards_csv.exists():
        print(f"ERROR: awards CSV not found: {awards_csv}", file=sys.stderr)
        return 1

    print(f"Area: {cfg['display_name']} ({cfg['area_id']})")
    print("Loading Phase II awards...")
    awards = load_phase2_awards(awards_csv)
    print(f"  {len(awards):,} Phase II awards")

    core, soft, negatives, src_a = resolve_method_a(cfg, taxonomy)
    soft_requires = (cfg.get("keyword_pack") or {}).get("soft_requires", "title_or_multi")
    print(
        f"Method A: {len(core)} core + {len(soft)} soft patterns from {src_a}; "
        f"{len(negatives)} negatives; soft_requires={soft_requires}"
    )
    kw_cohort = build_keyword_cohort(
        awards, core, soft, negatives, src_a, soft_requires=soft_requires
    )
    print(f"  {len(kw_cohort):,} awards matched")
    adm = Counter(r.get("admitted_by", "") for r in kw_cohort)
    if adm:
        print(f"  admitted_by: {dict(adm)}")

    compiled_b, src_b = resolve_method_b(cfg, taxonomy)
    print(f"Method B: {len(compiled_b)} terms from {src_b}")
    cet_cohort = build_method_b_cohort(awards, compiled_b, src_b)
    print(f"  {len(cet_cohort):,} awards matched")

    a_ids = {r["award_id"] for r in kw_cohort if r.get("award_id")}
    b_ids = {r["award_id"] for r in cet_cohort if r.get("award_id")}
    stats = overlap_stats(a_ids, b_ids)
    if stats["jaccard"] is not None and stats["containment_a_in_b"] is not None:
        print(
            f"Overlap: ∩={stats['intersection_n']:,}  "
            f"Jaccard={stats['jaccard']:.3f}  "
            f"A⊆B={stats['containment_a_in_b']:.3f}"
        )
    else:
        print(f"Overlap: ∩={stats['intersection_n']:,}")

    enriched, absent, channel_summary = try_enrich(kw_cohort)
    if absent:
        print("Signal artifacts absent — writing deficiency_class with empty signals:")
        for p in absent:
            print(f"  - {p}")
        print("  (dark-majority WS need digest/Form D/M&A for meaningful buckets)")
    elif channel_summary:
        print("Transition channels (keyword cohort):")
        for k, v in channel_summary.items():
            print(f"  {k}: {v}")

    spot = contamination_spotcheck(
        enriched, core, soft, negatives, args.sample_negatives
    )
    print(
        f"Negative co-occurrence in Method A: {spot['method_a_with_negative_cooccurrence']:,} "
        f"(pure-negative admissions={spot['pure_negative_admissions']})"
    )

    negation = negation_spotcheck(enriched, core, soft)
    print(
        f"Negated-positive admissions in Method A (diagnostic, not vetoed): "
        f"{negation['method_a_with_negated_positive']:,}"
    )

    qdot_excluded = None
    if cfg.get("cet_id") == "quantum_information_science":
        qdot_excluded = quantum_dot_only_false_positives(awards, core, soft)
        print(
            f"Quantum-dot/well awards with no QIS positive (correctly excluded from A): "
            f"{qdot_excluded:,}"
        )

    from sbir_etl.utils.transition_report_paths import ReportPaths

    paths = ReportPaths.for_area(cfg["area_id"])
    paths.ensure_dirs()
    write_csv(enriched, paths.artifact("cohort_keyword"))
    write_csv(cet_cohort, paths.artifact("cohort_cet"))

    composition = aggregate_composition(enriched)
    paths.artifact("composition").write_text(
        json.dumps(composition, indent=2) + "\n", encoding="utf-8"
    )
    if composition["duplicate_award_id_rows"]:
        print(
            f"Composition: {composition['n_unique_awards']:,} unique awards "
            f"({composition['duplicate_award_id_rows']} duplicate award_id rows dropped)"
        )
    else:
        print(f"Composition: {composition['n_unique_awards']:,} unique awards")
    summary = {
        "area_id": cfg["area_id"],
        "display_name": cfg["display_name"],
        "cet_id": cfg.get("cet_id"),
        "phase2_universe": len(awards),
        "method_a_source": src_a,
        "method_b_source": src_b,
        "overlap": stats,
        "signals_absent": absent,
        "channels": channel_summary,
        "spotcheck": spot,
        "negation_spotcheck": negation,
        "quantum_dot_well_excluded_count": qdot_excluded,
        "has_deficiency_class": bool(enriched)
        and "deficiency_class" in enriched[0],
    }
    paths.artifact("overlap_summary").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_methodology_stub(
        cfg, paths.artifact("methodology_stub"), stats, absent, channel_summary
    )
    print(f"Wrote {paths.report_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
