import hashlib
import json
import os
import subprocess
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.inventory import InventoryError
from bd_packet_builder.ocr import OcrError, OcrLimits, run_ocr

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext\n"
)
TSV = HEADER + "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t95.25\tSYNTHETIC\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "bd_agreements/supporting_data/Focus_Reports/Scan_Aug2026.pdf"
    path.parent.mkdir(parents=True)
    canvas = Canvas(str(path), pagesize=(612, 792))
    canvas.setFont("Helvetica", 18)
    for index, line in enumerate(
        [
            "SYNTHETIC OCR SAMPLE",
            "As of August 31, 2026",
            "Net capital 1,234,567.89",
            "CRD 001234",
            "Assets     9,876.54",
            "Liabilities     (123.45)",
        ]
    ):
        canvas.drawString(60, 720 - index * 40, line)
    canvas.save()
    # Rasterize and embed an image so the test cannot pass using the native text layer.
    with pdfium.PdfDocument(str(path)) as document:
        page = document[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil()
        try:
            scanned = Canvas(str(path.with_name("staging.pdf")), pagesize=(612, 792))
            scanned.drawImage(ImageReader(image), 0, 0, width=612, height=792)
            scanned.showPage()
            scanned.save()
        finally:
            image.close()
            bitmap.close()
            page.close()
    path.with_name("staging.pdf").replace(path)
    return tmp_path


SOURCE = Path("bd_agreements/supporting_data/Focus_Reports/Scan_Aug2026.pdf")


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        output = b"tesseract 5.5.3\n" if "--version" in command else TSV.encode()
        kwargs["stdout"].write(output)  # type: ignore[union-attr]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_ocr_is_separate_unverified_output_with_geometry_and_versions(
    root: Path, fake_engine: list[list[str]]
) -> None:
    original = (root / SOURCE).read_bytes()
    folder = run_ocr(root, SOURCE, 1)
    data = json.loads((folder / "ocr.json").read_text())
    assert data["status"] == "ocr_feasibility_unverified_not_answers"
    assert data["page"] == 1
    assert data["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert data["engine_version"] == "5.5.3"
    assert data["language"] == "eng"
    assert data["dpi"] == 300
    assert data["page_segmentation_mode"] == 6
    assert data["image_width"] == 2550
    assert data["image_height"] == 3301  # PDFium rounds rendered dimensions upward.
    assert data["text"] == "SYNTHETIC"
    assert data["words"][0]["confidence"] == 95.25
    assert data["words"][0]["left"] == 10
    assert data["words"][0]["top"] == 20
    assert "ocr_unverified" in data["flags"]
    assert len(data["render_sha256"]) == 64
    assert str(root) not in json.dumps(data)
    assert (root / SOURCE).read_bytes() == original
    assert len(fake_engine) == 2
    assert not list((root / "outputs").glob(".ocr-working-*"))
    assert not list((root / "outputs").glob(".staging-*"))
    assert run_ocr(root, SOURCE, 1) != folder


def test_missing_engine_is_actionable_and_does_not_publish(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: None)
    with pytest.raises(OcrError, match="install"):
        run_ocr(root, SOURCE, 1)
    assert not (root / "outputs").exists()


@pytest.mark.parametrize("page", [0, -1, True, "1", 2])
def test_invalid_page_never_invokes_ocr(
    root: Path, page: int, fake_engine: list[list[str]]
) -> None:
    with pytest.raises((OcrError, InventoryError), match="page"):
        run_ocr(root, SOURCE, page)
    assert fake_engine == []


@pytest.mark.parametrize("source", ["../outside.pdf", "/tmp/outside.pdf", "README.md"])
def test_only_inventory_support_sources_are_allowed(
    root: Path, source: str, fake_engine: list[list[str]]
) -> None:
    with pytest.raises(OcrError, match="supporting"):
        run_ocr(root, Path(source), 1)
    assert fake_engine == []


def test_symlink_source_and_output_rejected(root: Path, fake_engine: list[list[str]]) -> None:
    link = root / SOURCE.parent / "link.pdf"
    link.symlink_to(root / SOURCE)
    with pytest.raises(OcrError, match="supporting"):
        run_ocr(root, link.relative_to(root), 1)
    (root / "elsewhere").mkdir()
    (root / "outputs").symlink_to(root / "elsewhere")
    with pytest.raises(InventoryError, match="output"):
        run_ocr(root, SOURCE, 1)
    assert fake_engine == []


@pytest.mark.parametrize("value", [0, -1, True, "30"])
def test_limits_are_strict(value: int) -> None:
    with pytest.raises(OcrError, match="limit"):
        OcrLimits(timeout_seconds=value)


def test_pixel_limit_is_checked_before_rendering(root: Path, fake_engine: list[list[str]]) -> None:
    with pytest.raises(OcrError, match="pixel limit"):
        run_ocr(root, SOURCE, 1, limits=OcrLimits(max_pixels=100))
    assert not list((root / "outputs").glob("ocr-*"))


@pytest.mark.parametrize("mode", ["timeout", "nonzero", "malformed", "oversize", "badbox"])
def test_engine_failures_are_safe_and_leave_no_published_or_temporary_results(
    root: Path, fake_engine: list[list[str]], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "--version" in command:
            kwargs["stdout"].write(b"tesseract 5.5.3\n")  # type: ignore[union-attr]
            return subprocess.CompletedProcess(command, 0)
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 1, stderr=b"PRIVATE ERROR")
        if mode == "nonzero":
            return subprocess.CompletedProcess(command, 1, stderr=b"PRIVATE ERROR")
        value = {
            "malformed": "PRIVATE INVALID TSV",
            "oversize": "x" * 500,
            "badbox": TSV.replace("\t100\t30\t", "\t999999\t30\t"),
        }[mode]
        kwargs["stdout"].write(value.encode())  # type: ignore[union-attr]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(OcrError) as error:
        run_ocr(root, SOURCE, 1, limits=OcrLimits(max_output_bytes=400))
    assert "PRIVATE" not in str(error.value)
    assert list((root / "outputs").iterdir()) == []


def test_blank_ocr_result_is_explicit(
    root: Path, fake_engine: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "TSV", HEADER)
    folder = run_ocr(root, SOURCE, 1)
    data = json.loads((folder / "ocr.json").read_text())
    assert data["text"] == ""
    assert "no_ocr_text" in data["flags"]


def test_source_mutation_during_ocr_prevents_publication(
    root: Path, fake_engine: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = subprocess.run

    def mutate(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        result = original(command, **kwargs)  # type: ignore[arg-type]
        if "--version" not in command:
            (root / SOURCE).write_bytes(b"changed")
        return result

    monkeypatch.setattr(subprocess, "run", mutate)
    with pytest.raises(InventoryError, match="changed"):
        run_ocr(root, SOURCE, 1)
    assert list((root / "outputs").iterdir()) == []


def test_cli_counts_only(
    root: Path, fake_engine: list[list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert main(["ocr", "--root", str(root), "--source", str(SOURCE), "--page", "1"]) == 0
    captured = capsys.readouterr()
    assert "ocr.json" in captured.out
    assert "SYNTHETIC" not in captured.out + captured.err
    assert captured.err == ""


@pytest.mark.ocr
@pytest.mark.skipif(os.environ.get("BD_RUN_OCR") != "1", reason="Opt in with BD_RUN_OCR=1")
def test_real_tesseract_reads_synthetic_scan_exactly(root: Path) -> None:
    with pdfium.PdfDocument(str(root / SOURCE)) as document:
        page = document[0]
        textpage = page.get_textpage()
        try:
            assert textpage.count_chars() == 0
        finally:
            textpage.close()
            page.close()
    folder = run_ocr(root, SOURCE, 1)
    data = json.loads((folder / "ocr.json").read_text())
    expected = [
        "SYNTHETIC OCR SAMPLE",
        "August 31, 2026",
        "1,234,567.89",
        "001234",
        "Assets 9,876.54",
        "Liabilities (123.45)",
    ]
    assert all(value in data["text"] for value in expected), data["text"]
    words = data["words"]
    assert len(words) > 0
    assert all(0 <= word["confidence"] <= 100 for word in words)


@pytest.mark.parametrize(
    "output",
    [
        TSV.replace("95.25", "nan"),
        TSV.replace("95.25", "101"),
        TSV.replace("\t10\t20\t", "\t-1\t20\t"),
        TSV.replace("\t1\t1\t1\t1\t1\t", "\t2\t1\t1\t1\t1\t"),
        TSV.replace("SYNTHETIC\n", "\n"),
        TSV.replace("\t100\t30\t", "\ttext\t30\t"),
        HEADER + "5\t1\n",
    ],
)
def test_malformed_engine_word_data_is_not_published(
    root: Path, fake_engine: list[list[str]], monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setitem(globals(), "TSV", output)
    with pytest.raises(OcrError):
        run_ocr(root, SOURCE, 1)
    assert list((root / "outputs").iterdir()) == []


def test_unsupported_engine_version_is_explicit(
    root: Path, fake_engine: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        kwargs["stdout"].write(b"tesseract 4.1.1\n")  # type: ignore[union-attr]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OcrError, match="5.x"):
        run_ocr(root, SOURCE, 1)
    assert list((root / "outputs").iterdir()) == []


def test_cli_engine_failure_does_not_expose_raw_diagnostics(
    root: Path,
    fake_engine: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("PRIVATE engine error")

    monkeypatch.setattr(subprocess, "run", fail)
    assert main(["ocr", "--root", str(root), "--source", str(SOURCE), "--page", "1"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cannot execute" in captured.err
    assert "PRIVATE" not in captured.err
    assert list((root / "outputs").iterdir()) == []
