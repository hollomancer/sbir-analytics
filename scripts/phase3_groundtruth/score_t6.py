#!/usr/bin/env python3
"""T6 triangulated scoring: frozen fusion ranker vs independent Phase III ground truth.

Two paths (design: ``specs/phase3-transition-groundtruth/T6_DESIGN.md``):

* **Path A — contract ranking.** For each ground-truth firm whose real transition
  PIID resolves to a substantive-description contract in ``phase3_universe.jsonl``,
  build a candidate pool of the true contract + K decoy Phase III contracts and rank
  them with the frozen fusion model over (firm SBIR abstract x contract description).
  This is the scale headline and is agency-balanced / non-Navy-inclusive.
* **Path B — notice retrieval.** The faithful anchor: the frozen model over the
  notice corpus's own (query_abstract x notice_text, label) rows, limited to the
  ground-truth firms present there (small-N, Navy-heavy).

The A<->B gap is the contract->notice transfer caveat, measured. Neither path
validates forward / open-solicitation use — both score a *retrospective* ranking.

Epistemic tier: exploratory. T6 scoring results are non-citable until promoted
through the evidence-tier contract of specs/phase3-transition-groundtruth.
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

_WORKTREE_ROOT = Path(__file__).resolve().parents[2]
# The frozen ranker (fusion_scoring et al.) lives on this branch's sbir-ml, which
# the editable install does not point at; put it first so its submodules win.
sys.path.insert(0, str(_WORKTREE_ROOT / "packages" / "sbir-ml"))
sys.path.insert(0, str(_WORKTREE_ROOT))

import pandas as pd  # noqa: E402

from scripts.phase3_groundtruth.resolve_firm_awards import (  # noqa: E402
    normalize_name,
    resolve_firm,
)
from sbir_ml.transition.detection.fusion_model import (  # noqa: E402
    load_fusion_coefficients,
)
from sbir_ml.transition.detection.fusion_scoring import (  # noqa: E402
    score_pairs_with_fusion,
)


EPISTEMIC_TIER = "exploratory"

REPO_MAIN = Path("/Users/hollomancer/projects/sbir-analytics")
DEFAULT_AWARD_DATA = REPO_MAIN / "data" / "raw" / "sbir" / "award_data.csv"
DEFAULT_UNIVERSE = REPO_MAIN / "data" / "processed" / "sbir_phase3" / "phase3_universe.jsonl"
DEFAULT_CORPUS = Path(
    "/Users/hollomancer/projects/sbir-analytics/.claude/worktrees/"
    "notice-corpus-fusion-spec/data/derived/phase3_notice_corpus.parquet"
)
SPEC_DIR = _WORKTREE_ROOT / "specs" / "phase3-transition-groundtruth"
COLLECTED_DIR = SPEC_DIR / "collected"

SEED = 20260801
DECOYS = 9
ABSTRACT_CAP = 4000
SUBSTANTIVE_MIN = 80
THIN_MIN = 20
BOOTSTRAP_N = 2000
PROXY_BASELINE_P1 = 0.681

# FPDS contract awards are the award-notice stage of a procurement, so every
# Path A candidate is encoded as the corpus's "Award Notice" ordinal. It is
# therefore constant across a firm's contract-only pool and cannot shift the
# within-firm ranking; it only keeps the feature vector faithful to the fit.
CONTRACT_NOTICE_TYPE = "Award Notice"

# Description boilerplate that clears the length gate only when padded; treat the
# canonical self-declarations as non-substantive regardless of length.
_BOILERPLATE = {"SBIRPHASEIIIAWARD", "SBIRPHASEIII", "SBIRPHASE3AWARD", "SBIRPHASE3"}

_PIID_TOKEN = re.compile(r"[A-Za-z0-9\-]{10,}")
_NAVY_OFFICE = re.compile(r"\b(NAV|NAVAIR|NAVAL|NUWC|NIWC|NSWC|SPAWAR|MARINE|MARCOR)", re.I)


class TechDomain(StrEnum):
    MEDICAL = "medical"
    MATERIALS = "materials"
    LOGISTICS = "logistics"
    SENSING_OTHER = "sensing/other"


class Provenance(StrEnum):
    INDEPENDENT = "independent"
    PIPELINE = "pipeline"


_DOMAIN_KEYWORDS: dict[TechDomain, tuple[str, ...]] = {
    TechDomain.MEDICAL: (
        "medic",
        "health",
        "patient",
        "wound",
        "drug",
        "vaccine",
        "clinic",
        "surg",
        "therap",
        "diagnos",
        "pharma",
        "blood",
        "hospital",
        "casualty",
        "biolog",
        "antimicrob",
        "hemorrhage",
        "trauma",
    ),
    TechDomain.MATERIALS: (
        "magnet",
        "alloy",
        "coating",
        "composite",
        "material",
        "polymer",
        "ceramic",
        "corros",
        "additive manufact",
        "metal",
        "adhesive",
        "textile",
    ),
    TechDomain.LOGISTICS: (
        "supply",
        "spare",
        "logistic",
        "depot",
        "inventory",
        "sustainment",
        "maintenance",
        "repair",
        "overhaul",
        "part number",
        "nsn",
    ),
}


def norm_piid(value: object) -> str:
    """Strip non-alphanumerics and uppercase — the FPDS-key comparison form."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def corpus_key(name: object) -> str:
    """Firm key in the notice corpus's form: normalized name with spaces removed."""
    return normalize_name(name).replace(" ", "")


def naics_code(naics: object) -> str:
    """Pull the numeric code out of the universe NAICS field (a dict or a string)."""
    if isinstance(naics, dict):
        return str(naics.get("code") or "")
    return str(naics or "")


def is_substantive(description: object, *, minimum: int = SUBSTANTIVE_MIN) -> bool:
    """A description long enough to carry signal and not a self-declaration stub."""
    text = str(description or "")
    if len(text) < minimum:
        return False
    return norm_piid(text) not in _BOILERPLATE


def assign_tech_domain(text: str, sub_agency: str) -> TechDomain:
    """Coarse domain from agency prior then description keywords."""
    agency = (sub_agency or "").lower()
    if "health" in agency:
        return TechDomain.MEDICAL
    if "logistics" in agency:
        return TechDomain.LOGISTICS
    lowered = text.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return domain
    return TechDomain.SENSING_OTHER


def provenance_of(source_url: str) -> Provenance:
    """pipeline == attributed from the in-repo universe file; else independent."""
    return (
        Provenance.PIPELINE if "phase3_universe" in (source_url or "") else Provenance.INDEPENDENT
    )


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
@dataclass
class UniverseContract:
    award_id: str
    key: str
    recipient_name: str
    recipient_uei: str
    description: str
    naics: str
    award_type: str
    awarding_sub_agency: str
    funding_sub_agency: str


def load_universe(path: Path) -> tuple[dict[str, UniverseContract], list[UniverseContract]]:
    """Return (by-normalized-PIID index, full list) of universe Phase III contracts."""
    by_key: dict[str, UniverseContract] = {}
    rows: list[UniverseContract] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            d = json.loads(line)
            contract = UniverseContract(
                award_id=str(d.get("Award ID") or ""),
                key=norm_piid(d.get("Award ID")),
                recipient_name=str(d.get("Recipient Name") or ""),
                recipient_uei=str(d.get("Recipient UEI") or ""),
                description=str(d.get("Description") or ""),
                naics=naics_code(d.get("NAICS")),
                award_type=str(d.get("Contract Award Type") or ""),
                awarding_sub_agency=str(d.get("Awarding Sub Agency") or ""),
                funding_sub_agency=str(d.get("Funding Sub Agency") or ""),
            )
            by_key[contract.key] = contract
            rows.append(contract)
    return by_key, rows


@dataclass
class GTRow:
    firm: str
    agency: str
    transition_contract: str
    source_url: str
    stratum: str
    piids: list[str] = field(default_factory=list)


def load_gt_rows(collected_dir: Path) -> list[GTRow]:
    """All procurement ground-truth rows with their candidate PIID tokens."""
    rows: list[GTRow] = []
    for path in sorted(collected_dir.glob("*.csv")):
        with path.open(encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                if (raw.get("transition_type") or "").strip() != "procurement":
                    continue
                contract = raw.get("transition_contract") or ""
                piids = [
                    tok
                    for tok in (norm_piid(t) for t in _PIID_TOKEN.findall(contract))
                    if 12 <= len(tok) <= 20 and any(c.isdigit() for c in tok)
                ]
                rows.append(
                    GTRow(
                        firm=str(raw.get("firm") or "").strip(),
                        agency=str(raw.get("agency") or "").strip(),
                        transition_contract=contract,
                        source_url=str(raw.get("source_url") or "").strip(),
                        stratum=str(raw.get("stratum") or "").strip() or "unknown",
                        piids=piids,
                    )
                )
    return rows


def load_firm_abstracts(award_data_path: Path) -> dict[str, list[str]]:
    """Map normalized company name -> its deduped Phase I/II abstract strings."""
    df = pd.read_csv(award_data_path, usecols=["Company", "Phase", "Abstract"], dtype=str)
    df = df[df["Abstract"].notna() & df["Phase"].isin(["Phase I", "Phase II"])]
    df["key"] = df["Company"].map(normalize_name)
    out: dict[str, list[str]] = {}
    for key, group in df.groupby("key"):
        seen: dict[str, None] = {}
        for text in group["Abstract"]:
            stripped = str(text).strip()
            if stripped:
                seen.setdefault(stripped, None)
        if seen:
            out[str(key)] = list(seen)
    return out


def firm_query_text(
    firm: str, award_data_path: Path, abstracts_by_key: dict[str, list[str]]
) -> tuple[str | None, str]:
    """Resolve firm -> pooled, capped SBIR abstract text; ("", reason) on failure."""
    resolution = resolve_firm(firm, str(award_data_path))
    if resolution.matched_company is None:
        return None, "firm_unresolved"
    key = normalize_name(resolution.matched_company)
    abstracts = abstracts_by_key.get(key, [])
    if not abstracts:
        return None, "no_phase12_abstract"
    return " ".join(abstracts)[:ABSTRACT_CAP], "ok"


# --------------------------------------------------------------------------- #
# Ranking + metrics                                                           #
# --------------------------------------------------------------------------- #
def competition_rank(true_score: float, other_scores: list[float]) -> int:
    """1-based rank of the true item; ties do not credit the true (strict >)."""
    return 1 + sum(1 for s in other_scores if s > true_score)


def score_candidates(
    query: str,
    targets: list[str],
    naics: list[str],
    firm: str,
    notice_types: list[str] | None = None,
) -> list[float]:
    """Frozen-fusion score for one firm's candidate pool (TF-IDF fit within the pool)."""
    n = len(targets)
    types = notice_types if notice_types is not None else [CONTRACT_NOTICE_TYPE] * n
    return score_pairs_with_fusion([query] * n, targets, naics, types, firm_names=[firm] * n)


@dataclass
class RankedCase:
    firm: str
    piid: str
    rank: int
    n_candidates: int
    agency: str
    provenance: Provenance
    stratum: str
    tech_domain: TechDomain


def aggregate(ranks: list[int]) -> dict[str, float]:
    """precision@1, precision@3, MRR over 1-based ranks."""
    if not ranks:
        return {"n": 0, "p1": 0.0, "p3": 0.0, "mrr": 0.0}
    n = len(ranks)
    return {
        "n": n,
        "p1": sum(1 for r in ranks if r == 1) / n,
        "p3": sum(1 for r in ranks if r <= 3) / n,
        "mrr": sum(1.0 / r for r in ranks) / n,
    }


def bootstrap_cis(ranks: list[int], *, seed: int = SEED, draws: int = BOOTSTRAP_N) -> dict:
    """95% percentile CIs for p1/p3/mrr via case resampling."""
    if not ranks:
        return dict.fromkeys(("p1", "p3", "mrr"), (0.0, 0.0))
    rng = random.Random(seed)
    n = len(ranks)
    samples: dict[str, list[float]] = {"p1": [], "p3": [], "mrr": []}
    for _ in range(draws):
        resample = [ranks[rng.randrange(n)] for _ in range(n)]
        stats = aggregate(resample)
        for key in samples:
            samples[key].append(stats[key])

    def ci(values: list[float]) -> tuple[float, float]:
        values = sorted(values)
        lo = values[int(0.025 * (len(values) - 1))]
        hi = values[int(0.975 * (len(values) - 1))]
        return round(lo, 3), round(hi, 3)

    return {key: ci(vals) for key, vals in samples.items()}


# --------------------------------------------------------------------------- #
# Path A                                                                       #
# --------------------------------------------------------------------------- #
def _decoy_pool(
    universe: list[UniverseContract], true: UniverseContract, firm_key: str, minimum: int
) -> tuple[list[UniverseContract], list[UniverseContract]]:
    """(same-awarding-agency, all-agency) substantive Phase III contracts, firm excluded."""
    same, everywhere = [], []
    for c in universe:
        if c.key == true.key or not is_substantive(c.description, minimum=minimum):
            continue
        if normalize_name(c.recipient_name) == firm_key or (
            true.recipient_uei and c.recipient_uei == true.recipient_uei
        ):
            continue
        everywhere.append(c)
        if c.awarding_sub_agency == true.awarding_sub_agency:
            same.append(c)
    return same, everywhere


def sample_decoys(
    universe: list[UniverseContract],
    true: UniverseContract,
    firm_key: str,
    *,
    minimum: int,
    rng: random.Random,
) -> list[UniverseContract]:
    """K same-agency decoys, backfilled from all agencies when same-agency is short."""
    same, everywhere = _decoy_pool(universe, true, firm_key, minimum)
    rng.shuffle(same)
    chosen = same[:DECOYS]
    if len(chosen) < DECOYS:
        have = {c.key for c in chosen}
        backfill = [c for c in everywhere if c.key not in have]
        rng.shuffle(backfill)
        chosen += backfill[: DECOYS - len(chosen)]
    return chosen


def _rank_true(
    query: str, true: UniverseContract, decoys: list[UniverseContract], firm: str
) -> int:
    targets = [true.description] + [c.description for c in decoys]
    naics = [true.naics] + [c.naics for c in decoys]
    scores = score_candidates(query, targets, naics, firm)
    return competition_rank(scores[0], scores[1:])


@dataclass
class PathAResult:
    scored: list[RankedCase]
    hard: list[RankedCase]
    dropped: list[tuple[str, str, str]]  # (firm, piid_or_contract, reason)
    n_gt_rows: int
    n_piid_matched: int


def run_path_a(
    gt_rows: list[GTRow],
    universe_by_key: dict[str, UniverseContract],
    universe_list: list[UniverseContract],
    abstracts_by_key: dict[str, list[str]],
    award_data_path: Path,
    *,
    minimum: int = SUBSTANTIVE_MIN,
) -> PathAResult:
    """Rank each resolvable GT transition contract against decoys; balanced + hard variant."""
    scored: list[RankedCase] = []
    hard: list[RankedCase] = []
    dropped: list[tuple[str, str, str]] = []
    n_piid_matched = 0
    seen_pairs: set[tuple[str, str]] = set()

    for row in gt_rows:
        true = next((universe_by_key[p] for p in row.piids if p in universe_by_key), None)
        if true is None:
            reason = "no_piid_in_contract_text" if not row.piids else "piid_not_in_universe"
            dropped.append((row.firm, row.transition_contract, reason))
            continue
        n_piid_matched += 1
        pair = (normalize_name(row.firm), true.key)
        if pair in seen_pairs:
            dropped.append((row.firm, true.award_id, "duplicate_firm_contract"))
            continue
        seen_pairs.add(pair)
        if not is_substantive(true.description, minimum=minimum):
            dropped.append((row.firm, true.award_id, "thin_description"))
            continue

        query, reason = firm_query_text(row.firm, award_data_path, abstracts_by_key)
        if query is None:
            dropped.append((row.firm, true.award_id, reason))
            continue

        firm_key = normalize_name(row.firm)
        rng = random.Random(f"{SEED}:{true.key}")
        decoys = sample_decoys(universe_list, true, firm_key, minimum=minimum, rng=rng)
        if len(decoys) < DECOYS:
            dropped.append((row.firm, true.award_id, f"insufficient_decoys_{len(decoys)}"))
            continue

        rank = _rank_true(query, true, decoys, row.firm)
        scored.append(
            RankedCase(
                firm=row.firm,
                piid=true.award_id,
                rank=rank,
                n_candidates=len(decoys) + 1,
                agency=true.awarding_sub_agency,
                provenance=provenance_of(row.source_url),
                stratum=row.stratum,
                tech_domain=assign_tech_domain(true.description, true.awarding_sub_agency),
            )
        )

        # Hard variant: decoys are the firm's OWN other substantive Phase III contracts.
        own = [
            c
            for c in universe_list
            if c.key != true.key
            and is_substantive(c.description, minimum=minimum)
            and (
                (true.recipient_uei and c.recipient_uei == true.recipient_uei)
                or normalize_name(c.recipient_name) == firm_key
            )
        ]
        if own:
            hrank = _rank_true(query, true, own, row.firm)
            hard.append(
                RankedCase(
                    firm=row.firm,
                    piid=true.award_id,
                    rank=hrank,
                    n_candidates=len(own) + 1,
                    agency=true.awarding_sub_agency,
                    provenance=provenance_of(row.source_url),
                    stratum=row.stratum,
                    tech_domain=assign_tech_domain(true.description, true.awarding_sub_agency),
                )
            )

    return PathAResult(scored, hard, dropped, len(gt_rows), n_piid_matched)


# --------------------------------------------------------------------------- #
# Path B                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class PathBResult:
    ranks: list[int]
    n_firms: int
    navy_firms: int


def run_path_b(corpus_path: Path, gt_name_keys: set[str]) -> PathBResult:
    """Rank each GT firm's notice candidates by frozen fusion; label==1 is the target."""
    df = pd.read_parquet(corpus_path)
    ranks: list[int] = []
    navy = 0
    firms = 0
    for name_key, group in df.groupby("name_key"):
        if str(name_key) not in gt_name_keys or len(group) < 2:
            continue
        if not (group["label"] == 1).any():
            continue
        firms += 1
        query = str(group["query_abstract"].iloc[0])
        firm = str(group["firm_name"].iloc[0])
        targets = [str(t) for t in group["notice_text"]]
        naics = [str(c) for c in group["naics_code"]]
        types = [str(t) for t in group["notice_type"]]
        scores = score_candidates(query, targets, naics, firm, notice_types=types)
        labels = list(group["label"])
        pos = [(s, i) for i, (s, lab) in enumerate(zip(scores, labels, strict=True)) if lab == 1]
        best_score = max(s for s, _ in pos)
        others = [s for s, lab in zip(scores, labels, strict=True) if lab != 1]
        ranks.append(competition_rank(best_score, others))
        offices = " ".join(str(o) for o in group["office"])
        if _NAVY_OFFICE.search(offices):
            navy += 1
    return PathBResult(ranks, firms, navy)


# --------------------------------------------------------------------------- #
# Reporting                                                                    #
# --------------------------------------------------------------------------- #
def _stratify(cases: list[RankedCase], key) -> list[tuple[str, dict, dict]]:
    groups: dict[str, list[int]] = {}
    for c in cases:
        groups.setdefault(str(key(c)), []).append(c.rank)
    out = []
    for name, ranks in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        out.append((name, aggregate(ranks), bootstrap_cis(ranks)))
    return out


def _fmt_row(label: str, stats: dict, cis: dict) -> str:
    return (
        f"| {label} | {stats['n']} | {stats['p1']:.3f} {cis['p1']} | "
        f"{stats['p3']:.3f} {cis['p3']} | {stats['mrr']:.3f} {cis['mrr']} |"
    )


def _table(title: str, cases: list[RankedCase], key) -> list[str]:
    lines = [
        f"**{title}**",
        "",
        "| group | n | p@1 [95% CI] | p@3 [95% CI] | MRR [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for name, stats, cis in _stratify(cases, key):
        lines.append(_fmt_row(name, stats, cis))
    lines.append("")
    return lines


def write_results(
    path_a: PathAResult,
    path_a_thin: PathAResult,
    path_b: PathBResult,
    gt_overlap: int,
    out_path: Path,
    dropped_csv: Path,
) -> None:
    scored = path_a.scored
    head = aggregate([c.rank for c in scored])
    head_ci = bootstrap_cis([c.rank for c in scored])
    hard = aggregate([c.rank for c in path_a.hard])
    hard_ci = bootstrap_cis([c.rank for c in path_a.hard])
    thin = aggregate([c.rank for c in path_a_thin.scored])
    thin_ci = bootstrap_cis([c.rank for c in path_a_thin.scored])
    pb = aggregate(path_b.ranks)
    pb_ci = bootstrap_cis(path_b.ranks)

    lines: list[str] = []
    lines.append("# T6 — Triangulated Scoring Results")
    lines.append("")
    lines.append(
        "Frozen fusion ranker (`fusion_coefficients.json`) vs independent Phase III "
        "ground truth. Generated by `scripts/phase3_groundtruth/score_t6.py`. All numbers "
        "reproducible with `SEED=20260801`, K=9 decoys, 2000-resample bootstrap CIs."
    )
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Procurement GT rows scanned: **{path_a.n_gt_rows}**")
    lines.append(f"- Rows whose PIID resolves into `phase3_universe`: **{path_a.n_piid_matched}**")
    lines.append(
        f"- Path A scored (substantive desc, K=9 decoys): **{head['n']}**; "
        f"thin-inclusive sensitivity set: **{thin['n']}**"
    )
    lines.append(f"- Path A hard-decoy variant (firm's own contracts, >=1 other): **{hard['n']}**")
    lines.append(
        f"- Path B firms (GT ∩ notice corpus, >=2 candidates): **{path_b.n_firms}** "
        f"(Navy {path_b.navy_firms} = {path_b.navy_firms / max(path_b.n_firms, 1):.0%})"
    )
    lines.append(f"- GT firms present in the notice corpus at all: **{gt_overlap}**")
    lines.append("")

    lines.append("## Path A — contract ranking (headline)")
    lines.append("")
    lines.append("| set | n | p@1 [95% CI] | p@3 [95% CI] | MRR [95% CI] |")
    lines.append("|---|---|---|---|---|")
    lines.append(_fmt_row("substantive (headline)", head, head_ci))
    lines.append(_fmt_row("thin-inclusive (sensitivity)", thin, thin_ci))
    lines.append(_fmt_row("hard decoys = firm's own contracts", hard, hard_ci))
    lines.append("")
    lines.append(
        f"Proxy-label baseline (T5) p@1 = **{PROXY_BASELINE_P1:.3f}**. "
        "Delta = headline p@1 minus baseline."
    )
    lines.append("")

    lines += _table("Path A by awarding sub-agency", scored, lambda c: c.agency)
    lines += _table("Path A by tech domain", scored, lambda c: c.tech_domain)
    lines += _table("Path A by provenance", scored, lambda c: c.provenance)
    lines += _table("Path A by stratum", scored, lambda c: c.stratum)

    lines.append("## Path B — notice retrieval (faithful anchor, Navy-limited)")
    lines.append("")
    lines.append("| set | n | p@1 [95% CI] | p@3 [95% CI] | MRR [95% CI] |")
    lines.append("|---|---|---|---|---|")
    lines.append(_fmt_row("notice corpus (GT firms)", pb, pb_ci))
    lines.append("")
    lines.append(
        f"N={path_b.n_firms} firms, {path_b.navy_firms / max(path_b.n_firms, 1):.0%} Navy — an "
        "anchor, not a headline. Each firm's true notice competes only against its own "
        "candidate notices (per-firm ranking)."
    )
    lines.append("")

    lines.append("## Triangulation — the A<->B gap")
    lines.append("")
    gap = head["p1"] - pb["p1"]
    lines.append(
        f"Path A p@1 {head['p1']:.3f} vs Path B p@1 {pb['p1']:.3f} (gap {gap:+.3f}). "
        "Path A ranks *contract descriptions*; Path B ranks *solicitation/notice text* — the "
        "structure the model was fit on. The gap is the contract->notice transfer caveat, "
        "measured on overlapping firms. Path A's larger decoy realism (cross-firm, same-agency) "
        "and Path B's fit-faithful text pull in opposite directions; read them together, not "
        "as one number."
    )
    lines.append("")

    lines.append("## Go / no-go")
    lines.append("")
    clears = head["p1"] >= PROXY_BASELINE_P1 and head_ci["p1"][0] > 0.10
    verdict = "ORDER-CAPABLE" if clears else "DEADLINE-PRIMARY"
    lines.append(f"**Read: {verdict}.**")
    lines.append("")
    lines.append(
        "- Fusion should " + ("order" if clears else "NOT solely order") + " the review packet: "
        f"headline p@1 {head['p1']:.3f} [{head_ci['p1'][0]:.3f}, {head_ci['p1'][1]:.3f}] "
        f"vs the {PROXY_BASELINE_P1:.3f} proxy baseline and {1 / 10:.3f} random."
    )
    lines.append(
        "- Neither path validates forward / open-solicitation use: both rank a *retrospective* "
        "candidate set where the true transition is present by construction."
    )
    lines.append(
        "- The hard-decoy variant (firm's own contracts) is the honest stress case; when it "
        "collapses, fusion is separating firms, not contracts — keep deadline signals primary."
    )
    lines.append("")

    lines.append("## Dropped / unscorable cases")
    lines.append("")
    reasons = Counter(r for _, _, r in path_a.dropped)
    lines.append(f"Total dropped (substantive pass): **{len(path_a.dropped)}**. By reason:")
    lines.append("")
    for reason, count in reasons.most_common():
        lines.append(f"- `{reason}`: {count}")
    lines.append("")
    lines.append(f"Full per-case drop log: `{dropped_csv.name}` (no silent truncation).")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with dropped_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["firm", "contract_or_piid", "reason"])
        writer.writerows(path_a.dropped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--award-data", type=Path, default=DEFAULT_AWARD_DATA)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--collected", type=Path, default=COLLECTED_DIR)
    parser.add_argument("--out", type=Path, default=SPEC_DIR / "T6_RESULTS.md")
    parser.add_argument("--dropped", type=Path, default=SPEC_DIR / "t6_dropped_cases.csv")
    args = parser.parse_args(argv)

    # Fail loudly if the frozen ranker is not the expected 6-feature model.
    model = load_fusion_coefficients()
    assert len(model.feature_order) == 6, model.feature_order

    universe_by_key, universe_list = load_universe(args.universe)
    gt_rows = load_gt_rows(args.collected)
    abstracts_by_key = load_firm_abstracts(args.award_data)

    path_a = run_path_a(gt_rows, universe_by_key, universe_list, abstracts_by_key, args.award_data)
    path_a_thin = run_path_a(
        gt_rows,
        universe_by_key,
        universe_list,
        abstracts_by_key,
        args.award_data,
        minimum=THIN_MIN,
    )

    gt_name_keys = {corpus_key(r.firm) for r in gt_rows}
    corpus_keys = set(pd.read_parquet(args.corpus, columns=["name_key"])["name_key"].astype(str))
    gt_overlap = len(gt_name_keys & corpus_keys)
    path_b = run_path_b(args.corpus, gt_name_keys)

    write_results(path_a, path_a_thin, path_b, gt_overlap, args.out, args.dropped)

    head = aggregate([c.rank for c in path_a.scored])
    hard = aggregate([c.rank for c in path_a.hard])
    pb = aggregate(path_b.ranks)
    print(
        f"Path A headline  n={head['n']}  p@1={head['p1']:.3f}  p@3={head['p3']:.3f}  "
        f"MRR={head['mrr']:.3f}"
    )
    print(
        f"Path A hard      n={hard['n']}  p@1={hard['p1']:.3f}  p@3={hard['p3']:.3f}  "
        f"MRR={hard['mrr']:.3f}"
    )
    print(
        f"Path B anchor    n={pb['n']}  p@1={pb['p1']:.3f}  p@3={pb['p3']:.3f}  "
        f"MRR={pb['mrr']:.3f}  navy={path_b.navy_firms}/{path_b.n_firms}"
    )
    print(f"dropped={len(path_a.dropped)}  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
