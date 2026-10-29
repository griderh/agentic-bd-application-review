import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError

from bd_packet_builder.blob_storage import (
    AzureBlobs,
    BlobStorageError,
    InputBundle,
    PacketBlobStorage,
)
from bd_packet_builder.history import ArchiveEntry, ArchiveManifest
from bd_packet_builder.run import (
    ComponentVersion,
    EvidenceSnapshot,
    FileRunStore,
    RunLimits,
    RunRequest,
)


class MemoryBlobs:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], bytes] = {}

    def read(self, container: str, name: str, limit: int) -> bytes:
        value = self.data[container, name]
        if len(value) > limit:
            raise BlobStorageError("Blob exceeds byte limit")
        return value

    def put_new(self, container: str, name: str, data: bytes) -> bool:
        key = container, name
        if key in self.data:
            if self.data[key] != data:
                raise BlobStorageError("Immutable blob already exists with different contents")
            return False
        self.data[key] = data
        return True


def entry(path: str, content: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def seed(blobs: MemoryBlobs) -> InputBundle:
    blank = b"%PDF-blank"
    evidence = b"%PDF-evidence"
    payload = {
        "schema_version": 1,
        "blank_id": "blank-1",
        "evidence_set_id": "set-1",
        "blank": entry("bd_agreements/Blank/form.pdf", blank),
        "evidence": [entry("bd_agreements/supporting_data/FINRA_Certification/firm.pdf", evidence)],
    }
    bundle = InputBundle.model_validate_json(json.dumps(payload))
    prefix = "bundles/blank-1/set-1/"
    blobs.data["packet-inputs", prefix + "manifest.json"] = bundle.model_dump_json().encode()
    blobs.data["packet-inputs", prefix + bundle.blank.path] = blank
    blobs.data["packet-inputs", prefix + bundle.evidence[0].path] = evidence
    return bundle


def test_blob_read_failure_exposes_http_status_but_not_remote_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = HttpResponseError("sensitive-example-storage-error")
    error.status_code = 403
    client = Mock()
    client.get_blob_client.return_value.get_blob_properties.side_effect = error
    with pytest.raises(BlobStorageError) as failure:
        AzureBlobs(client).read("packet-inputs", "manifest.json", 100)
    assert "403" in str(failure.value)
    assert "sensitive-example" not in str(failure.value)
    assert "HTTP 403" in caplog.text
    assert "sensitive-example" not in caplog.text


def test_stages_original_bytes_and_verifies_hashes(tmp_path: Path) -> None:
    blobs = MemoryBlobs()
    bundle = seed(blobs)
    storage = PacketBlobStorage(blobs)
    staged = storage.stage("blank-1", "set-1", tmp_path)
    assert staged == bundle
    assert (tmp_path / bundle.blank.path).read_bytes() == b"%PDF-blank"
    assert (tmp_path / bundle.evidence[0].path).read_bytes() == b"%PDF-evidence"


def test_history_bundle_stages_only_approved_references_not_holdouts(tmp_path: Path) -> None:
    blobs = MemoryBlobs()
    bundle = seed(blobs)
    prior = b"%PDF-prior-private"
    reference = ArchiveEntry(
        path="bd_agreements/Completed/Broward/prior.pdf",
        sha256=hashlib.sha256(prior).hexdigest(),
        partition="reference",
        issuer="Broward",
    )
    heldout = ArchiveEntry(
        path="bd_agreements/Completed/Holdout/never-read.pdf",
        sha256="0" * 64,
        partition="evaluation",
        issuer="Holdout",
    )
    payload = bundle.model_dump(mode="json")
    payload.update(
        issuer="Broward",
        historical_archive=ArchiveManifest(entries=(reference, heldout)).model_dump(mode="json"),
        historical_inputs=[entry(reference.path, prior)],
    )
    configured = InputBundle.model_validate_json(json.dumps(payload))
    blobs.data["packet-inputs", "bundles/blank-1/set-1/manifest.json"] = (
        configured.model_dump_json().encode()
    )
    blobs.data["packet-inputs", "bundles/blank-1/set-1/" + reference.path] = prior
    PacketBlobStorage(blobs).stage("blank-1", "set-1", tmp_path)
    assert (tmp_path / reference.path).read_bytes() == prior
    assert not (tmp_path / heldout.path).exists()
    assert (tmp_path / reference.path).stat().st_mode & 0o777 == 0o600


def test_history_bundle_rejects_an_evaluation_file_as_reference_input() -> None:
    blobs = MemoryBlobs()
    bundle = seed(blobs)
    data = b"private-heldout"
    heldout = ArchiveEntry(
        path="bd_agreements/Completed/Holdout/answer.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        partition="evaluation",
        issuer="Holdout",
    )
    payload = bundle.model_dump(mode="json")
    payload.update(
        issuer="Broward",
        historical_archive=ArchiveManifest(entries=(heldout,)).model_dump(mode="json"),
        historical_inputs=[entry(heldout.path, data)],
    )
    with pytest.raises(ValueError, match="reference partition"):
        InputBundle.model_validate_json(json.dumps(payload))


def test_changed_evidence_is_an_explicit_failure(tmp_path: Path) -> None:
    blobs = MemoryBlobs()
    bundle = seed(blobs)
    blobs.data["packet-inputs", "bundles/blank-1/set-1/" + bundle.evidence[0].path] = b"changed"
    with pytest.raises(BlobStorageError, match="hash|snapshot"):
        PacketBlobStorage(blobs).stage("blank-1", "set-1", tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.pdf",
        "/tmp/outside.pdf",
        "bd_agreements/supporting_data/../escape.pdf",
        "bd_agreements/Completed/prior.pdf",
        "bd_agreements/supporting_data/Unknown/source.pdf",
        "bd_agreements\\supporting_data\\source.pdf",
    ],
)
def test_bundle_rejects_non_designated_evidence_paths(path: str) -> None:
    with pytest.raises(ValueError):
        InputBundle.model_validate_json(
            json.dumps(
                {
                    "blank_id": "blank-1",
                    "evidence_set_id": "set-1",
                    "blank": entry("bd_agreements/Blank/form.pdf", b"%PDF"),
                    "evidence": [entry(path, b"%PDF")],
                }
            )
        )


def test_staging_rejects_symlink_escape(tmp_path: Path) -> None:
    blobs = MemoryBlobs()
    seed(blobs)
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    root = tmp_path / "stage"
    root.mkdir()
    (root / "bd_agreements").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(BlobStorageError, match="symlink|escape"):
        PacketBlobStorage(blobs).stage("blank-1", "set-1", root)
    assert not list(elsewhere.iterdir())


def test_retry_claim_never_overwrites_or_starts_a_second_run() -> None:
    blobs = MemoryBlobs()
    storage = PacketBlobStorage(blobs)
    storage.claim("request-1", "blank-1", "set-1")
    with pytest.raises(BlobStorageError, match="already|retry"):
        storage.claim("request-1", "blank-1", "set-1")


def test_manifest_identity_must_match_requested_ids(tmp_path: Path) -> None:
    blobs = MemoryBlobs()
    bundle = seed(blobs)
    blobs.data["packet-inputs", "bundles/blank-2/set-1/manifest.json"] = (
        bundle.model_dump_json().encode()
    )
    with pytest.raises(BlobStorageError, match="identity"):
        PacketBlobStorage(blobs).stage("blank-2", "set-1", tmp_path)


def published_run(root: Path) -> tuple[FileRunStore, str]:
    root.mkdir()
    store = FileRunStore(root)
    m = store.create(
        RunRequest(evidence_set_id="set-1", requester_id="reviewer", blank_name="Form.pdf"),
        b"%PDF-blank",
        EvidenceSnapshot(evidence_set_id="set-1", items=()),
        versions=(ComponentVersion(name="code", version="test"),),
        limits=RunLimits(),
    )
    transitions = [
        ("created", "form_interpreted"),
        ("form_interpreted", "evidence_collected"),
        ("evidence_collected", "answers_validated"),
        ("answers_validated", "packet_assembled"),
        ("packet_assembled", "published"),
    ]
    for before, after in transitions:
        store.advance(
            m.run_id,
            step=f"step-{before}",
            expected_status=before,
            to_status=after,
            artifacts={"packet.pdf": b"%PDF-packet", "reviewer-summary.txt": b"INTERNAL"}
            if after == "packet_assembled"
            else None,
            outcome="incomplete" if after == "packet_assembled" else None,
        )
    return store, m.run_id


def test_publish_is_idempotent_and_keeps_reviewer_data_out_of_packet_container(
    tmp_path: Path,
) -> None:
    store, run_id = published_run(tmp_path / "runs")
    blobs = MemoryBlobs()
    storage = PacketBlobStorage(blobs)
    manifest = store.load(run_id)
    locations = storage.publish("request-1", store, manifest)
    assert storage.publish("request-1", store, manifest) == locations
    packet_keys = [n for c, n in blobs.data if c == "packet-results"]
    assert packet_keys == [f"runs/request-1/{run_id}/packet.pdf"]
    assert blobs.data["packet-results", packet_keys[0]] == b"%PDF-packet"
    assert ("reviewer-results", "requests/request-1-result.json") in blobs.data


def test_partial_publication_never_writes_a_completed_result(tmp_path: Path) -> None:
    store, run_id = published_run(tmp_path / "runs")

    class FailedUpload(MemoryBlobs):
        def put_new(self, container: str, name: str, data: bytes) -> bool:
            if name.endswith("reviewer-summary.txt"):
                raise BlobStorageError("Synthetic storage failure")
            return super().put_new(container, name, data)

    blobs = FailedUpload()
    with pytest.raises(BlobStorageError, match="Synthetic storage failure"):
        PacketBlobStorage(blobs).publish("request-1", store, store.load(run_id))
    assert ("reviewer-results", "requests/request-1-result.json") not in blobs.data
