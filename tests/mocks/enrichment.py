"""Mock factories for enrichment components."""

from unittest.mock import Mock


class EnrichmentMocks:
    """Factory for enrichment mock objects."""

    @staticmethod
    def sam_gov_client(responses: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock SAM.gov API client."""
        client = Mock()
        client.search = Mock(side_effect=responses or [])
        client.get_entity = Mock(return_value=None)
        client.rate_limit_remaining = 100

        for key, value in kwargs.items():
            setattr(client, key, value)

        return client

    @staticmethod
    def usaspending_client(responses: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock USAspending API client."""
        client = Mock()
        client.search_awards = Mock(side_effect=responses or [])
        client.get_award_details = Mock(return_value=None)

        for key, value in kwargs.items():
            setattr(client, key, value)

        return client

    @staticmethod
    def fuzzy_matcher(match_score: float = 0.85, **kwargs) -> Mock:
        """Create a mock fuzzy matcher."""
        matcher = Mock()
        matcher.match = Mock(return_value={"score": match_score, "matched": True})
        matcher.match_batch = Mock(return_value=[])

        for key, value in kwargs.items():
            setattr(matcher, key, value)

        return matcher
