"""TypeSafe Jev shadow transport for non-authoritative preflight comparison."""

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .engine import assess_readiness
from .models import BlockerCode, PreflightInput, ReadinessResult, ReadinessStatus


EPISTEMIC_TIER = "exploratory"
DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"


class ChoiceAnswer(BaseModel):
    """Validated Jev Choice answer for readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["choice"]
    choice: ReadinessStatus
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[ReadinessStatus, float]

    @model_validator(mode="after")
    def require_every_readiness_option(self) -> "ChoiceAnswer":
        if set(self.probabilities) != set(ReadinessStatus):
            raise ValueError("readiness probabilities must include every configured status")
        if any(value < 0.0 or value > 1.0 for value in self.probabilities.values()):
            raise ValueError("readiness probabilities must be between zero and one")
        return self


class ShadowBlocker(StrEnum):
    """First-blocker choices exposed to the Jev shadow."""

    NONE = "none"
    SOURCE_OUTCOME_IMPOSSIBLE = BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE.value
    SOURCE_OUTCOME_REMEDIABLE = BlockerCode.SOURCE_OUTCOME_REMEDIABLE.value
    INPUT_UNPINNED = BlockerCode.INPUT_UNPINNED.value
    DEFINITION_MISSING = BlockerCode.DEFINITION_MISSING.value
    VALIDATION_INCOMPLETE = BlockerCode.VALIDATION_INCOMPLETE.value
    EVIDENCE_STATUS_INSUFFICIENT = BlockerCode.EVIDENCE_STATUS_INSUFFICIENT.value


class BlockerChoiceAnswer(BaseModel):
    """Validated Jev Choice answer for the first material blocker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["choice"]
    choice: ShadowBlocker
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[ShadowBlocker, float]

    @model_validator(mode="after")
    def require_every_blocker_option(self) -> "BlockerChoiceAnswer":
        if set(self.probabilities) != set(ShadowBlocker):
            raise ValueError("blocker probabilities must include every configured option")
        if any(value < 0.0 or value > 1.0 for value in self.probabilities.values()):
            raise ValueError("blocker probabilities must be between zero and one")
        return self


class NoulAnswer(BaseModel):
    """Validated Jev yes-probability answer for one fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["noul"]
    noul: float = Field(ge=0.0, le=1.0)


class Usage(BaseModel):
    """Token usage returned by TypeSafe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class SystemOneResponse(BaseModel):
    """Top-level response used by the preflight shadow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    answers: dict[str, dict[str, object]]
    usage: Usage


class JevPrediction(BaseModel):
    """Validated subset of Jev output used by the shadow comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    readiness: ChoiceAnswer
    first_blocker: BlockerChoiceAnswer
    atomic_facts: dict[str, NoulAnswer]
    usage: Usage


class ShadowResult(BaseModel):
    """Private, non-authoritative comparison with deterministic policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: str = "exploratory"
    citable: bool = False
    authoritative_source: str = "deterministic_preflight"
    deterministic: ReadinessResult
    jev: JevPrediction
    status_agreement: bool
    first_blocker_agreement: bool
    agreement: bool


class PrivateShadowBundle(BaseModel):
    """On-disk envelope for private, non-citable shadow results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: str = "exploratory"
    citable: bool = False
    private_shadow: bool = True
    results: list[ShadowResult]


class JevClient(Protocol):
    """Transport seam for live and fake Jev calls."""

    def predict(self, preflight: PreflightInput) -> JevPrediction:
        """Return one typed shadow prediction."""


def build_request(preflight: PreflightInput) -> dict[str, object]:
    """Build atomic questions from one bounded preflight input."""

    state = json.dumps(
        {
            "claim": preflight.claim.model_dump(mode="json"),
            "facts": preflight.facts.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in preflight.evidence],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "state": state,
        "model": DEFAULT_MODEL,
        "questions": {
            "readiness": {
                "type": "choice",
                "instructions": (
                    "Classify readiness under the supplied claim contract and facts. "
                    "Do not invent missing evidence."
                ),
                "criteria": {
                    "GO": "No configured blocker is present for the claim as stated.",
                    "NARROW": "The claim is blocked, but an explicitly declared narrower claim is available.",
                    "REDESIGN": "A remediable design, provenance, definition, validation, or evidence-status blocker exists.",
                    "STOP": "A required source outcome is permanently impossible and no narrower claim is declared.",
                },
            },
            "first_blocker": {
                "type": "choice",
                "instructions": (
                    "Select the first material blocker under this precedence: permanently "
                    "impossible source outcome; remediable source outcome; unpinned input; "
                    "missing definition; incomplete required validation; insufficient evidence "
                    "status. Select none only when no blocker applies."
                ),
                "criteria": {
                    "none": "No configured blocker applies.",
                    "source_outcome_impossible": "The required source outcome is permanently unavailable.",
                    "source_outcome_remediable": "The required source outcome is absent but may be recovered.",
                    "input_unpinned": "A required input is not pinned or its hash does not match.",
                    "definition_missing": "A required measurement definition is absent.",
                    "validation_incomplete": "Required validation is incomplete.",
                    "evidence_status_insufficient": "Current evidence status is below the claim target.",
                },
            },
            "source_outcome_available": {
                "type": "noul",
                "instructions": "The required source outcome is marked available or not applicable.",
            },
            "inputs_pinned": {
                "type": "noul",
                "instructions": "The supplied facts state that required inputs are pinned.",
            },
            "definitions_complete": {
                "type": "noul",
                "instructions": "The supplied facts state that required definitions are complete.",
            },
            "validation_complete": {
                "type": "noul",
                "instructions": (
                    "No required validation remains incomplete: validation is complete or the "
                    "claim does not require it."
                ),
            },
        },
    }


def parse_response(payload: Mapping[str, object]) -> JevPrediction:
    """Validate the API response and the expected answer IDs."""

    response = SystemOneResponse.model_validate(payload)
    try:
        readiness_raw = response.answers["readiness"]
        blocker_raw = response.answers["first_blocker"]
        atomic_raw = {
            answer_id: response.answers[answer_id]
            for answer_id in (
                "source_outcome_available",
                "inputs_pinned",
                "definitions_complete",
                "validation_complete",
            )
        }
    except KeyError as exc:
        raise ValueError(f"Jev response is missing answer {exc.args[0]!r}") from exc
    return JevPrediction(
        model=response.model,
        readiness=ChoiceAnswer.model_validate(readiness_raw),
        first_blocker=BlockerChoiceAnswer.model_validate(blocker_raw),
        atomic_facts={
            answer_id: NoulAnswer.model_validate(answer) for answer_id, answer in atomic_raw.items()
        },
        usage=response.usage,
    )


class TypeSafeJevClient:
    """Small synchronous client for the documented System One endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("TYPESAFE_API_KEY", "")
        if not self._api_key:
            raise ValueError("TYPESAFE_API_KEY is required for a live Jev shadow")
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._transport = transport

    def predict(self, preflight: PreflightInput) -> JevPrediction:
        """Call Jev once and validate its typed response."""

        headers = {"Authorization": f"Bearer {self._api_key}"}
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers=headers,
        ) as client:
            response = client.post(self._endpoint, json=build_request(preflight))
            response.raise_for_status()
            return parse_response(response.json())


class FakeJevClient:
    """Hermetic transport returning one fixed prediction."""

    def __init__(self, prediction: JevPrediction) -> None:
        self._prediction = prediction

    def predict(self, preflight: PreflightInput) -> JevPrediction:
        del preflight
        return self._prediction


def run_shadow(preflight: PreflightInput, *, client: JevClient) -> ShadowResult:
    """Compare Jev with deterministic policy without changing that policy."""

    deterministic = assess_readiness(preflight)
    prediction = client.predict(preflight)
    expected_blocker = (
        ShadowBlocker(deterministic.first_blocker.code.value)
        if deterministic.first_blocker
        else ShadowBlocker.NONE
    )
    status_agreement = prediction.readiness.choice is deterministic.status
    blocker_agreement = prediction.first_blocker.choice is expected_blocker
    return ShadowResult(
        deterministic=deterministic,
        jev=prediction,
        status_agreement=status_agreement,
        first_blocker_agreement=blocker_agreement,
        agreement=status_agreement and blocker_agreement,
    )
