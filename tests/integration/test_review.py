import hashlib
import json
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.evidence import extract_evidence
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.review import ReviewError, run_review

BLANK = Path("bd_agreements/Blank/example.pdf")
REQUIREMENTS = Path("outputs/inputs/requirements.json")
PROPOSALS = Path("outputs/inputs/proposals.json")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for relative, text in [
        (BLANK, "Provide firm identifier. Signature. Signature date."),
        (Path("bd_agreements/supporting_data/identity.pdf"), "Firm identifier 001234"),
    ]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(path))
        canvas.drawString(50, 700, text)
        canvas.save()
    page = extract_evidence(tmp_path, build_inventory(tmp_path)).documents[0].pages[0]
    digest = hashlib.sha256((tmp_path / BLANK).read_bytes()).hexdigest()
    requirements = [
        {
            "requirement_id": name,
            "application_sha256": digest,
            "page": 1,
            "instruction": instruction,
            "kind": kind,
        }
        for name, instruction, kind in [
            ("firm", "Provide firm identifier.", "identifier"),
            ("missing", "Provide current contact.", "text"),
            ("signature", "Signature.", "signature"),
            ("signature-date", "Signature date.", "signature_date"),
        ]
    ]
    proposals = [
        {
            "requirement_id": "firm",
            "outcome": "proposed",
            "value": {"kind": "identifier", "value": "001234"},
            "confidence": 0.9,
            "citations": [
                {
                    "source_id": page.source_id,
                    "page": 1,
                    "start": 0,
                    "end": len(page.text),
                    "quote": page.text,
                }
            ],
        }
    ]
    (tmp_path / REQUIREMENTS).parent.mkdir(parents=True)
    (tmp_path / REQUIREMENTS).write_text(json.dumps({"requirements": requirements}))
    (tmp_path / PROPOSALS).write_text(json.dumps({"proposals": proposals}))
    return tmp_path


def change_json(root: Path, path: Path, change: object) -> None:
    (root / path).write_text(json.dumps(change))


def report(root: Path) -> dict[str, object]:
    folder = run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    return json.loads((folder / "review.json").read_text())


def test_reports_every_requirement_and_never_exposes_a_fillable_answer(root: Path) -> None:
    original = (root / BLANK).read_bytes()
    data = report(root)
    assert data["status"] == "internal_review_only_no_packet"
    assert data["counts"] == {"review_required": 1, "unanswered": 1, "deferred_to_signing": 2}
    assert len(data["items"]) == 4
    assert all(item["check"]["fill_value"] is None for item in data["items"])
    assert data["items"][0]["proposal"]["value"]["value"] == "001234"
    assert data["items"][1]["check"]["issues"] == ["missing_proposal"]
    assert data["coverage"] == "supplied_requirements_only_not_full_form"
    assert str(root) not in json.dumps(data)
    assert (root / BLANK).read_bytes() == original
    assert not list((root / "outputs").glob(".staging-*"))


@pytest.mark.parametrize("failure", ["orphan", "duplicate", "wrong_hash", "bad_page", "extra"])
def test_invalid_batch_is_explicit_failure_not_a_successful_report(
    root: Path, failure: str
) -> None:
    requirements = json.loads((root / REQUIREMENTS).read_text())
    proposals = json.loads((root / PROPOSALS).read_text())
    if failure == "orphan":
        proposals["proposals"][0]["requirement_id"] = "unknown"
    elif failure == "duplicate":
        proposals["proposals"].append(proposals["proposals"][0])
    elif failure == "wrong_hash":
        for req in requirements["requirements"]:
            req["application_sha256"] = "0" * 64
    elif failure == "bad_page":
        requirements["requirements"][0]["page"] = 2
    else:
        proposals["publish_to_issuer"] = True
    change_json(root, REQUIREMENTS, requirements)
    change_json(root, PROPOSALS, proposals)
    with pytest.raises(ReviewError):
        run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    assert not list((root / "outputs").glob("review-*"))


def test_bad_citation_rejects_one_answer_but_keeps_other_requirements(root: Path) -> None:
    data = json.loads((root / PROPOSALS).read_text())
    data["proposals"][0]["citations"][0]["source_id"] = "0" * 64
    change_json(root, PROPOSALS, data)
    result = report(root)
    assert result["counts"]["rejected"] == 1
    assert len(result["items"]) == 4


@pytest.mark.parametrize("path", [Path("../outside.json"), Path("/tmp/outside.json"), BLANK])
def test_payload_paths_are_confined_to_local_outputs(root: Path, path: Path) -> None:
    with pytest.raises(ReviewError, match="outputs"):
        run_review(root, BLANK, path, PROPOSALS)


def test_symlink_input_and_output_rejected(root: Path) -> None:
    link = root / "outputs/inputs/link.json"
    link.symlink_to(root / REQUIREMENTS)
    with pytest.raises(ReviewError, match="symlink"):
        run_review(root, BLANK, link.relative_to(root), PROPOSALS)
    source = root / BLANK
    target = root / "elsewhere.pdf"
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises(ReviewError, match="symlink"):
        run_review(root, BLANK, REQUIREMENTS, PROPOSALS)


@pytest.mark.parametrize("content", [b'{"PRIVATE SECRET":', b"\xff", b"x" * (2 * 1024 * 1024 + 1)])
def test_bad_payloads_do_not_leak_inputs(
    root: Path, content: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    (root / REQUIREMENTS).write_bytes(content)
    assert (
        main(
            [
                "review",
                "--root",
                str(root),
                "--source",
                str(BLANK),
                "--requirements",
                str(REQUIREMENTS),
                "--proposals",
                str(PROPOSALS),
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "Review command rejected" in captured.err
    assert "PRIVATE" not in captured.err
    assert captured.out == ""


def test_report_write_mutation_prevents_publication(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.write_text

    def mutate(path: Path, *args: object, **kwargs: object) -> int:
        result = original(path, *args, **kwargs)  # type: ignore[arg-type]
        if path.name == "review.json":
            (root / BLANK).write_bytes(b"changed")
        return result

    monkeypatch.setattr(Path, "write_text", mutate)
    with pytest.raises(ReviewError, match="changed"):
        run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    assert not list((root / "outputs").glob("review-*"))
    assert not list((root / "outputs").glob(".staging-*"))


def test_cli_success_prints_only_counts_and_location(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert (
        main(
            [
                "review",
                "--root",
                str(root),
                "--source",
                str(BLANK),
                "--requirements",
                str(REQUIREMENTS),
                "--proposals",
                str(PROPOSALS),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "4 requirements" in captured.out
    assert "review.json" in captured.out
    assert "001234" not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("target", [REQUIREMENTS, PROPOSALS])
def test_payload_mutation_during_publication_is_detected(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: Path,
) -> None:
    original = Path.write_text

    def mutate(path: Path, *args: object, **kwargs: object) -> int:
        result = original(path, *args, **kwargs)  # type: ignore[arg-type]
        if path.name == "review.json":
            (root / target).write_bytes(b"changed")
        return result

    monkeypatch.setattr(Path, "write_text", mutate)
    with pytest.raises(ReviewError, match="changed"):
        run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    assert not list((root / "outputs").glob("review-*"))
    assert not list((root / "outputs").glob(".staging-*"))


def test_reports_missing_and_conflicting_evidence_explanations(root: Path) -> None:
    data = {
        "proposals": [
            {
                "requirement_id": "firm",
                "outcome": "conflicting_evidence",
                "explanation": "Two current identifiers require resolution",
            },
            {
                "requirement_id": "missing",
                "outcome": "missing_evidence",
                "explanation": "No current contact evidence",
            },
        ]
    }
    change_json(root, PROPOSALS, data)
    result = report(root)
    assert result["counts"]["unanswered"] == 2
    assert result["items"][0]["proposal"]["explanation"] == data["proposals"][0]["explanation"]
    assert result["items"][1]["check"]["issues"] == ["missing_evidence"]


def test_empty_proposal_batch_marks_all_answerable_requirements_unanswered(root: Path) -> None:
    change_json(root, PROPOSALS, {"proposals": []})
    first = run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    second = run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    assert first != second
    data = json.loads((first / "review.json").read_text())
    assert data["counts"] == {"unanswered": 2, "deferred_to_signing": 2}


@pytest.mark.parametrize(
    "source",
    [
        Path("bd_agreements/Completed/x.pdf"),
        Path("/tmp/x.pdf"),
        Path("../outside.pdf"),
        Path("README.md"),
    ],
)
def test_application_is_confined_to_blank_pdf_tree(root: Path, source: Path) -> None:
    with pytest.raises(ReviewError):
        run_review(root, source, REQUIREMENTS, PROPOSALS)


def test_unreadable_application_is_not_reported_as_success(root: Path) -> None:
    (root / BLANK).write_bytes(b"PRIVATE unreadable")
    with pytest.raises(ReviewError, match="unreadable"):
        run_review(root, BLANK, REQUIREMENTS, PROPOSALS)
    assert not list((root / "outputs").glob("review-*"))
