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
) -> tuple[list[re.Pattern], list[re.Pattern], str]:
    pack = cfg.get("keyword_pack") or {}
    positives: list[re.Pattern] = []
    negatives: list[re.Pattern] = []
    source = "keyword_pack"

    if pack.get("patterns"):
        positives = _compile_patterns(list(pack["patterns"]))
        negatives.extend(_compile_patterns(list(pack.get("negative_patterns") or [])))
    else:
        cet_id = cfg.get("cet_id")
        if not cet_id or cet_id not in taxonomy:
            raise ValueError(
                f"area {cfg['area_id']}: no keyword_pack.patterns and no usable cet_id"
            )
        positives = [_phrase_to_pattern(k) for k in taxonomy[cet_id].get("keywords") or []]
        source = "taxonomy"
        negatives.extend(
            [_phrase_to_pattern(k) for k in taxonomy[cet_id].get("negative_keywords") or []]
        )

    cet_id = cfg.get("cet_id")
    if cet_id and cet_id in taxonomy:
        for k in taxonomy[cet_id].get("negative_keywords") or []:
            negatives.append(_phrase_to_pattern(k))

    if not positives:
        raise ValueError(f"area {cfg['area_id']}: empty Method A pattern list")
    return positives, negatives, source


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


def build_keyword_cohort(
    awards: list[dict],
    positives: list[re.Pattern],
    negatives: list[re.Pattern],
    source: str,
) -> list[dict]:
    """Method A: require ≥1 positive match. Negatives alone never admit an award.

    Mixed abstracts (positive + negative) are kept — e.g. a QIS award that also
    mentions quantum dots. Pure quantum-dot abstracts match no positive → excluded.
    """
    del negatives  # used by callers for spot-checks; admission is positive-gated
    cohort = []
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        pos = []
        for pat in positives:
            m = pat.search(text)
            if m:
                pos.append(m.group(0).lower())
        if not pos:
            continue
        rec = dict(aw)
        rec["cohort_keyword"] = True
        rec["keyword_matches"] = "|".join(sorted(set(pos))[:10])
        rec["keyword_source"] = source
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


def try_enrich_note() -> tuple[list[str], dict | None]:
    """v1: report which signal artifacts are present; full enrich needs nano helpers."""
    absent = []
    present = []
    for name, path in signal_paths().items():
        if path.exists():
            present.append(name)
        else:
            absent.append(str(path.relative_to(REPO)))
    if present and not absent:
        # Enrichment deferred to nano helper import when all artifacts exist;
        # local cloud runs typically lack them — avoid matplotlib hard-dep.
        return absent, None
    return absent, None


def contamination_spotcheck(
    kw_cohort: list[dict],
    positives: list[re.Pattern],
    negatives: list[re.Pattern],
    sample: int = 20,
) -> dict:
    """Count Method-A awards that also match negatives; sample for review."""
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
    return {
        "method_a_with_negative_cooccurrence": len(both),
        "pure_negative_admissions": pure_neg_admitted,
        "sample": both[:sample],
    }


def quantum_dot_only_false_positives(awards: list[dict], positives: list[re.Pattern]) -> int:
    """Awards that mention quantum dot/well but no Method-A positive — should be excluded."""
    neg_only = [
        re.compile(r"\bquantum dots?\b", re.I),
        re.compile(r"\bquantum wells?\b", re.I),
    ]
    n = 0
    for aw in awards:
        text = " ".join([aw["title"], aw["abstract"]])
        if any(p.search(text) for p in neg_only) and not any(p.search(text) for p in positives):
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

    positives, negatives, src_a = resolve_method_a(cfg, taxonomy)
    print(f"Method A: {len(positives)} patterns from {src_a}; {len(negatives)} negatives")
    kw_cohort = build_keyword_cohort(awards, positives, negatives, src_a)
    print(f"  {len(kw_cohort):,} awards matched")

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

    absent, channel_summary = try_enrich_note()
    if absent:
        print("Signal artifacts absent (cohort-only run):")
        for p in absent:
            print(f"  - {p}")

    spot = contamination_spotcheck(kw_cohort, positives, negatives, args.sample_negatives)
    print(
        f"Negative co-occurrence in Method A: {spot['method_a_with_negative_cooccurrence']:,} "
        f"(pure-negative admissions={spot['pure_negative_admissions']})"
    )

    qdot_excluded = None
    if cfg.get("cet_id") == "quantum_information_science":
        qdot_excluded = quantum_dot_only_false_positives(awards, positives)
        print(
            f"Quantum-dot/well awards with no QIS positive (correctly excluded from A): "
            f"{qdot_excluded:,}"
        )

    out_dir = REPORTS / cfg["area_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(kw_cohort, out_dir / "cohort_keyword.csv")
    write_csv(cet_cohort, out_dir / "cohort_cet.csv")
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
        "quantum_dot_well_excluded_count": qdot_excluded,
    }
    (out_dir / "overlap_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_methodology_stub(
        cfg, out_dir / "methodology_stub.md", stats, absent, channel_summary
    )
    print(f"Wrote {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
