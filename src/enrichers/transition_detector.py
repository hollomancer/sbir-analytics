
import pandas as pd

from src.models.transitions import CompanyTransition, TransitionType


class TransitionDetector:
    def detect(self, df: pd.DataFrame) -> list[CompanyTransition]:
        # Placeholder for transition detection logic
        transitions = []
        for i, row in df.iterrows():
            if "acquired" in row["description"].lower():
                transitions.append(
                    CompanyTransition(
                        company_id=row["company_id"],
                        transition_type=TransitionType.ACQUISITION,
                        date="2024-01-01",
                        confidence=0.9,
                        source="sec",
                    )
                )
        return transitions
