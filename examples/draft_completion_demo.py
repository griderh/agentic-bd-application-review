"""Complete a real public blank with fictional evidence only; never a business submission."""

import argparse
import hashlib
import json
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pypdfium2 as pdfium
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import (
    AnswerProposal,
    AnswerValue,
    ApplicationRequirements,
    Citation,
    IdentifierValue,
    MultiSelectValue,
    NarrativeValue,
    Requirement,
    RequirementKind,
    SingleSelectValue,
    TextValue,
)
from bd_packet_builder.draft import (
    DraftDecision,
    DraftRequest,
    DraftReview,
    DraftSource,
    run_draft,
)
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.layout import MappedResponse, PageBox, ResponseLayout
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.responses import NarrativeRegion, wrap_text
from bd_packet_builder.review import AnswerProposals
from examples.broward_response_layout import SOURCE, VERSION, _mapping


def prepare(root: Path, *, overflow: bool) -> tuple[Path, Path, Path]:
    root = root.resolve(strict=True)
    original = read_local_input(root, SOURCE, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
    if hashlib.sha256(original).hexdigest() != VERSION:
        raise ValueError("Example requires the independently mapped public blank version")
    if (root / "outputs").resolve() != root / "outputs":
        raise ValueError("Output must not resolve through a symlink")
    data = root / "outputs" / f"draft-demo-{uuid4().hex}" / "fictional-root"
    (data / SOURCE).parent.mkdir(parents=True)
    (data / SOURCE).write_bytes(original)
    (data / "outputs").mkdir()
    with pdfium.PdfDocument(original) as document:
        pages = {}
        for number in (1, 2, 4, 5):
            with closing(document[number - 1]) as page, closing(page.get_textpage()) as text:
                pages[number] = text.get_text_bounded().replace("\r\n", "\n")
    mapped = _mapping(pages)
    name = Requirement(
        requirement_id="broward-firm-name",
        application_sha256=VERSION,
        page=1,
        instruction="Name of Firm:",
        kind="text",
    )
    crd = Requirement(
        requirement_id="broward-crd",
        application_sha256=VERSION,
        page=1,
        instruction="Firms CRD Number:",
        kind="identifier",
    )
    missing = Requirement(
        requirement_id="broward-dtc",
        application_sha256=VERSION,
        page=1,
        instruction="Broker Dealer/DTC Number:",
        kind="identifier",
    )
    signing_kinds: tuple[tuple[RequirementKind, str], ...] = (
        ("signature", "Signature"),
        ("signature_date", "Date"),
    )
    signing = tuple(
        Requirement(
            requirement_id=f"broward-{kind}",
            application_sha256=VERSION,
            page=5,
            instruction=instruction,
            kind=kind,
        )
        for kind, instruction in signing_kinds
    )
    layout = ResponseLayout(
        application_sha256=VERSION,
        responses=(
            MappedResponse(
                requirement=name,
                text_region=NarrativeRegion(
                    page=1, left=125.0, bottom=542.0, right=575.0, top=556.0
                ),
            ),
            MappedResponse(
                requirement=crd,
                text_region=NarrativeRegion(
                    page=1, left=151.0, bottom=526.0, right=290.0, top=540.0
                ),
            ),
            *mapped.responses,
        ),
    )
    short = (
        "This fictional firm specializes in public-sector fixed-income services. "
        "Its demonstration service includes plain-language research and a dedicated support team."
    )
    narrative = (
        " ".join(
            f"Demonstration service {number} provides fictional research, "
            "clear transaction explanations and dedicated public-sector client support."
            for number in range(1, 41)
        )
        if overflow
        else short
    )
    proof = Path("bd_agreements/supporting_data/FINRA_Certification/fictional-evidence.pdf")
    (data / proof).parent.mkdir(parents=True)
    canvas = Canvas(str(data / proof), pagesize=(612, 792), invariant=True)
    paragraphs = [
        "FICTIONAL EVIDENCE ONLY - NOT A REAL FIRM RECORD",
        "Legal name: Fictional Demonstration Dealer LLC.",
        "CRD: 001234",
        "Test eligibility: Primary dealer as defined by the Federal Reserve Bank of New York.",
        "Test offerings: Treasury Bills; Treasury Notes/Bonds; Other: Fictional Notes.",
        narrative,
    ]
    evidence_lines: list[str] = []
    for paragraph in paragraphs:
        wrapped = wrap_text(
            paragraph, 520.0, 10.0, lambda t, s: float(stringWidth(t, "Helvetica", s))
        )
        if wrapped is None:
            raise ValueError("Fictional evidence cannot fit")
        evidence_lines.extend(wrapped)
        evidence_lines.append("")
    for start in range(0, len(evidence_lines), 44):
        canvas.setFont("Helvetica", 10)
        for index, line in enumerate(evidence_lines[start : start + 44]):
            canvas.drawString(40, 740 - index * 14, line)
        canvas.showPage()
    canvas.save()
    inventory = build_inventory(data)
    source = inventory.sources[0]
    evidence = []
    with pdfium.PdfDocument(str(data / proof)) as document:
        for index in range(len(document)):
            with closing(document[index]) as page, closing(page.get_textpage()) as text:
                evidence.append(text.get_text_bounded().replace("\r\n", "\n"))

    def cite(quote: str) -> Citation:
        for index, text in enumerate(evidence):
            if quote in text:
                start = text.index(quote)
                return Citation(
                    source_id=source.source_id,
                    page=index + 1,
                    start=start,
                    end=start + len(quote),
                    quote=quote,
                )
        raise ValueError("Fictional evidence quotation missing")

    def proposed(
        identity: str, value: AnswerValue, citations: tuple[Citation, ...]
    ) -> AnswerProposal:
        return AnswerProposal(
            requirement_id=identity,
            outcome="proposed",
            value=value,
            confidence=1.0,
            citations=citations,
        )

    proposals = [
        proposed(
            name.requirement_id,
            TextValue(kind="text", value="Fictional Demonstration Dealer LLC"),
            (cite("Legal name: Fictional Demonstration Dealer LLC."),),
        ),
        proposed(
            crd.requirement_id,
            IdentifierValue(kind="identifier", value="001234"),
            (cite("CRD: 001234"),),
        ),
        proposed(
            "broward-q1",
            SingleSelectValue(kind="single_select", selected=("primary",)),
            (
                cite(
                    "Test eligibility: Primary dealer as defined by the "
                    "Federal Reserve Bank of New York."
                ),
            ),
        ),
        proposed(
            "broward-q2",
            MultiSelectValue.model_validate_json(
                json.dumps(
                    {
                        "kind": "multi_select",
                        "selected": ["treasury-bills", "treasury-notes", "other-instrument"],
                        "write_ins": [{"option_id": "other-instrument", "text": "Fictional Notes"}],
                    }
                )
            ),
            (
                cite(
                    "Test offerings: Treasury Bills; Treasury Notes/Bonds; Other: Fictional Notes."
                ),
            ),
        ),
        proposed(
            "broward-q11",
            NarrativeValue(kind="narrative", value=narrative),
            tuple(
                Citation(source_id=source.source_id, page=i + 1, start=0, end=len(text), quote=text)
                for i, text in enumerate(evidence)
            ),
        ),
        AnswerProposal(
            requirement_id=missing.requirement_id,
            outcome="missing_evidence",
            explanation="No DTC number is supplied by the fictional evidence.",
        ),
        *(
            AnswerProposal(
                requirement_id=req.requirement_id,
                outcome="deferred_to_signing",
                explanation="Human electronic signing only.",
            )
            for req in signing
        ),
    ]
    request = DraftRequest(
        mode="fictional",
        source=SOURCE.as_posix(),
        requirements=ApplicationRequirements(
            requirements=(name, crd, *(m.requirement for m in mapped.responses), missing, *signing)
        ),
        layout=layout,
        proposals=AnswerProposals(proposals=tuple(proposals)),
        sources=(DraftSource(path=proof.as_posix(), sha256=source.sha256),),
        attachments=(source.source_id,),
        protected_regions=(PageBox(page=5, left=0.0, bottom=0.0, right=612.0, top=792.0),),
    )
    request_path = data / "outputs/request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n")
    review = DraftReview(
        request_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),
        reviewer="Synthetic development fixture, not a business reviewer",
        attachment_source_ids=(source.source_id,),
        decisions=tuple(
            DraftDecision(
                requirement_id=p.requirement_id,
                decision="draft_verified",
                source_approved=True,
                evidence_support_confirmed=True,
                placement_confirmed=True,
                reason=(
                    "Fictional writer test against a developer-mapped public blank; "
                    "not real approval."
                ),
            )
            for p in proposals
            if p.outcome == "proposed"
        ),
    )
    review_path = data / "outputs/review.json"
    review_path.write_text(review.model_dump_json(indent=2) + "\n")
    if read_local_input(root, SOURCE, Path("bd_agreements/Blank"), 64 * 1024 * 1024) != original:
        raise ValueError("Original public blank changed during preparation")
    return data, request_path.relative_to(data), review_path.relative_to(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--overflow", action="store_true")
    args = parser.parse_args()
    data, request, review = prepare(args.root, overflow=args.overflow)
    result = run_draft(data, request, review)
    print(f"Fictional, incomplete draft only: {result / 'draft-packet.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
