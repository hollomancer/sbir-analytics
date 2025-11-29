"""Mock factories for R/rpy2 adapter testing."""

from unittest.mock import MagicMock


class RMocks:
    """Factory for creating mock R objects and packages."""

    @staticmethod
    def stateio_package():
        """Create a mock StateIO R package.

        Returns:
            MagicMock configured as StateIO package.
        """
        return MagicMock()

    @staticmethod
    def importr_side_effect(stateio_mock=None):
        """Create side_effect function for importr mock.

        Args:
            stateio_mock: Optional pre-configured StateIO mock

        Returns:
            Function that returns stateio_mock for 'stateior', MagicMock for others.
        """
        if stateio_mock is None:
            stateio_mock = MagicMock()
        return lambda pkg: stateio_mock if pkg == "stateior" else MagicMock()

    @staticmethod
    def r_dataframe():
        """Create a mock R DataFrame object.

        Returns:
            MagicMock configured as R DataFrame.
        """
        return MagicMock()

    @staticmethod
    def r_result():
        """Create a mock R function result.

        Returns:
            MagicMock configured as R result object.
        """
        return MagicMock()
