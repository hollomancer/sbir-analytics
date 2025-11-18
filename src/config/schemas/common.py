"""Shared helpers for configuration schema modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional


class PercentageMappingMixin:
    """Mixin that normalizes mapping values into bounded percentages."""

    @staticmethod
    def _coerce_percentage_mapping(
        values: Mapping[str, Any],
        *,
        field_name: str,
        lower_bound: float = 0.0,
        upper_bound: float = 1.0,
    ) -> dict[str, float]:
        if not isinstance(values, Mapping):
            raise TypeError(f"Expected a mapping for {field_name}")

        normalized: dict[str, float] = {}
        for key, value in values.items():
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError(f"{key} must be numeric, got {value!r}") from exc

            if not (lower_bound <= number <= upper_bound):
                raise ValueError(
                    f"{key} must be between {lower_bound} and {upper_bound}, got {number}"
                )
            normalized[key] = number

        return normalized


class FloatRangeValidatorMixin:
    """Mixin that constrains float values to a configurable range."""

    @staticmethod
    def _coerce_float(
        value: Any,
        *,
        field_name: str,
        lower_bound: Optional[float] = None,
        upper_bound: Optional[float] = None,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"{field_name} must be numeric, got {value!r}") from exc

        if lower_bound is not None and number < lower_bound:
            raise ValueError(f"{field_name} must be >= {lower_bound}, got {number}")
        if upper_bound is not None and number > upper_bound:
            raise ValueError(f"{field_name} must be <= {upper_bound}, got {number}")

        return number


__all__ = ["FloatRangeValidatorMixin", "PercentageMappingMixin"]
