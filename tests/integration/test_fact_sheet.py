import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.evidence import extract_evidence
from bd_packet_builder.fact_sheet import FactSheet, FactSheetError, run_fact_sheet_check
from bd_packet_builder.inventory import InventoryError, build_inventory

DRAFT = Path("outputs/fact-sheets/draft.json")
AS_OF = date(2026, 10, 21)


@pytest.fixture
def example(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    path = tmp_path / "bd_agreements/supporting_data/synthetic-identity.pdf"
    path.parent.mkdir(parents=True)
    canvas = Canvas(str(path))
    canvas.drawString(50, 740, "Synthetic Example LLC; CRD 001234; CCO: Alex Example")
    canvas.save()
    page = extract_evidence(tmp_path, build_inventory(tmp_path)).documents[0].pages[0]
    citation = {
        "source_id": page.source_id,
        "page": 1,
        "start": 0,
        "end": len(page.text),
        "quote": page.text,
    }
    common = {
        "owner": "Synthetic Compliance Steward",
        "reviewed_by": "Synthetic Reviewer",
        "reviewed_on": "2026-10-01",
        "review_due": "2027-01-01",
        "effective_from": "2026-01-01",
        "citations": [citation],
    }
    data = {
        "schema_version": 1,
        "version_id": "synthetic-draft-001",
        "steward": "Synthetic Steward",
        "facts": [
            {
                **common,
                "fact_id": "firm-id-1",
                "key": "firm.crd",
                "category": "firm_identity",
                "value": {"kind": "identifier", "value": "001234"},
            },
            {
                **common,
                "fact_id": "cco-1",
                "key": "signer_roles.cco",
                "category": "signer_role",
                "role": "Chief Compliance Officer",
                "value": {"kind": "text", "value": "Alex Example"},
            },
        ],
    }
    (tmp_path / DRAFT).parent.mkdir(parents=True)
    (tmp_path / DRAFT).write_text(json.dumps(data))
    return tmp_path, data


def save(root: Path, data: dict[str, object]) -> None:
    (root / DRAFT).write_text(json.dumps(data))


def run(root: Path) -> dict[str, object]:
    folder = run_fact_sheet_check(root, DRAFT, as_of=AS_OF)
    return json.loads((folder / "fact-sheet-check.json").read_text())


def test_current_draft_resolves_evidence_without_becoming_approved(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    before = (root / DRAFT).read_bytes()
    result = run(root)
    assert result["status"] == "draft_validation_only_not_approved"
    assert result["as_of"] == "2026-10-21"
    assert result["facts_with_exceptions"] == 0
    assert len(result["items"]) == 2
    assert result["items"][0]["fact"]["value"]["value"] == "001234"
    assert result["items"][1]["fact"]["role"] == "Chief Compliance Officer"
    assert all(not item["check"]["usable_for_filling"] for item in result["items"])
    assert "approval_not_verified" in result["flags"]
    assert "semantic_support_unverified" in result["flags"]
    assert all(item["check"]["resolved_citations"] == 1 for item in result["items"])
    assert (root / DRAFT).read_bytes() == before
    assert str(root) not in json.dumps(result)
    assert result["version_id"] == data["version_id"]


@pytest.mark.parametrize(
    "change",
    [
        {"owner": ""},
        {"reviewed_by": " "},
        {"effective_from": "01/01/26"},
        {"review_due": "2026-09-30"},
        {"effective_to": "2025-12-31"},
        {"approved": True},
        {"value": {"kind": "identifier", "value": 1234}},
        {"value": {"kind": "money", "amount": "1.00", "unit": "USD"}},
        {"category": "signature"},
        {"key": "firm.Signature"},
    ],
)
def test_malformed_or_out_of_scope_facts_are_rejected(
    example: tuple[Path, dict[str, object]],
    change: dict[str, object],
) -> None:
    _, data = example
    data["facts"][0].update(change)
    with pytest.raises(ValidationError):
        FactSheet.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "change", [{"role": None}, {"value": {"kind": "identifier", "value": "001"}}]
)
def test_signer_assignment_needs_explicit_role_and_person_name(
    example: tuple[Path, dict[str, object]],
    change: dict[str, object],
) -> None:
    _, data = example
    data["facts"][1].update(change)
    with pytest.raises(ValidationError):
        FactSheet.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("field", ["approved", "approver", "released_at"])
def test_file_cannot_self_approve(example: tuple[Path, dict[str, object]], field: str) -> None:
    _, data = example
    data[field] = True
    with pytest.raises(ValidationError):
        FactSheet.model_validate_json(json.dumps(data))


def test_duplicate_fact_ids_rejected(example: tuple[Path, dict[str, object]]) -> None:
    _, data = example
    data["facts"][1]["fact_id"] = data["facts"][0]["fact_id"]
    with pytest.raises(ValidationError):
        FactSheet.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    ("change", "issue"),
    [
        ({"review_due": "2026-10-20"}, "review_overdue"),
        ({"reviewed_on": "2026-11-01"}, "future_review_date"),
        ({"effective_from": "2026-11-01"}, "not_yet_effective"),
        ({"effective_to": "2026-10-20"}, "no_longer_effective"),
        ({"citations": []}, "missing_evidence"),
    ],
)
def test_date_and_missing_evidence_exceptions_do_not_lose_supported_facts(
    example: tuple[Path, dict[str, object]],
    change: dict[str, object],
    issue: str,
) -> None:
    root, data = example
    data["facts"][0].update(change)
    save(root, data)
    result = run(root)
    assert issue in result["items"][0]["check"]["issues"]
    assert result["items"][1]["check"]["issues"] == []
    assert result["facts_with_exceptions"] == 1


def test_review_due_and_effective_end_are_inclusive(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0].update({"review_due": "2026-10-21", "effective_to": "2026-10-21"})
    save(root, data)
    assert run(root)["facts_with_exceptions"] == 0


def test_review_schedule_cannot_silently_exceed_the_scopes_annual_review(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0]["review_due"] = "2027-10-02"
    save(root, data)
    assert "review_interval_exceeds_annual" in run(root)["items"][0]["check"]["issues"]
    data["facts"][0]["review_due"] = "2027-10-01"
    save(root, data)
    assert run(root)["items"][0]["check"]["issues"] == []


def test_leap_day_review_uses_february_28_as_the_next_annual_deadline(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0].update({"reviewed_on": "2024-02-29", "review_due": "2025-03-01"})
    save(root, data)
    result = run(root)
    assert "review_interval_exceeds_annual" in result["items"][0]["check"]["issues"]


@pytest.mark.parametrize("same_value", [False, True])
def test_overlapping_key_versions_are_never_silently_selected(
    example: tuple[Path, dict[str, object]],
    same_value: bool,
) -> None:
    root, data = example
    other = {**data["facts"][0], "fact_id": "firm-id-2"}
    if not same_value:
        other["value"] = {"kind": "identifier", "value": "009999"}
    data["facts"].append(other)
    save(root, data)
    result = run(root)
    issue = "overlapping_duplicate_fact" if same_value else "conflicting_fact"
    assert issue in result["items"][0]["check"]["issues"]
    assert issue in result["items"][2]["check"]["issues"]
    assert result["items"][1]["check"]["issues"] == []


def test_nonoverlapping_versions_are_allowed_and_history_is_not_current(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0]["effective_from"] = "2026-07-01"
    prior = {
        **data["facts"][0],
        "fact_id": "firm-id-old",
        "effective_from": "2026-01-01",
        "effective_to": "2026-06-30",
    }
    data["facts"].append(prior)
    save(root, data)
    result = run(root)
    assert result["items"][0]["check"]["issues"] == []
    assert result["items"][2]["check"]["issues"] == ["no_longer_effective"]


@pytest.mark.parametrize("mode", ["unknown", "wrong_page", "quote"])
def test_fabricated_or_altered_citations_are_explicit(
    example: tuple[Path, dict[str, object]],
    mode: str,
) -> None:
    root, data = example
    citation = data["facts"][0]["citations"][0]
    if mode == "unknown":
        citation["source_id"] = "0" * 64
    elif mode == "wrong_page":
        citation["page"] = 999
    else:
        citation["quote"] = "X" * len(citation["quote"])
    save(root, data)
    result = run(root)
    expected = "citation_quote_mismatch" if mode == "quote" else "citation_unresolved"
    assert expected in result["items"][0]["check"]["issues"]


@pytest.mark.parametrize(
    "path",
    [
        Path("../draft.json"),
        Path("/tmp/draft.json"),
        Path("bd_agreements/supporting_data/draft.json"),
    ],
)
def test_input_is_confined_to_outputs(example: tuple[Path, dict[str, object]], path: Path) -> None:
    root, _ = example
    with pytest.raises(FactSheetError, match="outputs"):
        run_fact_sheet_check(root, path, as_of=AS_OF)


def test_symlink_draft_rejected(example: tuple[Path, dict[str, object]]) -> None:
    root, _ = example
    link = root / "outputs/link.json"
    link.symlink_to(root / DRAFT)
    with pytest.raises(FactSheetError, match="symlink"):
        run_fact_sheet_check(root, link.relative_to(root), as_of=AS_OF)


def test_draft_mutation_during_publication_cleans_staging(
    example: tuple[Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = example
    original = Path.write_text

    def mutate(path: Path, *args: object, **kwargs: object) -> int:
        result = original(path, *args, **kwargs)  # type: ignore[arg-type]
        if path.name == "fact-sheet-check.json":
            (root / DRAFT).write_bytes(b"changed")
        return result

    monkeypatch.setattr(Path, "write_text", mutate)
    with pytest.raises(FactSheetError, match="changed"):
        run_fact_sheet_check(root, DRAFT, as_of=AS_OF)
    assert not list((root / "outputs").glob("fact-sheet-check-*"))
    assert not list((root / "outputs").glob(".staging-*"))


def test_source_mutation_is_not_hidden_as_review_exception(
    example: tuple[Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = example
    inventory = build_inventory(root)
    (root / inventory.sources[0].path).write_bytes(b"changed")
    monkeypatch.setattr("bd_packet_builder.fact_sheet.build_inventory", lambda _: inventory)
    with pytest.raises(InventoryError, match="changed"):
        run_fact_sheet_check(root, DRAFT, as_of=AS_OF)


def test_cli_prints_counts_not_confidential_data(
    example: tuple[Path, dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    root, _ = example
    assert (
        main(
            [
                "fact-sheet-check",
                "--root",
                str(root),
                "--source",
                str(DRAFT),
                "--as-of",
                "2026-10-21",
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    assert "2 facts" in output.out
    assert "fact-sheet-check.json" in output.out
    assert "Alex Example" not in output.out + output.err
    assert output.err == ""


@pytest.mark.parametrize("content", [b'{"PRIVATE":', b"\xff", b"x" * (2 * 1024 * 1024 + 1)])
def test_cli_schema_errors_are_safe(
    example: tuple[Path, dict[str, object]],
    content: bytes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    root, _ = example
    (root / DRAFT).write_bytes(content)
    assert (
        main(
            [
                "fact-sheet-check",
                "--root",
                str(root),
                "--source",
                str(DRAFT),
                "--as-of",
                "2026-10-21",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "PRIVATE" not in output.err
    assert "rejected" in output.err
    assert output.out == ""


def test_readme_demo_creates_its_own_synthetic_inputs_and_validation_report(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[2] / "examples/fact_sheet_demo.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Synthetic-only" in result.stdout
    reports = list(
        (tmp_path / "outputs").glob(
            "fact-sheet-demo-*/synthetic-root/outputs/fact-sheet-check-*/fact-sheet-check.json"
        )
    )
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert len(data["items"]) == 3
    assert data["facts_with_exceptions"] == 1
    assert data["items"][2]["check"]["issues"] == ["review_overdue"]
    assert data["items"][0]["fact"]["value"]["value"] == "Example Demonstration LLC"
    assert data["items"][1]["fact"]["value"]["value"] == "001234"
    assert not list((tmp_path / "outputs").glob(".fact-sheet-demo-*"))


@pytest.mark.parametrize("as_of", ["20261021", "2026-W43-3", "10/21/2026", "bad"])
def test_cli_rejects_ambiguous_or_compact_as_of_dates(
    example: tuple[Path, dict[str, object]],
    as_of: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    root, _ = example
    assert (
        main(["fact-sheet-check", "--root", str(root), "--source", str(DRAFT), "--as-of", as_of])
        == 1
    )
    assert "YYYY-MM-DD" in capsys.readouterr().err
    assert not list((root / "outputs").glob("fact-sheet-check-*"))


def test_fact_value_is_not_verified_merely_because_citation_resolves(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0]["value"] = {"kind": "identifier", "value": "009999"}
    save(root, data)
    result = run(root)
    assert "semantic_support_unverified" in result["flags"]
    assert result["items"][0]["check"]["usable_for_filling"] is False


def test_named_draft_version_and_supersession_hash_are_not_verified_release_history(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["supersedes_sha256"] = "0" * 64
    save(root, data)
    first = run_fact_sheet_check(root, DRAFT, as_of=AS_OF)
    second = run_fact_sheet_check(root, DRAFT, as_of=AS_OF)
    assert first != second
    report = json.loads((first / "fact-sheet-check.json").read_text())
    assert report["supersedes_sha256"] == "0" * 64
    assert report["status"] == "draft_validation_only_not_approved"


def test_technical_write_failure_cleans_staging(
    example: tuple[Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = example

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(OSError, match="disk failure"):
        run_fact_sheet_check(root, DRAFT, as_of=AS_OF)
    assert not list((root / "outputs").glob("fact-sheet-check-*"))
    assert not list((root / "outputs").glob(".staging-*"))


def test_overlapping_interval_endpoints_are_conflicting(
    example: tuple[Path, dict[str, object]],
) -> None:
    root, data = example
    data["facts"][0]["effective_to"] = "2026-07-01"
    data["facts"].append(
        {
            **data["facts"][0],
            "fact_id": "new-id",
            "effective_from": "2026-07-01",
            "effective_to": None,
            "value": {"kind": "identifier", "value": "009999"},
        }
    )
    save(root, data)
    result = run(root)
    assert "conflicting_fact" in result["items"][0]["check"]["issues"]
    assert "conflicting_fact" in result["items"][2]["check"]["issues"]
