"""Private, immutable Blob inputs and separately published packet/reviewer outputs."""

import argparse
import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol, Self
from urllib.parse import urlsplit

from azure.core import MatchConditions
from azure.core.exceptions import AzureError, HttpResponseError, ResourceExistsError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient
from pydantic import Field, field_validator, model_validator

from bd_packet_builder.contracts import Contract, Identifier, Nonblank, Sha256
from bd_packet_builder.history import ArchiveManifest, with_historical_sources
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.retrieval import default_catalog
from bd_packet_builder.run import RunManifest, RunStore

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
INPUTS = "packet-inputs"
PACKETS = "packet-results"
REVIEWS = "reviewer-results"
_LOGGER = logging.getLogger(__name__)


class BlobStorageError(ValueError):
    """Storage failure; never a completed packet or a missing business fact."""


class BlobPort(Protocol):
    def read(self, container: str, name: str, limit: int) -> bytes: ...

    def put_new(self, container: str, name: str, data: bytes) -> bool:
        """Create immutably; return False for identical existing bytes, reject changes."""
        ...


class AzureBlobs:
    def __init__(self, client: BlobServiceClient) -> None:
        self.client = client

    def read(self, container: str, name: str, limit: int) -> bytes:
        try:
            blob = self.client.get_blob_client(container, name)
            properties = blob.get_blob_properties(timeout=30)
            if properties.size > limit:
                raise BlobStorageError("Blob exceeds byte limit")
            data = blob.download_blob(
                offset=0,
                length=limit + 1,
                etag=properties.etag,
                match_condition=MatchConditions.IfNotModified,
                timeout=30,
            ).readall()
        except AzureError as error:
            _LOGGER.error("Blob read failed (%s)", _azure_error_label(error))
            raise BlobStorageError(f"Blob read failed ({_azure_error_label(error)})") from None
        if len(data) > limit:
            raise BlobStorageError("Blob exceeds byte limit")
        return data

    def put_new(self, container: str, name: str, data: bytes) -> bool:
        try:
            self.client.get_blob_client(container, name).upload_blob(
                data, overwrite=False, timeout=30
            )
        except ResourceExistsError:
            if self.read(container, name, len(data)) != data:
                raise BlobStorageError(
                    "Immutable blob already exists with different contents"
                ) from None
            return False
        except AzureError as error:
            _LOGGER.error("Blob write failed (%s)", _azure_error_label(error))
            raise BlobStorageError(f"Blob write failed ({_azure_error_label(error)})") from None
        return True


def _azure_error_label(error: AzureError) -> str:
    status = f", HTTP {error.status_code}" if isinstance(error, HttpResponseError) else ""
    return f"{type(error).__name__}{status}"


def validate_account_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not (parsed.hostname or "").endswith(".blob.core.windows.net")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or parsed.port not in (None, 443)
    ):
        raise BlobStorageError("Use an HTTPS Azure Blob account URL without keys or SAS")
    return url.rstrip("/")


class BlobInput(Contract):
    path: str
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=1, le=MAX_FILE_BYTES)]

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        if (
            PurePosixPath(value).is_absolute()
            or "\\" in value
            or any(p in ("", ".", "..") for p in value.split("/"))
        ):
            raise ValueError("Input paths must be normalized relative paths")
        return value


class InputBundle(Contract):
    schema_version: Literal[1] = 1
    blank_id: Identifier
    evidence_set_id: Identifier
    blank: BlobInput
    evidence: Annotated[tuple[BlobInput, ...], Field(max_length=100)]
    issuer: Nonblank | None = None
    historical_archive: ArchiveManifest | None = None
    historical_inputs: Annotated[tuple[BlobInput, ...], Field(max_length=100)] = ()

    @model_validator(mode="after")
    def allowed_inputs(self) -> Self:
        blank = PurePosixPath(self.blank.path)
        if not blank.is_relative_to("bd_agreements/Blank") or blank.suffix.lower() != ".pdf":
            raise ValueError("Blank must be a PDF under the blank boundary")
        families = {f.folder for f in default_catalog().families}
        paths = []
        for item in self.evidence:
            path = PurePosixPath(item.path)
            if (
                len(path.parts) < 4
                or path.parts[:2] != ("bd_agreements", "supporting_data")
                or path.parts[2] not in families
            ):
                raise ValueError("Evidence must belong to a designated supporting family")
            paths.append(item.path)
        if len(paths) != len(set(paths)):
            raise ValueError("Evidence paths must be unique")
        expected = (
            {
                entry.path: entry.sha256
                for entry in self.historical_archive.entries
                if entry.partition == "reference"
            }
            if self.historical_archive
            else {}
        )
        if len({i.path for i in self.historical_inputs}) != len(self.historical_inputs) or (
            {i.path: i.sha256 for i in self.historical_inputs} != expected
        ):
            raise ValueError("Historical inputs must match the explicit reference partition")
        excluded = (
            {e.sha256 for e in self.historical_archive.entries}
            if self.historical_archive
            else set()
        )
        if any(i.sha256 in excluded for i in self.evidence):
            raise ValueError(
                "Historical/evaluation content cannot be relabeled as current evidence"
            )
        if self.historical_inputs and self.issuer is None:
            raise ValueError("Historical discovery requires an explicit target issuer")
        if (
            sum(i.size_bytes for i in (*self.evidence, *self.historical_inputs, self.blank))
            > MAX_BUNDLE_BYTES
        ):
            raise ValueError("Bundle exceeds total byte limit")
        return self


def _id(value: str) -> str:
    # Identifiers become a single Blob name segment, never filesystem or URL paths.
    if (
        not value
        or len(value) > 128
        or not all(c.isascii() and (c.isalnum() or c in "-_") for c in value)
    ):
        raise BlobStorageError("Invalid storage identifier")
    return value


class PacketBlobStorage:
    def __init__(self, blobs: BlobPort) -> None:
        self.blobs = blobs

    def upload(
        self,
        root: Path,
        blank: Path,
        blank_id: str,
        evidence_set_id: str,
        *,
        historical_archive: ArchiveManifest | None = None,
        issuer: str | None = None,
    ) -> InputBundle:
        """Stage approved original inputs only; a manifest commits the immutable bundle last."""
        prefix = f"bundles/{_id(blank_id)}/{_id(evidence_set_id)}/"
        root = root.resolve(strict=True)
        blank_data = read_local_input(root, blank, Path("bd_agreements/Blank"), MAX_FILE_BYTES)
        folders = tuple(f.folder for f in default_catalog().families)
        inventory = build_inventory(root, families=folders, max_sources=100)
        combined = with_historical_sources(root, inventory, historical_archive)
        bundle = InputBundle(
            blank_id=blank_id,
            evidence_set_id=evidence_set_id,
            blank=BlobInput(
                path=blank.as_posix(),
                sha256=hashlib.sha256(blank_data).hexdigest(),
                size_bytes=len(blank_data),
            ),
            evidence=tuple(
                BlobInput(path=s.path, sha256=s.sha256, size_bytes=s.size_bytes)
                for s in inventory.sources
            ),
            issuer=issuer,
            historical_archive=historical_archive,
            historical_inputs=tuple(
                BlobInput(path=s.path, sha256=s.sha256, size_bytes=s.size_bytes)
                for s in combined.sources
                if s.family == "historical_reference"
            ),
        )
        self.blobs.put_new(INPUTS, prefix + bundle.blank.path, blank_data)
        for item in bundle.evidence:
            data = read_local_input(
                root, Path(item.path), Path("bd_agreements/supporting_data"), item.size_bytes
            )
            if hashlib.sha256(data).hexdigest() != item.sha256:
                raise BlobStorageError("Evidence changed while uploading its snapshot")
            self.blobs.put_new(INPUTS, prefix + item.path, data)
        for item in bundle.historical_inputs:
            data = read_local_input(
                root, Path(item.path), Path("bd_agreements/Completed"), item.size_bytes
            )
            if hashlib.sha256(data).hexdigest() != item.sha256:
                raise BlobStorageError("Historical evidence changed while uploading")
            self.blobs.put_new(INPUTS, prefix + item.path, data)
        self.blobs.put_new(INPUTS, prefix + "manifest.json", bundle.model_dump_json().encode())
        return bundle

    def stage(self, blank_id: str, evidence_set_id: str, root: Path) -> InputBundle:
        prefix = f"bundles/{_id(blank_id)}/{_id(evidence_set_id)}/"
        bundle = InputBundle.model_validate_json(
            self.blobs.read(INPUTS, prefix + "manifest.json", 2 * 1024 * 1024)
        )
        if (bundle.blank_id, bundle.evidence_set_id) != (blank_id, evidence_set_id):
            raise BlobStorageError("Bundle identity does not match requested input")
        resolved = root.resolve(strict=True)
        if root.is_symlink():
            raise BlobStorageError("Staging root must not be a symlink")
        for item in (bundle.blank, *bundle.evidence, *bundle.historical_inputs):
            target = resolved / item.path
            if target.resolve() != target:
                raise BlobStorageError("Staging path resolves through a symlink escape")
            data = self.blobs.read(INPUTS, prefix + item.path, item.size_bytes)
            if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
                raise BlobStorageError("Input hash does not match bundle snapshot")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as stream:
                target.chmod(0o600)
                stream.write(data)
        return bundle

    def claim(self, request_id: str, blank_id: str, evidence_set_id: str) -> None:
        payload = json.dumps(
            {"blank_id": _id(blank_id), "evidence_set_id": _id(evidence_set_id)}, sort_keys=True
        ).encode()
        if not self.blobs.put_new(REVIEWS, f"requests/{_id(request_id)}.json", payload):
            raise BlobStorageError(
                "Request already claimed; inspect its result before retrying with a new ID"
            )

    def publish(self, request_id: str, store: RunStore, manifest: RunManifest) -> dict[str, str]:
        prefix = f"runs/{_id(request_id)}/{_id(manifest.run_id)}/"
        locations = {}
        self.blobs.put_new(REVIEWS, prefix + "blank.pdf", store.read_blank(manifest.run_id))
        for artifact in manifest.artifacts:
            container = PACKETS if artifact.name == "packet.pdf" else REVIEWS
            data = store.read_artifact(manifest.run_id, artifact.name)
            self.blobs.put_new(container, prefix + artifact.name, data)
            locations[artifact.name] = f"{container}/{prefix}{artifact.name}"
        # Commit marker written last; partial uploads have no completed result record.
        self.blobs.put_new(REVIEWS, prefix + "manifest.json", manifest.model_dump_json().encode())
        self.blobs.put_new(
            REVIEWS,
            f"requests/{_id(request_id)}-result.json",
            json.dumps(
                {
                    "run_id": manifest.run_id,
                    "status": manifest.status,
                    "outcome": manifest.outcome,
                    "locations": locations,
                },
                sort_keys=True,
            ).encode(),
        )
        return locations


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage approved originals or download a Blob run.")
    parser.add_argument("--account-url", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--root", type=Path, required=True)
    stage.add_argument("--blank", type=Path, required=True)
    stage.add_argument("--blank-id", required=True)
    stage.add_argument("--evidence-set-id", required=True)
    stage.add_argument("--issuer")
    stage.add_argument("--historical-manifest", type=Path)
    download = commands.add_parser("download")
    download.add_argument("--request-id", required=True)
    download.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    account = validate_account_url(args.account_url)
    with (
        AzureCliCredential(process_timeout=10) as credential,
        BlobServiceClient(
            account, credential=credential, retry_total=0, connection_timeout=10, read_timeout=60
        ) as client,
    ):
        storage = PacketBlobStorage(AzureBlobs(client))
        if args.command == "stage":
            historical = (
                ArchiveManifest.model_validate_json(
                    read_local_input(
                        args.root.resolve(strict=True),
                        args.historical_manifest,
                        Path("outputs"),
                        2 * 1024 * 1024,
                    )
                )
                if args.historical_manifest
                else None
            )
            bundle = storage.upload(
                args.root,
                args.blank,
                args.blank_id,
                args.evidence_set_id,
                historical_archive=historical,
                issuer=args.issuer,
            )
            print(f"Staged {bundle.blank_id}, evidence set {bundle.evidence_set_id}.")
        else:
            request_id = _id(args.request_id)
            result = json.loads(
                storage.blobs.read(REVIEWS, f"requests/{request_id}-result.json", 2 * 1024 * 1024)
            )
            run_id = _id(result["run_id"])
            prefix = f"runs/{request_id}/{run_id}/"
            manifest = RunManifest.model_validate_json(
                storage.blobs.read(REVIEWS, prefix + "manifest.json", 16 * 1024 * 1024)
            )
            if manifest.run_id != run_id:
                raise BlobStorageError("Result run identity mismatch")
            output = args.output.resolve()
            output.mkdir(parents=True, exist_ok=False)
            (output / "manifest.json").write_text(manifest.model_dump_json(indent=2))
            for artifact in manifest.artifacts:
                container = PACKETS if artifact.name == "packet.pdf" else REVIEWS
                data = storage.blobs.read(container, prefix + artifact.name, artifact.size_bytes)
                if hashlib.sha256(data).hexdigest() != artifact.sha256:
                    raise BlobStorageError("Result artifact hash mismatch")
                (output / artifact.name).write_bytes(data)
            print(f"Downloaded {manifest.status}/{manifest.outcome} run to {output}")


if __name__ == "__main__":
    main()
