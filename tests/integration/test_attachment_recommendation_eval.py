"""Opt-in semantic evaluation of general supporting-document recommendations."""

import json
import os
from io import BytesIO
from typing import Literal

import pytest
from PIL import Image, ImageDraw, ImageFont

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.contracts import Contract, Nonblank
from bd_packet_builder.foundry import FoundryConfig, request_structured
from bd_packet_builder.scan import FoundryScanReader


class AttachmentDecision(Contract):
    decision: Literal["include", "exclude", "review_required"]
    reason: Nonblank


class AttachmentNextAction(Contract):
    action: Literal["inspect_attachment_page", "include", "exclude", "review_required"]
    reason: Nonblank


@pytest.mark.skipif(
    os.environ.get("BD_RUN_ATTACHMENT_EVAL") != "1",
    reason="Opt in with BD_RUN_ATTACHMENT_EVAL=1; paid synthetic image identification evaluation",
)
@pytest.mark.parametrize("identified", [True, False])
def test_visual_reader_identifies_a_rendered_yearless_table_not_unlabelled_shapes(
    identified: bool,
) -> None:
    with Image.new("RGB", (1000, 480), "white") as image:
        draw = ImageDraw.Draw(image)
        if identified:
            draw.text(
                (40, 40),
                "Example Markets\nCallable League Table\nExample LLC",
                fill="black",
                font=ImageFont.load_default(size=36),
            )
        for y in range(250, 430, 30):
            draw.line((40, y, 850, y), fill="gray", width=2)
        with BytesIO() as buffer:
            image.save(buffer, format="PNG")
            transcript = FoundryScanReader(
                FoundryConfig(
                    endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
                    deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
                    timeout_seconds=180,
                ),
                allow_paid=True,
            ).transcribe(buffer.getvalue())
    assert (transcript.identification is not None) == identified
    assert transcript.reporting_period is None
    if identified:
        assert "league" in transcript.identification.description.casefold()


CASES = (
    (
        "An issuer checklist explicitly requests the firm's audited FY2025 statements. "
        "The candidate is the firm's audited FY2025 financial report, with matching entity "
        "and printed year.",
        "include",
    ),
    (
        "The form asks the firm to describe its U.S. agency market capabilities. The candidate "
        "is a current corporate-agency business overview describing the firm's services and "
        "capabilities. It is not a market snapshot or an audited performance record.",
        "include",
    ),
    (
        "The issuer requests the firm's sustainable-finance activities. The candidate is a "
        "current firm statement describing the firm's own role in those activities and covers "
        "the requested period.",
        "include",
    ),
    (
        "The form asks for agency underwriting league-table experience during FY2025. An "
        "approved packet from another municipality linked a league table to a question about "
        "the same firm-wide underwriting experience. The candidate table is for this firm, "
        "the same ranking category and FY2025.",
        "include",
    ),
    (
        "The current form asks only for settlement instructions. A prior packet from another "
        "municipality included a broad U.S. agency market snapshot, but its linked question "
        "and reason for inclusion are unavailable. The snapshot does not contain settlement "
        "instructions.",
        "exclude_or_review",
    ),
    (
        "The current form requests settlement and delivery instructions for the firm's "
        "identified legal entity and account. The candidate is the approved confidential "
        "instruction document for that same entity and account.",
        "include",
    ),
    (
        "The form asks for agency market positioning. The official FY2025 table is already "
        "included. Two approved, readable snapshots show the same firm's category and "
        "2026 reporting year, but no full printed publication date. The candidate PDF has "
        "repository-extracted version_date=2026-07-14, version_timestamp="
        "2026-07-14T09:41:16-04:00, version_date_basis=pdf_creation. An equivalent PNG has "
        "version_date=2026-07-13, version_date_basis=filename and no capture metadata. "
        "Neither has a content or reporting-period contradiction.",
        "include",
    ),
    (
        "The form asks for agency market positioning. The official FY2025 table is already "
        "included. The candidate is an approved readable 2026 snapshot PNG, "
        "version_date=2026-07-13, version_date_basis=filename. An equivalent approved readable "
        "2026 PDF snapshot is available with version_date=2026-07-14 and "
        "version_date_basis=pdf_creation. Their firm, category and scope match. "
        "No full printed publication date is available. Only the latest equivalent supplement "
        "is needed, not both copies.",
        "exclude",
    ),
    (
        "The form asks for callable-agency market positioning without specifying a reporting "
        "period. The official FY2025 table is already included. Visual inspection of the "
        "approved candidate PDF returned status=identified, transcript.readable=false: "
        "the small numerical rows cannot be transcribed reliably, but visible cues "
        "'Bloomberg', 'Callable League Table' and the firm's name identify a relevant table. "
        "No year or printed date is visible. An older comparable PNG has the same identifying "
        "contents. The PDF's version_date=2026-07-14, basis=pdf_creation; the PNG's "
        "version_date=2026-07-13, basis=filename. There are no content contradictions.",
        "include",
    ),
    (
        "The form asks for callable-agency market positioning with no explicit period. "
        "The candidate PNG is visually identified as a relevant Bloomberg callable league "
        "table for the firm; neither it nor the comparable PDF has a visible year. The PNG's "
        "version_date=2026-07-13, basis=filename. The PDF has matching visible identifying "
        "contents and version_date=2026-07-14, basis=pdf_creation. Both are approved. "
        "Only the latest equivalent supplement is needed.",
        "exclude",
    ),
    (
        "The form asks only for callable-agency market positioning. The candidate is a "
        "newer PDF, version_date=2026-07-14, basis=pdf_creation. Its clear identifying "
        "contents describe unrelated commodity futures trading, not agency market positioning. "
        "An older approved snapshot is clearly a relevant callable-agency league table. "
        "Neither has a printed year. A newer creation date does not change the candidate's scope.",
        "exclude",
    ),
    (
        "The form explicitly requires a FY2025 callable-agency league table. The candidate "
        "PDF is clearly a Bloomberg league table printed for FY2024, but its version_date "
        "is 2026-07-14, basis=pdf_creation. A matching approved FY2025 official table is "
        "already included. There is no separate request or answer-support need for FY2024.",
        "exclude_or_review",
    ),
)


@pytest.mark.skipif(
    os.environ.get("BD_RUN_ATTACHMENT_EVAL") != "1",
    reason="Opt in with BD_RUN_ATTACHMENT_EVAL=1; paid synthetic attachment-reasoning evaluation",
)
@pytest.mark.parametrize(("scenario", "expected"), CASES)
def test_model_recommends_support_from_request_content_and_context(
    scenario: str, expected: str
) -> None:
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation only: no tools. Classify the candidate document for this current packet. Return
include only when its described contents support the current requirement; use exclude when it
does not; use review_required if the available facts cannot establish relevance. Prior inclusion
alone is never sufficient. Keep the rationale tied to the supplied scenario.
""",
        input_json=json.dumps({"scenario": scenario}),
        response_type=AttachmentDecision,
        max_output_tokens=1024,
    )
    if expected == "exclude_or_review":
        assert result.value.decision in {"exclude", "review_required"}
    else:
        assert result.value.decision == expected


@pytest.mark.skipif(
    os.environ.get("BD_RUN_ATTACHMENT_EVAL") != "1",
    reason="Opt in with BD_RUN_ATTACHMENT_EVAL=1; paid synthetic inspection-routing evaluation",
)
@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (
            "A scanned market supplement plausibly supports a firm-background requirement. "
            "OCR did not read its title or period. No visual inspection has been attempted. "
            "The image tool is enabled and there is image budget remaining.",
            "inspect_attachment_page",
        ),
        (
            "A scanned certificate plausibly supports an issuer's registration requirement. "
            "OCR was insufficient. The one permitted visual inspection returned unreadable "
            "with no identifiable title or subject. Repeating it would use the cached result. "
            "The document is still only a plausible lead, not established support.",
            "review_required",
        ),
    ],
)
def test_model_inspects_once_then_escalates_to_the_reviewer(scenario: str, expected: str) -> None:
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation only: do not execute tools. Return the next action for the supplied attachment
situation. Use review_required for a remaining ambiguity and explain the question for the
human reviewer. Do not treat document identification as verification of its figures.
""",
        input_json=json.dumps({"scenario": scenario}),
        response_type=AttachmentNextAction,
        max_output_tokens=1024,
    )
    assert result.value.action == expected
