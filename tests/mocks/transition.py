"""Mock factories for transition detection testing."""

from unittest.mock import Mock


class TransitionMocks:
    """Factory for creating mock transition detection objects."""

    @staticmethod
    def vendor_record(name="Acme Corporation", vendor_id="VENDOR001"):
        """Create a mock vendor record.

        Args:
            name: Vendor name
            vendor_id: Vendor identifier

        Returns:
            Mock vendor record with name and metadata.
        """
        mock_record = Mock()
        mock_record.name = name
        mock_record.metadata = {"vendor_id": vendor_id}
        return mock_record

    @staticmethod
    def vendor_match(record=None, score=1.0):
        """Create a mock vendor match result.

        Args:
            record: Vendor record (creates default if None)
            score: Match confidence score

        Returns:
            Mock with record and score attributes.
        """
        if record is None:
            record = TransitionMocks.vendor_record()
        match = Mock()
        match.record = record
        match.score = score
        return match
