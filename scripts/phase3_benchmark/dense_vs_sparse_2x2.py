"""Optional dense-model version of the provisional field-substitution 2x2.

The script is retained for a future rerun on an identical persisted cohort.
Historical dense values are not reproduced by this PR, and no model comparison
is valid unless both implementations consume the same text and negative IDs.

REQUIRES a torch + sentence-transformers environment (NOT the repo .venv — those deps are absent there):
    python -m venv .venv-torch && .venv-torch/bin/pip install torch sentence-transformers pandas scikit-learn
    .venv-torch/bin/python dense_vs_sparse_2x2.py --techport <cached_search.json>
On Apple silicon it uses the MPS GPU. The pure retrieval logic mirrors text_richness_2x2.firm_retrieval_auc.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from retrieval_metrics import tie_corrected_auc
from text_richness_2x2 import _firm_orgs, _is_sbir, normalize_name


def dense_auc(
    model, query_texts: list[str], target_texts: list[str], neg_indices: dict[int, np.ndarray]
) -> tuple[float, float]:
    """Firm-clustered retrieval AUC + top-1 under a dense embedding model, fixed negatives (Nomic prefixes)."""
    q = model.encode(
        ["search_query: " + t for t in query_texts], normalize_embeddings=True, batch_size=32
    )
    t = model.encode(
        ["search_document: " + t for t in target_texts], normalize_embeddings=True, batch_size=32
    )
    sims = q @ t.T
    n = len(query_texts)
    aucs, top1 = [], 0
    for i in range(n):
        neg = sims[i, neg_indices[i]]
        aucs.append(tie_corrected_auc(float(sims[i, i]), neg))
        top1 += int((neg >= sims[i, i]).sum() == 0)
    return float(np.mean(aucs)), top1 / n


def main(argv: list[str] | None = None) -> int:
    from sentence_transformers import SentenceTransformer  # local import: torch env only

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True)
    parser.add_argument("--model", default="nomic-ai/modernbert-embed-base")
    parser.add_argument("--device", default="mps")
    args = parser.parse_args(argv)

    awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
    awards = awards[awards["UEI"].str.len() > 5]
    name_to_ueis: dict[str, set[str]] = {}
    for company, uei in zip(awards["Company"], awards["UEI"], strict=True):
        key = normalize_name(company)
        if len(key) > 4:
            name_to_ueis.setdefault(key, set()).add(str(uei))
    name_to_uei = {key: next(iter(ueis)) for key, ueis in name_to_ueis.items() if len(ueis) == 1}
    q_title = (
        awards.groupby("UEI")["Award Title"]
        .apply(lambda s: " ".join(x for x in s if x)[:2000])
        .to_dict()
    )
    q_abstract = (
        awards.groupby("UEI")["Abstract"]
        .apply(lambda s: " ".join(x for x in s if x)[:8000])
        .to_dict()
    )

    listing = json.loads(args.techport.read_text())
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
            if uei and uei in q_abstract and uei not in rec:
                rec[uei] = {"desc": description[:8000], "title": str(project.get("title", ""))}
    firms = [
        u
        for u in rec
        if len(q_abstract[u]) > 80 and len(q_title.get(u, "")) > 10 and len(rec[u]["title"]) > 10
    ]
    n = len(firms)
    rng = np.random.RandomState(0)
    negs = {i: rng.choice([j for j in range(n) if j != i], 25, replace=False) for i in range(n)}

    model = SentenceTransformer(args.model, device=args.device)
    t_title = {u: rec[u]["title"] for u in firms}
    t_desc = {u: rec[u]["desc"] for u in firms}
    print(f"firms {n}   model {args.model}   device {args.device}\n")
    cells = {}
    for name, qmap, tmap in (
        ("thin_query/thin_target", q_title, t_title),
        ("thin_query/rich_target", q_title, t_desc),
        ("rich_query/thin_target", q_abstract, t_title),
        ("rich_query/rich_target", q_abstract, t_desc),
    ):
        auc, top1 = dense_auc(model, [qmap[u] for u in firms], [tmap[u] for u in firms], negs)
        cells[name] = auc
        print(f"  {name:24s} AUC {auc:.3f}  top1 {100 * top1:.0f}%")
    tt, tr = cells["thin_query/thin_target"], cells["thin_query/rich_target"]
    rt, rr = cells["rich_query/thin_target"], cells["rich_query/rich_target"]
    print(
        f"\n  DENSE: target +{((tr - tt) + (rr - rt)) / 2:.3f}  query +{((rt - tt) + (rr - tr)) / 2:.3f}  "
        f"interaction {(rr - rt) - (tr - tt):+.3f}"
    )
    print(
        "  Compare only with a TF-IDF artifact regenerated on the identical persisted cohort and negatives."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
