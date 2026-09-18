"""Edison Analysis adapter. ``edison_client`` is imported only when used."""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import (
    EdisonSupportNotInstalled,
    InvalidProviderResponse,
    MissingApiKey,
    ProviderArtifact,
    ProviderFailure,
    ProviderJob,
    StudyBundle,
)


EPISTEMIC_TIER = "exploratory"

DEFAULT_MAX_STEPS = 30
DEFAULT_LANGUAGE = "PYTHON"
DEFAULT_POLL_INTERVAL_SECONDS = 15.0
_IN_FLIGHT = frozenset({"in progress", "queued"})


def data_entry_uri(storage_id: str) -> str:
    """Return the Edison ``data_storage_uris`` value for one uploaded entry."""

    if not storage_id:
        raise InvalidProviderResponse("Edison storage id is empty")
    return f"data_entry:{storage_id}"


def analysis_environment_config(
    storage_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Provider request fragment: language plus the uploaded bundle URI."""

    return {
        "language": language,
        "data_storage_uris": [data_entry_uri(storage_id)],
    }


def _import_edison() -> tuple[Any, Any, Any, Any]:
    try:
        from edison_client import EdisonClient
        from edison_client.models import RuntimeConfig, TaskRequest
        from edison_client.models.app import JobNames
    except ImportError as exc:
        raise EdisonSupportNotInstalled(
            "Edison support is not installed. "
            "Install the Edison optional dependency before using this provider."
        ) from exc
    return EdisonClient, JobNames, RuntimeConfig, TaskRequest


def _await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


class EdisonProvider:
    """Execution backend for Edison Analysis. Not a study contract."""

    name = "edison"
    executor = "analysis"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._sleep = sleep

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        EdisonClient, _, _, _ = _import_edison()
        key = self._api_key or os.environ.get("EDISON_API_KEY")
        if not key:
            raise MissingApiKey("EDISON_API_KEY is not set")
        self._client = EdisonClient(api_key=key)
        self._api_key = None
        return self._client

    def submit(
        self,
        bundle: StudyBundle,
        *,
        prompt: str,
        max_steps: int = DEFAULT_MAX_STEPS,
        language: str = DEFAULT_LANGUAGE,
    ) -> ProviderJob:
        client = self._require_client()
        _, JobNames, RuntimeConfig, TaskRequest = (
            _import_edison() if self._needs_edison_types(client) else (None, None, None, None)
        )
        upload = _await(
            client.astore_file_content(
                name=f"sbir-analytics {bundle.manifest.study_id} bundle",
                file_path=str(bundle.directory),
                description=(
                    f"Frozen exploratory bundle for study {bundle.manifest.study_id}. Not citable."
                ),
                as_collection=True,
            )
        )
        storage_id = _storage_id(upload)
        environment = analysis_environment_config(storage_id, language=language)
        if TaskRequest is None:
            task: Any = {
                "name": "analysis",
                "query": prompt,
                "runtime_config": {
                    "max_steps": max_steps,
                    "environment_config": environment,
                },
            }
        else:
            task = TaskRequest(
                name=JobNames.ANALYSIS,
                query=prompt,
                runtime_config=RuntimeConfig(
                    max_steps=max_steps,
                    environment_config=environment,
                ),
            )
        job_id = client.create_task(task)
        if not job_id:
            raise InvalidProviderResponse("Edison create_task returned an empty trajectory id")
        return ProviderJob(job_id=str(job_id), storage_id=storage_id)

    def _needs_edison_types(self, client: Any) -> bool:
        return client.__class__.__module__.startswith("edison_client")

    def status(self, job: ProviderJob) -> str:
        client = self._require_client()
        result = client.get_task(job.job_id)
        status = getattr(result, "status", None)
        if not status:
            raise InvalidProviderResponse("Edison get_task returned no status")
        return str(status)

    def wait(self, job: ProviderJob) -> str:
        status = self.status(job)
        while status in _IN_FLIGHT:
            self._sleep(self._poll_interval)
            status = self.status(job)
        return status

    def fetch_results(self, job: ProviderJob) -> tuple[str, list[ProviderArtifact]]:
        client = self._require_client()
        result = client.get_task(job.job_id, verbose=True)
        status = getattr(result, "status", None)
        if status == "failed":
            raise ProviderFailure(f"Edison task {job.job_id} failed")
        frame = getattr(result, "environment_frame", None)
        if not isinstance(frame, dict):
            raise InvalidProviderResponse("Edison verbose result has no environment_frame")
        answer = _nested(frame, "state", "state", "answer") or ""
        output_data = _nested(frame, "state", "info", "output_data") or []
        if not isinstance(output_data, list):
            raise InvalidProviderResponse("Edison output_data is not a list")
        artifacts: list[ProviderArtifact] = []
        for item in output_data:
            if not isinstance(item, dict):
                raise InvalidProviderResponse("Edison output_data item is not an object")
            entry_id = item.get("entry_id") or item.get("id")
            if not entry_id:
                raise InvalidProviderResponse("Edison output_data item has no entry_id")
            name = str(item.get("name") or item.get("filename") or entry_id)
            fetched = _await(client.afetch_data_from_storage(data_storage_id=entry_id))
            artifacts.append(ProviderArtifact(name=name, content=_fetch_bytes(fetched, name)))
        return str(answer), artifacts


def _storage_id(upload: Any) -> str:
    data_storage = getattr(upload, "data_storage", None)
    storage_id = getattr(data_storage, "id", None) if data_storage is not None else None
    if storage_id is None and isinstance(upload, dict):
        storage_id = (upload.get("data_storage") or {}).get("id")
    if not storage_id:
        raise InvalidProviderResponse("Edison upload response has no data_storage.id")
    return str(storage_id)


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _fetch_bytes(response: Any, name: str) -> bytes:
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)
    if isinstance(response, str):
        return response.encode("utf-8")
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    path = getattr(response, "path", None) or getattr(response, "file_path", None)
    if path:
        return Path(path).read_bytes()
    raise InvalidProviderResponse(f"cannot read Edison fetch response for {name!r}")
