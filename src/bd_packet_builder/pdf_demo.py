"""A deliberately narrow native-field feasibility experiment, not packet completion."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter

DEMO_VALUE = "SYNTHETIC POC - NOT FOR SUBMISSION"
_FIRM_FIELDS = ("Name of Firm", "Firm_name")


class PdfDemoError(ValueError):
    """Safe, actionable validation errors with no extracted document content."""


@dataclass(frozen=True)
class PdfInspection:
    page_count: int
    text_field_count: int


def _reader(path: Path) -> PdfReader:
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise PdfDemoError("Encrypted PDFs are not supported by the feasibility demo")
    if not reader.pages:
        raise PdfDemoError("PDF has no pages")
    return reader


def inspect_pdf(path: Path) -> PdfInspection:
    reader = _reader(path)
    fields = reader.get_fields() or {}
    return PdfInspection(
        page_count=len(reader.pages),
        text_field_count=sum(field.get("/FT") == "/Tx" for field in fields.values()),
    )


def _render_first_page(path: Path, output: Path) -> None:
    # PDFium is isolated here because its Python API does not ship type information.
    with pdfium.PdfDocument(str(path)) as document:
        document.init_forms()
        page = document[0]
        try:
            bitmap = page.render(scale=1)
            try:
                image = bitmap.to_pil()
                try:
                    image.save(output)
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()


def create_demo(root: Path, source: Path) -> Path:
    """Write only a fixed synthetic firm name; preserve every other form field.

    Only blank-tree PDFs are accepted. Outputs always go to a unique local outputs/
    run directory. No field names or values can be supplied by model/user input.
    """
    root = root.resolve(strict=True)
    blank_root = root / "bd_agreements" / "Blank"
    source_path = (root / source).resolve()
    if (
        source.is_absolute()
        or not source_path.is_relative_to(blank_root)
        or source_path.suffix.lower() != ".pdf"
    ):
        raise PdfDemoError("Source must be a relative PDF path within the blank forms folder")
    output_root = root / "outputs"
    if output_root.resolve() != output_root:
        raise PdfDemoError("Local output folder must not resolve through a symlink")

    reader = _reader(source_path)
    fields = reader.get_fields() or {}
    if any(field.get("/V") not in (None, "", "/Off") for field in fields.values()):
        raise PdfDemoError("Demo requires blank fields; prefilled or signed forms are not accepted")
    if any(field.get("/FT") == "/Sig" for field in fields.values()):
        raise PdfDemoError("Digital signature fields are not supported by this feasibility demo")
    field_names = [
        name for name in _FIRM_FIELDS if name in fields and fields[name].get("/FT") == "/Tx"
    ]
    if len(field_names) != 1:
        raise PdfDemoError("Demo requires exactly one supported native firm-name field")
    field_name = field_names[0]
    field_pages = reader.get_pages_showing_field(fields[field_name])
    if not field_pages or field_pages[0] is not reader.pages[0]:
        raise PdfDemoError("Demo requires the native firm-name field on the first page")

    input_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    output_root.mkdir(exist_ok=True)
    final = output_root / f"pdf-demo-{uuid4().hex}"
    with TemporaryDirectory(prefix=".staging-", dir=output_root) as temporary:
        staging = Path(temporary)
        writer = PdfWriter(clone_from=reader)
        try:
            writer.update_page_form_field_values(
                writer.pages[0], {field_name: DEMO_VALUE}, auto_regenerate=False
            )
            writer.add_metadata({"/Title": "Synthetic feasibility demo - NOT FOR SUBMISSION"})
            with (staging / "demo.pdf").open("xb") as stream:
                writer.write(stream)
        finally:
            writer.close()
        _render_first_page(source_path, staging / "before.png")
        _render_first_page(staging / "demo.pdf", staging / "after.png")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != input_hash:
            raise PdfDemoError("Source changed during the demo; output was not published")
        manifest = {
            "status": "synthetic_demo_not_for_submission",
            "input_sha256": input_hash,
            "output_sha256": hashlib.sha256((staging / "demo.pdf").read_bytes()).hexdigest(),
            "page_count": len(reader.pages),
            "field": field_name,
            "value": DEMO_VALUE,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(final)
    return final
