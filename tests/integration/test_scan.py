import hashlib
import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from bd_packet_builder.contracts import ReportingPeriod
from bd_packet_builder.draft import DraftRequest, run_draft
from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.gate import validate_answers
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.scan import (
    FoundryScanReader,
    ScanEvidence,
    ScanTranscript,
    ScanVerificationError,
)
from tests.integration.test_draft import add_ocr_citation, prepare


def scan_setup(root: Path) -> tuple[Path, Path, ScanEvidence, Mock, str]:
    request, review, data = prepare(root)
    artifact = add_ocr_citation(root, request, data, "crd", subject="Example LLC")
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript(
        readable=True,
        subject="Example LLC",
        text="Firm: Example LLC\nCRD: 001234",
        reporting_period=None,
    )
    scans = ScanEvidence(
        root,
        build_inventory(root),
        reader,
        endpoint="https://synthetic.openai.azure.com/openai/v1",
        deployment="test",
    )
    return request, review, scans, reader, artifact.relative_to(root).as_posix()


def test_blind_image_cross_check_is_cached_and_can_fill_a_scalar_without_human_flags(
    tmp_path: Path,
) -> None:
    request, review_path, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    source_id = parsed.proposals.proposals[0].citations[0].source_id
    for _ in range(2):
        scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    reader.transcribe.assert_called_once()
    assert reader.transcribe.call_args.args[0].startswith(b"\x89PNG")
    assert len(scans.checks) == 1
    review = validate_answers(
        tmp_path,
        parsed,
        hashlib.sha256(request.read_bytes()).hexdigest(),
        scan_checks=tuple(scans.checks),
    )
    decision = next(d for d in review.decisions if d.requirement_id == "crd")
    assert decision.decision == "draft_verified"
    assert not decision.ocr_visual_confirmed and not decision.source_subject_confirmed
    review_path.write_text(review.model_dump_json())
    output = run_draft(tmp_path, request.relative_to(tmp_path), review_path.relative_to(tmp_path))
    result = json.loads((output / "draft.json").read_bytes())
    assert "crd" in result["written_requirements"]
    answer = next(a for a in result["answers"] if a["requirement_id"] == "crd")
    assert answer["ocr_review_method"] == "machine_cross_checked_draft_not_human_approval"
    assert "not human visual approval" in (output / "reviewer-summary.txt").read_text()


@pytest.mark.parametrize("problem", ["digit", "subject", "confidence", "period", "kind", "role"])
def test_scan_disagreements_or_unsupported_requirements_never_become_writable(
    tmp_path: Path,
    problem: str,
) -> None:
    request, _, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    proposal = parsed.proposals.proposals[0]
    requirement = parsed.requirements.requirements[0]
    source_id = proposal.citations[0].source_id
    if problem in ("digit", "subject"):
        reader.transcribe.return_value = ScanTranscript(
            readable=True,
            subject="Other LLC" if problem == "subject" else "Example LLC",
            text="Firm: Example LLC\nCRD: 1234",
            reporting_period=None,
        )
        with pytest.raises(ScanVerificationError, match="disagrees"):
            scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
        assert not scans.checks
        return
    if problem == "confidence":
        path = tmp_path / artifact
        data = json.loads(path.read_bytes())
        data["words"][1]["confidence"] = 89.99
        path.write_text(json.dumps(data))
        with pytest.raises(ScanVerificationError, match="low_word_confidence"):
            scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
        reader.transcribe.assert_not_called()
        return
    scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    if problem == "period":
        requirement = requirement.model_copy(
            update={
                "requested_period": ReportingPeriod(start=date(2026, 8, 1), end=date(2026, 8, 31)),
            }
        )
    elif problem == "kind":
        requirement = requirement.model_copy(update={"kind": "boolean"})
    elif problem == "role":
        requirement = requirement.model_copy(update={"required_signer_role": "CCO"})
    assert not scans.checks[0].supports(requirement, proposal)


def test_scan_page_budget_cannot_be_bypassed_by_rejected_transcriptions(tmp_path: Path) -> None:
    request, _, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    source_id = parsed.proposals.proposals[0].citations[0].source_id
    scans.max_pages = 0
    with pytest.raises(ScanVerificationError, match="budget_exhausted"):
        scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    reader.transcribe.assert_not_called()


def test_five_request_ceiling_includes_failed_remote_attempts(tmp_path: Path) -> None:
    request, _, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    source_id = parsed.proposals.proposals[0].citations[0].source_id
    reader.transcribe.side_effect = FoundryError("Synthetic remote timeout")
    for _ in range(5):
        with pytest.raises(FoundryError, match="timeout"):
            scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    with pytest.raises(ScanVerificationError, match="scan_verification_budget_exhausted"):
        scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    assert reader.transcribe.call_count == 5
    assert not scans.checks


def test_source_subject_case_difference_does_not_block_independent_verification(
    tmp_path: Path,
) -> None:
    request, _, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    source_id = parsed.proposals.proposals[0].citations[0].source_id
    data = json.loads((tmp_path / artifact).read_bytes())
    data["words"][2]["text"] = "EXAMPLE"
    data["text"] = "CRD: 001234\nEXAMPLE LLC"
    (tmp_path / artifact).write_text(json.dumps(data))
    citation = scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    assert citation.quote == "CRD: 001234"
    reader.transcribe.assert_called_once()
    assert scans.checks[0].agrees_with_artifact((tmp_path / artifact).read_bytes())


@pytest.mark.parametrize("problem", ["artifact_hash", "render_hash", "missing_receipt"])
def test_gate_rechecks_scan_artifact_instead_of_trusting_receipt_alone(
    tmp_path: Path,
    problem: str,
) -> None:
    request, _, scans, _, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    source_id = parsed.proposals.proposals[0].citations[0].source_id
    scans.locate(source_id, 1, "CRD: 001234", "Example LLC", artifact)
    if problem == "artifact_hash":
        path = tmp_path / artifact
        path.write_bytes(path.read_bytes() + b"\n")
    elif problem == "render_hash":
        parsed_data = json.loads(request.read_bytes())
        parsed_data["proposals"]["proposals"][0]["citations"][0]["render_sha256"] = "0" * 64
        parsed = DraftRequest.model_validate_json(json.dumps(parsed_data))
    review = validate_answers(
        tmp_path,
        parsed,
        hashlib.sha256(request.read_bytes()).hexdigest(),
        scan_checks=() if problem == "missing_receipt" else tuple(scans.checks),
    )
    decision = next(d for d in review.decisions if d.requirement_id == "crd")
    assert decision.decision == "withhold"


def test_receipt_cannot_be_replayed_for_a_different_identifier_or_claimed_period(
    tmp_path: Path,
) -> None:
    request, _, scans, _, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    proposal = parsed.proposals.proposals[0]
    requirement = parsed.requirements.requirements[0]
    scans.locate(proposal.citations[0].source_id, 1, "CRD: 001234", "Example LLC", artifact)
    receipt = scans.checks[0]
    assert proposal.value is not None
    changed_value = proposal.value.model_copy(update={"value": "1234"})
    assert not receipt.supports(requirement, proposal.model_copy(update={"value": changed_value}))
    different_period = ReportingPeriod(start=date(2026, 8, 1), end=date(2026, 8, 31))
    assert not receipt.supports(
        requirement,
        proposal.model_copy(update={"claimed_period": different_period}),
    )


@pytest.mark.parametrize("problem", ["words", "page", "confidence"])
def test_malformed_ocr_artifact_is_rejected_before_an_image_request(
    tmp_path: Path,
    problem: str,
) -> None:
    request, _, scans, reader, artifact = scan_setup(tmp_path)
    parsed = DraftRequest.model_validate_json(request.read_bytes())
    data = json.loads((tmp_path / artifact).read_bytes())
    if problem == "words":
        data["words"] = None
    elif problem == "page":
        data["page"] = True
    else:
        data["words"][0]["confidence"] = float("nan")
    (tmp_path / artifact).write_text(json.dumps(data))
    with pytest.raises(ScanVerificationError, match="scan_artifact_invalid"):
        scans.locate(
            parsed.proposals.proposals[0].citations[0].source_id,
            1,
            "CRD: 001234",
            "Example LLC",
            artifact,
        )
    reader.transcribe.assert_not_called()


def test_scan_image_reader_requires_explicit_paid_opt_in() -> None:
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1",
        deployment="test",
    )
    with pytest.raises(FoundryError, match="explicit paid-call authorization"):
        FoundryScanReader(config, allow_paid=False)


def test_image_reader_prompt_never_receives_ocr_text_quote_or_proposed_answer() -> None:
    api = Mock()
    transcript = ScanTranscript(
        readable=False,
        subject=None,
        text="",
        reporting_period=None,
    )
    api.responses.parse.return_value = Mock(
        status="completed",
        output_parsed=transcript,
        model="test",
        usage=Mock(input_tokens=100, output_tokens=20, total_tokens=120),
    )
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
    )
    reader = FoundryScanReader(config, allow_paid=True, client_factory=lambda _: api)
    reader.transcribe(b"\x89PNG\r\n\x1a\nsynthetic-image")
    arguments = api.responses.parse.call_args.kwargs
    assert "independent_page_transcription" in str(arguments["input"])
    assert "001234" not in str(arguments)
    assert arguments["store"] is False
