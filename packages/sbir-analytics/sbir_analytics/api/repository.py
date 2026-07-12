"""Curated, parameterized Neo4j reads used by every API transport."""

from collections.abc import Mapping
from typing import Any, Protocol

from neo4j import Query


class QuerySession(Protocol):
    def run(self, query: Query | str, parameters: Mapping[str, Any] | None = None): ...


class SessionProvider(Protocol):
    def session(self, **kwargs: Any): ...


class AnalyticsRepository:
    """Read-only domain queries; callers cannot supply Cypher."""

    def __init__(self, driver: SessionProvider, database: str = "neo4j", timeout: float = 10.0):
        self.driver = driver
        self.database = database
        self.timeout = timeout

    def _read(self, cypher: str, **parameters: Any) -> list[dict[str, Any]]:
        query = Query(cypher, timeout=self.timeout)
        with self.driver.session(database=self.database, default_access_mode="READ") as session:
            result = session.run(query, parameters)
            return [dict(record["item"]) for record in result]

    def organization(self, identifier: str) -> list[dict[str, Any]]:
        return self._read(
            """
            MATCH (o:Organization)
            WHERE o.organization_id = $identifier OR o.uei = $identifier
               OR o.duns = $identifier OR o.cage = $identifier
            RETURN o { .organization_id, .name, .organization_type, .uei, .duns, .cage,
                       .city, .state, .country, .business_size, .naics_primary,
                       .transition_total_awards, .transition_total_transitions,
                       .transition_success_rate, .updated_at } AS item
            LIMIT 1
            """,
            identifier=identifier,
        )

    def award_history(self, identifier: str, limit: int, offset: int) -> list[dict[str, Any]]:
        return self._read(
            """
            MATCH (a:FinancialTransaction {transaction_type: 'AWARD'})-[:RECIPIENT_OF]->(o)
            WHERE o.organization_id = $identifier OR o.uei = $identifier
               OR o.duns = $identifier OR o.cage = $identifier
            OPTIONAL MATCH (a)-[:TRANSITIONED_TO]->(t:Transition)
            RETURN a { .award_id, .title, .agency, .agency_name, .phase, .program, .amount,
                       .transaction_date, .fiscal_year, .naics_code,
                       transition_count: count(DISTINCT t) } AS item
            ORDER BY a.transaction_date DESC, a.award_id
            SKIP $offset LIMIT $limit
            """,
            identifier=identifier,
            limit=limit,
            offset=offset,
        )

    def transition_metrics(
        self, agency: str | None, fiscal_year: int | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        return self._read(
            """
            MATCH (a:FinancialTransaction {transaction_type: 'AWARD'})
            WHERE ($agency IS NULL OR a.agency = $agency OR a.agency_name = $agency)
              AND ($fiscal_year IS NULL OR a.fiscal_year = $fiscal_year)
            OPTIONAL MATCH (a)-[:TRANSITIONED_TO]->(t:Transition)
            WITH a.agency AS agency, a.agency_name AS agency_name,
                 count(DISTINCT a) AS awards,
                 count(DISTINCT CASE WHEN t IS NOT NULL THEN a END) AS transitioned_awards
            RETURN { agency: agency, agency_name: agency_name, awards: awards,
                     transitioned_awards: transitioned_awards,
                     transition_rate: CASE WHEN awards = 0 THEN 0.0
                       ELSE toFloat(transitioned_awards) / awards END } AS item
            ORDER BY awards DESC, agency
            SKIP $offset LIMIT $limit
            """,
            agency=agency,
            fiscal_year=fiscal_year,
            limit=limit,
            offset=offset,
        )

    def cet_concentration(
        self, agency: str | None, fiscal_year: int | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        return self._read(
            """
            MATCH (a:FinancialTransaction {transaction_type: 'AWARD'})-[:APPLICABLE_TO]->(c:CETArea)
            MATCH (a)-[:RECIPIENT_OF]->(o:Organization)
            WHERE ($agency IS NULL OR a.agency = $agency OR a.agency_name = $agency)
              AND ($fiscal_year IS NULL OR a.fiscal_year = $fiscal_year)
            WITH c, o, count(DISTINCT a) AS firm_awards, sum(coalesce(a.amount, 0.0)) AS firm_amount
            WITH c, collect({organization_id: o.organization_id, awards: firm_awards,
                             amount: firm_amount}) AS firms,
                 sum(firm_awards) AS awards, sum(firm_amount) AS amount
            UNWIND firms AS firm
            WITH c, firms, awards, amount,
                 sum((toFloat(firm.awards) / awards) * (toFloat(firm.awards) / awards)) AS hhi
            RETURN { cet_id: c.cet_id, cet_name: c.name, award_count: awards,
                     award_amount: amount, distinct_awardees: size(firms),
                     award_count_hhi: hhi } AS item
            ORDER BY hhi DESC, awards DESC
            SKIP $offset LIMIT $limit
            """,
            agency=agency,
            fiscal_year=fiscal_year,
            limit=limit,
            offset=offset,
        )

    def freshness(self) -> list[dict[str, Any]]:
        return self._read(
            """
            MATCH (n)
            WHERE n:FinancialTransaction OR n:Organization OR n:Patent OR n:Transition OR n:CETArea
            WITH labels(n)[0] AS entity, count(n) AS records,
                 max(coalesce(n.updated_at, n.detected_at, n.created_at, n.transaction_date)) AS latest
            RETURN { entity: entity, records: records, latest: toString(latest) } AS item
            ORDER BY entity
            """
        )
