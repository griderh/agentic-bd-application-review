"""Run a synthetic-only draft validation example; requires development dependencies."""

import argparse
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import Citation, IdentifierValue, TextValue
from bd_packet_builder.evidence import extract_evidence
from bd_packet_builder.fact_sheet import Fact, FactSheet, FactSheetError, run_fact_sheet_check
from bd_packet_builder.fact_sheet_excel import export_workbook
from bd_packet_builder.inventory import build_inventory

DEMO_DATE = date(2026, 10, 21)


def create_demo(root: Path) -> Path:
    """Keep all synthetic source/input/report files beneath a unique outputs/ run."""
    root = root.resolve(strict=True)
    output = root / "outputs"
    if output.resolve() != output:
        raise FactSheetError("Demo output folder must not resolve through a symlink")
    output.mkdir(exist_ok=True)
    final = output / f"fact-sheet-demo-{uuid4().hex}"
    with TemporaryDirectory(prefix=".fact-sheet-demo-", dir=output) as directory:
        staging = Path(directory)
        demo_root = staging / "synthetic-root"
        source = demo_root / "bd_agreements/supporting_data/synthetic-firm.pdf"
        source.parent.mkdir(parents=True)
        canvas = Canvas(str(source))
        for index, line in enumerate(
            [
                "SYNTHETIC EXAMPLE ONLY - NOT REAL FIRM DATA",
                "Legal name: Example Demonstration LLC",
                "Firm CRD: 001234",
                "Chief Compliance Officer: Alex Example",
            ]
        ):
            canvas.drawString(50, 740 - index * 30, line)
        canvas.save()
        page = extract_evidence(demo_root, build_inventory(demo_root)).documents[0].pages[0]
        citation = Citation(
            source_id=page.source_id, page=1, start=0, end=len(page.text), quote=page.text
        )
        name = Fact(
            fact_id="legal-name-1",
            key="firm.legal_name",
            category="firm_identity",
            value=TextValue(kind="text", value="Example Demonstration LLC"),
            owner="Synthetic business steward",
            reviewed_by="Synthetic domain reviewer",
            reviewed_on=date(2026, 10, 1),
            review_due=date(2027, 1, 1),
            effective_from=date(2026, 1, 1),
            citations=(citation,),
        )
        identifier = Fact.model_validate(
            {
                **dict(name),
                "fact_id": "crd-1",
                "key": "firm.crd",
                "value": IdentifierValue(kind="identifier", value="001234"),
            }
        )
        signer = Fact.model_validate(
            {
                **dict(name),
                "fact_id": "cco-1",
                "key": "signer_roles.cco",
                "category": "signer_role",
                "role": "Chief Compliance Officer",
                "value": TextValue(kind="text", value="Alex Example"),
                "review_due": date(2026, 10, 20),
            }
        )
        sheet = FactSheet(
            version_id="synthetic-draft-001",
            steward="Synthetic business steward",
            facts=(name, identifier, signer),
        )
        draft = Path("outputs/fact-sheets/synthetic-draft.xlsx")
        (demo_root / draft).parent.mkdir(parents=True)
        (demo_root / draft).write_bytes(export_workbook(sheet, build_inventory(demo_root)))
        report = run_fact_sheet_check(demo_root, draft, as_of=DEMO_DATE)
        relative = (report / "fact-sheet.xlsx").relative_to(staging)
        staging.rename(final)
    return final / relative


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic-only fact-sheet validation demo")
    parser.add_argument("--root", type=Path, default=Path("."), help="Explicit local data root")
    args = parser.parse_args()
    try:
        result = create_demo(args.root)
    except (FactSheetError, OSError):
        parser.exit(
            1, "Synthetic demo failed; check root/output paths and local write permissions.\n"
        )
    print(f"Synthetic-only draft demo; not approved business facts: {result}")
