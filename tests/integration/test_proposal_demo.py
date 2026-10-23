import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.inventory import InventoryError
from bd_packet_builder.proposals import ModelProposals
from examples.proposal_demo import create_demo

CONFIG = FoundryConfig(
    endpoint="https://synthetic-resource.openai.azure.com/openai/v1", deployment="synthetic-model"
)


def model_client(*, failure: str | None = None) -> Mock:
    client = Mock()

    def parse(**kwargs: object) -> Mock:
        data = json.loads(str(kwargs["input"]))
        pages = data["evidence"]
        proposals = []
        outcomes = {
            "tax-id": "missing_evidence",
            "phone": "conflicting_evidence",
            "current-capital": "missing_evidence",
            "cco": "unresolved_signer",
            "disclosure": "missing_evidence",
            "signature": "deferred_to_signing",
            "signature-date": "deferred_to_signing",
        }
        for req in data["requirements"]["requirements"]:
            key = req["requirement_id"]
            proposal = {
                "requirement_id": key,
                "outcome": outcomes.get(key, "proposed"),
                "value": None,
                "citations": [],
                "claimed_period": None,
                "confidence": None,
                "explanation": "Synthetic controlled response.",
            }
            if key == "current-capital":
                proposal["explanation"] = "September 2026 requested; only July 2026 supplied."
            expected = {
                "legal-name": (
                    "Legal name: Example Demonstration LLC",
                    "Example Demonstration LLC",
                ),
                "crd": ("Firm CRD: 001234", "001234"),
                "category": (
                    "Eligibility category: Regional dealer.",
                    {"kind": "single_select", "selected": ["regional"], "write_ins": []},
                ),
                "products": (
                    "Products offered: Treasury Bills; Synthetic Notes.",
                    {
                        "kind": "multi_select",
                        "selected": ["bills", "other"],
                        "write_ins": [{"option_id": "other", "text": "Synthetic Notes"}],
                    },
                ),
                "description": (
                    "The fictional firm specializes in public-sector fixed-income services.",
                    "The fictional firm specializes in public-sector fixed-income services.",
                ),
            }
            if key in expected:
                quote, value = expected[key]
                page = next(p for p in pages if quote in p["text"])
                start = page["text"].index(quote)
                proposal.update(
                    value=value
                    if isinstance(value, dict)
                    else {"kind": req["kind"], "value": value},
                    confidence=0.9,
                    citations=[
                        {
                            "source_id": page["source_id"],
                            "page": page["page"],
                            "start": start,
                            "end": start + len(quote),
                            "quote": quote,
                        }
                    ],
                )
            proposals.append(proposal)
        if failure == "wrong-value":
            proposals[0]["value"]["value"] = "Invented Name LLC"
        elif failure == "wrong-quote":
            proposals[0]["citations"][0]["source_id"] = "0" * 64
        elif failure == "missing":
            proposals.pop()
        elif failure == "unknown":
            proposals[0]["requirement_id"] = "unknown"
        elif failure == "duplicate":
            proposals.append(proposals[0])
        elif failure == "incomplete-explanation":
            capital = next(p for p in proposals if p["requirement_id"] == "current-capital")
            capital["explanation"] = "No matching evidence."
        elif failure == "period":
            capital = next(p for p in proposals if p["requirement_id"] == "current-capital")
            page = next(p for p in pages if "Net capital" in p["text"])
            capital.update(
                outcome="proposed",
                value={"kind": "money", "amount": "1250000", "unit": "USD"},
                confidence=0.9,
                claimed_period={"start": "2026-07-01", "end": "2026-07-31"},
                citations=[
                    {
                        "source_id": page["source_id"],
                        "page": 1,
                        "start": 0,
                        "end": len(page["text"]),
                        "quote": page["text"],
                    }
                ],
            )
        elif failure == "signing":
            proposals[-1].update(
                outcome="proposed",
                value={"kind": "date", "value": "2026-10-23"},
                confidence=0.9,
                citations=proposals[0]["citations"],
            )
        elif failure == "malformed":
            proposals[0]["value"] = {"kind": "identifier", "value": 1234}
        parsed = ModelProposals.model_validate_json(json.dumps({"proposals": proposals}))
        return Mock(
            status="completed",
            output_parsed=parsed,
            model="synthetic-model",
            usage=Mock(input_tokens=1000, output_tokens=1000, total_tokens=2000),
        )

    client.responses.parse.side_effect = parse
    return client


def test_explicit_paid_opt_in_before_generating_documents(tmp_path: Path) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="allow-paid"):
        create_demo(tmp_path, CONFIG, allow_paid=False, client_factory=factory)
    factory.assert_not_called()
    assert not (tmp_path / "outputs").exists()


def test_generated_pdfs_model_proposals_and_existing_checks_are_wired(tmp_path: Path) -> None:
    client = model_client()
    sentinel = tmp_path / "bd_agreements/supporting_data/PRIVATE.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("PRIVATE_BUSINESS_DATA")
    result = create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=lambda _: client)
    data = json.loads(result.read_text())
    assert data["status"] == "synthetic_proposals_passed_no_packet"
    assert data["evaluation"]["passed"] == data["evaluation"]["total"] == 9
    assert len(data["items"]) == 9
    assert all(item["check"]["fill_value"] is None for item in data["items"])
    assert data["items"][0]["check"]["status"] == "review_required"
    assert data["items"][0]["check"]["resolved_citations"] == 1
    assert data["items"][-1]["check"]["status"] == "deferred_to_signing"
    assert data["coverage"] == "predefined_requirements_not_form_discovery"
    assert len(data["prompt_sha256"]) == len(data["schema_sha256"]) == 64
    client.responses.parse.assert_called_once()
    sent = client.responses.parse.call_args.kwargs
    assert sent["store"] is False
    assert sent["max_output_tokens"] == 4096
    assert "expected" not in sent["input"]
    assert "PRIVATE" not in sent["input"]
    assert "bd_agreements/Completed" not in sent["input"]
    client.close.assert_called_once()
    pdfs = list(result.parents[3].rglob("*.pdf"))
    assert len(pdfs) == 4
    assert all(p.read_bytes().startswith(b"%PDF-") for p in pdfs)
    application = result.parents[2] / data["application"]["path"]
    assert hashlib.sha256(application.read_bytes()).hexdigest() == data["application"]["sha256"]
    assert sentinel.read_text() == "PRIVATE_BUSINESS_DATA"
    assert not list((tmp_path / "outputs").glob(".proposal-demo-*"))
    assert not list((tmp_path / "outputs").rglob("*.xlsx"))


def test_structured_responses_use_existing_model_and_review_boundaries(tmp_path: Path) -> None:
    client = model_client()
    result = create_demo(
        tmp_path, CONFIG, allow_paid=True, include_structured=True, client_factory=lambda _: client
    )
    data = json.loads(result.read_text())
    assert data["evaluation"]["passed"] == data["evaluation"]["total"] == 12
    assert all(i["check"]["fill_value"] is None for i in data["items"])
    reqs = json.loads(client.responses.parse.call_args.kwargs["input"])["requirements"][
        "requirements"
    ]
    assert reqs[-2]["kind"] == "multi_select"
    assert reqs[-2]["choices"]["options"][-1]["write_in"] is True


@pytest.mark.parametrize(
    "failure",
    ["wrong-value", "wrong-quote", "missing", "period", "signing", "incomplete-explanation"],
)
def test_bad_behavior_is_published_as_failed_not_approved(tmp_path: Path, failure: str) -> None:
    result = create_demo(
        tmp_path, CONFIG, allow_paid=True, client_factory=lambda _: model_client(failure=failure)
    )
    data = json.loads(result.read_text())
    assert data["status"] == "synthetic_proposals_failed_no_packet"
    assert data["evaluation"]["passed"] < data["evaluation"]["total"] == 9
    assert all(item["check"]["fill_value"] is None for item in data["items"])
    if failure == "period":
        item = next(
            i for i in data["items"] if i["requirement"]["requirement_id"] == "current-capital"
        )
        assert "requested_period_mismatch" in item["check"]["issues"]


@pytest.mark.parametrize("failure", ["unknown", "malformed", "duplicate"])
def test_invalid_model_contract_never_publishes_success_or_leaves_partial_run(
    tmp_path: Path,
    failure: str,
) -> None:
    with pytest.raises(FoundryError):
        create_demo(
            tmp_path,
            CONFIG,
            allow_paid=True,
            client_factory=lambda _: model_client(failure=failure),
        )
    assert list((tmp_path / "outputs").iterdir()) == []


def test_output_symlink_rejected_before_model_or_writes(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (tmp_path / "outputs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FoundryError, match="symlink"):
        create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=Mock())
    assert not list(outside.iterdir())


def test_source_mutation_during_request_fails_without_partial_publication(tmp_path: Path) -> None:
    client = model_client()
    parse = client.responses.parse.side_effect

    def mutate(**kwargs: object) -> Mock:
        result = parse(**kwargs)
        source = next(
            (tmp_path / "outputs").glob(
                ".proposal-demo-*/synthetic-root/bd_agreements/supporting_data/identity.pdf"
            )
        )
        source.write_bytes(source.read_bytes() + b"\nchanged")
        return result

    client.responses.parse.side_effect = mutate
    with pytest.raises(InventoryError, match="changed"):
        create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=lambda _: client)
    client.close.assert_called_once()
    assert list((tmp_path / "outputs").iterdir()) == []


def test_repeated_runs_do_not_overwrite_and_generated_inputs_are_stable(tmp_path: Path) -> None:
    first = create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=lambda _: model_client())
    first_bytes = first.read_bytes()
    second = create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=lambda _: model_client())
    assert first != second
    assert first.read_bytes() == first_bytes
    a, b = json.loads(first_bytes), json.loads(second.read_text())
    assert a["application"]["sha256"] == b["application"]["sha256"]
    assert a["input_sha256"] == b["input_sha256"]
    assert a["sources"] == b["sources"]


def test_unreadable_evidence_is_not_silently_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from examples import proposal_demo

    original = proposal_demo._pdf

    def write_pdf(path: Path, lines: tuple[str, ...]) -> None:
        original(path, lines)
        if path.name == "identity.pdf":
            path.write_bytes(b"not a PDF")

    monkeypatch.setattr(proposal_demo, "_pdf", write_pdf)
    client = Mock()
    with pytest.raises(FoundryError, match="readable"):
        create_demo(tmp_path, CONFIG, allow_paid=True, client_factory=client)
    client.assert_not_called()
    assert list((tmp_path / "outputs").iterdir()) == []
