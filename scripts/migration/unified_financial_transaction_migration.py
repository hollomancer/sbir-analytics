#!/usr/bin/env python3
"""Migration script to consolidate Award and Contract into unified FinancialTransaction nodes.

This script:
1. Migrates Award nodes → FinancialTransaction (transaction_type: "AWARD")
2. Migrates Contract nodes → FinancialTransaction (transaction_type: "CONTRACT")
3. Updates all relationships to point to FinancialTransaction nodes
4. Updates Transition nodes to reference FinancialTransaction

Usage:
    python scripts/migration/unified_financial_transaction_migration.py [--dry-run] [--yes] [--resume] [--batch-size N] [--parallel-workers N]

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not available, skip loading .env file
    pass

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError, SessionExpired
except ImportError:
    GraphDatabase = None  # type: ignore[assignment, misc]
    Neo4jError = Exception  # type: ignore[assignment, misc]
    SessionExpired = Exception  # type: ignore[assignment, misc]

# Default batch size (increased from 500 for better performance)
DEFAULT_BATCH_SIZE = 2000
# Checkpoint file location
CHECKPOINT_DIR = Path("data/state")
CHECKPOINT_FILE = CHECKPOINT_DIR / "migration_checkpoint.json"


class MigrationCheckpoint:
    """Checkpoint state for migration progress."""
    
    def __init__(
        self,
        step: str = "",
        batch_num: int = 0,
        total_batches: int = 0,
        processed_ids: list[str] | None = None,
        total_count: int = 0,
        timestamp: str | None = None,
    ):
        """Initialize checkpoint.
        
        Args:
            step: Current migration step (e.g., "awards", "contracts")
            batch_num: Current batch number
            total_batches: Total number of batches
            processed_ids: List of IDs already processed
            total_count: Total count of items to process
            timestamp: ISO timestamp of checkpoint
        """
        self.step = step
        self.batch_num = batch_num
        self.total_batches = total_batches
        self.processed_ids = processed_ids or []
        self.total_count = total_count
        self.timestamp = timestamp or datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "step": self.step,
            "batch_num": self.batch_num,
            "total_batches": self.total_batches,
            "processed_ids": self.processed_ids,
            "total_count": self.total_count,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationCheckpoint:
        """Create checkpoint from dictionary."""
        return cls(
            step=data.get("step", ""),
            batch_num=data.get("batch_num", 0),
            total_batches=data.get("total_batches", 0),
            processed_ids=data.get("processed_ids", []),
            total_count=data.get("total_count", 0),
            timestamp=data.get("timestamp"),
        )
    
    def save(self, checkpoint_file: Path) -> None:
        """Save checkpoint to file."""
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text(json.dumps(self.to_dict(), indent=2))
        logger.debug("Checkpoint saved: step={}, batch={}/{}", self.step, self.batch_num, self.total_batches)
    
    @classmethod
    def load(cls, checkpoint_file: Path) -> MigrationCheckpoint | None:
        """Load checkpoint from file if it exists."""
        if not checkpoint_file.exists():
            return None
        try:
            data = json.loads(checkpoint_file.read_text())
            checkpoint = cls.from_dict(data)
            logger.info("Loaded checkpoint: step={}, batch={}/{}", checkpoint.step, checkpoint.batch_num, checkpoint.total_batches)
            return checkpoint
        except Exception as e:
            logger.warning("Failed to load checkpoint: {}", e)
            return None
    
    def clear(self, checkpoint_file: Path) -> None:
        """Clear checkpoint file."""
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info("Checkpoint cleared")


def execute_batch_with_retry(
    driver: Any, query: str, params: dict[str, Any], max_retries: int = 3, batch_num: int = 0, total_batches: int = 0
) -> dict[str, Any]:
    """Execute a batch query with retry logic for connection timeouts.
    
    Creates a new session for each attempt to avoid defunct session issues.
    
    Args:
        driver: Neo4j driver (not session - we create new sessions per attempt)
        query: Cypher query to execute
        params: Query parameters
        max_retries: Maximum retry attempts
        batch_num: Batch number for logging
        total_batches: Total batches for logging
        
    Returns:
        Dictionary with 'created' count from query result
        
    Raises:
        Exception: If query fails after all retries
    """
    for attempt in range(max_retries):
        session = None
        try:
            # Create a fresh session for each attempt
            session = driver.session(default_access_mode="WRITE")
            result = session.run(query, **params)
            # Consume the result immediately to catch timeouts here too
            single_result = result.single()
            created_count = single_result["created"] if single_result else 0
            session.close()
            return {"created": created_count}
        except (SessionExpired, TimeoutError) as e:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            error_str = str(e).lower()
            is_timeout = "timeout" in error_str or isinstance(e, (SessionExpired, TimeoutError))
            if attempt < max_retries - 1 and is_timeout:
                wait_seconds = 2 ** attempt
                logger.warning(
                    "Batch {}/{} failed (attempt {}/{}): {}. Retrying in {}s...",
                    batch_num,
                    total_batches,
                    attempt + 1,
                    max_retries,
                    e,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
            else:
                logger.error(
                    "Batch {}/{} failed after {} attempts: {}",
                    batch_num,
                    total_batches,
                    max_retries,
                    e,
                )
                raise
        except Exception as e:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            # For non-timeout errors, retry once but fail faster
            if attempt < max_retries - 1:
                wait_seconds = 1
                logger.warning(
                    "Batch {}/{} failed (attempt {}/{}): {}. Retrying in {}s...",
                    batch_num,
                    total_batches,
                    attempt + 1,
                    max_retries,
                    e,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
            else:
                logger.error(
                    "Batch {}/{} failed after {} attempts: {}",
                    batch_num,
                    total_batches,
                    max_retries,
                    e,
                )
                raise
    # This should never be reached, but mypy needs it for type checking
    return {"created": 0}


def get_env_variable(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable {} is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str) -> Any:
    """Create Neo4j driver connection with extended timeouts for long-running migrations."""
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.info("Connecting to Neo4j at {} as user {}", uri, user)
    
    # Configure driver with extended timeouts for long-running migrations
    pool_size = int(os.getenv("NEO4J_POOL_SIZE", "20"))
    driver_config: dict[str, Any] = {
        "max_connection_lifetime": 3600 * 2,  # 2 hours
        "max_connection_pool_size": pool_size,
        "connection_acquisition_timeout": 300.0,  # 5 minutes to get connection from pool
        "connection_timeout": 60.0,  # 1 minute to establish connection
    }
    
    # Only add parameters that are supported by the driver version
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password), **driver_config)  # type: ignore[misc]
    except TypeError:
        # Fallback if some parameters aren't supported
        logger.warning("Some timeout parameters may not be supported by this driver version")
        driver = GraphDatabase.driver(uri, auth=(user, password))  # type: ignore[misc]
    
    logger.info("Driver configured with extended timeouts for long-running migrations")
    return driver


def collect_award_ids(driver: Any, checkpoint: MigrationCheckpoint | None = None) -> list[str]:
    """Collect all award IDs, excluding already processed ones.
    
    Args:
        driver: Neo4j driver
        checkpoint: Optional checkpoint to exclude already processed IDs
        
    Returns:
        List of award IDs to process
    """
    logger.info("Collecting award IDs...")
    processed_set = set(checkpoint.processed_ids) if checkpoint and checkpoint.step == "awards" else set()
    
    with driver.session(default_access_mode="READ") as session:
        if processed_set:
            # Exclude already processed IDs
            query = """
            MATCH (a:Award)
            WHERE NOT a.award_id IN $processed_ids
            RETURN collect(a.award_id) as award_ids
            """
            result = session.run(query, processed_ids=list(processed_set))
        else:
            query = "MATCH (a:Award) RETURN collect(a.award_id) as award_ids"
            result = session.run(query)
        
        record = result.single()
        award_ids = record["award_ids"] if record else []
        logger.info("Collected {} award IDs to process", len(award_ids))
        return award_ids


def collect_contract_ids(driver: Any, checkpoint: MigrationCheckpoint | None = None) -> list[str]:
    """Collect all contract IDs, excluding already processed ones.
    
    Args:
        driver: Neo4j driver
        checkpoint: Optional checkpoint to exclude already processed IDs
        
    Returns:
        List of contract IDs to process
    """
    logger.info("Collecting contract IDs...")
    processed_set = set(checkpoint.processed_ids) if checkpoint and checkpoint.step == "contracts" else set()
    
    with driver.session(default_access_mode="READ") as session:
        if processed_set:
            # Exclude already processed IDs
            query = """
            MATCH (c:Contract)
            WHERE NOT c.contract_id IN $processed_ids
            RETURN collect(c.contract_id) as contract_ids
            """
            result = session.run(query, processed_ids=list(processed_set))
        else:
            query = "MATCH (c:Contract) RETURN collect(c.contract_id) as contract_ids"
            result = session.run(query)
        
        record = result.single()
        contract_ids = record["contract_ids"] if record else []
        logger.info("Collected {} contract IDs to process", len(contract_ids))
        return contract_ids


def migrate_awards_batch(
    driver: Any,
    award_ids: list[str],
    batch_num: int,
    total_batches: int,
    checkpoint_file: Path,
) -> int:
    """Migrate a batch of awards to FinancialTransaction nodes.
    
    Args:
        driver: Neo4j driver
        award_ids: List of award IDs to process in this batch
        batch_num: Current batch number
        total_batches: Total number of batches
        checkpoint_file: Path to checkpoint file
        
    Returns:
        Number of transactions created
    """
    batch_query = """
    UNWIND $award_ids as award_id
    MATCH (a:Award {award_id: award_id})
    MERGE (ft:FinancialTransaction {transaction_id: 'txn_award_' + a.award_id})
    SET ft.transaction_type = 'AWARD',
        ft.award_id = a.award_id,
        ft.agency = a.agency,
        ft.agency_name = a.agency_name,
        ft.sub_agency = a.branch,
        ft.recipient_name = a.company_name,
        ft.recipient_uei = a.company_uei,
        ft.recipient_duns = a.company_duns,
        ft.amount = a.award_amount,
        ft.transaction_date = a.award_date,
        ft.completion_date = a.completion_date,
        ft.start_date = a.contract_start_date,
        ft.end_date = a.contract_end_date,
        ft.title = a.award_title,
        ft.description = a.abstract,
        ft.phase = a.phase,
        ft.program = a.program,
        ft.principal_investigator = a.principal_investigator,
        ft.research_institution = a.research_institution,
        ft.cet_area = a.cet_area,
        ft.award_year = a.award_year,
        ft.fiscal_year = a.fiscal_year,
        ft.naics_code = a.naics_primary,
        ft.created_at = coalesce(a.created_at, datetime()),
        ft.updated_at = datetime()
    RETURN count(ft) as created
    """
    
    result = execute_batch_with_retry(
        driver,
        batch_query,
        {"award_ids": award_ids},
        batch_num=batch_num,
        total_batches=total_batches,
    )
    return result["created"]


def migrate_contracts_batch(
    driver: Any,
    contract_ids: list[str],
    batch_num: int,
    total_batches: int,
    checkpoint_file: Path,
) -> int:
    """Migrate a batch of contracts to FinancialTransaction nodes.
    
    Args:
        driver: Neo4j driver
        contract_ids: List of contract IDs to process in this batch
        batch_num: Current batch number
        total_batches: Total number of batches
        checkpoint_file: Path to checkpoint file
        
    Returns:
        Number of transactions created
    """
    batch_query = """
    UNWIND $contract_ids as contract_id
    MATCH (c:Contract {contract_id: contract_id})
    MERGE (ft:FinancialTransaction {transaction_id: 'txn_contract_' + c.contract_id})
    SET ft.transaction_type = 'CONTRACT',
        ft.contract_id = c.contract_id,
        ft.agency = c.agency,
        ft.agency_name = c.agency_name,
        ft.sub_agency = c.sub_agency,
        ft.sub_agency_name = c.sub_agency_name,
        ft.recipient_name = c.vendor_name,
        ft.recipient_uei = c.vendor_uei,
        ft.amount = c.obligated_amount,
        ft.base_and_all_options_value = c.base_and_all_options_value,
        ft.transaction_date = c.action_date,
        ft.start_date = c.start_date,
        ft.end_date = c.end_date,
        ft.title = c.description,
        ft.description = c.description,
        ft.competition_type = c.competition_type,
        ft.piid = c.piid,
        ft.fain = c.fain,
        ft.psc_code = c.psc_code,
        ft.place_of_performance = c.place_of_performance,
        ft.naics_code = c.naics_code,
        ft.created_at = coalesce(c.created_at, datetime()),
        ft.updated_at = datetime()
    RETURN count(ft) as created
    """
    
    result = execute_batch_with_retry(
        driver,
        batch_query,
        {"contract_ids": contract_ids},
        batch_num=batch_num,
        total_batches=total_batches,
    )
    return result["created"]


def migrate_awards_to_financial_transactions(
    driver: Any,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    checkpoint_file: Path = CHECKPOINT_FILE,
    resume: bool = False,
    parallel_workers: int = 1,
) -> int:
    """Migrate Award nodes to FinancialTransaction nodes in batches.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
        batch_size: Number of nodes to process per batch
        checkpoint_file: Path to checkpoint file
        resume: If True, resume from checkpoint
        parallel_workers: Number of parallel workers (1 = sequential)

    Returns:
        Number of transactions created
    """
    logger.info("Step 1: Migrating Award nodes to FinancialTransaction nodes")

    if dry_run:
        logger.info("DRY RUN: Would migrate Award nodes in batches of {}", batch_size)
        return 0

    # Load checkpoint if resuming
    checkpoint = None
    if resume:
        checkpoint = MigrationCheckpoint.load(checkpoint_file)
        if checkpoint and checkpoint.step != "awards":
            # Checkpoint is for a different step, start fresh
            checkpoint = None

    # Collect award IDs
    award_ids = collect_award_ids(driver, checkpoint)
    
    if not award_ids:
        logger.info("No Award nodes to migrate")
        if checkpoint:
            checkpoint.clear(checkpoint_file)
        return 0

    # Create batches
    total_batches = (len(award_ids) + batch_size - 1) // batch_size
    batches = [award_ids[i:i + batch_size] for i in range(0, len(award_ids), batch_size)]
    
    # Determine starting batch
    start_batch = checkpoint.batch_num if checkpoint else 0
    processed_ids = set(checkpoint.processed_ids) if checkpoint else set()
    
    logger.info(
        "Processing {} awards in {} batches (batch size: {}){}",
        len(award_ids),
        total_batches,
        batch_size,
        f" (resuming from batch {start_batch + 1})" if start_batch > 0 else "",
    )

    total_created = 0
    
    if parallel_workers > 1 and len(batches) > 1:
        # Parallel processing
        logger.info("Using {} parallel workers", parallel_workers)
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for batch_idx, batch_ids in enumerate(batches[start_batch:], start=start_batch):
                future = executor.submit(
                    migrate_awards_batch,
                    driver,
                    batch_ids,
                    batch_idx + 1,
                    total_batches,
                    checkpoint_file,
                )
                futures[future] = (batch_idx, batch_ids)
            
            for future in as_completed(futures):
                batch_idx, batch_ids = futures[future]
                try:
                    batch_created = future.result()
                    total_created += batch_created
                    processed_ids.update(batch_ids)
                    
                    # Save checkpoint after each batch
                    checkpoint = MigrationCheckpoint(
                        step="awards",
                        batch_num=batch_idx + 1,
                        total_batches=total_batches,
                        processed_ids=list(processed_ids),
                        total_count=len(award_ids),
                    )
                    checkpoint.save(checkpoint_file)
                    
                    logger.info(
                        "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                        batch_idx + 1,
                        total_batches,
                        batch_created,
                        total_created,
                        len(award_ids),
                    )
                except Exception as e:
                    logger.error("Batch {}/{} failed: {}", batch_idx + 1, total_batches, e)
                    raise
    else:
        # Sequential processing
        for batch_idx, batch_ids in enumerate(batches[start_batch:], start=start_batch):
            logger.info(
                "Processing batch {}/{} ({} awards)...",
                batch_idx + 1,
                total_batches,
                len(batch_ids),
            )
            
            batch_created = migrate_awards_batch(
                driver,
                batch_ids,
                batch_idx + 1,
                total_batches,
                checkpoint_file,
            )
            total_created += batch_created
            processed_ids.update(batch_ids)
            
            # Save checkpoint after each batch
            checkpoint = MigrationCheckpoint(
                step="awards",
                batch_num=batch_idx + 1,
                total_batches=total_batches,
                processed_ids=list(processed_ids),
                total_count=len(award_ids),
            )
            checkpoint.save(checkpoint_file)
            
            logger.info(
                "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                batch_idx + 1,
                total_batches,
                batch_created,
                total_created,
                len(award_ids),
            )

    logger.info("✓ Migration complete: Created {} FinancialTransaction nodes from Award nodes", total_created)
    return total_created


def migrate_contracts_to_financial_transactions(
    driver: Any,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    checkpoint_file: Path = CHECKPOINT_FILE,
    resume: bool = False,
    parallel_workers: int = 1,
) -> int:
    """Migrate Contract nodes to FinancialTransaction nodes in batches.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
        batch_size: Number of nodes to process per batch
        checkpoint_file: Path to checkpoint file
        resume: If True, resume from checkpoint
        parallel_workers: Number of parallel workers (1 = sequential)

    Returns:
        Number of transactions created
    """
    logger.info("Step 2: Migrating Contract nodes to FinancialTransaction nodes")

    if dry_run:
        logger.info("DRY RUN: Would migrate Contract nodes in batches of {}", batch_size)
        return 0

    # Load checkpoint if resuming
    checkpoint = None
    if resume:
        checkpoint = MigrationCheckpoint.load(checkpoint_file)
        if checkpoint and checkpoint.step != "contracts":
            # Checkpoint is for a different step, start fresh
            checkpoint = None

    # Collect contract IDs
    contract_ids = collect_contract_ids(driver, checkpoint)
    
    if not contract_ids:
        logger.info("No Contract nodes to migrate")
        if checkpoint:
            checkpoint.clear(checkpoint_file)
        return 0

    # Create batches
    total_batches = (len(contract_ids) + batch_size - 1) // batch_size
    batches = [contract_ids[i:i + batch_size] for i in range(0, len(contract_ids), batch_size)]
    
    # Determine starting batch
    start_batch = checkpoint.batch_num if checkpoint else 0
    processed_ids = set(checkpoint.processed_ids) if checkpoint else set()
    
    logger.info(
        "Processing {} contracts in {} batches (batch size: {}){}",
        len(contract_ids),
        total_batches,
        batch_size,
        f" (resuming from batch {start_batch + 1})" if start_batch > 0 else "",
    )

    total_created = 0
    
    if parallel_workers > 1 and len(batches) > 1:
        # Parallel processing
        logger.info("Using {} parallel workers", parallel_workers)
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for batch_idx, batch_ids in enumerate(batches[start_batch:], start=start_batch):
                future = executor.submit(
                    migrate_contracts_batch,
                    driver,
                    batch_ids,
                    batch_idx + 1,
                    total_batches,
                    checkpoint_file,
                )
                futures[future] = (batch_idx, batch_ids)
            
            for future in as_completed(futures):
                batch_idx, batch_ids = futures[future]
                try:
                    batch_created = future.result()
                    total_created += batch_created
                    processed_ids.update(batch_ids)
                    
                    # Save checkpoint after each batch
                    checkpoint = MigrationCheckpoint(
                        step="contracts",
                        batch_num=batch_idx + 1,
                        total_batches=total_batches,
                        processed_ids=list(processed_ids),
                        total_count=len(contract_ids),
                    )
                    checkpoint.save(checkpoint_file)
                    
                    logger.info(
                        "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                        batch_idx + 1,
                        total_batches,
                        batch_created,
                        total_created,
                        len(contract_ids),
                    )
                except Exception as e:
                    logger.error("Batch {}/{} failed: {}", batch_idx + 1, total_batches, e)
                    raise
    else:
        # Sequential processing
        for batch_idx, batch_ids in enumerate(batches[start_batch:], start=start_batch):
            logger.info(
                "Processing batch {}/{} ({} contracts)...",
                batch_idx + 1,
                total_batches,
                len(batch_ids),
            )
            
            batch_created = migrate_contracts_batch(
                driver,
                batch_ids,
                batch_idx + 1,
                total_batches,
                checkpoint_file,
            )
            total_created += batch_created
            processed_ids.update(batch_ids)
            
            # Save checkpoint after each batch
            checkpoint = MigrationCheckpoint(
                step="contracts",
                batch_num=batch_idx + 1,
                total_batches=total_batches,
                processed_ids=list(processed_ids),
                total_count=len(contract_ids),
            )
            checkpoint.save(checkpoint_file)
            
            logger.info(
                "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                batch_idx + 1,
                total_batches,
                batch_created,
                total_created,
                len(contract_ids),
            )

    logger.info("✓ Migration complete: Created {} FinancialTransaction nodes from Contract nodes", total_created)
    return total_created


def update_award_relationships(driver: Any, dry_run: bool = False) -> int:
    """Update relationships from Award nodes to FinancialTransaction.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 3: Updating Award relationships")

    queries = [
        # Update AWARDED_TO relationships
        """
        MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:AWARDED_TO]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update FUNDED_BY relationships
        """
        MATCH (a:Award)-[r:FUNDED_BY]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:FUNDED_BY]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update PARTICIPATED_IN relationships
        """
        MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (i)-[r2:PARTICIPATED_IN]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update CONDUCTED_AT relationships
        """
        MATCH (a:Award)-[r:CONDUCTED_AT]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:CONDUCTED_AT]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update FOLLOWS relationships (Award -> Award)
        """
        MATCH (a1:Award)-[r:FOLLOWS]->(a2:Award)
        MATCH (ft1:FinancialTransaction {award_id: a1.award_id})
        MATCH (ft2:FinancialTransaction {award_id: a2.award_id})
        MERGE (ft1)-[r2:FOLLOWS]->(ft2)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update TRANSITIONED_TO relationships
        """
        MATCH (a:Award)-[r:TRANSITIONED_TO]->(t:Transition)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:TRANSITIONED_TO]->(t)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update GENERATED_FROM relationships (Patent -> Award)
        """
        MATCH (p:Patent)-[r:GENERATED_FROM]->(a:Award)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (p)-[r2:GENERATED_FROM]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
    ]

    if dry_run:
        for query in queries:
            logger.info("DRY RUN: Would execute:\n{}", query)
        return 0

    total_updated = 0
    with driver.session() as session:
        for query in queries:
            try:
                result = session.run(query)
                single_result = result.single()
                count = single_result["updated"] if single_result else 0
                total_updated += count
            except Exception as e:
                logger.warning("Failed to update relationship: {}", e)

    logger.info("✓ Updated {} Award relationships", total_updated)
    return total_updated


def update_contract_relationships(driver: Any, dry_run: bool = False) -> int:
    """Update relationships from Contract nodes to FinancialTransaction.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 4: Updating Contract relationships")

    queries = [
        # Update AWARDED_CONTRACT relationships
        """
        MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(c:Contract)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (o)-[r2:AWARDED_CONTRACT]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update AWARDED_BY relationships
        """
        MATCH (c:Contract)-[r:AWARDED_BY]->(o:Organization)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (ft)-[r2:AWARDED_BY]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update RESULTED_IN relationships (Transition -> Contract)
        """
        MATCH (t:Transition)-[r:RESULTED_IN]->(c:Contract)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (t)-[r2:RESULTED_IN]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
    ]

    if dry_run:
        for query in queries:
            logger.info("DRY RUN: Would execute:\n{}", query)
        return 0

    total_updated = 0
    with driver.session() as session:
        for query in queries:
            try:
                result = session.run(query)
                single_result = result.single()
                count = single_result["updated"] if single_result else 0
                total_updated += count
            except Exception as e:
                logger.warning("Failed to update relationship: {}", e)

    logger.info("✓ Updated {} Contract relationships", total_updated)
    return total_updated


def update_transition_nodes(driver: Any, dry_run: bool = False) -> int:
    """Update Transition nodes to reference FinancialTransaction instead of Award/Contract.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of transitions updated
    """
    logger.info("Step 5: Updating Transition nodes")

    query = """
    MATCH (t:Transition)
    WHERE t.award_id IS NOT NULL OR t.contract_id IS NOT NULL
    WITH t
    OPTIONAL MATCH (ft_award:FinancialTransaction {award_id: t.award_id})
    OPTIONAL MATCH (ft_contract:FinancialTransaction {contract_id: t.contract_id})
    SET t.award_transaction_id = ft_award.transaction_id,
        t.contract_transaction_id = ft_contract.transaction_id
    RETURN count(t) as updated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n{}", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["updated"] if result.peek() else 0
        logger.info("✓ Updated {} Transition nodes", count)
        return count


def create_financial_transaction_constraints_and_indexes(driver: Any, dry_run: bool = False) -> None:
    """Create constraints and indexes for FinancialTransaction nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
    """
    logger.info("Step 6: Creating FinancialTransaction constraints and indexes")

    statements = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_type)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.agency)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.award_id)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.contract_id)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.recipient_uei)",
    ]

    if dry_run:
        for stmt in statements:
            logger.info("DRY RUN: Would execute:\n{}", stmt)
        return

    with driver.session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
                logger.info("✓ Created constraint/index: {}", stmt.split()[2:5])
            except Neo4jError as e:
                if "already exists" in str(e).lower():
                    logger.info("Constraint/index already exists, skipping")
                else:
                    logger.warning("Failed to create constraint/index: {}", e)


def validate_migration(driver: Any) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 7: Validating migration")

    validation_queries = {
        "remaining_awards": "MATCH (a:Award) RETURN count(a) as count",
        "remaining_contracts": "MATCH (c:Contract) RETURN count(c) as count",
        "financial_transactions_by_type": """
            MATCH (ft:FinancialTransaction)
            RETURN ft.transaction_type, count(*) as count
            ORDER BY count DESC
        """,
        "awarded_to_relationships": "MATCH (ft:FinancialTransaction)-[r:AWARDED_TO]->(o:Organization) RETURN count(r) as count",
        "funded_by_relationships": "MATCH (ft:FinancialTransaction)-[r:FUNDED_BY]->(o:Organization) RETURN count(r) as count",
        "transitioned_to_relationships": "MATCH (ft:FinancialTransaction)-[r:TRANSITIONED_TO]->(t:Transition) RETURN count(r) as count",
        "resulted_in_relationships": "MATCH (t:Transition)-[r:RESULTED_IN]->(ft:FinancialTransaction) RETURN count(r) as count",
    }

    results: dict[str, Any] = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "financial_transactions_by_type":
                    records: list[dict[str, Any]] = [dict(record) for record in result]
                    results[key] = records
                else:
                    record = result.single()
                    results[key] = record["count"] if record else 0
            except Exception as e:
                logger.warning("Validation query failed for {}: {}", key, e)
                results[key] = None

    return results


def print_validation_results(results: dict[str, Any]) -> None:
    """Print validation results in a readable format."""
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION VALIDATION RESULTS")
    logger.info("=" * 60)

    logger.info("\nRemaining legacy nodes:")
    logger.info("  Awards: {}", results.get("remaining_awards", "N/A"))
    logger.info("  Contracts: {}", results.get("remaining_contracts", "N/A"))

    logger.info("\nFinancialTransactions by type:")
    tx_types = results.get("financial_transactions_by_type", [])
    for tx_type in tx_types:
        logger.info("  {}: {}", tx_type.get("ft.transaction_type", "UNKNOWN"), tx_type.get("count", 0))

    logger.info("\nRelationships:")
    logger.info("  AWARDED_TO: {}", results.get("awarded_to_relationships", "N/A"))
    logger.info("  FUNDED_BY: {}", results.get("funded_by_relationships", "N/A"))
    logger.info("  TRANSITIONED_TO: {}", results.get("transitioned_to_relationships", "N/A"))
    logger.info("  RESULTED_IN: {}", results.get("resulted_in_relationships", "N/A"))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Award and Contract to unified FinancialTransaction nodes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migration queries without executing them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation queries after migration.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume migration from last checkpoint.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for processing (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Number of parallel workers for batch processing (default: 1 = sequential).",
    )
    parser.add_argument(
        "--clear-checkpoint",
        action="store_true",
        help="Clear existing checkpoint before starting.",
    )
    return parser.parse_args()


def main() -> int:
    """Main migration function."""
    args = parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Clear checkpoint if requested
    if args.clear_checkpoint and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("Checkpoint cleared")

    # Get Neo4j connection details
    uri = get_env_variable("NEO4J_URI", "bolt://neo4j:7687") or "bolt://neo4j:7687"
    user = get_env_variable("NEO4J_USER", "neo4j") or "neo4j"
    password = get_env_variable("NEO4J_PASSWORD", None)

    if not password and not args.dry_run:
        logger.error("NEO4J_PASSWORD is not set. Set it or run with --dry-run.")
        return 1

    if not args.dry_run and not args.yes:
        logger.warning("This will modify your Neo4j database. Press Ctrl+C to cancel.")
        try:
            input("Press Enter to continue...")
        except KeyboardInterrupt:
            logger.info("Migration cancelled.")
            return 0

    try:
        driver = connect(uri, user, password or "")
    except Exception as e:
        logger.exception("Failed to connect to Neo4j: %s", e)
        return 1

    try:
        # Run migration steps
        migrate_awards_to_financial_transactions(
            driver,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            resume=args.resume,
            parallel_workers=args.parallel_workers,
        )
        migrate_contracts_to_financial_transactions(
            driver,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            resume=args.resume,
            parallel_workers=args.parallel_workers,
        )
        update_award_relationships(driver, dry_run=args.dry_run)
        update_contract_relationships(driver, dry_run=args.dry_run)
        update_transition_nodes(driver, dry_run=args.dry_run)
        create_financial_transaction_constraints_and_indexes(driver, dry_run=args.dry_run)

        # Clear checkpoint on successful completion
        if not args.dry_run and CHECKPOINT_FILE.exists():
            checkpoint = MigrationCheckpoint.load(CHECKPOINT_FILE)
            if checkpoint:
                checkpoint.clear(CHECKPOINT_FILE)

        if not args.dry_run and not args.skip_validation:
            results = validate_migration(driver)
            print_validation_results(results)

        logger.info("✓ Migration completed successfully")
        return 0

    except Exception as e:
        logger.exception("Migration failed: %s", e)
        logger.info("Checkpoint saved. Run with --resume to continue from where it left off.")
        return 1

    finally:
        try:
            driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
