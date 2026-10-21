import hashlib
import json
import os
from pathlib import Path

import pytest
from pypdf import PdfWriter

from bd_packet_builder.inventory import (
    EvidenceReference,
    InventoryError,
    build_inventory,
    publish_inventory,
    resolve_reference,
    select_evidence,
)


def write_pdf(path: Path, *, pages: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfWriter() as writer:
        for _ in range(pages):
            writer.add_blank_page(width=612, height=792)
        with path.open("wb") as stream:
            writer.write(stream)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    support = tmp_path / "bd_agreements/supporting_data"
    write_pdf(support / "Focus_Reports/Example_Aug2026_Public.pdf")
    write_pdf(support / "Focus_Reports/Example_Feb2023_Public.pdf", pages=1)
    write_pdf(support / "Audited_Financials/Example FY2025.pdf")
    write_pdf(support / "bios/Synthetic representative.pdf")
    # A completed packet must never become an authoritative inventory source.
    write_pdf(tmp_path / "bd_agreements/Completed/Example_2027-01.pdf")
    return tmp_path


def test_inventory_has_relative_versioned_provenance_and_preserves_inputs(root: Path) -> None:
    files = list((root / "bd_agreements/supporting_data").rglob("*.pdf"))
    before = {p: p.read_bytes() for p in files}
    inventory = build_inventory(root)
    assert len(inventory.sources) == 4
    assert inventory.issues == ()
    assert inventory.created_at.utcoffset().total_seconds() == 0
    for source in inventory.sources:
        assert source.path.startswith("bd_agreements/supporting_data/")
        assert source.sha256 == hashlib.sha256((root / source.path).read_bytes()).hexdigest()
        assert source.size_bytes == len((root / source.path).read_bytes())
        assert source.page_count in (1, 2)
        assert len(source.source_id) == 64
        assert "content_date_unverified" in source.flags
    undated = next(s for s in inventory.sources if s.family == "bios")
    assert undated.period is None
    assert "period_not_configured" in undated.flags
    assert {p: p.read_bytes() for p in files} == before
    again = build_inventory(root)
    assert inventory.sources == again.sources


def test_only_dated_homogeneous_families_are_selected(root: Path) -> None:
    inventory = build_inventory(root)
    focus = select_evidence(inventory, "Focus_Reports")
    assert focus.source is not None
    assert focus.source.path.endswith("Example_Aug2026_Public.pdf")
    assert focus.period == "2026-08"
    assert "content_date_unverified" in focus.flags
    annual = select_evidence(inventory, "Audited_Financials")
    assert annual.period == "2025"
    with pytest.raises(InventoryError, match="family"):
        select_evidence(inventory, "bios")


def test_explicit_missing_period_keeps_evidence_and_mismatch_visible(root: Path) -> None:
    result = select_evidence(build_inventory(root), "Focus_Reports", requested_period="2026-09")
    assert result.source is not None
    assert result.period == "2026-08"
    assert result.requested_period == "2026-09"
    assert "requested_period_unavailable" in result.flags


@pytest.mark.parametrize("period", ["2026-13", "2026-8", "2026-08-17", "", "nonsense"])
def test_requested_period_is_strictly_validated(root: Path, period: str) -> None:
    with pytest.raises(InventoryError, match="period"):
        select_evidence(build_inventory(root), "Focus_Reports", requested_period=period)


def test_unknown_date_blocks_selection_but_not_inventory(root: Path) -> None:
    write_pdf(root / "bd_agreements/supporting_data/Focus_Reports/undated.pdf")
    inventory = build_inventory(root)
    assert len(inventory.sources) == 5
    result = select_evidence(inventory, "Focus_Reports")
    assert result.source is None
    assert "unparseable_period" in result.flags


def test_duplicate_period_is_not_resolved_by_hash_or_modified_time(root: Path) -> None:
    support = root / "bd_agreements/supporting_data"
    (support / "Focus_Reports/Copy_Aug2026.pdf").write_bytes(
        (support / "Focus_Reports/Example_Aug2026_Public.pdf").read_bytes()
    )
    inventory = build_inventory(root)
    assert select_evidence(inventory, "Focus_Reports").source is None
    assert "ambiguous_period" in select_evidence(inventory, "Focus_Reports").flags
    assert sum("duplicate_content" in s.flags for s in inventory.sources) >= 2


def test_corrupt_pdf_is_visible_and_does_not_silently_fall_back(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/Focus_Reports/Example_Sept2026.pdf"
    path.write_bytes(b"not-a-PDF: synthetic confidential content")
    inventory = build_inventory(root)
    bad = next(s for s in inventory.sources if s.path.endswith("Example_Sept2026.pdf"))
    assert "unreadable_pdf" in bad.flags
    assert bad.page_count is None
    result = select_evidence(inventory, "Focus_Reports")
    assert result.source is None
    assert "unusable_document" in result.flags


@pytest.mark.parametrize("password", ["secret", ""])
def test_encrypted_pdf_is_unusable_even_with_empty_password(root: Path, password: str) -> None:
    path = root / "bd_agreements/supporting_data/Focus_Reports/Encrypted_Sept2026.pdf"
    with PdfWriter() as writer:
        writer.add_blank_page(width=612, height=792)
        writer.encrypt(password)
        with path.open("wb") as stream:
            writer.write(stream)
    inventory = build_inventory(root)
    encrypted = next(s for s in inventory.sources if s.path.endswith("Encrypted_Sept2026.pdf"))
    assert encrypted.page_count is None
    assert "unreadable_pdf" in encrypted.flags or "encrypted_pdf" in encrypted.flags
    assert select_evidence(inventory, "Focus_Reports").source is None


def test_other_formats_are_not_assumed_to_have_pdf_pages(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/Cover_Letters/template.docx"
    path.parent.mkdir()
    path.write_bytes(b"synthetic document bytes")
    source = next(s for s in build_inventory(root).sources if s.path.endswith(".docx"))
    assert source.page_count is None
    assert "page_reference_unavailable" in source.flags


def test_source_and_directory_symlinks_are_flagged_without_following(root: Path) -> None:
    support = root / "bd_agreements/supporting_data"
    (support / "completed-link").symlink_to(root / "bd_agreements/Completed")
    (support / "escape.pdf").symlink_to(root / "bd_agreements/Completed/Example_2027-01.pdf")
    inventory = build_inventory(root)
    assert len(inventory.sources) == 4
    assert len(inventory.issues) == 2
    assert all(issue.code == "symlink_rejected" for issue in inventory.issues)


def test_support_root_symlink_is_rejected(root: Path) -> None:
    alternate = root / "alternate"
    alternate.mkdir()
    support = root / "bd_agreements/supporting_data"
    support.rename(root / "original")
    support.symlink_to(alternate, target_is_directory=True)
    with pytest.raises(InventoryError, match="supporting"):
        build_inventory(root)


def test_reference_resolves_only_known_unchanged_source_and_valid_page(root: Path) -> None:
    inventory = build_inventory(root)
    source = inventory.sources[0]
    reference = EvidenceReference(source.source_id, page=1)
    assert resolve_reference(root, inventory, reference) == source
    with pytest.raises(InventoryError, match="page"):
        resolve_reference(root, inventory, EvidenceReference(source.source_id, page=100))
    with pytest.raises(InventoryError, match="unknown"):
        resolve_reference(root, inventory, EvidenceReference("0" * 64, page=1))
    (root / source.path).write_bytes(b"modified after inventory")
    with pytest.raises(InventoryError, match="changed"):
        resolve_reference(root, inventory, reference)


@pytest.mark.parametrize("page", [0, -1, True, "1"])
def test_reference_rejects_invalid_page_values(page: object) -> None:
    with pytest.raises(InventoryError, match="page"):
        EvidenceReference("0" * 64, page=page)  # type: ignore[arg-type]


def test_invalid_reference_identity_is_rejected() -> None:
    with pytest.raises(InventoryError, match="identity"):
        EvidenceReference("../outside.pdf", page=1)


def test_replacing_source_with_symlink_invalidates_reference(root: Path) -> None:
    inventory = build_inventory(root)
    source = inventory.sources[0]
    path = root / source.path
    duplicate = root / "duplicate.pdf"
    duplicate.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(duplicate)
    with pytest.raises(InventoryError, match="symlink"):
        resolve_reference(root, inventory, EvidenceReference(source.source_id, 1))


def test_inventory_manifest_is_unique_atomic_and_metadata_only(root: Path) -> None:
    inventory = build_inventory(root)
    folder = publish_inventory(root, inventory)
    second = publish_inventory(root, inventory)
    assert folder != second
    data = json.loads((folder / "inventory.json").read_text())
    assert data["schema_version"] == 1
    assert data["status"] == "metadata_only_not_answer_grounding"
    assert len(data["sources"]) == 4
    assert len(data["selections"]) == 2
    assert str(root) not in json.dumps(data)
    assert not any(p.name.startswith(".staging") for p in (root / "outputs").iterdir())


def test_output_symlink_rejected(root: Path) -> None:
    (root / "elsewhere").mkdir()
    (root / "outputs").symlink_to(root / "elsewhere")
    with pytest.raises(InventoryError, match="output"):
        publish_inventory(root, build_inventory(root))
    assert list((root / "elsewhere").iterdir()) == []


def test_empty_inventory_has_explicit_missing_family_selections(tmp_path: Path) -> None:
    (tmp_path / "bd_agreements/supporting_data").mkdir(parents=True)
    inventory = build_inventory(tmp_path)
    assert inventory.sources == ()
    assert select_evidence(inventory, "Focus_Reports").flags == ("missing_document",)
    result = select_evidence(inventory, "Audited_Financials", requested_period="2025")
    assert result.source is None
    assert result.requested_period == "2025"
    assert result.flags == ("missing_document",)


def test_unsupported_inputs_are_visible_and_make_family_selection_incomplete(root: Path) -> None:
    support = root / "bd_agreements/supporting_data"
    (support / ".DS_Store").write_bytes(b"ignored finder metadata")
    unsupported = support / "Focus_Reports/newest_2027-01.xlsx"
    unsupported.write_bytes(b"synthetic unsupported source")
    inventory = build_inventory(root)
    assert len(inventory.sources) == 4
    assert len(inventory.issues) == 1
    assert inventory.issues[0].code == "unsupported_format"
    selection = select_evidence(inventory, "Focus_Reports")
    assert selection.source is None
    assert "incomplete_family_inventory" in selection.flags


def test_non_pdf_in_versioned_family_cannot_be_proposed_as_page_evidence(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/Focus_Reports/Example_Sept2026.docx"
    path.write_bytes(b"synthetic")
    result = select_evidence(build_inventory(root), "Focus_Reports")
    assert result.source is None
    assert "unusable_document" in result.flags
    assert "page_reference_unavailable" in result.flags


def test_non_pdf_cannot_resolve_a_pdf_page(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/template.png"
    path.write_bytes(b"synthetic")
    inventory = build_inventory(root)
    source = next(s for s in inventory.sources if s.path.endswith(".png"))
    assert source.family == "unassigned"
    with pytest.raises(InventoryError, match="page"):
        resolve_reference(root, inventory, EvidenceReference(source.source_id, 1))


def test_publication_rechecks_source_versions_before_creating_output(root: Path) -> None:
    inventory = build_inventory(root)
    (root / inventory.sources[0].path).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        publish_inventory(root, inventory)
    assert not (root / "outputs").exists()


def test_mutation_during_manifest_write_prevents_inventory_publication(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = build_inventory(root)
    original = Path.write_text

    def mutate_after_write(path: Path, *args: object, **kwargs: object) -> int:
        result = original(path, *args, **kwargs)  # type: ignore[arg-type]
        (root / inventory.sources[0].path).write_bytes(b"changed during output write")
        return result

    monkeypatch.setattr(Path, "write_text", mutate_after_write)
    with pytest.raises(InventoryError, match="changed"):
        publish_inventory(root, inventory)
    assert list((root / "outputs").iterdir()) == []


def test_failed_manifest_write_leaves_no_successful_or_staged_run(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = build_inventory(root)

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        publish_inventory(root, inventory)
    assert list((root / "outputs").iterdir()) == []


def test_oversized_source_is_explicit_failure_without_publication(root: Path) -> None:
    path = root / "bd_agreements/supporting_data/oversized.pdf"
    with path.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    with pytest.raises(InventoryError, match="64 MiB"):
        build_inventory(root)
    assert not (root / "outputs").exists()


def test_mutation_during_reading_is_technical_failure(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.fstat
    calls = 0

    def changed_stat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        info = original(fd)
        if calls == 2:
            values = list(info)
            values[6] += 1  # Simulate a changed size on the still-open source handle.
            return os.stat_result(values)
        return info

    monkeypatch.setattr(os, "fstat", changed_stat)
    with pytest.raises(InventoryError, match="changed"):
        build_inventory(root)


def test_source_access_failure_does_not_skip_evidence_or_expose_payload(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    def fail_open(*args: object, **kwargs: object) -> None:
        raise PermissionError("synthetic confidential payload")

    monkeypatch.setattr(Path, "open", fail_open)
    assert main(["inventory", "--root", str(root)]) == 1
    output = capsys.readouterr()
    assert "Inventory I/O failed" in output.err
    assert "synthetic confidential payload" not in output.err
    assert output.out == ""
    assert not (root / "outputs").exists()


def test_missing_support_root_is_clear_cli_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["inventory", "--root", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert "supporting-data" in output.err
    assert output.out == ""


def test_cli_inventory_prints_only_counts_and_output_location(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["inventory", "--root", str(root)]) == 0
    output = capsys.readouterr()
    assert "4 sources" in output.out
    assert "inventory.json" in output.out
    assert "Synthetic representative" not in output.out
    assert output.err == ""
