import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.discovery import DiscoveredPage, discover_requirements
from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.local_inputs import LocalInputError

SOURCE = Path("bd_agreements/Blank/synthetic.pdf")
CONFIG = FoundryConfig(
    endpoint="https://synthetic-resource.openai.azure.com/openai/v1", deployment="synthetic-model"
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / SOURCE
    path.parent.mkdir(parents=True)
    canvas = Canvas(str(path), invariant=True)
    for line, y in [
        ("Primary Representative", 740),
        ("Name: ______", 710),
        ("Backup Representative", 680),
        ("Name: ______", 650),
    ]:
        canvas.drawString(50, y, line)
    canvas.showPage()
    for line, y in [
        ("CHECKLIST", 740),
        ("Attach most recent financial report.", 710),
        ("Signature: ______", 680),
        ("Signature date: ______", 650),
        ("If eligible, provide three public-sector references.", 620),
    ]:
        canvas.drawString(50, y, line)
    canvas.save()
    return tmp_path


def client_for(failure: str | None = None) -> Mock:
    client = Mock()

    def parse(**kwargs: object) -> Mock:
        payload = json.loads(str(kwargs["input"]))
        page = payload["page"]
        items: list[dict[str, str | None]] = (
            [
                {"quote": "Name:", "context": "Primary Representative", "kind": "text"},
                {"quote": "Name:", "context": "Backup Representative", "kind": "text"},
            ]
            if page == 1
            else [
                {
                    "quote": "Attach most recent financial report.",
                    "context": "CHECKLIST",
                    "kind": "attachment",
                },
                {"quote": "Signature:", "context": None, "kind": "signature"},
                {"quote": "Signature date:", "context": None, "kind": "signature_date"},
                {
                    "quote": "If eligible, provide three public-sector references.",
                    "context": None,
                    "kind": "text",
                },
            ]
        )
        if page == 1:
            if failure == "invented":
                items.append(
                    {"quote": "Private fabricated question", "context": None, "kind": "text"}
                )
            elif failure == "ambiguous":
                items[0]["context"] = None
            elif failure == "context":
                items[0]["context"] = "Invented section"
            elif failure == "duplicate":
                items.append(items[0])
        elif failure == "missing":
            items.pop()
        return Mock(
            status="incomplete" if failure == "incomplete" else "completed",
            output_parsed=DiscoveredPage.model_validate_json(json.dumps({"items": items})),
            model="synthetic-model",
            usage=Mock(input_tokens=100, output_tokens=100, total_tokens=200),
        )

    client.responses.parse.side_effect = parse
    return client


def test_no_upload_without_opt_in(root: Path) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="allow-paid"):
        discover_requirements(root, SOURCE, CONFIG, allow_paid=False, client_factory=factory)
    factory.assert_not_called()
    assert not (root / "outputs").exists()


def test_discovery_anchors_repeated_fields_and_never_reads_other_documents(root: Path) -> None:
    client = client_for()
    original = (root / SOURCE).read_bytes()
    secret = root / "bd_agreements/supporting_data/private.txt"
    secret.parent.mkdir()
    secret.write_text("PRIVATE_NEVER_UPLOAD")
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client
    )
    data = json.loads((result / "discovery.json").read_text())
    assert data["status"] == "requirement_discovery_review_required_no_packet"
    assert data["request_count"] == 2
    assert len(data["findings"]) == 6
    assert len(data["requirements"]["requirements"]) == 6
    assert data["counts"] == {"anchored": 6}
    assert data["coverage"] == "native_text_only_completeness_and_meaning_unverified"
    names = data["findings"][:2]
    assert names[0]["start"] != names[1]["start"]
    assert names[0]["context"] == "Primary Representative"
    assert names[1]["context"] == "Backup Representative"
    assert data["application"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert data["usage"]["total_tokens"] == 400
    assert (root / SOURCE).read_bytes() == original
    assert data["evaluation"] is None
    assert len(data["prompt_sha256"]) == len(data["schema_sha256"]) == 64
    assert len(data["requests"]) == 2
    for call in client.responses.parse.call_args_list:
        sent = call.kwargs
        assert "PRIVATE" not in sent["input"]
        assert "expected" not in sent["input"]
        assert sent["max_output_tokens"] == 4096
        assert sent["store"] is False
        assert "tools" not in sent
    assert client.close.call_count == 2


@pytest.mark.parametrize(
    "failure,issue",
    [
        ("invented", "quote_not_found"),
        ("ambiguous", "quote_ambiguous"),
        ("context", "context_not_found"),
        ("duplicate", "duplicate_anchor"),
    ],
)
def test_unanchored_findings_are_explicit_and_not_promoted(
    root: Path, failure: str, issue: str
) -> None:
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client_for(failure)
    )
    data = json.loads((result / "discovery.json").read_text())
    assert any(f["issue"] == issue for f in data["findings"])
    assert len(data["requirements"]["requirements"]) == data["counts"]["anchored"]
    assert all(
        r["application_sha256"] == data["application"]["sha256"]
        for r in data["requirements"]["requirements"]
    )


def test_missing_questions_do_not_become_a_claim_of_complete_discovery(root: Path) -> None:
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client_for("missing")
    )
    data = json.loads((result / "discovery.json").read_text())
    assert len(data["findings"]) == 5
    assert data["evaluation"] is None
    assert "completeness" in data["coverage"]


@pytest.mark.parametrize("failure", ["incomplete", "mutation"])
def test_technical_failures_do_not_publish_partial_success(root: Path, failure: str) -> None:
    client = client_for("incomplete" if failure == "incomplete" else None)
    if failure == "mutation":
        original = client.responses.parse.side_effect

        def mutate(**kwargs: object) -> Mock:
            reply = original(**kwargs)
            (root / SOURCE).write_bytes((root / SOURCE).read_bytes() + b"\nchanged")
            return reply

        client.responses.parse.side_effect = mutate
    with pytest.raises((FoundryError, LocalInputError)):
        discover_requirements(
            root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client
        )
    assert not list((root / "outputs").glob("discovery-*"))
    assert client.responses.parse.call_count == 1


@pytest.mark.parametrize(
    "source",
    [
        Path("../outside.pdf"),
        Path("/tmp/outside.pdf"),
        Path("bd_agreements/supporting_data/private.pdf"),
    ],
)
def test_only_explicit_blank_path_is_accepted(root: Path, source: Path) -> None:
    factory = Mock()
    with pytest.raises(LocalInputError):
        discover_requirements(root, source, CONFIG, allow_paid=True, client_factory=factory)
    factory.assert_not_called()


def test_textless_page_requires_review_not_invented_requirements(root: Path) -> None:
    path = root / SOURCE
    canvas = Canvas(str(path))
    canvas.rect(40, 40, 200, 200)
    canvas.save()
    factory = Mock()
    result = discover_requirements(root, SOURCE, CONFIG, allow_paid=True, client_factory=factory)
    data = json.loads((result / "discovery.json").read_text())
    assert data["request_count"] == 0
    assert data["page_issues"] == [{"page": 1, "issue": "no_native_text"}]
    assert data["requirements"] is None
    factory.assert_not_called()


def test_output_symlink_rejected_before_remote_access(root: Path) -> None:
    outside = root / "elsewhere"
    outside.mkdir()
    (root / "outputs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FoundryError, match="symlink"):
        discover_requirements(root, SOURCE, CONFIG, allow_paid=True, client_factory=Mock())
    assert not list(outside.iterdir())


def test_independent_checklist_is_evaluated_locally_not_sent(root: Path) -> None:
    path = root / "outputs/inputs/checklist.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "application_sha256": hashlib.sha256((root / SOURCE).read_bytes()).hexdigest(),
                "anchors": [
                    {
                        "anchor_id": "EXPECTED_PRIVATE_PRIMARY",
                        "page": 1,
                        "quote": "Name:",
                        "context": "Primary Representative",
                    },
                    {
                        "anchor_id": "EXPECTED_PRIVATE_REFERENCES",
                        "page": 2,
                        "quote": "If eligible, provide three public-sector references.",
                    },
                ],
            }
        )
    )
    client = client_for("missing")
    result = discover_requirements(
        root,
        SOURCE,
        CONFIG,
        allow_paid=True,
        checklist_path=path.relative_to(root),
        client_factory=lambda _: client,
    )
    data = json.loads((result / "discovery.json").read_text())
    assert data["evaluation"]["covered"] == 1
    assert data["evaluation"]["total"] == 2
    assert data["evaluation"]["matches"]["EXPECTED_PRIVATE_REFERENCES"] == []
    assert all(
        "EXPECTED_PRIVATE" not in c.kwargs["input"] for c in client.responses.parse.call_args_list
    )
    assert data["checklist_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", ["wrong-version", "invented-quote", "duplicate-id"])
def test_invalid_checklists_fail_before_spending(root: Path, problem: str) -> None:
    path = root / "outputs/checklist.json"
    path.parent.mkdir()
    anchor = {"anchor_id": "test", "page": 1, "quote": "Name:"}
    data = {
        "application_sha256": hashlib.sha256((root / SOURCE).read_bytes()).hexdigest(),
        "anchors": [anchor],
    }
    if problem == "wrong-version":
        data["application_sha256"] = "0" * 64
    elif problem == "invented-quote":
        anchor["quote"] = "invented"
    else:
        data["anchors"].append(anchor)
    path.write_text(json.dumps(data))
    factory = Mock()
    with pytest.raises(FoundryError):
        discover_requirements(
            root,
            SOURCE,
            CONFIG,
            allow_paid=True,
            checklist_path=path.relative_to(root),
            client_factory=factory,
        )
    factory.assert_not_called()


def test_repeated_label_cannot_be_borrowed_from_a_later_section(root: Path) -> None:
    path = root / SOURCE
    canvas = Canvas(str(path))
    for text, y in [
        ("Primary Representative", 740),
        ("No name supplied", 710),
        ("Backup Representative", 680),
        ("Name: ____", 650),
    ]:
        canvas.drawString(50, y, text)
    canvas.save()
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client_for()
    )
    data = json.loads((result / "discovery.json").read_text())
    assert data["findings"][0]["issue"] == "quote_not_found"
    assert data["findings"][1]["issue"] is None


@pytest.mark.parametrize("different_kind", [True, False])
def test_same_statement_can_require_attestation_and_initials_but_not_duplicate_actions(
    root: Path,
    different_kind: bool,
) -> None:
    client = client_for()
    original = client.responses.parse.side_effect

    def parse(**kwargs: object) -> Mock:
        reply = original(**kwargs)
        if json.loads(str(kwargs["input"]))["page"] == 2:
            items = [i.model_dump(mode="json") for i in reply.output_parsed.items]
            items.append({**items[1], "kind": "boolean" if different_kind else "signature"})
            reply.output_parsed = DiscoveredPage.model_validate_json(json.dumps({"items": items}))
        return reply

    client.responses.parse.side_effect = parse
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client
    )
    findings = json.loads((result / "discovery.json").read_text())["findings"]
    assert findings[-1]["issue"] == (None if different_kind else "duplicate_anchor")


def test_repeated_quote_with_only_broad_context_is_still_ambiguous(root: Path) -> None:
    canvas = Canvas(str(root / SOURCE))
    for text, y in [
        ("Primary Representative", 740),
        ("Name: ___", 710),
        ("Name: ___", 680),
        ("Backup Representative", 650),
        ("Name: ___", 620),
    ]:
        canvas.drawString(50, y, text)
    canvas.save()
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client_for()
    )
    findings = json.loads((result / "discovery.json").read_text())["findings"]
    assert findings[0]["issue"] == "quote_ambiguous"


def test_page_limit_fails_before_any_requests(root: Path) -> None:
    canvas = Canvas(str(root / SOURCE))
    for number in range(6):
        canvas.drawString(50, 740, f"Synthetic question {number}")
        canvas.showPage()
    canvas.save()
    factory = Mock()
    with pytest.raises(FoundryError, match="1-5"):
        discover_requirements(root, SOURCE, CONFIG, allow_paid=True, client_factory=factory)
    factory.assert_not_called()


def test_model_cannot_assign_units_to_a_financial_question_by_guessing(root: Path) -> None:
    client = client_for()
    original = client.responses.parse.side_effect

    def parse(**kwargs: object) -> Mock:
        reply = original(**kwargs)
        items = [i.model_dump(mode="json") for i in reply.output_parsed.items]
        items[0]["kind"] = "money"
        reply.output_parsed = DiscoveredPage.model_validate_json(json.dumps({"items": items}))
        return reply

    client.responses.parse.side_effect = parse
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client
    )
    data = json.loads((result / "discovery.json").read_text())
    assert data["findings"][0]["issue"] == "financial_units_and_period_need_interpretation"
    assert all(r["kind"] != "money" for r in data["requirements"]["requirements"])


def test_choice_findings_preserve_options_but_wait_for_layout_validation(root: Path) -> None:
    client = client_for()
    original = client.responses.parse.side_effect

    def parse(**kwargs: object) -> Mock:
        reply = original(**kwargs)
        items = [i.model_dump(mode="json") for i in reply.output_parsed.items]
        items[0]["kind"] = "single_select"
        items[0]["choices"] = {
            "options": [
                {"option_id": "one", "label": "One", "instruction": "One"},
                {"option_id": "other", "label": "Other", "instruction": "Other", "write_in": True},
            ]
        }
        reply.output_parsed = DiscoveredPage.model_validate_json(json.dumps({"items": items}))
        return reply

    client.responses.parse.side_effect = parse
    result = discover_requirements(
        root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client
    )
    data = json.loads((result / "discovery.json").read_text())
    assert data["findings"][0]["choices"]["options"][1]["write_in"] is True
    assert data["findings"][0]["issue"] == "choice_options_and_layout_need_interpretation"
    assert all(r["kind"] != "single_select" for r in data["requirements"]["requirements"])


def test_cli_requires_opt_in_for_selected_real_blank(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert (
        main(
            [
                "discover",
                "--root",
                str(root),
                "--source",
                str(SOURCE),
                "--endpoint",
                CONFIG.endpoint,
                "--deployment",
                CONFIG.deployment,
            ]
        )
        == 1
    )
    assert "allow-paid" in capsys.readouterr().err


def test_publication_failure_is_not_reported_as_discovery_success(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bd_packet_builder import discovery

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(discovery, "publish_json_run", fail)
    with pytest.raises(OSError):
        discover_requirements(
            root, SOURCE, CONFIG, allow_paid=True, client_factory=lambda _: client_for()
        )
    assert not list((root / "outputs").glob("discovery-*"))
