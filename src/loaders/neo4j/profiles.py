"""
Neo4j Transition Profile Loader for Company-Level Transition Analytics.

Loads company transition profiles (aggregated company-level metrics) into Neo4j
as TransitionProfile nodes and creates relationships to Company nodes.
"""

from datetime import datetime

import pandas as pd
from loguru import logger
from neo4j import Driver


class TransitionProfileLoader:
    """
    Load company transition profiles into Neo4j graph database.

    Handles:
    - Creating TransitionProfile nodes with aggregated metrics
    - Calculating success rates, average scores, and timing statistics
    - Creating ACHIEVED relationships from Companies to profiles
    - Batch MERGE operations for idempotency
    """

    def __init__(
        self,
        driver: Driver,
        batch_size: int = 500,
    ):
        """
        Initialize Transition Profile Loader.

        Args:
            driver: Neo4j driver instance
            batch_size: Number of profiles per transaction (default: 500)
        """
        self.driver = driver
        self.batch_size = batch_size
        self.stats = {
            "profiles_created": 0,
            "profiles_updated": 0,
            "relationships_created": 0,
            "errors": 0,
        }

    def calculate_company_profiles(
        self,
        transitions_df: pd.DataFrame,
        awards_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Calculate company-level transition profiles.

        Aggregates transition data by company with metrics:
        - total_awards: Count of awards for this company
        - total_transitions: Count of detected transitions
        - success_rate: Ratio of transitioned awards to total awards
        - avg_likelihood_score: Mean transition score
        - avg_time_to_transition: Mean days from award to transition
        - high_confidence_count: Transitions with confidence='high'
        - likely_confidence_count: Transitions with confidence='likely'
        - last_transition_date: Most recent transition detection
        - created_at: Profile creation timestamp

        Args:
            transitions_df: DataFrame with transition_id, award_id, confidence,
                          likelihood_score, detected_at
            awards_df: Optional DataFrame with company_id and award_date for timing calc

        Returns:
            DataFrame with company profiles (one row per company)
        """
        if transitions_df.empty:
            logger.warning("No transitions to aggregate")
            return pd.DataFrame()

        logger.info("Calculating company transition profiles")

        # Group by company (assuming company_id in award_id or separate column)
        # First, need to link transitions to companies via awards
        profile_data = []

        # Group transitions by award_id first
        transitions_df.groupby("award_id")
        awards_with_transitions = set(transitions_df["award_id"].unique())

        if awards_df is not None and not awards_df.empty:
            # Get all companies from awards
            for company_id in awards_df["company_id"].unique():
                company_awards = awards_df[awards_df["company_id"] == company_id]
                company_award_ids = set(company_awards["award_id"])

                # Find transitions for this company
                company_transitions = transitions_df[
                    transitions_df["award_id"].isin(company_award_ids)
                ]

                total_awards = len(company_awards)
                total_transitions = len(company_transitions)
                success_rate = total_transitions / total_awards if total_awards > 0 else 0.0

                if len(company_transitions) > 0:
                    avg_score = company_transitions["likelihood_score"].mean()
                    high_conf = len(
                        company_transitions[company_transitions["confidence"] == "high"]
                    )
                    likely_conf = len(
                        company_transitions[company_transitions["confidence"] == "likely"]
                    )
                    last_transition = company_transitions["detected_at"].max()

                    # Calculate avg time to transition if award dates available
                    avg_time_to_transition = None
                    if "award_date" in company_awards.columns:
                        times = []
                        for _, trans in company_transitions.iterrows():
                            award = company_awards[
                                company_awards["award_id"] == trans["award_id"]
                            ].iloc[0]
                            time_delta = trans["detected_at"] - award["award_date"]
                            times.append(time_delta.total_seconds() / 86400)  # Convert to days
                        avg_time_to_transition = sum(times) / len(times) if times else None

                else:
                    avg_score = 0.0
                    high_conf = 0
                    likely_conf = 0
                    last_transition = None
                    avg_time_to_transition = None

                profile = {
                    "profile_id": f"profile_{company_id}_{datetime.utcnow().timestamp()}",
                    "company_id": company_id,
                    "total_awards": total_awards,
                    "total_transitions": total_transitions,
                    "success_rate": round(success_rate, 4),
                    "avg_likelihood_score": round(avg_score, 4),
                    "high_confidence_count": high_conf,
                    "likely_confidence_count": likely_conf,
                    "last_transition_date": last_transition.isoformat()
                    if last_transition
                    else None,
                    "avg_time_to_transition_days": (
                        round(avg_time_to_transition, 2) if avg_time_to_transition else None
                    ),
                    "created_at": datetime.utcnow().isoformat(),
                }
                profile_data.append(profile)

        else:
            # Fallback: group by company_id if present, or create profiles per award recipient
            for award_id in awards_with_transitions:
                award_transitions = transitions_df[transitions_df["award_id"] == award_id]

                profile = {
                    "profile_id": f"profile_{award_id}_{datetime.utcnow().timestamp()}",
                    "award_id": award_id,
                    "total_awards": 1,
                    "total_transitions": len(award_transitions),
                    "success_rate": 1.0 if len(award_transitions) > 0 else 0.0,
                    "avg_likelihood_score": round(award_transitions["likelihood_score"].mean(), 4),
                    "high_confidence_count": len(
                        award_transitions[award_transitions["confidence"] == "high"]
                    ),
                    "likely_confidence_count": len(
                        award_transitions[award_transitions["confidence"] == "likely"]
                    ),
                    "last_transition_date": award_transitions["detected_at"].max().isoformat(),
                    "avg_time_to_transition_days": None,
                    "created_at": datetime.utcnow().isoformat(),
                }
                profile_data.append(profile)

        profiles_df = pd.DataFrame(profile_data)
        logger.info(f"✓ Calculated {len(profiles_df):,} company transition profiles")

        return profiles_df

    def ensure_indexes(self) -> None:
        """Create indexes for TransitionProfile nodes."""
        with self.driver.session() as session:
            try:
                # Index on profile_id
                session.run(
                    "CREATE INDEX profile_id_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.profile_id)"
                )
                logger.info("✓ Created index on TransitionProfile.profile_id")

                # Index on company_id for lookups
                session.run(
                    "CREATE INDEX profile_company_id_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.company_id)"
                )
                logger.info("✓ Created index on TransitionProfile.company_id")

                # Index on success_rate for ranking
                session.run(
                    "CREATE INDEX profile_success_rate_index IF NOT EXISTS "
                    "FOR (p:TransitionProfile) ON (p.success_rate)"
                )
                logger.info("✓ Created index on TransitionProfile.success_rate")

            except Exception as e:
                logger.error(f"Failed to create indexes: {e}")
                raise

    def load_profile_nodes(
        self,
        profiles_df: pd.DataFrame,
    ) -> int:
        """
        Load transition profile nodes into Neo4j.

        Args:
            profiles_df: DataFrame with company profile data

        Returns:
            Number of profiles created/updated
        """
        if profiles_df.empty:
            logger.warning("No profiles to load")
            return 0

        logger.info(f"Loading {len(profiles_df):,} transition profile nodes")

        total_processed = 0

        with self.driver.session() as session:
            for i in range(0, len(profiles_df), self.batch_size):
                batch = profiles_df.iloc[i : i + self.batch_size]
                batch_size_actual = len(batch)

                try:
                    result = session.run(
                        """
                        UNWIND $profiles AS p
                        MERGE (prof:TransitionProfile {profile_id: p.profile_id})
                        SET prof.company_id = p.company_id,
                            prof.total_awards = p.total_awards,
                            prof.total_transitions = p.total_transitions,
                            prof.success_rate = p.success_rate,
                            prof.avg_likelihood_score = p.avg_likelihood_score,
                            prof.high_confidence_count = p.high_confidence_count,
                            prof.likely_confidence_count = p.likely_confidence_count,
                            prof.last_transition_date = p.last_transition_date,
                            prof.avg_time_to_transition_days = p.avg_time_to_transition_days,
                            prof.created_at = datetime(p.created_at),
                            prof.updated_at = datetime()
                        RETURN count(prof) as created
                        """,
                        profiles=[t.to_dict() for _, t in batch.iterrows()],
                    )
                    count = result.single()["created"]
                    self.stats["profiles_created"] += count
                    total_processed += batch_size_actual

                    if (i // self.batch_size + 1) % 5 == 0:
                        logger.info(f"  Processed {total_processed:,} profiles")

                except Exception as e:
                    logger.error(f"Failed to load batch {i//self.batch_size}: {e}")
                    self.stats["errors"] += 1

        logger.info(f"✓ Loaded {self.stats['profiles_created']:,} profile nodes")

        return total_processed

    def create_achieved_relationships(
        self,
        profiles_df: pd.DataFrame,
    ) -> int:
        """
        Create ACHIEVED relationships from Companies to TransitionProfiles.

        Args:
            profiles_df: DataFrame with company_id and profile_id

        Returns:
            Number of relationships created
        """
        logger.info("Creating ACHIEVED relationships (Organization → TransitionProfile)")

        rel_count = 0

        with self.driver.session() as session:
            for i in range(0, len(profiles_df), self.batch_size):
                batch = profiles_df.iloc[i : i + self.batch_size]

                try:
                    result = session.run(
                        """
                        UNWIND $profiles AS p
                        MATCH (o:Organization {organization_type: "COMPANY"})
                        WHERE o.company_id = p.company_id OR o.organization_id = p.company_id
                        MATCH (prof:TransitionProfile {profile_id: p.profile_id})
                        MERGE (o)-[r:ACHIEVED]->(prof)
                        SET r.success_rate = p.success_rate,
                            r.created_at = datetime(p.created_at)
                        RETURN count(r) as created
                        """,
                        profiles=[
                            {
                                "company_id": t["company_id"],
                                "profile_id": t["profile_id"],
                                "success_rate": t["success_rate"],
                                "created_at": t["created_at"],
                            }
                            for _, t in batch.iterrows()
                        ],
                    )
                    count = result.single()["created"]
                    rel_count += count

                except Exception as e:
                    logger.error(f"Failed to create ACHIEVED relationships: {e}")
                    self.stats["errors"] += 1

        self.stats["relationships_created"] += rel_count
        logger.info(f"✓ Created {rel_count:,} ACHIEVED relationships")

        return rel_count

    def load_profiles(
        self,
        transitions_df: pd.DataFrame,
        awards_df: pd.DataFrame | None = None,
    ) -> dict[str, int]:
        """
        End-to-end profile loading orchestration.

        Calculates company profiles and loads them into Neo4j.

        Args:
            transitions_df: DataFrame with transition detections
            awards_df: Optional DataFrame with award information for timing calcs

        Returns:
            Statistics dictionary
        """
        logger.info("Starting transition profile loading orchestration")

        # Calculate profiles
        profiles_df = self.calculate_company_profiles(transitions_df, awards_df)

        if profiles_df.empty:
            logger.warning("No profiles to load")
            return self.stats

        # Ensure indexes exist
        self.ensure_indexes()

        # Load profile nodes
        self.load_profile_nodes(profiles_df)

        # Create relationships
        self.create_achieved_relationships(profiles_df)

        logger.info("✓ Transition profile loading complete")
        logger.info(f"Statistics: {self.stats}")

        return self.stats

    def get_stats(self) -> dict[str, int]:
        """Return loading statistics."""
        return self.stats.copy()
