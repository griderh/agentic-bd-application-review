import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.evidence import (
    EvidenceError,
    ExtractionLimits,
    TextCitation,
    extract_evidence,
    publish_evidence,
    resolve_quote,
)
from bd_packet_builder.inventory import InventoryError, build_inventory


def write_text_pdf(path: Path, pages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path))
    for text in pages:
        for line, value in enumerate(text.splitlines()):
            canvas.drawString(50, 740 - line * 20, value)
        canvas.showPage()
    canvas.save()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    support = tmp_path / "bd_agreements/supporting_data"
    write_text_pdf(
        support / "Focus_Reports/Example_Aug2026.pdf",
        ["SYNTHETIC PRIVATE TEXT\nAs of August 31, 2026", "Net capital: synthetic example only"],
    )
    write_text_pdf(
        support / "Audited_Financials/Statement_FY2025.pdf",
        ["Statement of Financial Condition\nDecember 31, 2025"],
    )
    return tmp_path


def test_extracts_native_text_with_known_version_and_one_based_pages(root: Path) -> None:
    inventory = build_inventory(root)
    before = {s.path: (root / s.path).read_bytes() for s in inventory.sources}
    bundle = extract_evidence(root, inventory)
    assert len(bundle.documents) == 2
    focus = next(d for d in bundle.documents if d.source.family == "Focus_Reports")
    assert focus.source in inventory.sources
    assert len(focus.pages) == 2
    assert [p.page for p in focus.pages] == [1, 2]
    assert all(p.source_id == focus.source.source_id for p in focus.pages)
    assert "SYNTHETIC PRIVATE TEXT" in focus.pages[0].text
    assert focus.period_check.status == "filename_period_corroborated"
    assert {s.path: (root / s.path).read_bytes() for s in inventory.sources} == before
    assert "not_semantic_grounding" in bundle.flags
    # The original metadata inventory must not be silently promoted to approved evidence.
    assert all("content_date_unverified" in s.flags for s in inventory.sources)


def test_blank_pages_stay_in_place_and_prevent_complete_period_check(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/Focus_Reports/Example_Aug2026.pdf"
    write_text_pdf(path, ["As of August 31, 2026", ""])
    bundle = extract_evidence(root, build_inventory(root))
    focus = next(d for d in bundle.documents if d.source.family == "Focus_Reports")
    assert focus.pages[1].text == ""
    assert focus.pages[1].flags == ("no_native_text",)
    assert focus.period_check.status == "reporting_period_unverified"
    assert "partial_native_text" in focus.flags


def test_unsupported_and_corrupt_inputs_are_visible_while_supported_work_continues(
    root: Path,
) -> None:
    support = root / "bd_agreements/supporting_data"
    (support / "sample.png").write_bytes(b"synthetic image")
    (support / "broken.pdf").write_bytes(b"synthetic corrupt content")
    bundle = extract_evidence(root, build_inventory(root))
    assert len(bundle.documents) == 4
    unusable = [d for d in bundle.documents if not d.pages]
    assert len(unusable) == 2
    assert all("native_text_unavailable" in d.flags for d in unusable)
    assert all(d.period_check.status != "filename_period_corroborated" for d in unusable)


def test_changed_sources_rejected_before_extraction(root: Path) -> None:
    inventory = build_inventory(root)
    (root / inventory.sources[0].path).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        extract_evidence(root, inventory)
    assert not (root / "outputs").exists()


def test_replacing_source_with_symlink_is_rejected(root: Path) -> None:
    inventory = build_inventory(root)
    path = root / inventory.sources[0].path
    outside = root / "outside.pdf"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(InventoryError, match="symlink"):
        extract_evidence(root, inventory)


@pytest.mark.parametrize(
    "limits",
    [
        ExtractionLimits(max_pages_per_document=1),
        ExtractionLimits(max_chars_per_page=10),
        ExtractionLimits(max_chars_per_run=10),
    ],
)
def test_limits_fail_explicitly_instead_of_publishing_truncated_evidence(
    root: Path, limits: ExtractionLimits
) -> None:
    with pytest.raises(EvidenceError, match="limit"):
        extract_evidence(root, build_inventory(root), limits=limits)
    assert not (root / "outputs").exists()


@pytest.mark.parametrize("value", [0, -1, True, "2"])
def test_limits_do_not_accept_coerced_or_nonpositive_values(value: object) -> None:
    with pytest.raises(EvidenceError, match="limit"):
        ExtractionLimits(max_pages_per_document=value)  # type: ignore[arg-type]


def test_citations_resolve_exact_substrings_not_merely_plausible_source_ids(root: Path) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    focus = next(d for d in bundle.documents if d.source.family == "Focus_Reports")
    citation = focus.period_check.observations[0].citation
    assert resolve_quote(root, inventory, citation) == citation.quote
    fabricated = TextCitation(
        citation.source_id, citation.page, citation.start, citation.end, "As of July 31, 2026"
    )
    with pytest.raises(EvidenceError, match="quote"):
        resolve_quote(root, inventory, fabricated)
    (root / focus.source.path).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        resolve_quote(root, inventory, citation)


@pytest.mark.parametrize(
    ("start", "end", "quote"),
    [(True, 5, "abc"), (-1, 5, "abc"), (5, 5, ""), (6, 5, "abc"), (0, 3, 123)],
)
def test_malformed_quote_locators_are_rejected(start: int, end: int, quote: str) -> None:
    with pytest.raises(EvidenceError, match="quote"):
        TextCitation("a" * 64, 1, start, end, quote)


def test_quote_locator_bounds_are_checked_against_actual_text(root: Path) -> None:
    inventory = build_inventory(root)
    source = inventory.sources[0]
    with pytest.raises(EvidenceError, match="quote"):
        resolve_quote(root, inventory, TextCitation(source.source_id, 1, 0, 10000, "invented"))


def test_publishes_confidential_local_bundle_without_absolute_source_paths(root: Path) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    folder = publish_evidence(root, inventory, bundle)
    data = json.loads((folder / "evidence.json").read_text())
    assert data["status"] == "native_text_only_not_approved_answers"
    assert data["schema_version"] == 1
    assert data["extractor_version"] == "pdfium-native-v1"
    assert data["period_rule_version"] == "labeled-report-dates-v1"
    assert "SYNTHETIC PRIVATE TEXT" in json.dumps(data)
    assert str(root) not in json.dumps(data)
    assert folder != publish_evidence(root, inventory, bundle)
    assert not any(p.name.startswith(".staging") for p in (root / "outputs").iterdir())


def test_changed_sources_prevent_evidence_publication(root: Path) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    (root / inventory.sources[0].path).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        publish_evidence(root, inventory, bundle)
    assert not (root / "outputs").exists()


def test_output_symlink_and_interrupted_write_do_not_publish(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    outside = root / "elsewhere"
    outside.mkdir()
    (root / "outputs").symlink_to(outside)
    with pytest.raises(InventoryError, match="output"):
        publish_evidence(root, inventory, bundle)
    (root / "outputs").unlink()

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic confidential error")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(OSError):
        publish_evidence(root, inventory, bundle)
    assert list((root / "outputs").iterdir()) == []
    assert list(outside.iterdir()) == []


def test_encrypted_input_does_not_become_extracted_evidence(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/encrypted.pdf"
    with PdfWriter() as writer:
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("")
        with path.open("wb") as stream:
            writer.write(stream)
    bundle = extract_evidence(root, build_inventory(root))
    document = next(d for d in bundle.documents if d.source.path.endswith("encrypted.pdf"))
    assert document.pages == ()
    assert "native_text_unavailable" in document.flags


def test_cli_keeps_text_and_private_filenames_out_of_console(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "bd_agreements/supporting_data").rglob("*.pdf")
    }
    assert main(["evidence", "--root", str(root)]) == 0
    captured = capsys.readouterr()
    assert "2 documents" in captured.out
    assert "evidence.json" in captured.out
    assert "SYNTHETIC PRIVATE TEXT" not in captured.out + captured.err
    assert "Example_Aug2026" not in captured.out + captured.err
    assert captured.err == ""
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())


def test_cli_limit_failure_is_explicit_and_leaves_no_successful_run(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["evidence", "--root", str(root), "--max-chars-per-page", "10"]) == 1
    output = capsys.readouterr()
    assert "Evidence command rejected" in output.err
    assert "limit" in output.err
    assert output.out == ""
    assert "SYNTHETIC PRIVATE TEXT" not in output.err
    assert not (root / "outputs").exists()


def test_mutation_during_manifest_write_prevents_publication(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    original = Path.write_text

    def mutate_after_write(path: Path, *args: object, **kwargs: object) -> int:
        result = original(path, *args, **kwargs)  # type: ignore[arg-type]
        (root / inventory.sources[0].path).write_bytes(b"changed during output write")
        return result

    monkeypatch.setattr(Path, "write_text", mutate_after_write)
    with pytest.raises(InventoryError, match="changed"):
        publish_evidence(root, inventory, bundle)
    assert list((root / "outputs").iterdir()) == []


def test_foreign_inventory_bundle_cannot_be_published(root: Path) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    write_text_pdf(root / inventory.sources[0].path, ["changed synthetic document"])
    fresh = build_inventory(root)
    with pytest.raises(EvidenceError, match="inventory"):
        publish_evidence(root, fresh, bundle)
    assert not (root / "outputs").exists()


def test_single_page_extraction_failure_is_explicit_and_other_pages_continue(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = build_inventory(root)
    original = pdfium.PdfTextPage.get_text_bounded
    calls = 0

    def fail_once(textpage: pdfium.PdfTextPage, *args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise pdfium.PdfiumError("synthetic confidential parsing error")
        return original(textpage, *args, **kwargs)

    monkeypatch.setattr(pdfium.PdfTextPage, "get_text_bounded", fail_once)
    bundle = extract_evidence(root, inventory)
    pages = [page for document in bundle.documents for page in document.pages]
    assert len(pages) == 3
    assert pages[0].flags == ("native_text_extraction_failed",)
    assert pages[0].text == ""
    assert all(page.text and not page.flags for page in pages[1:])
    assert bundle.documents[0].period_check.status == "reporting_period_unverified"


def test_run_and_page_limits_accept_exact_threshold_and_reject_one_below(root: Path) -> None:
    inventory = build_inventory(root)
    bundle = extract_evidence(root, inventory)
    total = sum(len(page.text) for document in bundle.documents for page in document.pages)
    assert (
        len(
            extract_evidence(
                root,
                inventory,
                limits=ExtractionLimits(max_pages_per_document=2, max_chars_per_run=total),
            ).documents
        )
        == 2
    )
    with pytest.raises(EvidenceError, match="run character limit"):
        extract_evidence(root, inventory, limits=ExtractionLimits(max_chars_per_run=total - 1))
    largest = 0
    for source in inventory.sources:
        with pdfium.PdfDocument((root / source.path).read_bytes()) as document:
            for index in range(len(document)):
                page = document[index]
                textpage = page.get_textpage()
                try:
                    largest = max(
                        largest,
                        textpage.count_chars(),
                        len(textpage.get_text_bounded(errors="strict").replace("\r\n", "\n")),
                    )
                finally:
                    textpage.close()
                    page.close()
    assert (
        len(
            extract_evidence(
                root, inventory, limits=ExtractionLimits(max_chars_per_page=largest)
            ).documents
        )
        == 2
    )
    with pytest.raises(EvidenceError, match="per-page character limit"):
        extract_evidence(root, inventory, limits=ExtractionLimits(max_chars_per_page=largest - 1))
