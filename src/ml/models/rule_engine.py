"""
Rule engine for applying heuristic adjustments to CET classification scores.
"""

from loguru import logger


class RuleEngine:
    """
    A rule engine for applying heuristic adjustments to CET classification scores.
    """

    def __init__(self, config: dict, cet_negative_keywords: dict):
        self.config = config
        self.cet_negative_keywords = cet_negative_keywords

    def apply_all_rules(self, scores: dict[str, float], text: str, agency: str | None, branch: str | None) -> dict[str, float]:
        """
        Apply all heuristic rules to the scores.
        """
        scores = self._apply_negative_keyword_penalty(scores, text)
        scores = self._apply_context_rules(scores, text)
        scores = self._apply_agency_branch_priors(scores, agency, branch)
        return scores

    def _apply_negative_keyword_penalty(self, scores: dict[str, float], text: str) -> dict[str, float]:
        """
        Apply penalty if negative keywords are present in text.
        """
        text_lower = text.lower()
        for cet_id, score in scores.items():
            negative_keywords = self.cet_negative_keywords.get(cet_id, [])
            if not negative_keywords:
                continue

            penalty_multiplier = 1.0
            for neg_kw in negative_keywords:
                if neg_kw.lower() in text_lower:
                    penalty_multiplier *= 0.7  # 30% reduction per negative keyword
                    logger.debug(f"Negative keyword '{neg_kw}' found for {cet_id}, applying penalty")

            scores[cet_id] = max(0.0, min(100.0, score * penalty_multiplier))
        return scores

    def _apply_agency_branch_priors(self, scores: dict[str, float], agency: str | None, branch: str | None) -> dict[str, float]:
        """
        Apply agency/branch contextual score boosts.
        """
        priors_config = self.config.get("priors", {})
        if not priors_config.get("enabled", True):
            return scores

        adjusted_scores = scores.copy()

        if agency:
            agency_priors = priors_config.get("agencies", {}).get(agency, {})
            for cet_id, boost in agency_priors.items():
                if cet_id == "_all_cets":
                    for cet in adjusted_scores:
                        adjusted_scores[cet] = min(100.0, adjusted_scores[cet] + boost)
                    logger.debug(f"Applied agency prior: {agency} -> all CETs +{boost}")
                elif cet_id in adjusted_scores:
                    adjusted_scores[cet_id] = min(100.0, adjusted_scores[cet_id] + boost)
                    logger.debug(f"Applied agency prior: {agency} -> {cet_id} +{boost}")

        if branch:
            branch_priors = priors_config.get("branches", {}).get(branch, {})
            for cet_id, boost in branch_priors.items():
                if cet_id in adjusted_scores:
                    adjusted_scores[cet_id] = min(100.0, adjusted_scores[cet_id] + boost)
                    logger.debug(f"Applied branch prior: {branch} -> {cet_id} +{boost}")

        return adjusted_scores

    def _apply_context_rules(self, scores: dict[str, float], text: str) -> dict[str, float]:
        """
        Apply context-aware rule boosts based on keyword combinations.
        """
        context_rules_config = self.config.get("context_rules", {})
        if not context_rules_config.get("enabled", True):
            return scores

        adjusted_scores = scores.copy()
        text_lower = text.lower()

        for cet_id, rules in context_rules_config.items():
            if cet_id == "enabled" or cet_id not in adjusted_scores or not isinstance(rules, list):
                continue

            for rule in rules:
                if not isinstance(rule, dict):
                    continue

                keywords = rule.get("keywords", [])
                boost = rule.get("boost", 0)

                if not keywords or not boost:
                    continue

                if all(kw.lower() in text_lower for kw in keywords):
                    adjusted_scores[cet_id] = min(100.0, adjusted_scores[cet_id] + boost)
                    logger.debug(
                        f"Applied context rule to {cet_id}: keywords={keywords}, boost=+{boost}"
                    )

        return adjusted_scores
