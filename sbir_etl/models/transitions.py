from enum import Enum

from pydantic import BaseModel


class TransitionType(Enum):
    MERGER = "merger"
    ACQUISITION = "acquisition"
    BANKRUPTCY = "bankruptcy"
    SPIN_OFF = "spin_off"
    IPO = "ipo"


class CompanyTransition(BaseModel):
    company_id: int
    transition_type: TransitionType
    date: str
    confidence: float
    source: str
