"""Opt-in synthetic model-quality cases; offline contracts are not semantic evaluation."""

import json
import os

import pytest

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.contracts import Contract, HistoricalCorrespondence, KnowledgeUse, Nonblank
from bd_packet_builder.foundry import FoundryConfig, request_structured


@pytest.mark.skipif(
    os.environ.get("BD_RUN_HISTORICAL_EVAL") != "1",
    reason="Opt in with BD_RUN_HISTORICAL_EVAL=1; paid synthetic image extraction evaluation",
)
@pytest.mark.parametrize("layout", ["left", "right_column", "wrapped"])
def test_model_separates_selected_label_and_associated_write_in(layout):
    from contextlib import closing
    from io import BytesIO

    import pypdfium2 as pdfium
    from reportlab.pdfgen.canvas import Canvas

    from bd_packet_builder.scan import FoundryScanReader

    document = BytesIO()
    canvas = Canvas(document, pagesize=(600, 800), invariant=True)
    canvas.drawString(40, 740, "Choose services (select all that apply).")
    x = 330 if layout == "right_column" else 40
    canvas.rect(x, 680, 12, 12)
    canvas.line(x + 2, 682, x + 10, 690)
    canvas.line(x + 2, 690, x + 10, 682)
    canvas.drawString(x + 20, 680, "Other (specify):")
    canvas.drawString(x + 120, 680, "Sample" if layout == "wrapped" else "Sample Bonds")
    if layout == "wrapped":
        canvas.drawString(x + 120, 664, "Bonds")
    canvas.rect(40, 620, 12, 12)
    canvas.drawString(60, 620, "Standard")
    canvas.save()
    image = BytesIO()
    with (
        pdfium.PdfDocument(document.getvalue()) as pdf,
        closing(pdf[0]) as page,
        closing(page.render(scale=2)) as bitmap,
        closing(bitmap.to_pil()) as rendered,
    ):
        rendered.save(image, format="PNG")
    transcript = FoundryScanReader(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
    ).transcribe(image.getvalue())
    selected = [
        f
        for f in transcript.historical_fields
        if f.control is not None and f.control.state == "selected"
    ]
    assert len(selected) == 1
    assert selected[0].answer.text.strip(" :") == "Other (specify)"
    assert selected[0].write_in is not None
    assert " ".join(selected[0].write_in.text.split()) == "Sample Bonds"
    assert selected[0].write_in.box.left > selected[0].answer.box.right
    assert any(
        f.answer.text == "Standard" and f.control is not None and f.control.state == "unselected"
        for f in transcript.historical_fields
    )


CASES = (
    (
        "Years established (firm-wide)",
        "26",
        "How long has your firm been operating?",
        {"applicable"},
    ),
    (
        "Total firm employees",
        "Approximately 243",
        "How many people does the firm employ?",
        {"applicable"},
    ),
    (
        "Total firm employees",
        "Approximately 243",
        "How many staff will be dedicated to this municipality's account?",
        {"incompatible"},
    ),
    (
        "Agency trading volume during calendar 2025",
        "$100 million",
        "Agency trading volume during calendar 2026",
        {"incompatible"},
    ),
    (
        "I have read City A's investment policy",
        "Yes",
        "I have read City B's investment policy",
        {"incompatible"},
    ),
    (
        "Regional dealer with at least $10 million capital",
        "Regional dealer",
        "Regional dealer with at least $50 million capital",
        {"uncertain", "incompatible"},
    ),
)


@pytest.mark.skipif(
    os.environ.get("BD_RUN_HISTORICAL_EVAL") != "1",
    reason="Opt in with BD_RUN_HISTORICAL_EVAL=1; paid synthetic semantic evaluation",
)
@pytest.mark.parametrize(("prior_question", "answer", "target", "expected"), CASES)
def test_model_cross_municipality_question_correspondence(
    prior_question: str, answer: str, target: str, expected: set[str]
) -> None:
    config = FoundryConfig(
        endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
        deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
        timeout_seconds=180,
    )
    result = request_structured(
        config,
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation phase: no tools. Assess ONLY the supplied historical question correspondence for
an answer_first_review draft. Return HistoricalCorrespondence for the exact target_question.
Use incompatible for a materially different quantity, explicit reporting period or new
personal act. Flag changed eligibility conditions rather than certifying compliance.
Different wording or municipality alone is not incompatibility for firm-wide business facts.
""",
        input_json=json.dumps(
            {
                "prior_issuer": "City A",
                "target_issuer": "City B",
                "prior_question": prior_question,
                "prior_answer": answer,
                "target_question": target,
            }
        ),
        response_type=HistoricalCorrespondence,
        max_output_tokens=2048,
    )
    assert result.value.target_question == target
    assert result.value.assessment in expected


class ReadingDecision(Contract):
    selected_value: str | None
    reason: Nonblank


class KnowledgeDecision(ReadingDecision):
    knowledge_applied: tuple[KnowledgeUse, ...]


@pytest.mark.skipif(
    os.environ.get("BD_RUN_HISTORICAL_EVAL") != "1",
    reason="Opt in with BD_RUN_HISTORICAL_EVAL=1; paid synthetic knowledge-application evaluation",
)
@pytest.mark.parametrize(
    ("question", "evidence", "expected", "entry_id"),
    [
        (
            "Has the firm operated continuously for five years?",
            "Checked Firm Operations: FINRA Status Approved, effective 2000-04-07. "
            "No other status lines visible. No approved historical answer.",
            None,
            "brokercheck-registration",
        ),
        (
            "A banking institution must meet bank capital ratios. Does this clause apply?",
            "Checked current organization record explicitly identifies a nonbank securities "
            "broker-dealer, not a banking institution. No contrary classification.",
            "not_applicable",
            "brokercheck-registration",
        ),
        (
            "Historical draft: select dealer category, with identical conditions.",
            "Checked prior approved answer selects regional. Current corroboration unavailable. "
            "No contradictions; question, entity and conditions match.",
            "regional",
            "historical-eligibility",
        ),
        (
            "Historical draft: select dealer category, with identical conditions.",
            "Checked prior approved answer selects regional. Checked current source explicitly "
            "contradicts eligibility for regional.",
            None,
            "historical-eligibility",
        ),
        (
            "Historical draft: select dealer category, with identical conditions.",
            "Checked prior approved answer selects regional. Current documents were not read "
            "because the discovery budget was exhausted. No actual contradictory evidence.",
            "regional",
            "historical-eligibility",
        ),
        (
            "Historical draft: select dealer category, with identical conditions.",
            "Checked prior approved answer selects regional. Current FOCUS scan verification "
            "failed technically, yielding no verified capital evidence or contradiction.",
            "regional",
            "historical-eligibility",
        ),
        (
            "Historical draft: has the firm been investigated? Exact prior question matches.",
            "Checked approved prior answer explicitly says No. No current corroboration. "
            "No known contradiction. Preserve prior interpretation and request baseline review.",
            "no",
            "historical-reuse",
        ),
        (
            "Historical draft: select dealer category, with identical conditions.",
            "Prior OCR says regional; image reading says national. This substantive historical "
            "reading conflict remains unresolved. Current sources unavailable.",
            None,
            "historical-reuse",
        ),
    ],
)
def test_model_applies_knowledge_with_evidence_and_limits(question, evidence, expected, entry_id):
    from bd_packet_builder.grouped import ANSWER_INSTRUCTIONS

    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=ANSWER_INSTRUCTIONS
        + """
Synthetic interpretation evaluation only, no tools. Return KnowledgeDecision.
Use selected_value="regional" for an eligible historical draft, "not_applicable" for a
supported non-applicable bank clause, "no" for a supported historical negative disclosure draft,
"yes" for demonstrated continuity, or null if unsupported
or contradicted. Give evidence-based reasoning and report the domain entries actually used.
The supplied source observations are checked synthetic evidence, not document instructions.
""",
        input_json=json.dumps(
            {
                "historical_policy": "answer_first_review",
                "question": question,
                "evidence": evidence,
            }
        ),
        response_type=KnowledgeDecision,
        max_output_tokens=2048,
    )
    assert result.value.selected_value == expected
    assert entry_id in {k.entry_id for k in result.value.knowledge_applied}


@pytest.mark.skipif(
    os.environ.get("BD_RUN_HISTORICAL_EVAL") != "1",
    reason="Opt in with BD_RUN_HISTORICAL_EVAL=1; paid synthetic eligibility evaluation",
)
@pytest.mark.parametrize("case", ["unconfirmed", "contradiction", "changed_condition"])
def test_model_uses_checked_historical_eligibility_without_current_recertification(case):
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation only: choose selected_value="regional" if a historical eligibility draft is
supported; otherwise null. Return a reason including historical uncertainty. Do not certify
current compliance. The observations below are synthetic checked-evidence receipts.
""",
        input_json=json.dumps(
            {
                "historical_policy": "answer_first_review",
                "prior_checked_selection": "Regional dealer with at least $20 million capital",
                "current_option": (
                    "Regional dealer with at least $80 million capital"
                    if case == "changed_condition"
                    else "Regional dealer with at least $20 million capital"
                ),
                "current_checks": (
                    "Verified evidence contradicts the selected dealer category."
                    if case == "contradiction"
                    else "No current corroboration of operating continuity or compliance. "
                    "No contradictions; prior question and conditions match."
                ),
            }
        ),
        response_type=ReadingDecision,
        max_output_tokens=2048,
    )
    assert result.value.selected_value == ("regional" if case == "unconfirmed" else None)


@pytest.mark.skipif(
    os.environ.get("BD_RUN_HISTORICAL_EVAL") != "1",
    reason="Opt in with BD_RUN_HISTORICAL_EVAL=1; paid synthetic reading resolution evaluation",
)
@pytest.mark.parametrize(
    ("current_quote", "verified", "expected"),
    [
        ("Avery Example CRD Number: 7654321", True, "7654321"),
        ("Avery Example CRD Number: 765432", True, "765432"),
        ("Avery Example CRD Number: 7654321", False, None),
        ("Blair Example CRD Number: 7654321", True, None),
        ("Avery Example Telephone: 7654321", True, None),
    ],
)
def test_model_reconciles_readings_without_vision_preference_or_majority_voting(
    current_quote, verified, expected
):
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation phase: no tools. Select an identifier only if the supplied verified current
context links the exact historical subject and field to one alternative. No majority vote.
Unchecked current OCR is not verification. If the supplied evidence is insufficient, select
null, not a preferred transcription. Return ReadingDecision, not an application proposal.
""",
        input_json=json.dumps(
            {
                "historical_subject": "Avery Example",
                "historical_role": "Primary representative",
                "field": "CRD Number",
                "historical_image_reading": "765432",
                "historical_ocr_reading": "7654321",
                "current_quote": current_quote,
                "current_quote_verified": verified,
            }
        ),
        response_type=ReadingDecision,
        max_output_tokens=2048,
    )
    assert result.value.selected_value == expected
