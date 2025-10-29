"""
Transition Pathway Queries for Neo4j Graph Analysis.

Implements sophisticated queries to traverse transition detection pathways:
- Award → Transition → Contract (basic pathway)
- Award → Patent → Transition → Contract (patent-backed)
- Award → CET → Transition (technology-focused)
- Company → TransitionProfile (company success)
- Aggregations by CET area and confidence levels
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from neo4j import Driver, Session
from loguru import logger


@dataclass
class PathwayResult:
    """Result of a pathway query."""

    pathway_name: str
    records_count: int
    records: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class TransitionPathwayQueries:
    """Execute transition pathway queries against Neo4j database."""

    def __init__(self, driver: Driver):
        """
        Initialize pathway query executor.

        Args:
            driver: Neo4j driver instance
        """
        self.driver = driver

    def award_to_transition_to_contract(
        self,
        award_id: Optional[str] = None,
        min_score: float = 0.0,
        confidence_levels: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> PathwayResult:
        """
        Query: Award → Transition → Contract

        Finds all contracts reachable from an award through transitions.

        Args:
            award_id: Specific award to query (None for all)
            min_score: Minimum transition score (0-1)
            confidence_levels: Filter by confidence (high/likely/possible)
            limit: Max results to return

        Returns:
            PathwayResult with matching records
        """
        confidence_filter = ""
        if confidence_levels:
            confidence_str = "', '".join(confidence_levels)
            confidence_filter = f"AND r.confidence IN ['{confidence_str}']"

        award_filter = "" if not award_id else f"WHERE a.award_id = '{award_id}'"

        query = f"""
        MATCH (a:Award) {award_filter}
        MATCH (a)-[r:TRANSITIONED_TO]->(trans:Transition)-[r2:RESULTED_IN]->(c:Contract)
        WHERE r.score >= {min_score} {confidence_filter}
        RETURN {{
            award_id: a.award_id,
            award_name: a.award_title,
            transition_id: trans.transition_id,
            transition_score: r.score,
            transition_confidence: r.confidence,
            contract_id: c.contract_id,
            contract_name: c.description,
            detection_date: r.detection_date
        }} as pathway
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["pathway"] for record in result]

        return PathwayResult(
            pathway_name="Award → Transition → Contract",
            records_count=len(records),
            records=records,
            metadata={"award_id": award_id, "min_score": min_score},
        )

    def award_to_patent_to_transition_to_contract(
        self,
        award_id: Optional[str] = None,
        min_patent_contribution: float = 0.0,
        limit: int = 1000,
    ) -> PathwayResult:
        """
        Query: Award → Patent → Transition → Contract

        Finds contract transitions backed by patents from an award.

        Args:
            award_id: Specific award to query (None for all)
            min_patent_contribution: Minimum patent contribution score
            limit: Max results to return

        Returns:
            PathwayResult with patent-backed transitions
        """
        award_filter = "" if not award_id else f"WHERE a.award_id = '{award_id}'"

        query = f"""
        MATCH (a:Award) {award_filter}
        MATCH (a)-[:FILED]->(p:Patent)
        MATCH (trans:Transition)-[r:ENABLED_BY]->(p)
        WHERE r.contribution_score >= {min_patent_contribution}
        MATCH (trans)-[r2:RESULTED_IN]->(c:Contract)
        RETURN {{
            award_id: a.award_id,
            award_name: a.award_title,
            patent_id: p.patent_id,
            patent_title: p.title,
            patent_contribution: r.contribution_score,
            transition_id: trans.transition_id,
            transition_score: trans.likelihood_score,
            contract_id: c.contract_id,
            contract_name: c.description
        }} as pathway
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["pathway"] for record in result]

        return PathwayResult(
            pathway_name="Award → Patent → Transition → Contract",
            records_count=len(records),
            records=records,
            metadata={"award_id": award_id, "min_patent_contribution": min_patent_contribution},
        )

    def award_to_cet_to_transition(
        self,
        cet_area: Optional[str] = None,
        min_score: float = 0.0,
        limit: int = 1000,
    ) -> PathwayResult:
        """
        Query: Award → CET → Transition (technology-specific)

        Finds transitions in specific technology areas.

        Args:
            cet_area: Specific CET area to filter (None for all)
            min_score: Minimum transition score
            limit: Max results to return

        Returns:
            PathwayResult with CET-focused transitions
        """
        cet_filter = "" if not cet_area else f"WHERE cet.cet_id = '{cet_area}'"

        query = f"""
        MATCH (a:Award)
        MATCH (trans:Transition)-[r1:TRANSITIONED_TO]-(a)
        MATCH (trans)-[r2:INVOLVES_TECHNOLOGY]->(cet:CETArea) {cet_filter}
        WHERE trans.likelihood_score >= {min_score}
        RETURN {{
            award_id: a.award_id,
            award_title: a.award_title,
            transition_id: trans.transition_id,
            transition_score: trans.likelihood_score,
            cet_area: cet.cet_id,
            cet_name: cet.name,
            cet_alignment: r2.alignment_score,
            confidence: trans.confidence
        }} as pathway
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["pathway"] for record in result]

        return PathwayResult(
            pathway_name="Award → CET → Transition",
            records_count=len(records),
            records=records,
            metadata={"cet_area": cet_area, "min_score": min_score},
        )

    def company_to_transition_profile(
        self,
        company_id: Optional[str] = None,
        min_success_rate: float = 0.0,
        limit: int = 100,
    ) -> PathwayResult:
        """
        Query: Company → TransitionProfile (company success)

        Retrieves company transition success profiles.

        Args:
            company_id: Specific company to query (None for top performers)
            min_success_rate: Minimum success rate filter (0-1)
            limit: Max results to return

        Returns:
            PathwayResult with company transition profiles
        """
        company_filter = "" if not company_id else f"WHERE c.company_id = '{company_id}'"

        query = f"""
        MATCH (c:Company) {company_filter}
        MATCH (c)-[r:ACHIEVED]->(prof:TransitionProfile)
        WHERE prof.success_rate >= {min_success_rate}
        RETURN {{
            company_id: c.company_id,
            company_name: c.name,
            profile_id: prof.profile_id,
            total_awards: prof.total_awards,
            total_transitions: prof.total_transitions,
            success_rate: prof.success_rate,
            avg_score: prof.avg_likelihood_score,
            high_confidence: prof.high_confidence_count,
            likely_confidence: prof.likely_confidence_count,
            last_transition: prof.last_transition_date,
            avg_time_to_transition_days: prof.avg_time_to_transition_days
        }} as pathway
        ORDER BY prof.success_rate DESC
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["pathway"] for record in result]

        return PathwayResult(
            pathway_name="Company → TransitionProfile",
            records_count=len(records),
            records=records,
            metadata={"company_id": company_id, "min_success_rate": min_success_rate},
        )

    def transition_rates_by_cet_area(self, limit: int = 50) -> PathwayResult:
        """
        Query: Transition rate by CET area

        Aggregates transition statistics across technology areas.

        Returns:
            PathwayResult with CET area transition rates
        """
        query = f"""
        MATCH (cet:CETArea)<-[r:INVOLVES_TECHNOLOGY]-(trans:Transition)
        WITH cet,
             COUNT(DISTINCT trans) as transition_count,
             AVG(trans.likelihood_score) as avg_score,
             COUNT(CASE WHEN trans.confidence = 'high' THEN 1 END) as high_conf_count
        MATCH (cet)<-[:APPLICABLE_TO]-(a:Award)
        WITH cet,
             transition_count,
             avg_score,
             high_conf_count,
             COUNT(DISTINCT a) as total_awards
        RETURN {{
            cet_area: cet.cet_id,
            cet_name: cet.name,
            total_awards: total_awards,
            transitions_detected: transition_count,
            transition_rate: ROUND(CAST(transition_count AS FLOAT) / total_awards, 4),
            avg_transition_score: ROUND(avg_score, 4),
            high_confidence_count: high_conf_count
        }} as result
        ORDER BY result.transition_rate DESC
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["result"] for record in result]

        return PathwayResult(
            pathway_name="Transition Rates by CET Area",
            records_count=len(records),
            records=records,
            metadata={"aggregation": "by_cet_area"},
        )

    def patent_backed_transition_rates_by_cet_area(self, limit: int = 50) -> PathwayResult:
        """
        Query: Patent-backed transition rate by CET area

        Identifies technology areas where patent-backed transitions are most common.

        Returns:
            PathwayResult with patent-backed transition rates per CET area
        """
        query = f"""
        MATCH (cet:CETArea)<-[r1:INVOLVES_TECHNOLOGY]-(trans:Transition)
        MATCH (trans)-[:ENABLED_BY]->(p:Patent)
        WITH cet,
             COUNT(DISTINCT trans) as patent_backed_transitions,
             AVG(trans.likelihood_score) as avg_score
        MATCH (cet)<-[:APPLICABLE_TO]-(a:Award)
        WITH cet,
             patent_backed_transitions,
             avg_score,
             COUNT(DISTINCT a) as total_awards
        RETURN {{
            cet_area: cet.cet_id,
            cet_name: cet.name,
            total_awards: total_awards,
            patent_backed_transitions: patent_backed_transitions,
            patent_backed_rate: ROUND(CAST(patent_backed_transitions AS FLOAT) / total_awards, 4),
            avg_transition_score: ROUND(avg_score, 4)
        }} as result
        ORDER BY result.patent_backed_rate DESC
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["result"] for record in result]

        return PathwayResult(
            pathway_name="Patent-Backed Transition Rates by CET Area",
            records_count=len(records),
            records=records,
            metadata={"aggregation": "patent_backed_by_cet_area"},
        )

    def confidence_distribution_analysis(self, limit: int = 100) -> PathwayResult:
        """
        Query: Transition confidence distribution analysis

        Analyzes the distribution of transition confidence levels.

        Returns:
            PathwayResult with confidence statistics
        """
        query = f"""
        MATCH (trans:Transition)
        WITH trans.confidence as confidence,
             COUNT(DISTINCT trans) as count,
             AVG(trans.likelihood_score) as avg_score,
             MIN(trans.likelihood_score) as min_score,
             MAX(trans.likelihood_score) as max_score
        RETURN {{
            confidence: confidence,
            count: count,
            avg_score: ROUND(avg_score, 4),
            min_score: ROUND(min_score, 4),
            max_score: ROUND(max_score, 4)
        }} as result
        ORDER BY count DESC
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["result"] for record in result]

        return PathwayResult(
            pathway_name="Transition Confidence Distribution",
            records_count=len(records),
            records=records,
            metadata={"aggregation": "confidence_levels"},
        )

    def top_companies_by_success_rate(self, limit: int = 20) -> PathwayResult:
        """
        Query: Top performing companies by transition success rate

        Identifies companies with highest transition success rates.

        Returns:
            PathwayResult with top companies
        """
        query = f"""
        MATCH (c:Company)-[:ACHIEVED]->(prof:TransitionProfile)
        WHERE prof.total_awards > 0
        RETURN {{
            company_id: c.company_id,
            company_name: c.name,
            total_awards: prof.total_awards,
            total_transitions: prof.total_transitions,
            success_rate: prof.success_rate,
            avg_score: ROUND(prof.avg_likelihood_score, 4),
            high_confidence: prof.high_confidence_count
        }} as result
        ORDER BY result.success_rate DESC, result.total_awards DESC
        LIMIT {limit}
        """

        with self.driver.session() as session:
            result = session.run(query)
            records = [record["result"] for record in result]

        return PathwayResult(
            pathway_name="Top Companies by Success Rate",
            records_count=len(records),
            records=records,
            metadata={"ranking": "success_rate"},
        )
