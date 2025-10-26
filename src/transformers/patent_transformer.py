# sbir-etl/src/transformers/patent_transformer.py
"""
PatentAssignmentTransformer

Transform raw USPTO rows (as yielded by USPTOExtractor) into normalized
PatentAssignment models ready for downstream validation and loading.

Responsibilities
- Normalize fields (identifiers, dates, names)
- Join assignment + conveyance + assignee + assignor + documentid semantics if provided on the raw row
- Heuristically parse conveyance text for conveyance type and employer-assign flags
- Link patents to SBIR companies via exact or fuzzy grant number matching (optional index provided)
- Provide batch and streaming helpers

Usage
-----
from src.transformers.patent_transformer import PatentAssignmentTransformer
transformer = PatentAssignmentTransformer(...
for assignment in transformer.transform_chunk(rows):
    # assignment is a PatentAssignment model (or dict with _error)
    ...
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
)

# Try to use rapidfuzz for fuzzy matching; fallback to difflib
try:
    from rapidfuzz import fuzz  # type: ignore

    _RAPIDFUZZ_AVAILABLE = True
except Exception:
    _RAPIDFUZZ_AVAILABLE = False

# Import Pydantic models from uspto_models
try:
    from src.models.uspto_models import (
        PatentAssignment,
        PatentDocument,
        PatentAssignee,
        PatentAssignor,
        PatentConveyance,
        ConveyanceType,
    )
except Exception:
    # If models are not importable, define simple placeholders to avoid hard failure.
    PatentAssignment = None  # type: ignore
    PatentDocument = None  # type: ignore
    PatentAssignee = None  # type: ignore
    PatentAssignor = None  # type: ignore
    PatentConveyance = None  # type: ignore
    ConveyanceType = None  # type: ignore

LOG = logging.getLogger(__name__)

# Keywords heuristics for conveyance type detection
_CONVEYANCE_KEYWORDS = {
    "assignment": ["assign", "assignment", "convey", "transferr", "transfer", "deed"],
    "license": ["license", "licence", "licensing", "licensed"],
    "security_interest": ["security interest", "security-interest", "security"],
    "merger": ["merger", "acquir", "acquisition", "merge", "purchase"],
}


@dataclass
class PatentTransformOptions:
    fuzzy_grant_threshold: float = 0.9
    fuzzy_secondary_threshold: float = 0.8
    normalize_names: bool = True
    normalize_identifiers: bool = True


class PatentAssignmentTransformer:
    """
    Transformer for patent assignment records.

    Constructor:
        PatentAssignmentTransformer(sbire_company_grant_index=None, options=None)

    Parameters:
    - sbir_company_grant_index: Optional mapping from normalized grant_doc_num -> company_id
      to help link transformed patent assignments to SBIR awardee companies. If not provided,
      linking is disabled unless a grant_doc_num appears exact in the mapping.
    - options: PatentTransformOptions instance for thresholds and normalization toggles.
    """

    def __init__(
        self,
        sbir_company_grant_index: Optional[Dict[str, str]] = None,
        options: Optional[PatentTransformOptions] = None,
    ) -> None:
        self.sbir_index = sbir_company_grant_index or {}
        self.options = options or PatentTransformOptions()
        LOG.debug(
            "PatentAssignmentTransformer initialized: sbir_index_keys=%d, options=%s",
            len(self.sbir_index),
            self.options,
        )

    # ------------------------
    # Normalization helpers
    # ------------------------
    @staticmethod
    def _normalize_identifier(val: Optional[Any]) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        # remove non-alphanumeric (retain dashes/underscores)
        s = re.sub(r"[^\w\-]", "", s)
        return s.upper()

    @staticmethod
    def _normalize_name(name: Optional[Any]) -> Optional[str]:
        if name is None:
            return None
        s = " ".join(str(name).strip().split())
        s = s.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ")
        return s.strip()

    @staticmethod
    def _parse_date(value: Optional[Any]) -> Optional[date]:
        # Delegate to models' parsing where possible; keep simple ISO acceptance here
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        try:
            # accept ISO YYYY-MM-DD
            from datetime import datetime

            return datetime.fromisoformat(str(value)).date()
        except Exception:
            # fallback: try common formats
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    from datetime import datetime

                    return datetime.strptime(str(value), fmt).date()
                except Exception:
                    continue
        return None

    # ------------------------
    # Conveyance parsing
    # ------------------------
    def _infer_conveyance_type(
        self, text: Optional[str]
    ) -> Tuple[Optional[ConveyanceType], Optional[bool]]:
        """
        Heuristically infer the conveyance type and whether it's an employer-assignment.
        Returns (ConveyanceType, employer_assign_flag)
        """
        if text is None:
            return ConveyanceType.ASSIGNMENT if ConveyanceType else None, None
        txt = str(text).lower()
        # employer assignment heuristics: phrases like "by employee", "work for hire", "assigned to employer"
        employer_keywords = [
            "work for hire",
            "employee",
            "employer",
            "by employee",
            "assigned to employer",
        ]
        employer_flag = any(k in txt for k in employer_keywords)

        # type detection: check for each group of keywords
        for tname, keywords in _CONVEYANCE_KEYWORDS.items():
            for kw in keywords:
                if kw in txt:
                    try:
                        return ConveyanceType(
                            tname if isinstance(tname, str) else tname
                        ), employer_flag
                    except Exception:
                        # ConveyanceType may be enum of different names; fall back to generic
                        return ConveyanceType.ASSIGNMENT if ConveyanceType else None, employer_flag

        # fallback: assignment default
        return ConveyanceType.ASSIGNMENT if ConveyanceType else None, employer_flag

    # ------------------------
    # Fuzzy matching helpers
    # ------------------------
    def _fuzzy_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        if _RAPIDFUZZ_AVAILABLE:
            try:
                return float(fuzz.token_sort_ratio(s1, s2) / 100.0)
            except Exception:
                pass
        try:
            return float(SequenceMatcher(None, s1, s2).ratio())
        except Exception:
            return 0.0

    def _match_grant_to_sbir(self, grant: Optional[str]) -> Optional[Tuple[str, float]]:
        """
        Try to match a normalized grant_doc_num to the SBIR company index.
        Returns (company_id, score) or None.
        """
        if grant is None:
            return None
        ngrant = self._normalize_identifier(grant)
        if not ngrant:
            return None

        # Exact match first
        if ngrant in self.sbir_index:
            return self.sbir_index[ngrant], 1.0

        # Fuzzy fallback across keys (if index not too large)
        # Avoid fuzz across extremely large index (caller should build efficient index).
        best_score = 0.0
        best_company = None
        # Iterate through keys (may be expensive); future: build inverted index or trie
        for key, company_id in self.sbir_index.items():
            score = self._fuzzy_similarity(ngrant, key)
            if score > best_score:
                best_score = score
                best_company = company_id

        if best_score >= self.options.fuzzy_grant_threshold:
            return best_company, best_score
        if best_score >= self.options.fuzzy_secondary_threshold:
            return best_company, best_score
        return None

    # ------------------------
    # Row -> Model mapping
    # ------------------------
    def transform_row(self, row: Dict[str, Any]) -> Union[PatentAssignment, Dict[str, Any]]:
        """
        Transform a single raw row dict into a PatentAssignment Pydantic model.
        On validation or mapping error, returns a dict with `_error` key describing the issue.
        """

        # Normalize common keys (in case upstream extractor left many variants)
        # We accept the extractor already normalized, but be defensive.
        def _get(*keys, default=None):
            for k in keys:
                if k in row and row[k] is not None:
                    return row[k]
            return default

        try:
            # Build subcomponents
            doc = PatentDocument(
                rf_id=_get("document_rf_id", "rf_id"),
                application_number=self._normalize_identifier(
                    _get("application_number", "app_num")
                ),
                publication_number=self._normalize_identifier(
                    _get("publication_number", "pub_num")
                ),
                grant_number=self._normalize_identifier(
                    _get("grant_doc_num", "grant_number", "patent_number")
                ),
                filing_date=self._parse_date(_get("filing_date")),
                publication_date=self._parse_date(_get("publication_date")),
                grant_date=self._parse_date(_get("grant_date")),
                title=_get("title"),
                abstract=_get("abstract"),
                language=_get("language"),
                raw=row,
            )
        except Exception as e:
            LOG.debug("Document construction failed: %s", e)
            # proceed but keep raw doc dict
            doc = {"_error": f"document_build_failed: {e}"}

        try:
            assignee = PatentAssignee(
                rf_id=_get("assignee_rf_id"),
                name=self._normalize_name(_get("assignee_name")),
                street=_get("assignee_street"),
                city=_get("assignee_city"),
                state=_get("assignee_state"),
                postal_code=_get("assignee_postal"),
                country=_get("assignee_country"),
                uei=self._normalize_identifier(_get("assignee_uei")),
                cage=self._normalize_identifier(_get("assignee_cage")),
                duns=self._normalize_identifier(_get("assignee_duns")),
                metadata={},
            )
        except Exception as e:
            LOG.debug("Assignee construction failed: %s", e)
            assignee = {"_error": f"assignee_build_failed: {e}"}

        try:
            assignor = PatentAssignor(
                rf_id=_get("assignor_rf_id"),
                name=self._normalize_name(_get("assignor_name")),
                execution_date=self._parse_date(_get("execution_date")),
                acknowledgment_date=self._parse_date(_get("acknowledgment_date")),
                metadata={},
            )
        except Exception as e:
            LOG.debug("Assignor construction failed: %s", e)
            assignor = {"_error": f"assignor_build_failed: {e}"}

        # Conveyance inference
        conv_text = _get("conveyance_text", "conveyance")
        conveyance_type, employer_flag = self._infer_conveyance_type(conv_text)
        try:
            conveyance = PatentConveyance(
                rf_id=_get("conveyance_rf_id"),
                conveyance_type=conveyance_type
                or (ConveyanceType.ASSIGNMENT if ConveyanceType else None),
                description=conv_text,
                employer_assign=employer_flag,
                recorded_date=self._parse_date(_get("recorded_date")),
                metadata={},
            )
        except Exception as e:
            LOG.debug("Conveyance build failed: %s", e)
            conveyance = {"_error": f"conveyance_build_failed: {e}"}

        # Build main assignment
        try:
            pa = PatentAssignment(
                rf_id=_get("rf_id", "record_id"),
                file_id=_get("file_id"),
                document=doc if isinstance(doc, PatentDocument) else None,
                conveyance=conveyance if isinstance(conveyance, PatentConveyance) else None,
                assignee=assignee if isinstance(assignee, PatentAssignee) else None,
                assignor=assignor if isinstance(assignor, PatentAssignor) else None,
                execution_date=self._parse_date(_get("execution_date")),
                recorded_date=self._parse_date(_get("recorded_date")),
                normalized_assignee_name=self._normalize_name(_get("assignee_name")),
                normalized_assignor_name=self._normalize_name(_get("assignor_name")),
                metadata={"_raw": row},
            )
        except Exception as e:
            LOG.exception("PatentAssignment model build failed: %s", e)
            row_with_err = dict(row)
            row_with_err["_error"] = f"model_build_failed: {e}"
            return row_with_err

        # Optional: link to SBIR company via grant_doc_num heuristic
        grantnum = None
        if isinstance(pa.document, PatentDocument):
            grantnum = pa.document.grant_number or pa.document.publication_number
        match = self._match_grant_to_sbir(grantnum) if grantnum else None
        if match:
            company_id, score = match
            # attach linking metadata
            pa.metadata["linked_sbir_company"] = {"company_id": company_id, "match_score": score}

        return pa

    # ------------------------
    # Batch helpers
    # ------------------------
    def transform_chunk(
        self, rows: Iterable[Dict[str, Any]]
    ) -> Iterator[Union[PatentAssignment, Dict[str, Any]]]:
        """
        Transform an iterable of raw rows into PatentAssignment models in a streaming fashion.
        """
        for row in rows:
            yield self.transform_row(row)
