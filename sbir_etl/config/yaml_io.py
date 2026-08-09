"""Strict YAML reads for files that must contain a mapping.

Several loaders read a YAML document and immediately treat it as a mapping —
``raw.get("version")``, ``Model(**raw)``. When the file is empty, ``safe_load``
returns ``None`` and those lines fail with ``AttributeError`` or ``TypeError``
naming neither the file nor the real problem. When it holds a list, they fail
just as opaquely.

``read_yaml_mapping`` is the one shared implementation of that check. It is
deliberately narrow: it does not merge, resolve environments, apply defaults, or
validate a schema. Pipeline configuration resolution belongs in
``loader.get_config``; per-file schema validation stays with the caller that
owns the schema.

Callers that intentionally treat an empty file as an empty mapping must opt in
with ``allow_empty=True``. Keeping that policy in this primitive prevents each
caller from growing its own ``safe_load(...) or {}`` implementation while the
default stays fail-closed.
"""

from pathlib import Path
from typing import Any

import yaml

from ..exceptions import ConfigurationError


__all__ = ["read_yaml_mapping"]


def read_yaml_mapping(
    path: Path,
    *,
    description: str = "YAML file",
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Read ``path`` and return its top-level mapping.

    Args:
        path: File to read.
        description: What the file is, used in error messages (e.g. "CET
            taxonomy"). Keep it a noun phrase — it is interpolated directly.
        allow_empty: Return an empty mapping when the document is empty or
            comment-only. Invalid YAML and non-mapping documents still fail.

    Returns:
        The parsed top-level mapping.

    Raises:
        ConfigurationError: The file is missing, unreadable, not valid YAML,
            empty when ``allow_empty`` is false, or does not hold a mapping at
            the top level.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"cannot read {description}: {path} ({exc})") from exc

    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"{description} is not valid YAML: {path} ({exc})") from exc

    if payload is None:
        if allow_empty:
            return {}
        raise ConfigurationError(f"{description} is empty: {path}")
    if not isinstance(payload, dict):
        raise ConfigurationError(
            f"{description} must hold a mapping at the top level, "
            f"found {type(payload).__name__}: {path}"
        )
    return payload
