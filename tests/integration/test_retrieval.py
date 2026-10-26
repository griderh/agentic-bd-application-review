import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import ApplicationRequirements
from bd_packet_builder.retrieval import (
    EvidencePlan,
    SourceCatalog,
    default_catalog,
    retrieve_evidence,
)


def pdf(path: Path, pages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), invariant=True)
    for text in pages:
        canvas.drawString(50, 700, text)
        canvas.showPage()
    canvas.save()


def requirements(kind: str = "identifier", period: dict | None = None) -> ApplicationRequirements:
    return ApplicationRequirements.model_validate_json(
        json.dumps(
            {
                "requirements": [
                    {
                        "requirement_id": "crd",
                        "application_sha256": "a" * 64,
                        "page": 1,
                        "instruction": "Provide the firm's CRD number",
                        "kind": kind,
                        "requested_period": period,
                    }
                ]
            }
        )
    )


def catalog(folder: str = "FINRA_Certification", selection: str = "single") -> SourceCatalog:
    return SourceCatalog.model_validate_json(
        json.dumps(
            {
                "families": [
                    {
                        "family_id": "registration",
                        "folder": folder,
                        "purpose": "Registration identifiers and proof",
                        "selection": selection,
                        "page_hints": [1, 2],
                    }
                ]
            }
        )
    )


def plan(action: str = "fact", family: str = "registration") -> EvidencePlan:
    return EvidencePlan.model_validate_json(
        json.dumps(
            {
                "needs": [
                    {
                        "requirement_id": "crd",
                        "action": action,
                        "families": [family],
                        "search_terms": ["CRD"],
                        "explanation": "Look in registration evidence",
                    }
                ]
            }
        )
    )


def run(root: Path, **kwargs: object) -> dict:
    result = retrieve_evidence(
        root, requirements(), catalog(), kwargs.pop("evidence_plan", plan()), **kwargs
    )
    return json.loads((result / "retrieval.json").read_text())


def test_reads_only_routed_family_and_bounded_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf(
        tmp_path / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf",
        ["CRD: 001234", "Registration details", "Do not read this page"],
    )
    unrelated = tmp_path / "bd_agreements/supporting_data/Restricted"
    unrelated.mkdir()
    (unrelated / "secret.pdf").write_bytes(b"not a PDF")
    scan = os.scandir

    def restricted_scan(path: int | str | Path) -> object:
        if isinstance(path, (str, Path)) and (
            Path(path) == unrelated.parent or Path(path).is_relative_to(unrelated)
        ):
            raise AssertionError("Retrieval must not inventory the full or unrelated collection")
        return scan(path)

    monkeypatch.setattr(os, "scandir", restricted_scan)
    data = run(tmp_path)
    assert data["status"] == "targeted_evidence_review_required_no_packet"
    assert {p["page"] for p in data["pages"]} == {1, 2}
    assert all(p["source"]["family"] == "FINRA_Certification" for p in data["pages"])
    assert data["needs"][0]["action"] == "fact"
    assert data["needs"][0]["matched_pages"] == [1]
    assert "Restricted" not in json.dumps(data)
    assert data["proposals"] is None


def test_attach_only_performs_minimum_inspection_not_whole_document(tmp_path: Path) -> None:
    pdf(tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf", ["Proof"] * 10)
    data = run(tmp_path, evidence_plan=plan("attach"))
    assert len(data["pages"]) == 1
    item = data["needs"][0]
    assert "attachment_identity_period_and_adequacy_unverified" in item["issues"]
    assert item["attachment_candidate"] is not None
    assert data["proposals"] is None


def test_missing_or_ambiguous_sources_continue_with_explicit_exceptions(tmp_path: Path) -> None:
    (tmp_path / "bd_agreements/supporting_data").mkdir(parents=True)
    data = run(tmp_path)
    assert "missing_document" in data["needs"][0]["issues"]
    for name in ("one", "two"):
        pdf(
            tmp_path / f"bd_agreements/supporting_data/FINRA_Certification/{name}.pdf",
            ["CRD: 001234"],
        )
    data = run(tmp_path)
    assert "ambiguous_current_version" in data["needs"][0]["issues"]
    assert data["pages"] == []


def test_unknown_family_or_requirement_never_reads_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="family"):
        retrieve_evidence(tmp_path, requirements(), catalog(), plan(family="unapproved"))
    invalid = plan().model_copy(
        update={
            "needs": tuple(n.model_copy(update={"requirement_id": "unknown"}) for n in plan().needs)
        }
    )
    with pytest.raises(ValueError, match="requirement"):
        retrieve_evidence(tmp_path, requirements(), catalog(), invalid)


@pytest.mark.parametrize("folder", ["../Completed", "/tmp", "FINRA_Certification/../../Completed"])
def test_catalog_cannot_grant_arbitrary_paths(folder: str) -> None:
    with pytest.raises(ValidationError):
        catalog(folder)


def test_catalog_has_purposes_not_business_facts() -> None:
    data = default_catalog().model_dump(mode="json")
    assert any(f["folder"] == "FINRA_Certification" for f in data["families"])
    assert "001234" not in json.dumps(data)


def test_requested_financial_period_mismatch_is_not_used_for_answer(tmp_path: Path) -> None:
    pdf(tmp_path / "bd_agreements/supporting_data/Focus_Reports/FOCUS_2026-08.pdf", ["CRD: 001234"])
    req = requirements(period={"start": "2026-09-01", "end": "2026-09-30"})
    result = retrieve_evidence(tmp_path, req, catalog("Focus_Reports", "monthly"), plan())
    data = json.loads((result / "retrieval.json").read_text())
    assert "requested_period_unavailable" in data["needs"][0]["issues"]
    assert data["needs"][0]["answer_evidence_usable"] is False


LONG_IDENTITY = "CRD: 001234. This fictional registration record is a synthetic test source. " * 2


def model_client() -> Mock:
    from bd_packet_builder.proposals import ModelProposals

    client = Mock()

    def respond(**kwargs: object) -> Mock:
        payload = json.loads(str(kwargs["input"]))
        if "catalog" in payload:
            parsed = plan()
        else:
            evidence = payload["evidence"][0]
            quote = "CRD: 001234"
            start = evidence["text"].index(quote)
            parsed = ModelProposals.model_validate_json(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "requirement_id": "crd",
                                "outcome": "proposed",
                                "value": {"kind": "identifier", "value": "001234"},
                                "confidence": 0.9,
                                "citations": [
                                    {
                                        "source_id": evidence["source_id"],
                                        "page": evidence["page"],
                                        "start": start,
                                        "end": start + len(quote),
                                        "quote": quote,
                                    }
                                ],
                            }
                        ]
                    }
                )
            )
        return Mock(
            status="completed",
            output_parsed=parsed,
            model="controlled-test",
            usage=Mock(input_tokens=100, output_tokens=100, total_tokens=200),
        )

    client.responses.parse.side_effect = respond
    return client


def test_automatic_routing_sends_catalog_only_then_selected_evidence(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.retrieval import run_targeted_retrieval

    pdf(
        tmp_path / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf",
        [LONG_IDENTITY],
    )
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs/requirements.json").write_text(requirements().model_dump_json())
    (tmp_path / "outputs/catalog.json").write_text(catalog().model_dump_json())
    api = model_client()
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
    )
    path = run_targeted_retrieval(
        tmp_path,
        Path("outputs/requirements.json"),
        catalog_path=Path("outputs/catalog.json"),
        config=config,
        allow_paid=True,
        client_factory=lambda _: api,
    )
    data = json.loads((path / "retrieval.json").read_text())
    assert api.responses.parse.call_count == 2
    first = json.loads(api.responses.parse.call_args_list[0].kwargs["input"])
    assert "evidence" not in first and "001234" not in json.dumps(first)
    assert data["proposals"]["proposals"][0]["value"]["value"] == "001234"
    assert data["proposal_checks"][0]["status"] == "review_required"
    assert data["proposal_checks"][0]["fill_value"] is None
    assert data["routing_request"]["usage"]["total_tokens"] == 200
    assert data["answer_request"]["usage"]["total_tokens"] == 200


def test_cache_reuses_only_identical_context_and_rechecks_current_citations(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig

    source = tmp_path / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf"
    pdf(source, [LONG_IDENTITY])
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
    )
    api = model_client()
    path = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        client_factory=lambda _: api,
    )
    cache = (path / "retrieval.json").relative_to(tmp_path)
    factory = Mock()
    path2 = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        cache_path=cache,
        client_factory=factory,
    )
    factory.assert_not_called()
    second = json.loads((path2 / "retrieval.json").read_text())
    assert second["cache_status"].startswith("reused_unapproved")
    assert second["proposal_checks"][0]["resolved_citations"] == 1
    pdf(source, [LONG_IDENTITY + " New revision"])
    api2 = model_client()
    path3 = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        cache_path=cache,
        client_factory=lambda _: api2,
    )
    assert api2.responses.parse.call_count == 1
    assert json.loads((path3 / "retrieval.json").read_text())["cache_status"].startswith(
        "invalidated"
    )


def test_mutation_during_answer_request_does_not_publish(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.inventory import InventoryError

    source = tmp_path / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf"
    pdf(source, [LONG_IDENTITY])
    api = model_client()
    original = api.responses.parse.side_effect

    def mutate(**kwargs: object) -> Mock:
        reply = original(**kwargs)
        source.write_bytes(b"changed")
        return reply

    api.responses.parse.side_effect = mutate
    with pytest.raises(InventoryError, match="changed"):
        retrieve_evidence(
            tmp_path,
            requirements(),
            catalog(),
            plan(),
            config=FoundryConfig(
                endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
            ),
            allow_paid=True,
            client_factory=lambda _: api,
        )
    assert not (tmp_path / "outputs").exists()


def test_local_ocr_is_scoped_to_selected_source_and_never_promoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import bd_packet_builder.retrieval as module

    source = tmp_path / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf"
    pdf(source, ["sparse footer"])

    def fake_ocr(root: Path, path: Path, page: int, **kwargs: object) -> Path:
        assert len(kwargs["inventory"].sources) == 1
        output = root / "outputs/local-ocr"
        output.mkdir(parents=True, exist_ok=True)
        (output / "ocr.json").write_text(
            json.dumps({"text": "CRD: 001234", "render_sha256": "a" * 64})
        )
        return output

    monkeypatch.setattr(module, "run_ocr", fake_ocr)
    data = run(tmp_path, allow_ocr=True)
    assert data["pages"][0]["mode"] == "ocr"
    assert "ocr_text_unverified_not_native_citations" in data["needs"][0]["issues"]
    assert data["needs"][0]["answer_evidence_usable"] is False
    assert data["proposals"] is None


def test_native_period_mismatch_blocks_proposals_even_if_filename_matches(tmp_path: Path) -> None:
    pdf(
        tmp_path / "bd_agreements/supporting_data/Focus_Reports/FOCUS_2026-09.pdf",
        ["For the month ending August 31, 2026. " + LONG_IDENTITY],
    )
    result = retrieve_evidence(
        tmp_path, requirements(), catalog("Focus_Reports", "monthly"), plan()
    )
    data = json.loads((result / "retrieval.json").read_text())
    assert data["needs"][0]["answer_evidence_usable"] is False
    assert data["proposals"] is None


def test_signatures_cannot_be_routed_and_paid_optin_precedes_io(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig, FoundryError

    with pytest.raises(ValueError, match="Signing"):
        retrieve_evidence(tmp_path, requirements("signature"), catalog(), plan())
    with pytest.raises(FoundryError, match="allow-paid"):
        retrieve_evidence(
            tmp_path,
            requirements(),
            catalog(),
            plan(),
            config=FoundryConfig(
                endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
            ),
        )


def test_inventory_rejects_selected_symlinks_not_unrelated_folders(tmp_path: Path) -> None:
    from bd_packet_builder.inventory import InventoryError

    support = tmp_path / "bd_agreements/supporting_data"
    support.mkdir(parents=True)
    target = tmp_path / "outside"
    target.mkdir()
    (support / "FINRA_Certification").symlink_to(target, target_is_directory=True)
    with pytest.raises(InventoryError, match="symlink"):
        run(tmp_path)


def test_model_cannot_cite_an_uninspected_page_of_a_routed_source(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.retrieval import RetrievalError

    pdf(
        tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf",
        [LONG_IDENTITY] * 3,
    )
    api = model_client()
    respond = api.responses.parse.side_effect

    def unread_page(**kwargs: object) -> Mock:
        reply = respond(**kwargs)
        proposal = reply.output_parsed.proposals[0]
        citation = proposal.citations[0].model_copy(update={"page": 3})
        reply.output_parsed = reply.output_parsed.model_copy(
            update={"proposals": (proposal.model_copy(update={"citations": (citation,)}),)}
        )
        return reply

    api.responses.parse.side_effect = unread_page
    with pytest.raises(RetrievalError, match="inspected"):
        retrieve_evidence(
            tmp_path,
            requirements(),
            catalog(),
            plan(),
            config=FoundryConfig(
                endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
            ),
            allow_paid=True,
            client_factory=lambda _: api,
        )


@pytest.mark.parametrize("contents", ["{", "[]", "{}", '{"schema_version":2}'])
def test_malformed_cache_is_an_explicit_safe_error(tmp_path: Path, contents: str) -> None:
    from bd_packet_builder.retrieval import RetrievalError

    (tmp_path / "bd_agreements/supporting_data").mkdir(parents=True)
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs/cache.json").write_text(contents)
    with pytest.raises(RetrievalError, match="cache"):
        run(tmp_path, cache_path=Path("outputs/cache.json"))


def test_multi_month_request_does_not_silently_select_its_last_month(tmp_path: Path) -> None:
    pdf(
        tmp_path / "bd_agreements/supporting_data/Focus_Reports/FOCUS_2026-09.pdf",
        ["As of September 30, 2026. " + LONG_IDENTITY],
    )
    result = retrieve_evidence(
        tmp_path,
        requirements(period={"start": "2026-08-01", "end": "2026-09-30"}),
        catalog("Focus_Reports", "monthly"),
        plan(),
    )
    data = json.loads((result / "retrieval.json").read_text())
    assert not data["needs"][0]["answer_evidence_usable"]
    assert "requested_period_granularity_unresolved" in data["needs"][0]["issues"]
    assert data["pages"] == []


def test_missing_initial_terms_expands_only_to_four_pages(tmp_path: Path) -> None:
    pdf(
        tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf",
        ["Unrelated contextual notes. " * 4] * 2 + [LONG_IDENTITY] * 8,
    )
    data = run(tmp_path)
    assert [p["page"] for p in data["pages"]] == [1, 2, 3]
    assert data["needs"][0]["matched_pages"] == [3]


def test_scan_with_a_long_native_footer_does_not_masquerade_as_native_evidence(
    tmp_path: Path,
) -> None:
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    source = tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf"
    source.parent.mkdir(parents=True)
    canvas = Canvas(str(source))
    with Image.new("RGB", (612, 792), "white") as image:
        canvas.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    canvas.drawString(10, 20, "CRD footer text, not the full scanned body. " * 4)
    canvas.save()
    data = run(tmp_path)
    assert not data["needs"][0]["answer_evidence_usable"]
    assert "image_dominant_page_ocr_not_enabled" in data["needs"][0]["issues"]


def test_reporting_month_match_does_not_prove_the_requested_as_of_day(tmp_path: Path) -> None:
    pdf(
        tmp_path / "bd_agreements/supporting_data/Focus_Reports/FOCUS_2026-09.pdf",
        ["As of September 15, 2026. " + LONG_IDENTITY],
    )
    result = retrieve_evidence(
        tmp_path,
        requirements(period={"start": "2026-09-01", "end": "2026-09-30"}),
        catalog("Focus_Reports", "monthly"),
        plan(),
    )
    data = json.loads((result / "retrieval.json").read_text())
    assert not data["needs"][0]["answer_evidence_usable"]
    assert "requested_reporting_date_not_corroborated" in data["needs"][0]["issues"]


def test_cache_mutation_during_regeneration_does_not_publish(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.retrieval import RetrievalError

    pdf(tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf", [LONG_IDENTITY])
    (tmp_path / "outputs").mkdir()
    cache = tmp_path / "outputs/cache.json"
    cache.write_text(json.dumps({"schema_version": 1, "cache_key": "0" * 64, "proposals": None}))
    api = model_client()
    respond = api.responses.parse.side_effect

    def change_cache(**kwargs: object) -> Mock:
        reply = respond(**kwargs)
        cache.write_text("{}")
        return reply

    api.responses.parse.side_effect = change_cache
    with pytest.raises(RetrievalError, match="cache changed"):
        retrieve_evidence(
            tmp_path,
            requirements(),
            catalog(),
            plan(),
            config=FoundryConfig(
                endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
            ),
            allow_paid=True,
            cache_path=Path("outputs/cache.json"),
            client_factory=lambda _: api,
        )
    assert not list((tmp_path / "outputs").glob("retrieval-*"))


def test_rejected_cached_citation_is_not_reported_as_successful_reuse(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig

    pdf(tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf", [LONG_IDENTITY])
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
    )
    output = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        client_factory=lambda _: model_client(),
    )
    cache = output / "retrieval.json"
    data = json.loads(cache.read_text())
    data["proposals"]["proposals"][0]["citations"][0]["quote"] = "CRD: 999999"
    cache.write_text(json.dumps(data))
    output = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        cache_path=cache.relative_to(tmp_path),
    )
    data = json.loads((output / "retrieval.json").read_text())
    assert data["cache_status"] == "rejected_cached_proposals_after_current_citation_check"
    assert data["proposal_checks"][0]["status"] == "rejected"
    assert data["proposal_checks"][0]["fill_value"] is None


def test_inventory_source_limit_is_enforced_before_ambiguous_selection(tmp_path: Path) -> None:
    from bd_packet_builder.inventory import InventoryError

    for number in range(31):
        pdf(
            tmp_path / f"bd_agreements/supporting_data/FINRA_Certification/proof{number}.pdf",
            [LONG_IDENTITY],
        )
    with pytest.raises(InventoryError, match="source limit"):
        run(tmp_path)


def test_attachment_only_text_is_not_sent_for_answer_generation(tmp_path: Path) -> None:
    from bd_packet_builder.foundry import FoundryConfig

    pdf(tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf", [LONG_IDENTITY])
    pdf(
        tmp_path / "bd_agreements/supporting_data/SIPC_list/proof.pdf",
        ["ATTACHMENT_ONLY_SENTINEL must stay out of answer model context. " * 3],
    )
    req_data = requirements().model_dump(mode="json")
    req_data["requirements"].append(
        {
            "requirement_id": "membership",
            "application_sha256": "a" * 64,
            "page": 1,
            "instruction": "Attach SIPC proof.",
            "kind": "attachment",
        }
    )
    plan_data = plan().model_dump(mode="json")
    plan_data["needs"].append(
        {
            "requirement_id": "membership",
            "action": "attach",
            "families": ["sipc"],
            "search_terms": [],
            "explanation": "Attach membership proof",
        }
    )
    api = model_client()
    retrieve_evidence(
        tmp_path,
        ApplicationRequirements.model_validate_json(json.dumps(req_data)),
        default_catalog(),
        EvidencePlan.model_validate_json(json.dumps(plan_data)),
        config=FoundryConfig(
            endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
        ),
        allow_paid=True,
        client_factory=lambda _: api,
    )
    payload = json.loads(api.responses.parse.call_args.kwargs["input"])
    assert "ATTACHMENT_ONLY_SENTINEL" not in json.dumps(payload)
    assert set(payload["allowed_source_pages"]) == {"crd"}


@pytest.mark.parametrize("changed_context", ["application", "instruction", "deployment", "catalog"])
def test_cache_is_invalidated_when_answer_context_changes(
    tmp_path: Path, changed_context: str
) -> None:
    from bd_packet_builder.foundry import FoundryConfig

    pdf(tmp_path / "bd_agreements/supporting_data/FINRA_Certification/proof.pdf", [LONG_IDENTITY])
    config = FoundryConfig(
        endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
    )
    output = retrieve_evidence(
        tmp_path,
        requirements(),
        catalog(),
        plan(),
        config=config,
        allow_paid=True,
        client_factory=lambda _: model_client(),
    )
    req_data, cat_data = requirements().model_dump(mode="json"), catalog().model_dump(mode="json")
    if changed_context == "application":
        req_data["requirements"][0]["application_sha256"] = "b" * 64
    elif changed_context == "instruction":
        req_data["requirements"][0]["instruction"] = "CRD for this specific application"
    elif changed_context == "deployment":
        config = config.model_copy(update={"deployment": "different-model"})
    else:
        cat_data["families"][0]["purpose"] = "Registration evidence; revised authority context"
    api = model_client()
    result = retrieve_evidence(
        tmp_path,
        ApplicationRequirements.model_validate_json(json.dumps(req_data)),
        SourceCatalog.model_validate_json(json.dumps(cat_data)),
        plan(),
        config=config,
        allow_paid=True,
        cache_path=(output / "retrieval.json").relative_to(tmp_path),
        client_factory=lambda _: api,
    )
    assert api.responses.parse.call_count == 1
    data = json.loads((result / "retrieval.json").read_text())
    assert data["cache_status"] == "invalidated_source_requirement_or_context_changed"


def test_total_page_budget_continues_with_explicit_unmet_needs(tmp_path: Path) -> None:
    families = [
        ("registration", "FINRA_Certification"),
        ("sipc", "SIPC_list"),
        ("firm-overview", "Insperex_Public_Funds"),
        ("settlement", "settlement_delivery_instructions"),
    ]
    req_data, plan_data = {"requirements": []}, {"needs": []}
    for identity, folder in families:
        pdf(
            tmp_path / f"bd_agreements/supporting_data/{folder}/proof.pdf",
            ["Context only; no requested identifier is present. " * 2] * 10,
        )
        req_data["requirements"].append(
            {
                "requirement_id": identity,
                "application_sha256": "a" * 64,
                "page": 1,
                "instruction": "Provide CRD",
                "kind": "identifier",
            }
        )
        plan_data["needs"].append(
            {
                "requirement_id": identity,
                "action": "fact",
                "families": [identity],
                "search_terms": ["CRD"],
                "explanation": "Test bounded lookup",
            }
        )
    output = retrieve_evidence(
        tmp_path,
        ApplicationRequirements.model_validate_json(json.dumps(req_data)),
        default_catalog(),
        EvidencePlan.model_validate_json(json.dumps(plan_data)),
    )
    report = json.loads((output / "retrieval.json").read_text())
    assert len(report["pages"]) == 8
    assert len(report["needs"]) == 4
    assert "page_budget_exhausted" in report["needs"][2]["issues"]
    assert not report["needs"][2]["answer_evidence_usable"]
    assert not report["needs"][3]["answer_evidence_usable"]


def test_cli_offline_plan_and_malformed_json_are_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    (tmp_path / "bd_agreements/supporting_data").mkdir(parents=True)
    (tmp_path / "outputs").mkdir()
    req = tmp_path / "outputs/requirements.json"
    req.write_text(requirements().model_dump_json())
    (tmp_path / "outputs/plan.json").write_text(plan().model_dump_json())
    args = [
        "retrieve",
        "--root",
        str(tmp_path),
        "--requirements",
        "outputs/requirements.json",
        "--plan",
        "outputs/plan.json",
    ]
    assert main(args) == 0
    assert "unapproved" in capsys.readouterr().out
    req.write_text('{"PRIVATE malformed')
    assert main(args) == 1
    captured = capsys.readouterr()
    assert "Invalid" in captured.err
    assert "PRIVATE" not in captured.err


@pytest.mark.ocr
@pytest.mark.skipif(os.environ.get("BD_RUN_OCR") != "1", reason="Opt-in local OCR")
@pytest.mark.parametrize("orientation", ["portrait", "landscape", "rotated"])
def test_real_local_ocr_reads_selected_scan_without_approving_it(
    tmp_path: Path,
    orientation: str,
) -> None:
    from contextlib import closing
    from io import BytesIO

    import pypdfium2 as pdfium
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    from bd_packet_builder.foundry import FoundryConfig

    dimensions = (792, 612) if orientation == "landscape" else (612, 792)
    native = BytesIO()
    canvas = Canvas(native, pagesize=dimensions)
    canvas.setFont("Helvetica", 20)
    canvas.drawString(60, dimensions[1] - 80, "FICTIONAL REGISTRATION")
    canvas.drawString(60, dimensions[1] - 130, "CRD 001234")
    canvas.save()
    with (
        pdfium.PdfDocument(native.getvalue()) as document,
        closing(document[0]) as page,
        closing(page.render(scale=2)) as bitmap,
        bitmap.to_pil() as image,
    ):
        scanned = (
            image.transpose(Image.Transpose.ROTATE_90) if orientation == "rotated" else image.copy()
        )
    source = tmp_path / "bd_agreements/supporting_data/FINRA_Certification/scan.pdf"
    source.parent.mkdir(parents=True)
    with scanned:
        width, height = scanned.width / 2, scanned.height / 2
        canvas = Canvas(str(source), pagesize=(width, height))
        canvas.drawImage(ImageReader(scanned), 0, 0, width=width, height=height)
        canvas.save()
    if orientation == "rotated":
        staged = source.with_name("staged.pdf")
        with pdfium.PdfDocument(str(source)) as document, closing(document[0]) as page:
            page.set_rotation(90)
            document.save(str(staged))
        staged.replace(source)
    original = source.read_bytes()
    factory = Mock()
    data = run(
        tmp_path,
        allow_ocr=True,
        allow_paid=True,
        config=FoundryConfig(
            endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"
        ),
        client_factory=factory,
    )
    factory.assert_not_called()
    page_result = data["pages"][0]
    assert page_result["mode"] == "ocr"
    assert "CRD 001234" in page_result["text"]
    assert page_result["rotation"] == (90 if orientation == "rotated" else 0)
    assert len(page_result["render_sha256"]) == 64
    assert not data["needs"][0]["answer_evidence_usable"]
    assert data["proposals"] is None
    assert source.read_bytes() == original
