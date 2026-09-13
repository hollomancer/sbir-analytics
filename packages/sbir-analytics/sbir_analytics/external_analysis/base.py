"""Provider protocol and the freeze → submit → import orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sbir_etl.quality.study_manifest import sha256_file

from .bundle import freeze_study_bundle, study_manifest_path
from .edison import DEFAULT_MAX_STEPS, EdisonProvider
from .models import (
    ExternalAnalysisRun,
    MissingInputError,
    ProviderArtifact,
    ProviderFailure,
    ProviderJob,
    RunStatus,
    StudyBundle,
)
from .results import (
    copy_bundle_manifest,
    default_output_dir,
    mark_incomplete,
    write_artifacts,
    write_run_record,
)
from .safety import assert_upload_authorized, evaluate_upload_policy


EPISTEMIC_TIER = "exploratory"

KNOWN_PROVIDERS = ("edison",)


class ExternalAnalysisProvider(Protocol):
    """Execution backend. Study logic does not live here."""

    name: str
    executor: str

    def submit(
        self,
        bundle: StudyBundle,
        *,
        prompt: str,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> ProviderJob: ...

    def status(self, job: ProviderJob) -> str: ...

    def wait(self, job: ProviderJob) -> str: ...

    def fetch_results(self, job: ProviderJob) -> tuple[str, list[ProviderArtifact]]: ...


def get_provider(name: str, **kwargs: object) -> ExternalAnalysisProvider:
    if name == "edison":
        return EdisonProvider(**kwargs)
    raise MissingInputError(
        f"unknown provider {name!r}; known providers: {', '.join(KNOWN_PROVIDERS)}"
    )


def resolve_prompt_path(
    repository_root: Path,
    study_id: str,
    prompt: Path | None,
) -> Path | None:
    if prompt is not None:
        return prompt if prompt.is_absolute() else repository_root / prompt
    default = repository_root / "studies" / study_id / "external_prompt.md"
    if default.is_file():
        return default
    return None


def _prompt_text(bundle: StudyBundle) -> str:
    prompt_path = bundle.directory / "prompt.md"
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8")
    question = bundle.directory / "research_question.md"
    constraints = bundle.directory / "constraints.md"
    parts = [
        "Analyze the supplied frozen study bundle.",
        "Follow constraints.md. Treat conclusions as exploratory and not citable.",
    ]
    if question.is_file():
        parts.append(question.read_text(encoding="utf-8"))
    if constraints.is_file():
        parts.append(constraints.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def run_external_analysis(
    *,
    repository_root: Path,
    provider: ExternalAnalysisProvider | str,
    study_id: str,
    datasets: list[Path],
    allow_external_upload: bool,
    prompt: Path | None = None,
    data_dictionary: Path | None = None,
    constraints: Path | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    output_dir: Path | None = None,
    bundle_only: bool = False,
    git_commit: str | None = None,
    extra_upload_rules: tuple = (),
) -> ExternalAnalysisRun:
    """Freeze a bundle and optionally submit it to a provider.

    Network I/O happens only after ``allow_external_upload`` is true and
    ``bundle_only`` is false. Provider output is always exploratory.
    """

    if not study_manifest_path(repository_root, study_id).is_file():
        raise MissingInputError(f"unknown study {study_id!r}")

    prompt_path = resolve_prompt_path(repository_root, study_id, prompt)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    provider_name = provider if isinstance(provider, str) else provider.name
    destination = output_dir or default_output_dir(
        repository_root,
        study_id=study_id,
        provider=provider_name,
        run_id=run_id,
    )
    bundle_dir = destination / "bundle"
    bundle = freeze_study_bundle(
        repository_root=repository_root,
        study_id=study_id,
        datasets=datasets,
        output_dir=bundle_dir,
        prompt=prompt_path,
        data_dictionary=data_dictionary,
        constraints=constraints,
        git_commit=git_commit,
    )
    copy_bundle_manifest(bundle.manifest_path, destination)
    if prompt_path is not None and (bundle.directory / "prompt.md").is_file():
        (destination / "prompt.md").write_bytes((bundle.directory / "prompt.md").read_bytes())

    manifest_sha = sha256_file(bundle.manifest_path)
    if bundle_only:
        run = ExternalAnalysisRun(
            provider=provider_name,
            executor="none",
            run_id=run_id,
            git_commit=bundle.manifest.git_commit,
            input_manifest_sha256=manifest_sha,
            evidence_status="exploratory",
            citable=False,
            status=RunStatus.BUNDLED,
            output_dir=destination.as_posix(),
            notes=["bundle-only; no provider was contacted"],
        )
        write_run_record(destination, run)
        return run

    assert_upload_authorized(allow_external_upload)
    evaluate_upload_policy(
        bundle,
        repository_root=repository_root,
        extra_rules=extra_upload_rules,
    )
    backend = get_provider(provider) if isinstance(provider, str) else provider
    submitted_at = datetime.now(UTC)
    try:
        job = backend.submit(bundle, prompt=_prompt_text(bundle), max_steps=max_steps)
        status = backend.wait(job)
        if status == "failed":
            raise ProviderFailure(f"{backend.name} task {job.job_id} failed")
        answer, artifacts = backend.fetch_results(job)
    except Exception as exc:
        mark_incomplete(destination, f"{type(exc).__name__}: {exc}")
        failed = ExternalAnalysisRun(
            provider=backend.name if not isinstance(provider, str) else provider_name,
            executor=getattr(backend, "executor", "unknown")
            if not isinstance(provider, str)
            else "analysis",
            run_id=run_id,
            git_commit=bundle.manifest.git_commit,
            input_manifest_sha256=manifest_sha,
            submitted_at=submitted_at,
            completed_at=datetime.now(UTC),
            evidence_status="exploratory",
            citable=False,
            status=RunStatus.INCOMPLETE,
            output_dir=destination.as_posix(),
            notes=[f"incomplete: {exc}"],
        )
        write_run_record(destination, failed)
        raise

    final_dir = default_output_dir(
        repository_root,
        study_id=study_id,
        provider=backend.name,
        run_id=job.job_id,
    )
    if output_dir is None and final_dir != destination:
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        destination.replace(final_dir)
        destination = final_dir
        bundle = StudyBundle(directory=destination / "bundle", manifest=bundle.manifest)

    write_artifacts(destination, artifacts)
    if answer:
        (destination / "answer.md").write_text(answer.rstrip() + "\n", encoding="utf-8")
    run = ExternalAnalysisRun(
        provider=backend.name,
        executor=backend.executor,
        run_id=job.job_id,
        trajectory_id=job.job_id,
        git_commit=bundle.manifest.git_commit,
        input_manifest_sha256=manifest_sha,
        submitted_at=submitted_at,
        completed_at=datetime.now(UTC),
        evidence_status="exploratory",
        citable=False,
        status=RunStatus.SUCCESS,
        output_dir=destination.as_posix(),
    )
    write_run_record(destination, run)
    return run
