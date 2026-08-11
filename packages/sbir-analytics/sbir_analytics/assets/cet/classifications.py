"""CET classification assets.

This module contains:
- enriched_cet_award_classifications: Batch classify awards with CET taxonomy
- enriched_cet_patent_classifications: Batch classify patents with CET taxonomy
- cet_award_classifications_quality_check: Quality validation for award classifications
- Helper functions for classification processing
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from sbir_ml.ml.config.taxonomy_loader import TaxonomyLoader

from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    Output,
    asset,
    asset_check,
    save_dataframe_parquet,
)


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from sbir_etl.models.quality import ModuleReport
    from sbir_etl.utils.reporting.analyzers.cet_analyzer import CetClassificationAnalyzer
except Exception:
    ModuleReport = None  # type: ignore[assignment, misc, no-redef]
    CetClassificationAnalyzer = None  # type: ignore[assignment, misc, no-redef]


@asset_check(
    asset="enriched_cet_award_classifications",
    description="Award classification quality thresholds (high confidence, evidence coverage) from checks JSON",
)
def cet_award_classifications_quality_check(context) -> AssetCheckResult:
    """
    Validate CET award classification quality against targets.
    Consumes data/processed/cet_award_classifications.checks.json written by the asset.
    """
    import json

    checks_path = Path("data/processed/cet_award_classifications.checks.json")
    if not checks_path.exists():
        desc = "Missing award classification checks JSON; classification asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        with checks_path.open("r", encoding="utf-8") as fh:
            checks = json.load(fh)
    except Exception as exc:
        desc = f"Failed to read award classification checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path)},
        )

    # Targets (defaults align with project guidance; override via env)
    target_high_conf = float(
        os.environ.get("SBIR_ETL__CET__CLASSIFICATION__HIGH_CONF_THRESHOLD", "0.60")
    )
    target_evidence_cov = float(
        os.environ.get("SBIR_ETL__CET__CLASSIFICATION__EVIDENCE_COVERAGE_THRESHOLD", "0.80")
    )

    high_conf_rate = checks.get("high_conf_rate")
    evidence_cov_rate = checks.get("evidence_coverage_rate")
    model_reason = checks.get("reason")

    # If model missing/failed to load, fail loudly
    if model_reason in {"model_missing", "model_load_failed"}:
        desc = f"Classification invalid: {model_reason}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), **checks},
        )

    # If metrics are missing, warn/fail
    metrics_present = (high_conf_rate is not None) and (evidence_cov_rate is not None)
    if not metrics_present:
        desc = "Classification checks JSON missing quality metrics"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), **checks},
        )

    passed = (high_conf_rate >= target_high_conf) and (evidence_cov_rate >= target_evidence_cov)
    desc = (
        "Classification quality meets thresholds"
        if passed
        else "Classification quality below thresholds"
    )
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    metadata = {
        "checks_path": str(checks_path),
        "high_conf_rate": high_conf_rate,
        "evidence_coverage_rate": evidence_cov_rate,
        "target_high_conf_rate": target_high_conf,
        "target_evidence_coverage_rate": target_evidence_cov,
        **{
            k: v for k, v in checks.items() if k not in {"high_conf_rate", "evidence_coverage_rate"}
        },
    }
    return AssetCheckResult(passed=passed, severity=severity, description=desc, metadata=metadata)  # type: ignore[arg-type]


@asset(
    name="enriched_cet_award_classifications",
    key_prefix=["ml"],
    description=(
        "Batch classify SBIR awards with the trained CET classifier, extract evidence "
        "per classification, persist results to `data/processed/cet_award_classifications.parquet` "
        "and emit a companion checks JSON for automated validation."
    ),
)
def enriched_cet_award_classifications() -> Output:
    """
    Dagster asset to perform batch CET classification over enriched award records.

    Required inputs and dependencies fail the materialization instead of producing a
    placeholder artifact. A successful materialization therefore means that real input
    data was processed and the returned path names the artifact that was actually written.

    Behavior:
    - Loads a trained ApplicabilityModel from a well-known artifacts path.
    - Loads the taxonomy via TaxonomyLoader and instantiates EvidenceExtractor.
    - Reads enriched award records from `data/processed/enriched_sbir_awards.ndjson`
      (NDJSON) or `data/processed/enriched_sbir_awards.parquet` if available.
    - Classifies awards in batches (configurable via classification config) and attaches
      up to N evidence statements per CET classification.
    - Persists classifications to `data/processed/cet_award_classifications.parquet`
      using the same parquet -> NDJSON fallback approach as the taxonomy asset.
    - Writes a checks JSON summarizing classification coverage and confidence rates.
    """
    logger.info("Starting cet_award_classifications asset")

    # Local imports to keep module import-safe when optional deps are missing

    # Lazy imports keep repository discovery import-safe, but materialization requires them.
    try:
        from sbir_ml.ml.features.evidence_extractor import EvidenceExtractor
    except Exception as exc:
        raise RuntimeError("CET evidence extraction dependency is unavailable") from exc

    try:
        from sbir_ml.ml.models.cet_classifier import ApplicabilityModel
    except Exception as exc:
        raise RuntimeError("CET award classifier dependency is unavailable") from exc

    # Paths and defaults
    awards_ndjson = Path("data/processed/enriched_sbir_awards.ndjson")
    awards_parquet = Path("data/processed/enriched_sbir_awards.parquet")
    model_path = Path("artifacts/models/cet_classifier_v1.pkl")
    output_path = Path("data/processed/cet_award_classifications.parquet")
    checks_path = output_path.with_suffix(".checks.json")

    # Load taxonomy and classification config (required for EvidenceExtractor and thresholds)
    try:
        loader = TaxonomyLoader()
        taxonomy = loader.load_taxonomy()
        classification_config = loader.load_classification_config()
    except Exception as exc:
        raise RuntimeError("Failed to load the CET taxonomy and classification config") from exc

    # Load awards (prefer parquet, then ndjson).
    awards: list[dict] = []
    try:
        if awards_parquet.exists():
            import pandas as pd

            df_awards = pd.read_parquet(awards_parquet)
            # Expect dataframe with at least award_id/title/abstract/keywords
            for _, row in df_awards.iterrows():
                awards.append(
                    {
                        "award_id": str(row.get("award_id") or row.get("id") or ""),
                        "title": str(row.get("title") or ""),
                        "abstract": str(row.get("abstract") or ""),
                        "keywords": row.get("keywords") or "",
                    }
                )
        elif awards_ndjson.exists():
            with open(awards_ndjson, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        awards.append(json.loads(line))
        else:
            raise FileNotFoundError(
                f"No enriched award input found at {awards_parquet} or {awards_ndjson}"
            )
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError("Failed to load enriched awards for CET classification") from exc

    if not awards:
        raise ValueError("Enriched award input is empty; no awards are available to classify")

    if not model_path.exists():
        raise FileNotFoundError(
            f"Trained CET award model not found: {model_path}. "
            "Provision a trained ApplicabilityModel artifact at this path before materializing."
        )

    # Load trained model
    try:
        model = ApplicabilityModel.load(model_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to load trained CET award model: {model_path}") from exc

    if model is None:
        raise RuntimeError(f"CET award model loader returned no model: {model_path}")

    try:
        extractor = EvidenceExtractor(list(taxonomy.cet_areas), classification_config)  # type: ignore[arg-type]
    except Exception as exc:
        raise RuntimeError("Failed to initialize the CET evidence extractor") from exc

    # Build texts for classification and perform batch classification
    texts = []
    award_ids = []
    for a in awards:
        combined = " ".join(
            filter(
                None,
                [
                    str(a.get("title", "")),
                    str(a.get("abstract", "")),
                    " ".join(a.get("keywords") or []),
                ],
            )
        )
        texts.append(combined)
        award_ids.append(a.get("award_id") or "")

    batch_size = (
        classification_config.get("batch", {}).get("size", 1000)
        if isinstance(classification_config, dict)
        else 1000
    )

    # Perform batch classification.
    try:
        classifications_by_award = list(model.classify_batch(texts, batch_size=batch_size))
    except Exception as exc:
        raise RuntimeError("CET award batch classification failed") from exc

    if len(classifications_by_award) != len(awards):
        raise ValueError(
            "CET award classifier returned "
            f"{len(classifications_by_award)} results for {len(awards)} source rows"
        )

    # Attach evidence if extractor available
    doc_parts_list = [
        {
            "abstract": str(a.get("abstract", "")),
            "keywords": " ".join(a.get("keywords") or []),
            "title": str(a.get("title", "")),
        }
        for a in awards
    ]
    try:
        classifications_with_evidence = list(
            extractor.extract_batch_evidence(classifications_by_award, doc_parts_list)
        )
    except Exception as exc:
        raise RuntimeError("CET award evidence extraction failed") from exc

    if len(classifications_with_evidence) != len(awards):
        raise ValueError(
            "CET award evidence extractor returned "
            f"{len(classifications_with_evidence)} results for {len(awards)} source rows"
        )

    # Flatten classification results into a DataFrame (one row per award)
    import pandas as pd

    rows: list[Any] = []
    for aid, cls_list in zip(award_ids, classifications_with_evidence, strict=True):
        if not cls_list:
            rows.append(
                {
                    "award_id": aid,
                    "primary_cet": None,
                    "primary_score": None,
                    "supporting_cets": [],
                    "evidence": [],
                    "classified_at": None,
                    "taxonomy_version": model.taxonomy_version if model else taxonomy.version,
                }
            )
            continue

        primary = cls_list[0]
        supporting = cls_list[1:4] if len(cls_list) > 1 else []
        rows.append(
            {
                "award_id": aid,
                "primary_cet": primary.cet_id,
                "primary_score": primary.score,
                "supporting_cets": [
                    {
                        "cet_id": s.cet_id,
                        "score": s.score,
                        "classification": s.classification.value
                        if hasattr(s.classification, "value")
                        else str(s.classification),
                    }
                    for s in supporting
                ],
                "evidence": [
                    {
                        "excerpt": e.excerpt,
                        "source": e.source_location,
                        "rationale": e.rationale_tag,
                    }
                    for e in primary.evidence
                ]
                if getattr(primary, "evidence", None)
                else [],
                "classified_at": primary.classified_at,
                "taxonomy_version": primary.taxonomy_version,
            }
        )

    df_out = pd.DataFrame(rows)

    # Persist classifications (parquet preferred, NDJSON fallback)
    artifact_path = save_dataframe_parquet(df_out, output_path)

    # Build checks: coverage, high-confidence rate, evidence coverage
    num_awards = len(rows)
    num_classified = sum(1 for r in rows if r.get("primary_cet"))
    # Precompute high confidence threshold to avoid complex inline conditional expressions
    if isinstance(classification_config, dict):
        high_threshold = classification_config.get("confidence_thresholds", {}).get("high", 70.0)  # type: ignore[unreachable]
    else:
        # classification_config may be a Pydantic model; attempt attribute access, fall back to default
        try:
            high_threshold = getattr(classification_config, "confidence_thresholds", {}).get(
                "high", 70.0
            )
        except Exception:
            high_threshold = 70.0
    high_conf_count = sum(1 for r in rows if (r.get("primary_score") or 0) >= high_threshold)
    evidence_coverage = sum(1 for r in rows if r.get("evidence"))

    checks = {
        "ok": True,
        "num_awards": num_awards,
        "num_classified": num_classified,
        "high_conf_count": int(high_conf_count),
        "high_conf_rate": float(high_conf_count / max(1, num_awards)),
        "evidence_coverage_count": int(evidence_coverage),
        "evidence_coverage_rate": float(evidence_coverage / max(1, num_awards)),
        "model_path": str(model_path),
    }

    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "path": str(artifact_path),
        "rows": len(df_out),
        "taxonomy_version": taxonomy.version,
        "model_version": getattr(model, "model_version", None),
        "checks_path": str(checks_path),
    }

    logger.info(
        "Completed cet_award_classifications asset", rows=len(df_out), output=str(artifact_path)
    )

    # Perform statistical analysis with CET analyzer
    if CetClassificationAnalyzer is not None:
        try:
            analyzer = CetClassificationAnalyzer()
            run_context = {
                "run_id": "cet_classification_run",  # Could be enhanced with actual run_id
                "pipeline_name": "cet_classification",
                "stage": "transform",
            }

            classified_df = df_out

            # Prepare module data for analysis
            module_data = {
                "classified_df": classified_df,
                "classification_results": {
                    "classified_records": len(classified_df),
                    "failed_records": 0,  # Assume all records were processed
                    "duration_seconds": 0.0,  # Could be enhanced with actual timing
                    "classification_rate": len(classified_df[classified_df["primary_cet"].notna()])
                    / len(classified_df)
                    if len(classified_df) > 0
                    else 0,
                    "model_accuracy": checks.get("accuracy", 0.0),
                    "model_precision": checks.get("precision", 0.0),
                    "model_recall": checks.get("recall", 0.0),
                    "model_f1_score": checks.get("f1_score", 0.0),
                },
                "taxonomy_data": {
                    "taxonomy_areas": [area.cet_id for area in taxonomy.cet_areas]
                    if hasattr(taxonomy, "cet_areas") and isinstance(taxonomy.cet_areas, list)
                    else [],
                    "total_areas": len(taxonomy.cet_areas) if hasattr(taxonomy, "cet_areas") else 0,
                },
                "run_context": run_context,
            }

            # Generate analysis report
            analysis_report = analyzer.analyze(module_data)

            logger.info(
                "CET classification analysis complete",
                extra={
                    "insights_generated": len(analysis_report.insights)
                    if hasattr(analysis_report, "insights")
                    else 0,
                    "data_hygiene_score": analysis_report.data_hygiene.quality_score_mean
                    if analysis_report.data_hygiene
                    else None,
                    "classification_success_rate": analysis_report.success_rate,
                },
            )

            # Add analysis results to metadata
            metadata.update(
                {
                    "analysis_insights_count": len(analysis_report.insights)
                    if hasattr(analysis_report, "insights")
                    else 0,
                    "analysis_data_hygiene_score": round(
                        analysis_report.data_hygiene.quality_score_mean, 3
                    )
                    if analysis_report.data_hygiene
                    else None,
                    "analysis_category_distribution": analysis_report.module_metrics.get(
                        "category_distribution", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                    "analysis_confidence_distribution": analysis_report.module_metrics.get(
                        "confidence_distribution", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                    "analysis_taxonomy_coverage": analysis_report.module_metrics.get(
                        "taxonomy_coverage", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                }
            )

        except Exception as e:
            logger.warning(f"CET classification analysis failed: {e}")
    else:
        logger.info("CET analyzer not available; skipping statistical analysis")  # type: ignore[unreachable]

    return Output(value=str(artifact_path), metadata=metadata)  # type: ignore[arg-type]


@asset(
    name="enriched_cet_patent_classifications",
    key_prefix=["ml"],
    description=(
        "Batch classify patents with a trained Patent CET classifier, persist results to "
        "`data/processed/cet_patent_classifications.parquet` and emit a companion checks JSON."
    ),
)
def enriched_cet_patent_classifications() -> Output:
    """
    Dagster asset to perform batch CET classification over patent title records.

    Required inputs and dependencies fail the materialization instead of producing a
    placeholder artifact.

    Behavior:
    - Loads a trained PatentCETClassifier from a well-known artifacts path.
    - Loads the taxonomy via TaxonomyLoader for metadata.
    - Reads transformed patent records from `data/processed/transformed_patents.ndjson`
      (NDJSON) or `data/processed/transformed_patents.parquet` if available.
    - Classifies patent titles in batches and persists outputs with NDJSON/parquet fallback.
    - Writes a companion checks JSON summarizing classification coverage.
    """
    logger.info("Starting cet_patent_classifications asset")

    # Local imports to keep module import-safe when optional deps are missing

    # Lazy import keeps repository discovery import-safe, but materialization requires it.
    try:
        from sbir_ml.ml.models.patent_classifier import PatentCETClassifier
    except Exception as exc:
        raise RuntimeError("CET patent classifier dependency is unavailable") from exc

    # Paths and defaults
    patents_ndjson = Path("data/processed/transformed_patents.ndjson")
    patents_parquet = Path("data/processed/transformed_patents.parquet")
    model_path = Path("artifacts/models/patent_classifier_v1.pkl")
    output_path = Path("data/processed/cet_patent_classifications.parquet")
    checks_path = output_path.with_suffix(".checks.json")

    try:
        loader = TaxonomyLoader()
        taxonomy = loader.load_taxonomy()
        classification_config = loader.load_classification_config()
    except Exception as exc:
        raise RuntimeError("Failed to load the CET taxonomy and classification config") from exc

    # Load patent records (prefer parquet, then ndjson).
    patents: list[dict] = []
    try:
        if patents_parquet.exists():
            import pandas as pd

            df_patents = pd.read_parquet(patents_parquet)
            # Expect dataframe with at least patent_id/title/assignee
            for _, row in df_patents.iterrows():
                patents.append(
                    {
                        "patent_id": str(row.get("patent_id") or row.get("id") or ""),
                        "title": str(row.get("title") or ""),
                        "assignee": row.get("assignee") or None,
                    }
                )
        elif patents_ndjson.exists():
            with open(patents_ndjson, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        patents.append(json.loads(line))
        else:
            raise FileNotFoundError(
                f"No transformed patent input found at {patents_parquet} or {patents_ndjson}"
            )
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError("Failed to load patents for CET classification") from exc

    if not patents:
        raise ValueError("Transformed patent input is empty; no patents are available to classify")

    if not model_path.exists():
        raise FileNotFoundError(f"Trained CET patent model not found: {model_path}")

    # Load trained model
    try:
        classifier = PatentCETClassifier.load(model_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to load trained CET patent model: {model_path}") from exc

    if classifier is None:
        raise RuntimeError(f"CET patent model loader returned no model: {model_path}")

    # Build texts for classification and perform batch classification
    titles = []
    patent_ids = []
    assignees: list[Any] = []
    # Prefer PatentFeatureExtractor for normalized title strings if available
    try:
        from sbir_ml.ml.features.patent_features import get_keywords_map
        from sbir_ml.ml.models.patent_classifier import PatentFeatureExtractor

        kw_map = get_keywords_map()
        extractor = PatentFeatureExtractor(keywords_map=kw_map)
        if hasattr(extractor, "transform"):
            feature_dicts = list(extractor.transform(patents))
            if len(feature_dicts) != len(patents):
                raise ValueError(
                    "CET patent feature extractor returned "
                    f"{len(feature_dicts)} results for {len(patents)} source rows"
                )
            for p, fv in zip(patents, feature_dicts, strict=True):
                norm_title = (
                    fv.get("normalized_title")
                    if isinstance(fv, dict)
                    else getattr(fv, "normalized_title", p.get("title"))
                )
                titles.append(str(norm_title or ""))
                patent_ids.append(p.get("patent_id") or "")
                # Avoid double-adding assignee when text already normalized
                assignees.append(None)
        else:
            # Fallback to simple normalization when only DF-based extractor is available
            from sbir_ml.ml.features.patent_features import normalize_title

            for p in patents:
                titles.append(normalize_title(p.get("title")))
                patent_ids.append(p.get("patent_id") or "")
                assignees.append(None)
    except ValueError:
        raise
    except Exception:
        for p in patents:
            titles.append(str(p.get("title") or ""))
            patent_ids.append(p.get("patent_id") or "")
            assignees.append(p.get("assignee") or None)

    batch_size = (
        classification_config.get("batch", {}).get("size", 1000)
        if isinstance(classification_config, dict)
        else 1000
    )

    try:
        classifications_by_patent = list(
            classifier.classify_batch(titles, assignees, batch_size=batch_size)
        )
    except Exception as exc:
        raise RuntimeError("CET patent batch classification failed") from exc

    if len(classifications_by_patent) != len(patents):
        raise ValueError(
            "CET patent classifier returned "
            f"{len(classifications_by_patent)} results for {len(patents)} source rows"
        )

    # Flatten classification results into a DataFrame (one row per patent)
    import pandas as pd

    rows: list[Any] = []
    for pid, cls_list in zip(patent_ids, classifications_by_patent, strict=True):
        if not cls_list:
            rows.append(
                {
                    "patent_id": pid,
                    "primary_cet": None,
                    "primary_score": None,
                    "supporting_cets": [],
                    "classified_at": None,
                    "taxonomy_version": classifier.taxonomy_version
                    if classifier
                    else (taxonomy.version if taxonomy else None),
                }
            )
            continue

        primary = cls_list[0]
        supporting = cls_list[1:4] if len(cls_list) > 1 else []
        rows.append(
            {
                "patent_id": pid,
                "primary_cet": primary.cet_id,
                "primary_score": primary.score,
                "supporting_cets": [{"cet_id": s.cet_id, "score": s.score} for s in supporting],
                "classified_at": getattr(primary, "classified_at", None),
                "taxonomy_version": getattr(
                    primary, "taxonomy_version", classifier.taxonomy_version if classifier else None
                ),
            }
        )

    df_out = pd.DataFrame(rows)

    # Persist classifications (parquet preferred, NDJSON fallback)
    artifact_path = save_dataframe_parquet(df_out, output_path)

    # Build checks: coverage and counts
    num_patents = len(rows)
    num_classified = sum(1 for r in rows if r.get("primary_cet"))
    checks = {
        "ok": True,
        "num_patents": num_patents,
        "num_classified": num_classified,
        "model_path": str(model_path),
    }

    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "path": str(artifact_path),
        "rows": len(df_out),
        "taxonomy_version": taxonomy.version if taxonomy else None,
        "model_version": getattr(classifier, "model_version", None),
        "checks_path": str(checks_path),
    }

    logger.info(
        "Completed cet_patent_classifications asset", rows=len(df_out), output=str(artifact_path)
    )

    return Output(value=str(artifact_path), metadata=metadata)  # type: ignore[arg-type]
