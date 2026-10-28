import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from bd_packet_builder.run import (
    ComponentVersion,
    EvidenceItem,
    EvidenceSnapshot,
    FileRunStore,
    ReviewException,
    RunConflictError,
    RunInputError,
    RunLimitError,
    RunLimits,
    RunRequest,
    RunStoreError,
    RunTransitionError,
)

BLANK = b"%PDF-1.7\nsynthetic blank\n%%EOF\n"
START = datetime(2026, 10, 28, 12, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> FileRunStore:
    root = tmp_path / "runs"
    root.mkdir()
    return FileRunStore(root, clock=clock)


def request() -> RunRequest:
    return RunRequest(
        evidence_set_id="synthetic-set",
        requester_id="00000000-0000-0000-0000-000000000001",
        blank_name="Synthetic issuer form.pdf",
        as_of=date(2026, 9, 30),
    )


def snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_set_id="synthetic-set",
        items=(
            EvidenceItem(
                path="Focus_Reports/Example_Aug2026.pdf",
                sha256=hashlib.sha256(b"focus").hexdigest(),
                size_bytes=5,
            ),
        ),
    )


VERSIONS = (ComponentVersion(name="code", version="0.1.0"),)


def create(store: FileRunStore, **limits: int) -> str:
    manifest = store.create(
        request(),
        BLANK,
        snapshot(),
        versions=VERSIONS,
        limits=RunLimits(**limits) if limits else RunLimits(),
    )
    return manifest.run_id


def advance_to_assembled(store: FileRunStore, run_id: str, *, outcome: str = "incomplete") -> None:
    store.advance(
        run_id,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"{}"},
    )
    store.advance(
        run_id,
        step="collect_evidence",
        expected_status="form_interpreted",
        to_status="evidence_collected",
        artifacts={"evidence.json": b"{}"},
    )
    store.advance(
        run_id,
        step="validate_answers",
        expected_status="evidence_collected",
        to_status="answers_validated",
        artifacts={"validation.json": b"{}"},
        exceptions=(
            ReviewException(
                code="missing_evidence",
                requirement_id="q7",
                message="No approved source states the DTC number.",
            ),
        )
        if outcome == "incomplete"
        else (),
    )
    store.advance(
        run_id,
        step="assemble_packet",
        expected_status="answers_validated",
        to_status="packet_assembled",
        artifacts={"packet.pdf": b"%PDF-packet", "reviewer-summary.txt": b"summary"},
        outcome=outcome,  # type: ignore[arg-type]
    )


def test_create_snapshots_blank_and_records_provenance(store: FileRunStore) -> None:
    run_id = create(store)
    manifest = store.load(run_id)

    assert manifest.status == "created"
    assert manifest.outcome is None
    assert manifest.blank_sha256 == hashlib.sha256(BLANK).hexdigest()
    assert manifest.request.blank_name == "Synthetic issuer form.pdf"
    assert manifest.evidence == snapshot()
    assert manifest.versions == VERSIONS
    assert manifest.created_at == START
    assert store.read_blank(run_id) == BLANK
    stored = list((store.root / run_id).rglob("*"))
    assert all("Synthetic issuer form" not in p.name for p in stored)


def test_run_ids_are_unique_and_isolated(store: FileRunStore) -> None:
    first, second = create(store), create(store)

    assert first != second
    store.advance(
        first,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"{}"},
    )
    assert store.load(second).status == "created"
    with pytest.raises(RunStoreError):
        store.read_artifact(second, "requirements.json")


def test_full_lifecycle_publishes_incomplete_outcome_with_exceptions(
    store: FileRunStore, clock: Clock
) -> None:
    run_id = create(store)
    advance_to_assembled(store, run_id)
    clock.now = START + timedelta(minutes=3)
    manifest = store.advance(
        run_id,
        step="publish",
        expected_status="packet_assembled",
        to_status="published",
    )

    assert manifest.status == "published"
    assert manifest.outcome == "incomplete"
    assert [s.step for s in manifest.steps] == [
        "interpret_form",
        "collect_evidence",
        "validate_answers",
        "assemble_packet",
        "publish",
    ]
    assert [e.code for e in manifest.exceptions()] == ["missing_evidence"]
    assert manifest.updated_at == START + timedelta(minutes=3)
    assert store.read_artifact(run_id, "packet.pdf") == b"%PDF-packet"
    artifacts = {a.name: a.sha256 for a in manifest.artifacts}
    assert artifacts["packet.pdf"] == hashlib.sha256(b"%PDF-packet").hexdigest()


def test_complete_outcome_requires_no_open_exceptions(store: FileRunStore) -> None:
    run_id = create(store)
    advance_to_assembled(store, run_id, outcome="complete")
    assert store.load(run_id).outcome == "complete"

    other = create(store)
    store.advance(
        other,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        exceptions=(ReviewException(code="unreadable_page", message="Page 3 unreadable."),),
    )
    store.advance(
        other,
        step="collect_evidence",
        expected_status="form_interpreted",
        to_status="evidence_collected",
    )
    store.advance(
        other,
        step="validate_answers",
        expected_status="evidence_collected",
        to_status="answers_validated",
    )
    with pytest.raises(RunTransitionError, match="exceptions"):
        store.advance(
            other,
            step="assemble_packet",
            expected_status="answers_validated",
            to_status="packet_assembled",
            outcome="complete",
        )
    assert store.load(other).status == "answers_validated"


@pytest.mark.parametrize(
    ("to_status", "outcome"),
    [("packet_assembled", None), ("form_interpreted", "incomplete")],
)
def test_outcome_is_set_only_when_packet_is_assembled(
    store: FileRunStore, to_status: str, outcome: str | None
) -> None:
    run_id = create(store)
    if to_status == "packet_assembled":
        for step, frm, to in (
            ("interpret_form", "created", "form_interpreted"),
            ("collect_evidence", "form_interpreted", "evidence_collected"),
            ("validate_answers", "evidence_collected", "answers_validated"),
        ):
            store.advance(run_id, step=step, expected_status=frm, to_status=to)  # type: ignore[arg-type]
        expected = "answers_validated"
        frm = "answers_validated"
    else:
        expected = "created"
        frm = "created"
    with pytest.raises(RunTransitionError, match="outcome"):
        store.advance(
            run_id,
            step="step",
            expected_status=frm,  # type: ignore[arg-type]
            to_status=to_status,  # type: ignore[arg-type]
            outcome=outcome,  # type: ignore[arg-type]
        )
    assert store.load(run_id).status == expected


@pytest.mark.parametrize(
    ("expected", "target"),
    [
        ("created", "evidence_collected"),
        ("created", "published"),
        ("created", "created"),
        ("form_interpreted", "evidence_collected"),
        ("created", "failed"),
    ],
)
def test_illegal_or_stale_transitions_are_typed_errors(
    store: FileRunStore, expected: str, target: str
) -> None:
    run_id = create(store)
    before = (store.root / run_id / "manifest.json").read_bytes()

    with pytest.raises(RunTransitionError):
        store.advance(
            run_id,
            step="skip",
            expected_status=expected,  # type: ignore[arg-type]
            to_status=target,  # type: ignore[arg-type]
        )
    assert (store.root / run_id / "manifest.json").read_bytes() == before


def test_retry_of_completed_step_with_identical_result_is_idempotent(store: FileRunStore) -> None:
    run_id = create(store)
    kwargs: dict[str, object] = {
        "step": "interpret_form",
        "expected_status": "created",
        "to_status": "form_interpreted",
        "artifacts": {"requirements.json": b'{"a": 1}'},
    }
    first = store.advance(run_id, **kwargs)  # type: ignore[arg-type]
    second = store.advance(run_id, **kwargs)  # type: ignore[arg-type]

    assert second == first
    assert len(second.steps) == 1


def test_retry_with_different_result_is_rejected_without_overwrite(store: FileRunStore) -> None:
    run_id = create(store)
    store.advance(
        run_id,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"first"},
    )

    with pytest.raises(RunConflictError):
        store.advance(
            run_id,
            step="interpret_form",
            expected_status="created",
            to_status="form_interpreted",
            artifacts={"requirements.json": b"second"},
        )
    assert store.read_artifact(run_id, "requirements.json") == b"first"


def test_artifacts_are_immutable_across_steps(store: FileRunStore) -> None:
    run_id = create(store)
    store.advance(
        run_id,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"first"},
    )

    with pytest.raises(RunConflictError):
        store.advance(
            run_id,
            step="collect_evidence",
            expected_status="form_interpreted",
            to_status="evidence_collected",
            artifacts={"requirements.json": b"replacement"},
        )
    assert store.load(run_id).status == "form_interpreted"
    assert store.read_artifact(run_id, "requirements.json") == b"first"


def test_published_run_cannot_be_overwritten_failed_or_cancelled(store: FileRunStore) -> None:
    run_id = create(store)
    advance_to_assembled(store, run_id)
    published = store.advance(
        run_id, step="publish", expected_status="packet_assembled", to_status="published"
    )

    assert (
        store.advance(
            run_id, step="publish", expected_status="packet_assembled", to_status="published"
        )
        == published
    )
    with pytest.raises(RunConflictError):
        store.advance(
            run_id,
            step="publish",
            expected_status="packet_assembled",
            to_status="published",
            artifacts={"late.txt": b"late"},
        )
    with pytest.raises(RunTransitionError):
        store.advance(
            run_id,
            step="assemble_packet",
            expected_status="answers_validated",
            to_status="packet_assembled",
            outcome="incomplete",
        )
    with pytest.raises(RunTransitionError):
        store.fail(run_id, code="late_failure", message="Should not apply.")
    with pytest.raises(RunTransitionError):
        store.cancel(run_id)
    assert store.load(run_id) == published


def test_technical_failure_is_distinct_from_incomplete_outcome(store: FileRunStore) -> None:
    run_id = create(store)
    store.advance(
        run_id, step="interpret_form", expected_status="created", to_status="form_interpreted"
    )
    manifest = store.fail(run_id, code="model_timeout", message="Model call timed out.")

    assert manifest.status == "failed"
    assert manifest.outcome is None
    assert manifest.failure is not None
    assert manifest.failure.code == "model_timeout"
    with pytest.raises(RunTransitionError):
        store.advance(
            run_id,
            step="collect_evidence",
            expected_status="form_interpreted",
            to_status="evidence_collected",
        )


def test_cancelled_run_rejects_further_steps(store: FileRunStore) -> None:
    run_id = create(store)
    assert store.cancel(run_id).status == "cancelled"
    with pytest.raises(RunTransitionError):
        store.advance(
            run_id, step="interpret_form", expected_status="created", to_status="form_interpreted"
        )


def test_step_budget_exhaustion_fails_run_visibly(store: FileRunStore) -> None:
    run_id = create(store, max_steps=1)
    store.advance(
        run_id, step="interpret_form", expected_status="created", to_status="form_interpreted"
    )

    with pytest.raises(RunLimitError, match="step"):
        store.advance(
            run_id,
            step="collect_evidence",
            expected_status="form_interpreted",
            to_status="evidence_collected",
        )
    manifest = store.load(run_id)
    assert manifest.status == "failed"
    assert manifest.failure is not None
    assert manifest.failure.code == "step_limit_exceeded"


def test_elapsed_limit_exhaustion_fails_run_visibly(store: FileRunStore, clock: Clock) -> None:
    run_id = create(store, max_elapsed_seconds=60)
    clock.now = START + timedelta(seconds=61)

    with pytest.raises(RunLimitError, match="elapsed"):
        store.advance(
            run_id, step="interpret_form", expected_status="created", to_status="form_interpreted"
        )
    manifest = store.load(run_id)
    assert manifest.status == "failed"
    assert manifest.failure is not None
    assert manifest.failure.code == "elapsed_limit_exceeded"
    assert manifest.limits.max_elapsed_seconds == 60


def test_tampered_blank_or_artifact_is_detected(store: FileRunStore) -> None:
    run_id = create(store)
    store.advance(
        run_id,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"{}"},
    )
    blank = store.root / run_id / "input" / "blank.pdf"
    blank.chmod(0o600)
    blank.write_bytes(BLANK + b"changed")
    artifact = store.root / run_id / "artifacts" / hashlib.sha256(b"{}").hexdigest()
    artifact.chmod(0o600)
    artifact.write_bytes(b"changed")

    with pytest.raises(RunStoreError, match="changed"):
        store.read_blank(run_id)
    with pytest.raises(RunStoreError, match="changed"):
        store.read_artifact(run_id, "requirements.json")


def test_evidence_change_during_run_is_detected(store: FileRunStore) -> None:
    run_id = create(store)
    manifest = store.load(run_id)
    item = manifest.evidence.items[0]

    manifest.evidence.verify(item.path, b"focus")
    with pytest.raises(RunInputError, match="changed"):
        manifest.evidence.verify(item.path, b"focus revised")
    with pytest.raises(RunInputError, match="snapshot"):
        manifest.evidence.verify("Focus_Reports/other.pdf", b"focus")


@pytest.mark.parametrize(
    "name",
    ["../escape.json", "nested/file.json", ".hidden", "", "a" * 200, "manifest.json/.."],
)
def test_artifact_names_are_confined(store: FileRunStore, name: str) -> None:
    run_id = create(store)
    with pytest.raises((RunInputError, ValidationError)):
        store.advance(
            run_id,
            step="interpret_form",
            expected_status="created",
            to_status="form_interpreted",
            artifacts={name: b"{}"},
        )
    assert store.load(run_id).status == "created"


@pytest.mark.parametrize("run_id", ["../runs", "x" * 32, "", "/etc", "A" * 32, "0" * 32])
def test_unknown_or_malformed_run_ids_are_rejected(store: FileRunStore, run_id: str) -> None:
    with pytest.raises(RunStoreError):
        store.load(run_id)


def test_symlinked_store_root_and_run_folder_are_rejected(tmp_path: Path, clock: Clock) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(RunStoreError, match="symlink"):
        FileRunStore(link, clock=clock)

    store = FileRunStore(real, clock=clock)
    run_id = create(store)
    elsewhere = tmp_path / "elsewhere"
    (real / run_id).rename(elsewhere)
    (real / run_id).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(RunStoreError, match="symlink"):
        store.load(run_id)


@pytest.mark.parametrize(
    "blank",
    [b"", b"not a pdf", b"%PDF" + b"x" * 10],
)
def test_non_pdf_blank_is_rejected_before_any_run_exists(store: FileRunStore, blank: bytes) -> None:
    with pytest.raises(RunInputError):
        store.create(request(), blank, snapshot(), versions=VERSIONS, limits=RunLimits())
    assert list(store.root.iterdir()) == []


def test_oversized_blank_is_rejected(tmp_path: Path, clock: Clock) -> None:
    store = FileRunStore(tmp_path, clock=clock, max_blank_bytes=len(BLANK) - 1)
    with pytest.raises(RunInputError, match="limit"):
        store.create(request(), BLANK, snapshot(), versions=VERSIONS, limits=RunLimits())


def test_evidence_set_must_match_request(store: FileRunStore) -> None:
    mismatched = EvidenceSnapshot(evidence_set_id="other-set", items=snapshot().items)
    with pytest.raises(RunInputError, match="evidence set"):
        store.create(request(), BLANK, mismatched, versions=VERSIONS, limits=RunLimits())


def test_naive_clock_is_rejected(tmp_path: Path) -> None:
    naive: Callable[[], datetime] = lambda: datetime(2026, 10, 28)  # noqa: E731, DTZ001
    store = FileRunStore(tmp_path, clock=naive)
    with pytest.raises(RunStoreError, match="timezone"):
        store.create(request(), BLANK, snapshot(), versions=VERSIONS, limits=RunLimits())


@pytest.mark.parametrize(
    "versions",
    [
        (),
        (ComponentVersion(name="prompts", version="1"),),
        (
            ComponentVersion(name="code", version="1"),
            ComponentVersion(name="code", version="2"),
        ),
    ],
)
def test_create_requires_unique_code_version(
    store: FileRunStore, versions: tuple[ComponentVersion, ...]
) -> None:
    with pytest.raises(RunInputError, match="version"):
        store.create(request(), BLANK, snapshot(), versions=versions, limits=RunLimits())


def test_manifest_round_trips_through_disk(store: FileRunStore) -> None:
    run_id = create(store)
    advance_to_assembled(store, run_id)
    reloaded = FileRunStore(store.root, clock=lambda: START).load(run_id)

    assert reloaded == store.load(run_id)
    raw = json.loads((store.root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert "synthetic blank" not in json.dumps(raw)


def test_stored_inputs_and_artifacts_are_read_only(store: FileRunStore) -> None:
    run_id = create(store)
    store.advance(
        run_id,
        step="interpret_form",
        expected_status="created",
        to_status="form_interpreted",
        artifacts={"requirements.json": b"{}"},
    )
    files = [p for p in (store.root / run_id).rglob("*") if p.is_file()]
    stored = [p for p in files if p.parent.name in ("input", "artifacts")]
    assert len(stored) == 2
    assert all(not os.access(path, os.W_OK) for path in stored)
