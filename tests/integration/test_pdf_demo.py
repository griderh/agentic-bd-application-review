import hashlib
import json
from pathlib import Path

import pypdfium2
import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.pdf_demo import DEMO_VALUE, create_demo, inspect_pdf


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "bd_agreements" / "Blank"
    folder.mkdir(parents=True)
    canvas = Canvas(str(folder / "blank.pdf"), pagesize=(612, 792))
    canvas.drawString(50, 740, "Synthetic issuer questionnaire")
    canvas.drawString(50, 700, "Firm name")
    canvas.acroForm.textfield(name="Name of Firm", x=50, y=665, width=400, height=24, fontSize=10)
    canvas.drawString(50, 600, "Signature")
    canvas.acroForm.textfield(name="Signature", x=50, y=560, width=250, height=24)
    canvas.drawString(350, 600, "Date")
    canvas.acroForm.textfield(name="Signature date", x=350, y=560, width=100, height=24)
    canvas.showPage()
    canvas.drawString(50, 740, "Unchanged second page")
    canvas.save()
    return tmp_path


def test_inspection_reads_structure_not_field_values(project: Path) -> None:
    result = inspect_pdf(project / "bd_agreements/Blank/blank.pdf")
    assert result.page_count == 2
    assert result.text_field_count == 3


def test_demo_writes_renders_and_preserves_source_and_signing_fields(project: Path) -> None:
    source = project / "bd_agreements/Blank/blank.pdf"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert result.parent == project / "outputs"
    reader = PdfReader(result / "demo.pdf")
    fields = reader.get_fields()
    assert fields is not None
    assert fields["Name of Firm"]["/V"] == DEMO_VALUE
    assert fields["Signature"]["/V"] == ""
    assert fields["Signature date"]["/V"] == ""
    assert len(reader.pages) == 2
    assert "Unchanged second page" in reader.pages[1].extract_text()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with (
        Image.open(result / "before.png") as before_image,
        Image.open(result / "after.png") as after_image,
    ):
        # Only the selected native field's appearance should change.
        difference = ImageChops.difference(before_image.convert("RGB"), after_image.convert("RGB"))
        bounds = difference.getbbox()
        assert bounds is not None
        assert 48 <= bounds[0] < bounds[2] <= 452
        assert 101 <= bounds[1] < bounds[3] <= 129
    manifest = json.loads((result / "manifest.json").read_text())
    assert manifest["status"] == "synthetic_demo_not_for_submission"
    assert manifest["input_sha256"] == before
    assert (
        manifest["output_sha256"] == hashlib.sha256((result / "demo.pdf").read_bytes()).hexdigest()
    )


def test_repeat_runs_are_isolated(project: Path) -> None:
    first = create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    second = create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert first != second
    assert (first / "demo.pdf").is_file()
    assert (second / "demo.pdf").is_file()


@pytest.mark.parametrize("source", ["../outside.pdf", "/tmp/outside.pdf", "README.md"])
def test_rejects_paths_outside_blank_source_tree(project: Path, source: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        create_demo(project, Path(source))
    assert not (project / "outputs").exists()


def test_rejects_source_symlink_escape(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"not a PDF")
    (project / "bd_agreements/Blank/link.pdf").symlink_to(outside)
    with pytest.raises(ValueError, match="blank"):
        create_demo(project, Path("bd_agreements/Blank/link.pdf"))


def test_rejects_output_symlink_escape(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "outputs").symlink_to(outside)
    with pytest.raises(ValueError, match="output"):
        create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert list(outside.iterdir()) == []


def test_flattened_pdf_fails_explicitly_without_fake_success(project: Path) -> None:
    flat = project / "bd_agreements/Blank/flat.pdf"
    canvas = Canvas(str(flat))
    canvas.drawString(50, 740, "No native form fields")
    canvas.save()
    with pytest.raises(ValueError, match="native firm-name"):
        create_demo(project, Path("bd_agreements/Blank/flat.pdf"))
    assert not (project / "outputs").exists()


def test_prefilled_form_is_rejected(project: Path) -> None:
    source = project / "bd_agreements/Blank/blank.pdf"
    writer = PdfWriter(clone_from=source)
    writer.update_page_form_field_values(writer.pages[0], {"Signature date": "2026-01-01"})
    filled = project / "bd_agreements/Blank/filled.pdf"
    with filled.open("wb") as stream:
        writer.write(stream)
    writer.close()
    with pytest.raises(ValueError, match="prefilled"):
        create_demo(project, Path("bd_agreements/Blank/filled.pdf"))
    assert not (project / "outputs").exists()


def test_encrypted_pdf_is_rejected(project: Path) -> None:
    encrypted = project / "bd_agreements/Blank/encrypted.pdf"
    writer = PdfWriter(clone_from=project / "bd_agreements/Blank/blank.pdf")
    writer.encrypt("synthetic-password")
    with encrypted.open("wb") as stream:
        writer.write(stream)
    writer.close()
    with pytest.raises(ValueError, match="Encrypted"):
        create_demo(project, Path("bd_agreements/Blank/encrypted.pdf"))


def test_cli_demo_and_inspect(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bd_packet_builder.cli import main

    source = Path("bd_agreements/Blank/blank.pdf")
    assert main(["inspect", str(project / source)]) == 0
    assert json.loads(capsys.readouterr().out)["text_field_count"] == 3
    assert main(["demo", "--root", str(project), "--source", str(source)]) == 0
    assert "not a completed application" in capsys.readouterr().out


def test_cli_errors_are_actionable_without_leaking_source_content(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["demo", "--root", str(project), "--source", "../outside.pdf"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "relative PDF path within the blank forms folder" in captured.err
    assert str(project) not in captured.err


def test_render_failure_does_not_publish_partial_outputs(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_render(*args: object, **kwargs: object) -> None:
        raise pypdfium2.PdfiumError("Synthetic rendering failure")

    monkeypatch.setattr(pypdfium2, "PdfDocument", fail_render)
    with pytest.raises(pypdfium2.PdfiumError):
        create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert list((project / "outputs").iterdir()) == []


def test_cli_reports_missing_file_without_success(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["inspect", str(project / "missing.pdf")]) == 1
    captured = capsys.readouterr()
    assert "Check the input exists" in captured.err
    assert captured.out == ""


def test_cli_reports_invalid_pdf_without_echoing_payload(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    invalid = project / "invalid.pdf"
    invalid.write_bytes(b"%PDF-1.4\n")
    assert main(["inspect", str(invalid)]) == 1
    captured = capsys.readouterr()
    assert "valid supported PDF" in captured.err
    assert captured.out == ""


def test_empty_pdf_fails_explicitly(project: Path) -> None:
    source = project / "bd_agreements/Blank/empty.pdf"
    writer = PdfWriter()
    with source.open("wb") as stream:
        writer.write(stream)
    writer.close()
    with pytest.raises(ValueError, match="no pages"):
        create_demo(project, Path("bd_agreements/Blank/empty.pdf"))


def test_digital_signature_widgets_are_not_modified(project: Path) -> None:
    writer = PdfWriter(clone_from=project / "bd_agreements/Blank/blank.pdf")
    for annotation in writer.pages[0]["/Annots"]:
        widget = annotation.get_object()
        if widget.get("/T") == "Signature":
            widget[NameObject("/FT")] = NameObject("/Sig")
    source = project / "bd_agreements/Blank/signable.pdf"
    with source.open("wb") as stream:
        writer.write(stream)
    writer.close()
    with pytest.raises(ValueError, match="Digital signature"):
        create_demo(project, Path("bd_agreements/Blank/signable.pdf"))
    assert not (project / "outputs").exists()


def test_paths_are_relative_to_explicit_root_not_current_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project.parent)
    output = create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert output.parent == project / "outputs"


def test_source_change_prevents_publication(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_document = pypdfium2.PdfDocument
    source = project / "bd_agreements/Blank/blank.pdf"

    def simulate_concurrent_change(path: str) -> pypdfium2.PdfDocument:
        document = original_document(path)
        if Path(path) == source:
            with source.open("ab") as stream:
                stream.write(b"\n")
        return document

    monkeypatch.setattr(pypdfium2, "PdfDocument", simulate_concurrent_change)
    with pytest.raises(ValueError, match="Source changed"):
        create_demo(project, Path("bd_agreements/Blank/blank.pdf"))
    assert list((project / "outputs").iterdir()) == []
