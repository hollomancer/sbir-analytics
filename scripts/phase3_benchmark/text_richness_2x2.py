"""Provisional 2x2 field-substitution retrieval experiment.

External review (see specs/phase3-match-benchmark/eval-validity.md) flagged that the AUC rose from #423's
~0.56 (ModernBERT-Embed, thin USAspending agreement text, classification framing) to the current ranker's
~0.84-0.88 (TF-IDF, rich abstracts->notices, firm-clustered retrieval) with THREE factors moving at once:
text field, model, and task framing. The gain was therefore unattributed.

This holds firms, negatives, and a frozen TF-IDF representation fixed while
substituting fields. Titles and descriptions differ in content as well as
length, so this does not identify a general causal effect of “richness”:
    query  : thin = SBIR award TITLES        rich = SBIR ABSTRACTS
    target : thin = NASA project TITLE        rich = NASA project DESCRIPTION

Negative construction (--negatives): `random` (uniform within same register — clean deltas but easy, so
optimistic absolutes) or `metadata` (same NASA technology-taxonomy area + close year, different firm — the
NAICS-analogue hard negative). Absolute values and cross-cell effects remain
provisional until regenerated from the missing input packet.

Inputs: data/raw/sbir/award_data.csv and a cached TechPort search JSON (see pull_techport_nasa.py).
"""

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from retrieval_metrics import tie_corrected_auc


def longest_shared_word_run(x: str, y: str, cap: int = 400) -> int:
    """Longest contiguous shared word run — the text-reuse / plagiarism probe. Pure.

    If positive (query, own target) pairs share far longer runs than negatives, TF-IDF is detecting copied
    strings, not technical relatedness (a fragile result). Equal distributions mean distributed vocabulary.
    """
    xt, yt = x.lower().split()[:cap], y.lower().split()[:cap]
    return (
        difflib.SequenceMatcher(None, xt, yt, autojunk=False)
        .find_longest_match(0, len(xt), 0, len(yt))
        .size
    )


def paired_bootstrap(
    per_firm: np.ndarray, n_boot: int = 2000, seed: int = 1
) -> tuple[float, float, float]:
    """Firm-clustered bootstrap of a per-firm statistic → (mean, 2.5%, 97.5%). Pure.

    Used on the paired per-firm difference of main effects (random vs metadata negatives): because the same
    firms appear in both conditions, correlated errors cancel and the CI on the difference is tight.
    """
    rng = np.random.RandomState(seed)
    n = len(per_firm)
    means = [per_firm[rng.choice(n, n, replace=True)].mean() for _ in range(n_boot)]
    return (
        float(per_firm.mean()),
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


_SUFFIX = re.compile(
    r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|THE|INCORPORATED|TECHNOLOGIES|"
    r"TECHNOLOGY|TECH|SYSTEMS)\b"
)


def normalize_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", text)).strip()


def random_negatives(n: int, n_neg: int, seed: int = 0) -> dict[int, np.ndarray]:
    """{firm i: n_neg random other-firm indices}. Same register, representation-independent."""
    rng = np.random.RandomState(seed)
    out = {}
    for i in range(n):
        others = [j for j in range(n) if j != i]
        out[i] = rng.choice(others, min(n_neg, len(others)), replace=False)
    return out


def metadata_hard_negatives_with_tiers(
    years: np.ndarray,
    tx_areas: np.ndarray,
    n_neg: int,
    seed: int = 0,
    year_window: int = 2,
    min_pool: int = 8,
) -> tuple[dict[int, np.ndarray], dict[str, int]]:
    """Hard negatives matched on metadata, NOT text (so representation-independent and artifact-free).

    Pool for firm i = other firms with the same NASA TX area and |year - year_i| <= window; relax to same-TX
    only if too small; fall back to random if still under min_pool. Returns (neg map, n_true_hard).
    """
    rng = np.random.RandomState(seed)
    n = len(years)
    out: dict[int, np.ndarray] = {}
    tiers = {"exact_tx_year": 0, "same_tx_relaxed_year": 0, "random_fallback": 0}
    for i in range(n):
        same_tx = [j for j in range(n) if j != i and tx_areas[j] and tx_areas[j] == tx_areas[i]]
        exact = [j for j in same_tx if abs(years[j] - years[i]) <= year_window]
        if len(exact) >= min_pool:
            pool = exact
            tiers["exact_tx_year"] += 1
        elif len(same_tx) >= min_pool:
            pool = same_tx
            tiers["same_tx_relaxed_year"] += 1
        else:
            pool = [j for j in range(n) if j != i]
            tiers["random_fallback"] += 1
        out[i] = rng.choice(pool, min(n_neg, len(pool)), replace=False)
    return out, tiers


def metadata_hard_negatives(
    years: np.ndarray,
    tx_areas: np.ndarray,
    n_neg: int,
    seed: int = 0,
    year_window: int = 2,
    min_pool: int = 8,
) -> tuple[dict[int, np.ndarray], int]:
    """Compatibility wrapper returning the number meeting the exact advertised match."""
    negatives, tiers = metadata_hard_negatives_with_tiers(
        years, tx_areas, n_neg, seed, year_window, min_pool
    )
    return negatives, tiers["exact_tx_year"]


def firm_retrieval_auc(
    query_texts: list[str],
    target_texts: list[str],
    neg_indices: dict[int, np.ndarray],
    *,
    vectorizer: TfidfVectorizer | None = None,
) -> tuple[float, float]:
    """Firm-clustered retrieval AUC + top-1 under a FIXED negative set (identical across text conditions).

    AUC = mean over firms of P(sim(i, own target) > sim(i, negative target)). Model = TF-IDF, held constant.
    """
    vec = vectorizer or TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    texts = list(query_texts) + list(target_texts)
    matrix = vec.transform(texts) if vectorizer is not None else vec.fit_transform(texts)
    n = len(query_texts)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    aucs, top1 = [], 0
    for i in range(n):
        neg = sims[i, neg_indices[i]]
        aucs.append(tie_corrected_auc(float(sims[i, i]), neg))
        top1 += int((neg >= sims[i, i]).sum() == 0)
    return float(np.mean(aucs)), top1 / n


def _firm_orgs(project: dict) -> list[str]:
    lead = project.get("leadOrganization")
    if not isinstance(lead, dict):
        return []
    org_type = lead.get("organization_type") or lead.get("organizationType")
    if str(org_type).lower() != "industry":
        return []
    name = lead.get("organization_name") or lead.get("organizationName") or ""
    return [str(name)] if name else []


def _is_sbir(project: dict) -> bool:
    program = project.get("program") or {}
    title = program.get("title", "") if isinstance(program, dict) else str(program)
    phase = re.sub(r"[^A-Z0-9]", "", str(project.get("phase", "")).upper())
    phase = phase.removeprefix("PHASE")
    return "SMALL BUSINESS" in title.upper() or phase in {
        "1",
        "I",
        "2",
        "II",
        "2E",
        "IIE",
        "2X",
        "IIX",
        "2S",
        "IIS",
        "3",
        "III",
    }


def _year(value: object) -> int | None:
    match = re.search(r"(19[89]\d|20[0-2]\d)", str(value))
    return int(match.group()) if match else None


def _tx_area(project: dict) -> str:
    tx = project.get("primaryTx")
    code = tx.get("code", "") if isinstance(tx, dict) else ""
    match = re.match(r"(TX\d+)", code)
    return match.group(1) if match else ""


def _asof_texts(
    phase2: pd.DataFrame, targets: dict[str, dict], field: str, limit: int
) -> dict[str, str]:
    values: dict[str, str] = {}
    for uei, target in targets.items():
        target_date = target.get("target_date")
        if pd.isna(target_date):
            continue
        eligible = phase2[(phase2["UEI"] == uei) & (phase2["_award_date"] <= target_date)]
        text = " ".join(str(value) for value in eligible[field] if str(value).strip())[:limit]
        if text:
            values[uei] = text
    return values


def run(
    award_csv: Path, techport_json: Path, *, negatives: str = "random", n_neg: int = 25
) -> dict[str, object]:
    awards = pd.read_csv(award_csv, dtype=str, keep_default_na=False)
    awards = awards[awards["UEI"].str.len() > 5]
    name_to_ueis: dict[str, set[str]] = {}
    for company, uei in zip(awards["Company"], awards["UEI"], strict=True):
        key = normalize_name(company)
        if len(key) > 4:
            name_to_ueis.setdefault(key, set()).add(str(uei))
    name_to_uei = {key: next(iter(ueis)) for key, ueis in name_to_ueis.items() if len(ueis) == 1}
    listing = json.loads(techport_json.read_text())
    projects = listing.get("results") or listing.get("projects") or listing
    rec: dict[str, dict] = {}
    for project in sorted(
        projects, key=lambda value: str(value.get("projectId") or value.get("id") or "")
    ):
        if _is_sbir(project):
            continue
        description = str(project.get("description") or "")
        if len(description) < 150:
            continue
        for org in _firm_orgs(project):
            uei = name_to_uei.get(normalize_name(org))
            target_date = pd.to_datetime(
                project.get("startDate") or project.get("startDateString"),
                errors="coerce",
                utc=True,
            )
            if uei and uei not in rec and pd.notna(target_date):
                rec[uei] = {
                    "desc": description,
                    "title": str(project.get("title", "")),
                    "yr": int(target_date.year),
                    "target_date": target_date,
                    "tx": _tx_area(project),
                    "project_id": project.get("projectId") or project.get("id"),
                }
    phase = awards["Phase"].astype(str).str.upper()
    phase2 = awards[
        phase.str.contains("II", na=False) & ~phase.str.contains("III", na=False)
    ].copy()
    award_dates = pd.to_datetime(phase2["Proposal Award Date"], errors="coerce", utc=True)
    if "Solicitation Year" in phase2:
        year_end = pd.to_datetime(
            phase2["Solicitation Year"].map(lambda value: f"{value}-12-31"),
            errors="coerce",
            utc=True,
        )
        award_dates = award_dates.fillna(year_end)
    phase2["_award_date"] = award_dates

    q_title = _asof_texts(phase2, rec, "Award Title", 2000)
    q_abstract = _asof_texts(phase2, rec, "Abstract", 9000)
    firms = [
        u
        for u in rec
        if len(q_abstract.get(u, "")) > 80
        and len(q_title.get(u, "")) > 10
        and len(rec[u]["title"]) > 10
    ]

    if negatives == "metadata":
        years = np.array([rec[u]["yr"] for u in firms])
        tx_areas = np.array([rec[u]["tx"] for u in firms])
        neg_indices, tier_counts = metadata_hard_negatives_with_tiers(years, tx_areas, n_neg)
    else:
        neg_indices = random_negatives(len(firms), n_neg)
        tier_counts = {"random": len(firms)}

    t_title = {u: rec[u]["title"] for u in firms}
    t_desc = {u: rec[u]["desc"] for u in firms}
    # Fit one representation on the union of field variants, then freeze its
    # vocabulary and IDF weights for all four cells. This makes the estimand a
    # field-substitution ablation instead of four separately fitted models.
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    vectorizer.fit(
        [q_title[u] for u in firms]
        + [q_abstract[u] for u in firms]
        + [t_title[u] for u in firms]
        + [t_desc[u] for u in firms]
    )

    def cell(qmap: dict, tmap: dict) -> tuple[float, float]:
        return firm_retrieval_auc(
            [qmap[u] for u in firms],
            [tmap[u] for u in firms],
            neg_indices,
            vectorizer=vectorizer,
        )

    return {
        "status": "provisional",
        "label_semantics": "firm-linked NASA portfolio proxy",
        "warnings": ["not a Phase III detector benchmark", "exact-name-linked selected cohort"],
        "firms": len(firms),
        "negatives": negatives,
        "negative_tier_counts": tier_counts,
        "true_hard_neg_firms": tier_counts.get("exact_tx_year", 0),
        "thin_query/thin_target": cell(q_title, t_title),
        "thin_query/rich_target": cell(q_title, t_desc),
        "rich_query/thin_target": cell(q_abstract, t_title),
        "rich_query/rich_target": cell(q_abstract, t_desc),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True, help="cached TechPort search JSON")
    parser.add_argument("--negatives", choices=("random", "metadata"), default="random")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    missing = [str(path) for path in (args.awards, args.techport) if not path.exists()]
    if missing:
        result: dict[str, object] = {"status": "blocked_missing_inputs", "missing": missing}
        payload = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload)
        print(payload, end="")
        return 0
    result = run(args.awards, args.techport, negatives=args.negatives)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"firms (fixed across all cells): {result['firms']}   model = TF-IDF   "
        f"negatives = {result['negatives']} (true-hard for {result['true_hard_neg_firms']})\n"
    )
    cell_names = (
        "thin_query/thin_target",
        "thin_query/rich_target",
        "rich_query/thin_target",
        "rich_query/rich_target",
    )
    cells = {name: cast(tuple[float, float], result[name]) for name in cell_names}
    for cell_name, (auc, top1) in cells.items():
        print(f"  {cell_name:24s} AUC {auc:.3f}  top1 {100 * top1:.0f}%")
    tt = cells["thin_query/thin_target"][0]
    tr = cells["thin_query/rich_target"][0]
    rt = cells["rich_query/thin_target"][0]
    rr = cells["rich_query/rich_target"][0]
    print(
        f"\n  target main effect (avg): +{((tr - tt) + (rr - rt)) / 2:.3f}   "
        f"query main effect (avg): +{((rt - tt) + (rr - tr)) / 2:.3f}   "
        f"interaction: {(rr - rt) - (tr - tt):.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
