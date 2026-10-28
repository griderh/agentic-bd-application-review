"""Per-run identity, state machine, and isolated workspace; not answer validation.

Every application tool reads and writes through a run store. The store enforces step
order, immutable inputs/artifacts, budgets, and explicit outcomes so a model that calls
tools out of order cannot skip a stage or publish an unchecked packet.
"""

import fcntl
import hashlib
import os
import re
import stat
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol, Self
from uuid import uuid4

from pydantic import AwareDatetime, Field, StringConstraints, ValidationError, model_validator

from bd_packet_builder.contracts import Contract, Identifier, Sha256

RunStatus = Literal[
    "created",
    "form_interpreted",
    "evidence_collected",
    "answers_validated",
    "packet_assembled",
    "published",
    "failed",
    "cancelled",
]
RunOutcome = Literal["complete", "incomplete"]

_NEXT: dict[str, str] = {
    "created": "form_interpreted",
    "form_interpreted": "evidence_collected",
    "evidence_collected": "answers_validated",
    "answers_validated": "packet_assembled",
    "packet_assembled": "published",
}
_TERMINAL = frozenset({"published", "failed", "cancelled"})
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*$")
_MAX_ARTIFACT_NAME = 128
_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_DEFAULT_MAX_BLANK_BYTES = 64 * 1024 * 1024

Message = Annotated[str, StringConstraints(min_length=1, max_length=2_000, pattern=r"\S")]
Label = Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")]
Version = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^\S+$")]


class RunStoreError(ValueError):
    """Safe run-store error without document contents or absolute paths."""


class RunInputError(RunStoreError):
    """A run input, evidence reference, or artifact name is not acceptable."""


class RunTransitionError(RunStoreError):
    """A requested step is out of order, stale, terminal, or inconsistent."""


class RunConflictError(RunStoreError):
    """A retry or later step would change an already recorded result."""


class RunLimitError(RunStoreError):
    """A configured run budget was exhausted; the run has been marked failed."""


class RunRequest(Contract):
    """Validated intake values. The blank name is a display label, never a path."""

    evidence_set_id: Identifier
    requester_id: Identifier
    blank_name: Label
    as_of: date | None = None


class EvidenceItem(Contract):
    path: Annotated[str, StringConstraints(min_length=1, max_length=1_024)]
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def relative(self) -> Self:
        posix = PurePosixPath(self.path)
        if (
            posix.is_absolute()
            or "\\" in self.path
            or any(part in ("", ".", "..") for part in self.path.split("/"))
        ):
            raise ValueError("Evidence paths must be normalized relative paths")
        return self


class EvidenceSnapshot(Contract):
    """Evidence versions fixed at run creation; later reads must match exactly."""

    evidence_set_id: Identifier
    items: Annotated[tuple[EvidenceItem, ...], Field(max_length=10_000)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({i.path for i in self.items}) != len(self.items):
            raise ValueError("Evidence paths must be unique")
        return self

    def verify(self, path: str, data: bytes) -> EvidenceItem:
        item = next((i for i in self.items if i.path == path), None)
        if item is None:
            raise RunInputError("Evidence is not part of this run's snapshot")
        if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
            raise RunInputError("Evidence changed after the run snapshot")
        return item


class ComponentVersion(Contract):
    name: Identifier
    version: Version


class RunLimits(Contract):
    max_steps: Annotated[int, Field(ge=1, le=1_000)] = 50
    max_elapsed_seconds: Annotated[int, Field(ge=1, le=86_400)] = 3_600


class ReviewException(Contract):
    """A business review item (missing/conflicting evidence), not a technical failure."""

    code: Identifier
    message: Message
    requirement_id: Identifier | None = None


class ArtifactRecord(Contract):
    name: Annotated[str, StringConstraints(min_length=1, max_length=_MAX_ARTIFACT_NAME)]
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]


class StepRecord(Contract):
    step: Identifier
    from_status: RunStatus
    to_status: RunStatus
    completed_at: AwareDatetime
    artifacts: Annotated[tuple[ArtifactRecord, ...], Field(max_length=100)] = ()
    exceptions: Annotated[tuple[ReviewException, ...], Field(max_length=1_000)] = ()
    outcome: RunOutcome | None = None


class RunFailure(Contract):
    """A technical or budget failure; never reported as an incomplete packet."""

    code: Identifier
    message: Message
    during_status: RunStatus
    failed_at: AwareDatetime


class RunManifest(Contract):
    schema_version: Literal[1] = 1
    run_id: Annotated[str, StringConstraints(pattern=_RUN_ID.pattern)]
    request: RunRequest
    blank_sha256: Sha256
    blank_size_bytes: Annotated[int, Field(ge=1)]
    evidence: EvidenceSnapshot
    versions: Annotated[tuple[ComponentVersion, ...], Field(min_length=1, max_length=50)]
    limits: RunLimits
    created_at: AwareDatetime
    updated_at: AwareDatetime
    status: RunStatus
    outcome: RunOutcome | None = None
    steps: Annotated[tuple[StepRecord, ...], Field(max_length=1_000)] = ()
    failure: RunFailure | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        names = [v.name for v in self.versions]
        if len(set(names)) != len(names) or "code" not in names:
            raise ValueError("Versions must be unique and include the code version")
        if self.evidence.evidence_set_id != self.request.evidence_set_id:
            raise ValueError("Evidence snapshot must match the requested evidence set")
        if (self.status == "failed") != (self.failure is not None):
            raise ValueError("Only failed runs record a failure, and they must")
        if (self.status in ("packet_assembled", "published")) != (self.outcome is not None):
            raise ValueError("Only assembled or published runs record an outcome")
        if self.outcome == "complete" and self.exceptions():
            raise ValueError("A complete outcome cannot have open review exceptions")
        names = [a.name for a in self.artifacts]
        if len(set(names)) != len(names):
            raise ValueError("Artifact names must be unique within a run")
        return self

    @property
    def artifacts(self) -> tuple[ArtifactRecord, ...]:
        return tuple(a for s in self.steps for a in s.artifacts)

    def exceptions(self) -> tuple[ReviewException, ...]:
        return tuple(e for s in self.steps for e in s.exceptions)


class RunStore(Protocol):
    """Storage port for run state; adapters must enforce the same transition rules."""

    def create(
        self,
        request: RunRequest,
        blank: bytes,
        evidence: EvidenceSnapshot,
        *,
        versions: tuple[ComponentVersion, ...],
        limits: RunLimits,
    ) -> RunManifest: ...

    def load(self, run_id: str) -> RunManifest: ...

    def advance(
        self,
        run_id: str,
        *,
        step: str,
        expected_status: RunStatus,
        to_status: RunStatus,
        artifacts: Mapping[str, bytes] | None = None,
        exceptions: tuple[ReviewException, ...] = (),
        outcome: RunOutcome | None = None,
    ) -> RunManifest: ...

    def fail(self, run_id: str, *, code: str, message: str) -> RunManifest: ...

    def cancel(self, run_id: str) -> RunManifest: ...

    def read_blank(self, run_id: str) -> bytes: ...

    def read_artifact(self, run_id: str, name: str) -> bytes: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _rebuild(manifest: RunManifest, **changes: object) -> RunManifest:
    values: dict[str, object] = {name: getattr(manifest, name) for name in RunManifest.model_fields}
    values.update(changes)
    return RunManifest(**values)  # type: ignore[arg-type]


class FileRunStore:
    """Filesystem run store: one isolated, path-confined directory per run.

    Layout: ``<root>/<run_id>/manifest.json``, ``input/blank.pdf`` and content-addressed
    ``artifacts/<sha256>``. Stored inputs and artifacts are read-only and never replaced.
    Mutations hold an exclusive per-run lock, released automatically if the process exits.
    """

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
        max_blank_bytes: int = _DEFAULT_MAX_BLANK_BYTES,
    ) -> None:
        if root.is_symlink():
            raise RunStoreError("Run store root must not be a symlink")
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise RunStoreError("Run store root must be a directory")
        self.root = resolved
        self._clock = clock
        self._max_blank_bytes = max_blank_bytes

    def create(
        self,
        request: RunRequest,
        blank: bytes,
        evidence: EvidenceSnapshot,
        *,
        versions: tuple[ComponentVersion, ...],
        limits: RunLimits,
    ) -> RunManifest:
        now = self._now()
        if len(blank) > self._max_blank_bytes:
            raise RunInputError("Blank form exceeds its byte limit")
        if not blank.startswith(b"%PDF-"):
            raise RunInputError("Blank form must be a PDF document")
        if evidence.evidence_set_id != request.evidence_set_id:
            raise RunInputError("Evidence snapshot must match the requested evidence set")
        names = [v.name for v in versions]
        if len(set(names)) != len(names) or "code" not in names:
            raise RunInputError("Versions must be unique and include the code version")
        manifest = RunManifest(
            run_id=uuid4().hex,
            request=request,
            blank_sha256=hashlib.sha256(blank).hexdigest(),
            blank_size_bytes=len(blank),
            evidence=evidence,
            versions=versions,
            limits=limits,
            created_at=now,
            updated_at=now,
            status="created",
        )
        staging = self.root / f".staging-{uuid4().hex}"
        staging.mkdir()
        try:
            (staging / "input").mkdir()
            (staging / "artifacts").mkdir()
            _write_new(staging / "input" / "blank.pdf", blank)
            _write_manifest(staging, manifest)
            staging.rename(self.root / manifest.run_id)
        except BaseException:
            _remove_tree(staging)
            raise
        return manifest

    def load(self, run_id: str) -> RunManifest:
        return self._load(self._run_dir(run_id))

    def advance(
        self,
        run_id: str,
        *,
        step: str,
        expected_status: RunStatus,
        to_status: RunStatus,
        artifacts: Mapping[str, bytes] | None = None,
        exceptions: tuple[ReviewException, ...] = (),
        outcome: RunOutcome | None = None,
    ) -> RunManifest:
        artifacts = artifacts or {}
        for name, data in artifacts.items():
            if len(name) > _MAX_ARTIFACT_NAME or not _ARTIFACT_NAME.fullmatch(name):
                raise RunInputError("Artifact names must be simple file names")
            if len(data) > _MAX_ARTIFACT_BYTES:
                raise RunInputError("Artifact exceeds its byte limit")
        records = tuple(
            ArtifactRecord(name=n, sha256=hashlib.sha256(d).hexdigest(), size_bytes=len(d))
            for n, d in artifacts.items()
        )
        run_dir = self._run_dir(run_id)
        with _locked(run_dir):
            manifest = self._load(run_dir)
            last = manifest.steps[-1] if manifest.steps else None
            if (
                last is not None
                and manifest.status == to_status
                and (last.step, last.from_status, last.to_status)
                == (step, expected_status, to_status)
            ):
                if (last.artifacts, last.exceptions, last.outcome) != (
                    records,
                    exceptions,
                    outcome,
                ):
                    raise RunConflictError("Retry would change an already completed step")
                return manifest
            if manifest.status in _TERMINAL:
                raise RunTransitionError("Run has already ended")
            if manifest.status != expected_status:
                raise RunTransitionError("Run is not in the expected status")
            if _NEXT.get(expected_status) != to_status:
                raise RunTransitionError("Requested transition is not allowed")
            if to_status == "packet_assembled" and outcome is None:
                raise RunTransitionError("An assembled packet requires an explicit outcome")
            if to_status != "packet_assembled" and outcome is not None:
                raise RunTransitionError("Only packet assembly may set the run outcome")
            if outcome == "complete" and (manifest.exceptions() or exceptions):
                raise RunTransitionError("A complete outcome cannot have open review exceptions")
            existing = {a.name for a in manifest.artifacts}
            if existing & artifacts.keys():
                raise RunConflictError("Recorded artifacts cannot be replaced")
            now = self._now()
            elapsed = (now - manifest.created_at).total_seconds()
            if elapsed > manifest.limits.max_elapsed_seconds:
                self._write_failure(
                    run_dir, manifest, "elapsed_limit_exceeded", "Run elapsed-time limit exceeded."
                )
                raise RunLimitError("Run elapsed-time limit exceeded")
            if len(manifest.steps) >= manifest.limits.max_steps:
                self._write_failure(
                    run_dir, manifest, "step_limit_exceeded", "Run step limit exceeded."
                )
                raise RunLimitError("Run step limit exceeded")
            record = StepRecord(
                step=step,
                from_status=expected_status,
                to_status=to_status,
                completed_at=now,
                artifacts=records,
                exceptions=exceptions,
                outcome=outcome,
            )
            updated = _rebuild(
                manifest,
                steps=(*manifest.steps, record),
                status=to_status,
                outcome=outcome if outcome is not None else manifest.outcome,
                updated_at=now,
            )
            for data in artifacts.values():
                _write_blob(run_dir / "artifacts", data)
            _write_manifest(run_dir, updated)
            return updated

    def fail(self, run_id: str, *, code: str, message: str) -> RunManifest:
        run_dir = self._run_dir(run_id)
        with _locked(run_dir):
            manifest = self._load(run_dir)
            if manifest.status in _TERMINAL:
                raise RunTransitionError("Run has already ended")
            return self._write_failure(run_dir, manifest, code, message)

    def cancel(self, run_id: str) -> RunManifest:
        run_dir = self._run_dir(run_id)
        with _locked(run_dir):
            manifest = self._load(run_dir)
            if manifest.status in _TERMINAL:
                raise RunTransitionError("Run has already ended")
            updated = _rebuild(manifest, status="cancelled", outcome=None, updated_at=self._now())
            _write_manifest(run_dir, updated)
            return updated

    def read_blank(self, run_id: str) -> bytes:
        run_dir = self._run_dir(run_id)
        manifest = self._load(run_dir)
        data = _read(run_dir / "input" / "blank.pdf", self._max_blank_bytes)
        if hashlib.sha256(data).hexdigest() != manifest.blank_sha256:
            raise RunStoreError("Stored blank form changed after run creation")
        return data

    def read_artifact(self, run_id: str, name: str) -> bytes:
        run_dir = self._run_dir(run_id)
        manifest = self._load(run_dir)
        record = next((a for a in manifest.artifacts if a.name == name), None)
        if record is None:
            raise RunStoreError("Unknown artifact for this run")
        data = _read(run_dir / "artifacts" / record.sha256, _MAX_ARTIFACT_BYTES)
        if hashlib.sha256(data).hexdigest() != record.sha256:
            raise RunStoreError("Stored artifact changed after it was recorded")
        return data

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RunStoreError("Run clock must return timezone-aware timestamps")
        return now

    def _run_dir(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise RunStoreError("Unknown run")
        run_dir = self.root / run_id
        for path in (run_dir, run_dir / "input", run_dir / "artifacts"):
            if path.is_symlink():
                raise RunStoreError("Run storage must not resolve through a symlink")
        if not run_dir.is_dir():
            raise RunStoreError("Unknown run")
        return run_dir

    def _load(self, run_dir: Path) -> RunManifest:
        raw = _read(run_dir / "manifest.json", _MAX_MANIFEST_BYTES)
        try:
            manifest = RunManifest.model_validate_json(raw)
        except ValidationError:
            raise RunStoreError("Run manifest is invalid") from None
        if manifest.run_id != run_dir.name:
            raise RunStoreError("Run manifest does not match its run")
        return manifest

    def _write_failure(
        self, run_dir: Path, manifest: RunManifest, code: str, message: str
    ) -> RunManifest:
        now = self._now()
        updated = _rebuild(
            manifest,
            status="failed",
            outcome=None,
            updated_at=now,
            failure=RunFailure(
                code=code, message=message, during_status=manifest.status, failed_at=now
            ),
        )
        _write_manifest(run_dir, updated)
        return updated


@contextmanager
def _locked(run_dir: Path) -> Generator[None]:
    descriptor = os.open(run_dir / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _read(path: Path, limit: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise RunStoreError("Run file is missing or not a regular file") from None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise RunStoreError("Run file is missing or not a regular file")
        if info.st_size > limit:
            raise RunStoreError("Run file exceeds its byte limit")
        return stream.read(limit + 1)


def _write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def _write_blob(folder: Path, data: bytes) -> None:
    final = folder / hashlib.sha256(data).hexdigest()
    if final.exists() or final.is_symlink():
        if hashlib.sha256(_read(final, _MAX_ARTIFACT_BYTES)).hexdigest() != final.name:
            raise RunStoreError("Stored artifact changed after it was recorded")
        return
    temporary = folder / f".tmp-{uuid4().hex}"
    _write_new(temporary, data)
    try:
        os.link(temporary, final)
    except FileExistsError:
        pass
    finally:
        temporary.unlink()


def _write_manifest(run_dir: Path, manifest: RunManifest) -> None:
    temporary = run_dir / f".manifest-{uuid4().hex}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(manifest.model_dump_json(indent=2).encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, run_dir / "manifest.json")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_dir() and not child.is_symlink():
            child.rmdir()
        else:
            child.chmod(0o600)
            child.unlink()
    path.rmdir()
