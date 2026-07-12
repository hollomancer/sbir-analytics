"""Transport-neutral analytics application service."""

import os
from collections.abc import Callable

from .models import AnalyticsResponse, Page, Provenance
from .repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    @staticmethod
    def _provenance(*limitations: str) -> Provenance:
        return Provenance(
            pipeline_run_id=os.getenv("SBIR_ANALYTICS_PIPELINE_RUN_ID"),
            limitations=list(limitations),
        )

    def _page(
        self, query: Callable[..., list[dict]], limit: int, offset: int, **filters
    ) -> AnalyticsResponse:
        data = query(limit=limit, offset=offset, **filters)
        return AnalyticsResponse(
            data=data,
            provenance=self._provenance(),
            page=Page(limit=limit, offset=offset, returned=len(data)),
        )

    def organization(self, identifier: str) -> AnalyticsResponse:
        return AnalyticsResponse(data=self.repository.organization(identifier), provenance=self._provenance())

    def award_history(self, identifier: str, limit: int, offset: int) -> AnalyticsResponse:
        return self._page(self.repository.award_history, limit, offset, identifier=identifier)

    def transition_metrics(
        self, agency: str | None, fiscal_year: int | None, limit: int, offset: int
    ) -> AnalyticsResponse:
        response = self._page(
            self.repository.transition_metrics,
            limit,
            offset,
            agency=agency,
            fiscal_year=fiscal_year,
        )
        response.provenance.limitations.append(
            "Phase III and transition detection are conservative and may undercount transitions."
        )
        return response

    def cet_concentration(
        self, agency: str | None, fiscal_year: int | None, limit: int, offset: int
    ) -> AnalyticsResponse:
        return self._page(
            self.repository.cet_concentration,
            limit,
            offset,
            agency=agency,
            fiscal_year=fiscal_year,
        )

    def freshness(self) -> AnalyticsResponse:
        return AnalyticsResponse(data=self.repository.freshness(), provenance=self._provenance())
