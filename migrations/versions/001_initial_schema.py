"""Initial Neo4j schema constraints and indexes."""

from migrations.base import Migration
from neo4j import Driver


class InitialSchema(Migration):
    """Create initial constraints and indexes."""

    def __init__(self):
        super().__init__("001", "Initial schema constraints and indexes")

    def upgrade(self, driver: Driver) -> None:
        """Create initial schema."""
        statements = [
            # Legacy constraints (kept for backward compatibility)
            "CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
            "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
            "CREATE CONSTRAINT researcher_id IF NOT EXISTS FOR (r:Researcher) REQUIRE r.researcher_id IS UNIQUE",
            "CREATE CONSTRAINT patent_id IF NOT EXISTS FOR (p:Patent) REQUIRE p.patent_id IS UNIQUE",
            "CREATE CONSTRAINT institution_name IF NOT EXISTS FOR (i:ResearchInstitution) REQUIRE i.name IS UNIQUE",
            # Organization constraints
            "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE",
            # Individual constraints
            "CREATE CONSTRAINT individual_id IF NOT EXISTS FOR (i:Individual) REQUIRE i.individual_id IS UNIQUE",
            # FinancialTransaction constraints
            "CREATE CONSTRAINT financial_transaction_id IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE",
            # Legacy indexes (kept for backward compatibility)
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
            "CREATE INDEX company_normalized_name IF NOT EXISTS FOR (c:Company) ON (c.normalized_name)",
            "CREATE INDEX company_uei IF NOT EXISTS FOR (c:Company) ON (c.uei)",
            "CREATE INDEX company_duns IF NOT EXISTS FOR (c:Company) ON (c.duns)",
            "CREATE INDEX award_date IF NOT EXISTS FOR (a:Award) ON (a.award_date)",
            "CREATE INDEX researcher_name IF NOT EXISTS FOR (r:Researcher) ON (r.name)",
            "CREATE INDEX patent_number IF NOT EXISTS FOR (p:Patent) ON (p.patent_number)",
            "CREATE INDEX institution_name IF NOT EXISTS FOR (i:ResearchInstitution) ON (i.name)",
            # Organization indexes
            "CREATE INDEX organization_name IF NOT EXISTS FOR (o:Organization) ON (o.name)",
            "CREATE INDEX organization_normalized_name IF NOT EXISTS FOR (o:Organization) ON (o.normalized_name)",
            "CREATE INDEX organization_type IF NOT EXISTS FOR (o:Organization) ON (o.organization_type)",
            "CREATE INDEX organization_uei IF NOT EXISTS FOR (o:Organization) ON (o.uei)",
            "CREATE INDEX organization_duns IF NOT EXISTS FOR (o:Organization) ON (o.duns)",
            "CREATE INDEX organization_agency_code IF NOT EXISTS FOR (o:Organization) ON (o.agency_code)",
            # Organization transition metrics indexes
            "CREATE INDEX organization_transition_success_rate IF NOT EXISTS FOR (o:Organization) ON (o.transition_success_rate)",
            "CREATE INDEX organization_transition_total_transitions IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_transitions)",
            "CREATE INDEX organization_transition_total_awards IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_awards)",
            # Individual indexes
            "CREATE INDEX individual_name IF NOT EXISTS FOR (i:Individual) ON (i.name)",
            "CREATE INDEX individual_normalized_name IF NOT EXISTS FOR (i:Individual) ON (i.normalized_name)",
            "CREATE INDEX individual_type IF NOT EXISTS FOR (i:Individual) ON (i.individual_type)",
            "CREATE INDEX individual_email IF NOT EXISTS FOR (i:Individual) ON (i.email)",
            # FinancialTransaction indexes
            "CREATE INDEX financial_transaction_type IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_type)",
            "CREATE INDEX financial_transaction_date IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date)",
            "CREATE INDEX financial_transaction_agency IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.agency)",
            "CREATE INDEX financial_transaction_award_id IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.award_id)",
            "CREATE INDEX financial_transaction_contract_id IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.contract_id)",
            "CREATE INDEX financial_transaction_recipient_uei IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.recipient_uei)",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    # Log but continue (constraint/index may already exist)
                    from loguru import logger

                    logger.debug(f"Schema statement may already exist: {e}")

    def downgrade(self, driver: Driver) -> None:
        """Remove initial schema (for testing)."""
        statements = [
            "DROP CONSTRAINT company_id IF EXISTS",
            "DROP CONSTRAINT award_id IF EXISTS",
            "DROP CONSTRAINT researcher_id IF EXISTS",
            "DROP CONSTRAINT patent_id IF EXISTS",
            "DROP CONSTRAINT institution_name IF EXISTS",
            "DROP CONSTRAINT organization_id IF EXISTS",
            "DROP CONSTRAINT individual_id IF EXISTS",
            "DROP CONSTRAINT financial_transaction_id IF EXISTS",
            "DROP INDEX company_name IF EXISTS",
            "DROP INDEX company_normalized_name IF EXISTS",
            "DROP INDEX company_uei IF EXISTS",
            "DROP INDEX company_duns IF EXISTS",
            "DROP INDEX award_date IF EXISTS",
            "DROP INDEX researcher_name IF EXISTS",
            "DROP INDEX patent_number IF EXISTS",
            "DROP INDEX institution_name IF EXISTS",
            "DROP INDEX organization_name IF EXISTS",
            "DROP INDEX organization_normalized_name IF EXISTS",
            "DROP INDEX organization_type IF EXISTS",
            "DROP INDEX organization_uei IF EXISTS",
            "DROP INDEX organization_duns IF EXISTS",
            "DROP INDEX organization_agency_code IF EXISTS",
            "DROP INDEX organization_transition_success_rate IF EXISTS",
            "DROP INDEX organization_transition_total_transitions IF EXISTS",
            "DROP INDEX organization_transition_total_awards IF EXISTS",
            "DROP INDEX individual_name IF EXISTS",
            "DROP INDEX individual_normalized_name IF EXISTS",
            "DROP INDEX individual_type IF EXISTS",
            "DROP INDEX individual_email IF EXISTS",
            "DROP INDEX financial_transaction_type IF EXISTS",
            "DROP INDEX financial_transaction_date IF EXISTS",
            "DROP INDEX financial_transaction_agency IF EXISTS",
            "DROP INDEX financial_transaction_award_id IF EXISTS",
            "DROP INDEX financial_transaction_contract_id IF EXISTS",
            "DROP INDEX financial_transaction_recipient_uei IF EXISTS",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception:
                    pass

