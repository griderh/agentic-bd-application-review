import hashlib
import json
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.history import HistoryError, run_history_check


def pdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path))
    canvas.drawString(40, 700, text)
    canvas.save()


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, dict, dict]:
    from bd_packet_builder.evidence import extract_evidence
    from bd_packet_builder.inventory import build_inventory

    pdf(
        tmp_path / "bd_agreements/supporting_data/current.pdf",
        "Current legal name: New Example LLC",
    )
    pdf(tmp_path / "bd_agreements/Completed/reference.pdf", "Legal name: Old Example LLC")
    pdf(tmp_path / "bd_agreements/Completed/held-out.pdf", "Held out: NEVER RETRIEVE")
    page = extract_evidence(tmp_path, build_inventory(tmp_path)).documents[0].pages[0]
    entries = []
    for name, partition in [("reference", "reference"), ("held-out", "evaluation")]:
        path = f"bd_agreements/Completed/{name}.pdf"
        entries.append(
            {
                "path": path,
                "sha256": hashlib.sha256((tmp_path / path).read_bytes()).hexdigest(),
                "partition": partition,
                "issuer": "Synthetic Issuer",
                "completed_on": "2025-01-01",
            }
        )
    manifest = {"schema_version": 1, "entries": entries}
    request = {
        "schema_version": 1,
        "issuer": "Synthetic Issuer",
        "requirements": {
            "requirements": [
                {
                    "requirement_id": "name",
                    "application_sha256": "a" * 64,
                    "page": 1,
                    "instruction": "Legal name?",
                    "kind": "text",
                }
            ]
        },
        "proposals": {
            "proposals": [
                {
                    "requirement_id": "name",
                    "outcome": "proposed",
                    "value": {"kind": "text", "value": "New Example LLC"},
                    "confidence": 0.99,
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
        },
        "comparisons": [
            {
                "requirement_id": "name",
                "path": entries[0]["path"],
                "sha256": entries[0]["sha256"],
                "page": 1,
                "quote": "Legal name: Old Example LLC",
                "question": "Legal name?",
                "value": {"kind": "text", "value": "Old Example LLC"},
            }
        ],
    }
    (tmp_path / "outputs").mkdir()
    save(tmp_path, manifest, request)
    return tmp_path, manifest, request


def save(root: Path, manifest: dict, request: dict) -> None:
    (root / "outputs/partitions.json").write_text(json.dumps(manifest))
    (root / "outputs/comparisons.json").write_text(json.dumps(request))


def run(root: Path) -> dict:
    result = run_history_check(
        root, Path("outputs/partitions.json"), Path("outputs/comparisons.json")
    )
    return json.loads((result / "history-check.json").read_text())


def test_difference_is_a_review_flag_never_a_factual_replacement(history: tuple) -> None:
    root, _, _ = history
    before = (root / "outputs/comparisons.json").read_bytes()
    result = run(root)
    item = result["items"][0]
    assert item["status"] == "value_difference_review"
    assert item["fill_value"] is None
    assert item["current_proposal"]["value"]["value"] == "New Example LLC"
    assert item["reference"]["value"]["value"] == "Old Example LLC"
    assert "historical_answer_support_unverified" in item["issues"]
    assert result["status"] == "historical_review_only_no_packet"
    assert "NEVER RETRIEVE" not in json.dumps(result)
    assert "held-out.pdf" not in json.dumps(result)
    assert (root / "outputs/comparisons.json").read_bytes() == before


@pytest.mark.parametrize("kind", ["single_select", "multi_select"])
def test_identical_choice_ids_do_not_prove_historical_option_equivalence(
    history: tuple,
    kind: str,
) -> None:
    root, manifest, request = history
    requirement = request["requirements"]["requirements"][0]
    requirement.update(
        kind=kind,
        choices={
            "options": [
                {"option_id": "one", "label": "One", "instruction": "Current option One"},
                {"option_id": "two", "label": "Two", "instruction": "Current option Two"},
            ]
        },
    )
    value = {"kind": kind, "selected": ["one"], "write_ins": []}
    request["proposals"]["proposals"][0]["value"] = value
    request["comparisons"][0]["value"] = value
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert "historical_choice_mapping_unverified" in item["issues"]
    assert item["fill_value"] is None


@pytest.mark.parametrize(
    "change,issue",
    [
        ({"quote": "Fabricated quotation"}, "historical_quote_unresolved"),
        ({"page": 900}, "historical_quote_unresolved"),
        ({"sha256": "0" * 64}, "historical_version_mismatch"),
        ({"path": "bd_agreements/Completed/held-out.pdf"}, "reference_not_allowed"),
        ({"path": "bd_agreements/Completed/unlisted.pdf"}, "reference_not_allowed"),
        ({"path": "../outside.pdf"}, "reference_not_allowed"),
        ({"question": "Different question?"}, "question_context_mismatch"),
        ({"value": {"kind": "identifier", "value": "001234"}}, "answer_kind_mismatch"),
    ],
)
def test_invalid_or_incomparable_history_never_wins(
    history: tuple,
    change: dict,
    issue: str,
) -> None:
    root, manifest, request = history
    request["comparisons"][0].update(change)
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert issue in item["issues"]
    assert item["fill_value"] is None


def test_copied_evaluation_pdf_cannot_become_a_reference(history: tuple) -> None:
    root, manifest, request = history
    heldout = root / manifest["entries"][1]["path"]
    reference = root / manifest["entries"][0]["path"]
    reference.write_bytes(heldout.read_bytes())
    manifest["entries"][0]["sha256"] = manifest["entries"][1]["sha256"]
    save(root, manifest, request)
    with pytest.raises(HistoryError, match="partition"):
        run(root)


def test_source_hash_is_verified_not_just_declared(history: tuple) -> None:
    root, manifest, request = history
    (root / manifest["entries"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(HistoryError, match="changed"):
        run(root)
    assert not list((root / "outputs").glob("history-check-*"))


def test_reference_symlinks_are_rejected(history: tuple) -> None:
    root, manifest, _ = history
    reference = root / manifest["entries"][0]["path"]
    target = root / "outside.pdf"
    reference.rename(target)
    reference.symlink_to(target)
    with pytest.raises(HistoryError, match="symlink"):
        run(root)


@pytest.mark.parametrize(
    "field,value,issue",
    [
        ("issuer", "Other issuer", "issuer_context_mismatch"),
        (
            "requested_period",
            {"start": "2026-01-01", "end": "2026-12-31"},
            "reporting_period_context_mismatch",
        ),
        ("required_signer_role", "Chief Compliance Officer", "signer_context_mismatch"),
    ],
)
def test_context_mismatches_are_not_reported_as_errors_in_current_facts(
    history: tuple,
    field: str,
    value: object,
    issue: str,
) -> None:
    root, manifest, request = history
    if field == "issuer":
        request[field] = value
    else:
        request["requirements"]["requirements"][0][field] = value
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert issue in item["issues"]


def test_missing_current_evidence_cannot_be_repaired_from_history(history: tuple) -> None:
    root, manifest, request = history
    request["proposals"]["proposals"][0] = {
        "requirement_id": "name",
        "outcome": "missing_evidence",
        "explanation": "No evidence",
    }
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert "current_answer_unavailable" in item["issues"]
    assert item["fill_value"] is None


def test_history_never_resolves_as_current_evidence(history: tuple) -> None:
    root, manifest, request = history
    entry = manifest["entries"][0]
    identity = hashlib.sha256(entry["path"].encode() + b"\0" + entry["sha256"].encode()).hexdigest()
    request["proposals"]["proposals"][0]["citations"][0]["source_id"] = identity
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert "current_proposal_rejected" in item["issues"]


def test_exact_match_is_not_an_accuracy_pass(history: tuple) -> None:
    root, manifest, request = history
    request["comparisons"][0]["value"]["value"] = "New Example LLC"
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "same_value_unverified"
    assert "historical_answer_support_unverified" in item["issues"]


def test_duplicate_comparison_and_orphan_requirement_rejected(history: tuple) -> None:
    root, manifest, request = history
    request["comparisons"].append(request["comparisons"][0])
    save(root, manifest, request)
    with pytest.raises(HistoryError, match="schema"):
        run(root)
    request["comparisons"] = [{**request["comparisons"][0], "requirement_id": "unknown"}]
    save(root, manifest, request)
    with pytest.raises(HistoryError, match="schema"):
        run(root)


def test_cli_manual_input_check_is_explicit(
    history: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    root, _, _ = history
    assert (
        main(
            [
                "history-check",
                "--root",
                str(root),
                "--manifest",
                "outputs/partitions.json",
                "--comparisons",
                "outputs/comparisons.json",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "history-check.json" in output
    assert "no packet" in output.lower()
    assert "Old Example" not in output


def test_evaluation_quotes_are_never_extracted(
    history: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import bd_packet_builder.history as module

    root, manifest, request = history
    request["comparisons"][0]["path"] = manifest["entries"][1]["path"]
    request["comparisons"][0]["quote"] = "NEVER RETRIEVE"
    save(root, manifest, request)

    def fail(*args: object) -> bool:
        raise AssertionError("Evaluation document must not reach PDF extraction")

    monkeypatch.setattr(module, "_quote_present", fail)
    result = run(root)
    assert result["items"][0]["reference"] is None
    assert "NEVER RETRIEVE" not in json.dumps(result)


def test_current_evidence_cannot_be_a_copy_of_an_evaluation_packet(history: tuple) -> None:
    root, manifest, _ = history
    data = (root / manifest["entries"][1]["path"]).read_bytes()
    (root / "bd_agreements/supporting_data/leaked.pdf").write_bytes(data)
    with pytest.raises(HistoryError, match="current evidence"):
        run(root)


def test_input_mutation_after_check_cleans_staging(
    history: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, _ = history
    original = Path.write_text

    def mutate(path: Path, data: str, *args: object, **kwargs: object) -> int:
        count = original(path, data, *args, **kwargs)
        if path.name == "history-check.json":
            (root / "outputs/partitions.json").write_bytes(b"{}")
        return count

    monkeypatch.setattr(Path, "write_text", mutate)
    with pytest.raises(HistoryError, match="input changed"):
        run(root)
    assert not list((root / "outputs").glob("history-check-*"))
    assert not list((root / "outputs").glob(".staging-*"))


def test_money_requires_known_period_and_uses_decimal_comparison(history: tuple) -> None:
    root, manifest, request = history
    requirement = request["requirements"]["requirements"][0]
    requirement.update({"kind": "money", "unit": "USD"})
    request["proposals"]["proposals"][0]["value"] = {
        "kind": "money",
        "amount": "123.00",
        "unit": "USD",
    }
    request["comparisons"][0]["value"] = {"kind": "money", "amount": "123", "unit": "USD"}
    save(root, manifest, request)
    assert "reporting_period_context_unknown" in run(root)["items"][0]["issues"]
    period = {"start": "2025-01-01", "end": "2025-12-31"}
    requirement["requested_period"] = period
    manifest["entries"][0]["reporting_period"] = period
    save(root, manifest, request)
    assert run(root)["items"][0]["status"] == "same_value_unverified"
    request["comparisons"][0]["value"]["unit"] = "EUR"
    save(root, manifest, request)
    assert "unit_mismatch" in run(root)["items"][0]["issues"]


@pytest.mark.parametrize(
    "entry_change",
    [
        {"partition": "automatic"},
        {"path": "bd_agreements/supporting_data/current.pdf"},
        {"path": "/tmp/packet.pdf"},
        {"sha256": "bad"},
    ],
)
def test_malformed_manifest_is_safe(history: tuple, entry_change: dict) -> None:
    root, manifest, request = history
    manifest["entries"][0].update(entry_change)
    save(root, manifest, request)
    with pytest.raises(HistoryError, match="schema"):
        run(root)


def test_reference_reader_exposes_only_reference_bytes_and_rechecks_versions(
    history: tuple,
) -> None:
    from bd_packet_builder.history import ArchiveManifest, open_reference_archive

    root, manifest, _ = history
    archive = open_reference_archive(
        root, ArchiveManifest.model_validate_json(json.dumps(manifest))
    )
    entry = manifest["entries"][0]
    assert archive.read_reference(entry["path"]) == (root / entry["path"]).read_bytes()
    with pytest.raises(HistoryError, match="not allowed"):
        archive.read_reference(manifest["entries"][1]["path"])
    (root / entry["path"]).write_bytes(b"changed")
    with pytest.raises(HistoryError, match="changed"):
        archive.read_reference(entry["path"])


def test_missing_completion_date_is_not_inferred(history: tuple) -> None:
    root, manifest, request = history
    manifest["entries"][0]["completed_on"] = None
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert "historical_completion_date_unknown" in item["issues"]


def test_signature_fields_are_never_revised_from_historical_values(history: tuple) -> None:
    root, manifest, request = history
    request["requirements"]["requirements"][0]["kind"] = "signature"
    save(root, manifest, request)
    item = run(root)["items"][0]
    assert item["status"] == "not_comparable"
    assert "current_proposal_rejected" in item["issues"]
    assert item["fill_value"] is None
