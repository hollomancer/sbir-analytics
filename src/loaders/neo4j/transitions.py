"""
Neo4j Transition Loader for Transition Detection Pipeline.

Loads transition detections into Neo4j as Transition nodes and creates
relationships to Awards, Contracts, Patents, and CET areas.
"""

import pandas as pd
from loguru import logger
from neo4j import Driver


class TransitionLoader:
    """
    Load transition detections into Neo4j graph database.

    Handles:
    - Creating Transition nodes with properties (score, confidence, evidence)
    - Creating indexes for performance
    - Batch MERGE operations for idempotency
    - Relationship creation (TRANSITIONED_TO, RESULTED_IN, etc.)
    """

    def __init__(
        self,
        driver: Driver,
        batch_size: int = 1000,
    ):
        """
        Initialize Transition Loader.

        Args:
            driver: Neo4j driver instance
            batch_size: Number of transitions per transaction (default: 1000)
        """
        self.driver = driver
        self.batch_size = batch_size
        self.stats = {
            "transitions_created": 0,
            "transitions_updated": 0,
            "relationships_created": 0,
            "errors": 0,
        }

    def ensure_indexes(self) -> None:
        """Create indexes for Transition nodes and relationships."""
        with self.driver.session() as session:
            try:
                # Index on transition_id (primary lookup)
                session.run(
                    "CREATE INDEX transition_id_index IF NOT EXISTS "
                    "FOR (t:Transition) ON (t.transition_id)"
                )
                logger.info("✓ Created index on Transition.transition_id")

                # Index on confidence for filtering
                session.run(
                    "CREATE INDEX transition_confidence_index IF NOT EXISTS "
                    "FOR (t:Transition) ON (t.confidence)"
                )
                logger.info("✓ Created index on Transition.confidence")

                # Index on likelihood_score for ranking
                session.run(
                    "CREATE INDEX transition_score_index IF NOT EXISTS "
                    "FOR (t:Transition) ON (t.likelihood_score)"
                )
                logger.info("✓ Created index on Transition.likelihood_score")

                # Index on detection_date for time-based queries
                session.run(
                    "CREATE INDEX transition_date_index IF NOT EXISTS "
                    "FOR (t:Transition) ON (t.detection_date)"
                )
                logger.info("✓ Created index on Transition.detection_date")

            except Exception as e:
                logger.error(f"Failed to create indexes: {e}")
                raise

    def load_transition_nodes(
        self,
        transitions_df: pd.DataFrame,
    ) -> int:
        """
        Load transition detections as Transition nodes.

        Args:
            transitions_df: DataFrame with columns:
                - transition_id: Unique identifier
                - award_id: Source award
                - contract_id: Target contract
                - likelihood_score: Composite score (0-1)
                - confidence: Confidence level (high/likely/possible)
                - signals: JSON array of signal contributions
                - evidence: Serialized evidence bundle
                - detected_at: Detection timestamp
                - vendor_match_score: Vendor resolution confidence

        Returns:
            Number of transition nodes created/updated
        """
        if transitions_df.empty:
            logger.warning("No transitions to load")
            return 0

        logger.info(f"Loading {len(transitions_df):,} transition nodes")

        total_processed = 0

        with self.driver.session() as session:
            for i in range(0, len(transitions_df), self.batch_size):
                batch = transitions_df.iloc[i : i + self.batch_size]
                batch_size_actual = len(batch)

                try:
                    result = session.run(
                        """
                        UNWIND $transitions AS t
                        MERGE (trans:Transition {transition_id: t.transition_id})
                        SET trans.award_id = t.award_id,
                            trans.contract_id = t.contract_id,
                            trans.likelihood_score = t.likelihood_score,
                            trans.confidence = t.confidence,
                            trans.signals = t.signals,
                            trans.evidence = t.evidence,
                            trans.detected_at = datetime(t.detected_at),
                            trans.vendor_match_score = t.vendor_match_score,
                            trans.updated_at = datetime()
                        RETURN count(trans) as created
                        """,
                        transitions=[t.to_dict() for _, t in batch.iterrows()],
                    )
                    count = result.single()["created"]
                    self.stats["transitions_created"] += count
                    total_processed += batch_size_actual

                    if (i // self.batch_size + 1) % 5 == 0:
                        logger.info(f"  Processed {total_processed:,} transitions")

                except Exception as e:
                    logger.error(f"Failed to load batch {i//self.batch_size}: {e}")
                    self.stats["errors"] += 1

        logger.info(
            f"✓ Loaded {self.stats['transitions_created']:,} transition nodes "
            f"({total_processed:,} total)"
        )

        return total_processed

    def create_transitioned_to_relationships(
        self,
        transitions_df: pd.DataFrame,
    ) -> int:
        """
        Create TRANSITIONED_TO relationships from Awards to Transitions.

        Args:
            transitions_df: DataFrame with transition_id and award_id

        Returns:
            Number of relationships created
        """
        logger.info("Creating TRANSITIONED_TO relationships (Award → Transition)")

        rel_count = 0

        with self.driver.session() as session:
            for i in range(0, len(transitions_df), self.batch_size):
                batch = transitions_df.iloc[i : i + self.batch_size]

                try:
                    result = session.run(
                        """
                        UNWIND $transitions AS t
                        MATCH (a:Award {award_id: t.award_id})
                        MATCH (trans:Transition {transition_id: t.transition_id})
                        MERGE (a)-[r:TRANSITIONED_TO]->(trans)
                        SET r.score = t.likelihood_score,
                            r.confidence = t.confidence,
                            r.detection_date = datetime(t.detected_at),
                            r.evidence = t.evidence
                        RETURN count(r) as created
                        """,
                        transitions=[
                            {
                                "transition_id": t["transition_id"],
                                "award_id": t["award_id"],
                                "likelihood_score": t["likelihood_score"],
                                "confidence": t["confidence"],
                                "detected_at": t["detected_at"],
                                "evidence": t["evidence"],
                            }
                            for _, t in batch.iterrows()
                        ],
                    )
                    count = result.single()["created"]
                    rel_count += count

                except Exception as e:
                    logger.error(f"Failed to create TRANSITIONED_TO relationships: {e}")
                    self.stats["errors"] += 1

        self.stats["relationships_created"] += rel_count
        logger.info(f"✓ Created {rel_count:,} TRANSITIONED_TO relationships")

        return rel_count

    def create_resulted_in_relationships(
        self,
        transitions_df: pd.DataFrame,
    ) -> int:
        """
        Create RESULTED_IN relationships from Transitions to Contracts.

        Args:
            transitions_df: DataFrame with transition_id and contract_id

        Returns:
            Number of relationships created
        """
        logger.info("Creating RESULTED_IN relationships (Transition → Contract)")

        rel_count = 0

        with self.driver.session() as session:
            for i in range(0, len(transitions_df), self.batch_size):
                batch = transitions_df.iloc[i : i + self.batch_size]

                try:
                    result = session.run(
                        """
                        UNWIND $transitions AS t
                        MATCH (trans:Transition {transition_id: t.transition_id})
                        MATCH (c:Contract {contract_id: t.contract_id})
                        MERGE (trans)-[r:RESULTED_IN]->(c)
                        SET r.confidence = t.confidence,
                            r.creation_date = datetime()
                        RETURN count(r) as created
                        """,
                        transitions=[
                            {
                                "transition_id": t["transition_id"],
                                "contract_id": t["contract_id"],
                                "confidence": t["confidence"],
                            }
                            for _, t in batch.iterrows()
                        ],
                    )
                    count = result.single()["created"]
                    rel_count += count

                except Exception as e:
                    logger.error(f"Failed to create RESULTED_IN relationships: {e}")
                    self.stats["errors"] += 1

        self.stats["relationships_created"] += rel_count
        logger.info(f"✓ Created {rel_count:,} RESULTED_IN relationships")

        return rel_count

    def create_enabled_by_relationships(
        self,
        transitions_df: pd.DataFrame,
        patent_transitions_df: pd.DataFrame | None = None,
    ) -> int:
        """
        Create ENABLED_BY relationships from Transitions to Patents.

        Only creates relationships for patent-backed transitions.

        Args:
            transitions_df: Full transitions DataFrame
            patent_transitions_df: Optional DataFrame with patent_id for patent-backed transitions

        Returns:
            Number of relationships created
        """
        if patent_transitions_df is None or patent_transitions_df.empty:
            logger.info("No patent-backed transitions to link")
            return 0

        logger.info("Creating ENABLED_BY relationships (Transition → Patent)")

        rel_count = 0

        with self.driver.session() as session:
            for i in range(0, len(patent_transitions_df), self.batch_size):
                batch = patent_transitions_df.iloc[i : i + self.batch_size]

                try:
                    result = session.run(
                        """
                        UNWIND $transitions AS t
                        MATCH (trans:Transition {transition_id: t.transition_id})
                        MATCH (p:Patent {patent_id: t.patent_id})
                        MERGE (trans)-[r:ENABLED_BY]->(p)
                        SET r.contribution_score = t.patent_contribution,
                            r.creation_date = datetime()
                        RETURN count(r) as created
                        """,
                        transitions=[
                            {
                                "transition_id": t["transition_id"],
                                "patent_id": t["patent_id"],
                                "patent_contribution": t.get("patent_contribution", 0.0),
                            }
                            for _, t in batch.iterrows()
                        ],
                    )
                    count = result.single()["created"]
                    rel_count += count

                except Exception as e:
                    logger.error(f"Failed to create ENABLED_BY relationships: {e}")
                    self.stats["errors"] += 1

        self.stats["relationships_created"] += rel_count
        logger.info(f"✓ Created {rel_count:,} ENABLED_BY relationships")

        return rel_count

    def create_involves_technology_relationships(
        self,
        transitions_df: pd.DataFrame,
    ) -> int:
        """
        Create INVOLVES_TECHNOLOGY relationships from Transitions to CET areas.

        Args:
            transitions_df: DataFrame with transition_id and cet_area

        Returns:
            Number of relationships created
        """
        # Filter to transitions with CET area
        cet_transitions = transitions_df[transitions_df["cet_area"].notna()]

        if cet_transitions.empty:
            logger.info("No CET-linked transitions to process")
            return 0

        logger.info(
            f"Creating INVOLVES_TECHNOLOGY relationships for {len(cet_transitions):,} transitions"
        )

        rel_count = 0

        with self.driver.session() as session:
            for i in range(0, len(cet_transitions), self.batch_size):
                batch = cet_transitions.iloc[i : i + self.batch_size]

                try:
                    result = session.run(
                        """
                        UNWIND $transitions AS t
                        MATCH (trans:Transition {transition_id: t.transition_id})
                        MATCH (cet:CETArea {cet_id: t.cet_area})
                        MERGE (trans)-[r:INVOLVES_TECHNOLOGY]->(cet)
                        SET r.alignment_score = t.cet_alignment_score,
                            r.creation_date = datetime()
                        RETURN count(r) as created
                        """,
                        transitions=[
                            {
                                "transition_id": t["transition_id"],
                                "cet_area": t["cet_area"],
                                "cet_alignment_score": t.get("cet_alignment_score", 0.0),
                            }
                            for _, t in batch.iterrows()
                        ],
                    )
                    count = result.single()["created"]
                    rel_count += count

                except Exception as e:
                    logger.error(f"Failed to create INVOLVES_TECHNOLOGY relationships: {e}")
                    self.stats["errors"] += 1

        self.stats["relationships_created"] += rel_count
        logger.info(f"✓ Created {rel_count:,} INVOLVES_TECHNOLOGY relationships")

        return rel_count

    def load_transitions(
        self,
        transitions_df: pd.DataFrame,
        patent_transitions_df: pd.DataFrame | None = None,
    ) -> dict[str, int]:
        """
        End-to-end transition loading orchestration.

        Loads transition nodes and creates all relationships.

        Args:
            transitions_df: DataFrame with transition detections
            patent_transitions_df: Optional DataFrame with patent linkages

        Returns:
            Statistics dictionary
        """
        logger.info("Starting transition loading orchestration")

        # Ensure indexes exist
        self.ensure_indexes()

        # Load Transition nodes
        self.load_transition_nodes(transitions_df)

        # Create relationships
        self.create_transitioned_to_relationships(transitions_df)
        self.create_resulted_in_relationships(transitions_df)
        self.create_enabled_by_relationships(transitions_df, patent_transitions_df)
        self.create_involves_technology_relationships(transitions_df)

        logger.info("✓ Transition loading complete")
        logger.info(f"Statistics: {self.stats}")

        return self.stats

    def get_stats(self) -> dict[str, int]:
        """Return loading statistics."""
        return self.stats.copy()


class TransitionProfileLoader:
    """
    Load company-level transition aggregations as TransitionProfile nodes.

    Creates:
    - TransitionProfile nodes (company-level aggregation of transitions)
    - ACHIEVED relationships (Company → TransitionProfile)

    Properties on TransitionProfile:
    - profile_id: Unique identifier
    - company_id: Associated company
    - total_awards: Total awards for company
    - total_transitions: Successful transitions
    - success_rate: success_rate = transitions / awards
    - avg_likelihood_score: Average transition score
    - avg_time_to_transition: Average days to transition (optional)
    - created_date: ISO datetime of profile creation
    """

    def __init__(
        self,
        driver: Driver,
        batch_size: int = 1000,
    ):
        """
        Initialize TransitionProfile Loader.

        Args:
            driver: Neo4j driver instance
            batch_size: Number of profiles per transaction (default: 1000)
        """
        self.driver = driver
        self.batch_size = batch_size
        self.stats = {
            "profiles_created": 0,
            "profiles_updated": 0,
            "achieved_relationships": 0,
            "errors": 0,
        }

    def ensure_profile_indexes(self) -> None:
        """Create indexes for TransitionProfile nodes."""
        with self.driver.session() as session:
            try:
                # Index on profile_id (primary lookup)
                session.run(
                    "CREATE INDEX transition_profile_id_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.profile_id)"
                )
                logger.info("✓ Created index on TransitionProfile.profile_id")

                # Index on company_id for company profile lookups
                session.run(
                    "CREATE INDEX transition_profile_company_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.company_id)"
                )
                logger.info("✓ Created index on TransitionProfile.company_id")

                # Index on success_rate for ranking
                session.run(
                    "CREATE INDEX transition_profile_rate_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.success_rate)"
                )
                logger.info("✓ Created index on TransitionProfile.success_rate")

            except Exception as e:
                logger.error(f"Failed to create profile indexes: {e}")
                raise

    def create_transition_profiles(
        self,
        transitions_df: pd.DataFrame,
        awards_df: pd.DataFrame | None = None,
    ) -> int:
        """
        Create TransitionProfile nodes from transition aggregations.

        Args:
            transitions_df: DataFrame with transition detections (must include award_id, contract_id, score)
            awards_df: Optional DataFrame with award data for company matching

        Returns:
            Number of profiles created/updated
        """
        if transitions_df.empty:
            logger.warning("No transitions for profile creation")
            return 0

        # Compute company-level aggregations
        try:
            with self.driver.session() as session:
                # Query: For each company, get transition stats
                cypher_query = """
                MATCH (c:Company)<-[:AWARDS]-(a:Award)
                OPTIONAL MATCH (a)-[tt:TRANSITIONED_TO]->(t:Transition)
                WITH c.company_id as company_id,
                     c as company_node,
                     count(distinct a) as total_awards,
                     count(distinct case when tt IS NOT NULL then a.award_id end) as total_transitions,
                     avg(case when tt IS NOT NULL then tt.likelihood_score else null end) as avg_likelihood_score
                WHERE total_awards > 0
                WITH company_id, company_node, total_awards, total_transitions, avg_likelihood_score,
                     (toFloat(total_transitions) / toFloat(total_awards)) as success_rate
                MERGE (p:TransitionProfile {profile_id: company_id + "_transition_profile"})
                ON CREATE SET
                    p.company_id = company_id,
                    p.total_awards = total_awards,
                    p.total_transitions = total_transitions,
                    p.success_rate = success_rate,
                    p.avg_likelihood_score = avg_likelihood_score,
                    p.created_date = datetime()
                ON MATCH SET
                    p.total_awards = total_awards,
                    p.total_transitions = total_transitions,
                    p.success_rate = success_rate,
                    p.avg_likelihood_score = avg_likelihood_score,
                    p.updated_date = datetime()
                MERGE (company_node)-[:ACHIEVED]->(p)
                RETURN count(p) as profiles_created
                """

                result = session.run(cypher_query)
                count = result.single()["profiles_created"]
                self.stats["profiles_created"] = count
                self.stats["achieved_relationships"] = count
                logger.info(f"✓ Created/updated {count} transition profiles")
                return count

        except Exception as e:
            logger.error(f"Failed to create transition profiles: {e}")
            self.stats["errors"] += 1
            raise

    def load_transition_profiles(
        self,
        transitions_df: pd.DataFrame,
        awards_df: pd.DataFrame | None = None,
    ) -> dict[str, int]:
        """
        Load company transition profiles into Neo4j.

        Args:
            transitions_df: DataFrame with transition detections
            awards_df: Optional DataFrame with award data

        Returns:
            Statistics dictionary
        """
        logger.info("Starting transition profile loading")

        # Ensure indexes exist
        self.ensure_profile_indexes()

        # Create profiles
        self.create_transition_profiles(transitions_df, awards_df)

        logger.info("✓ Transition profile loading complete")
        logger.info(f"Statistics: {self.stats}")

        return self.stats

    def get_stats(self) -> dict[str, int]:
        """Return loading statistics."""
        return self.stats.copy()
