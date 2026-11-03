from datetime import UTC, datetime

import pytest

from bd_packet_builder.contracts import (
    AnswerProposal,
    ChoiceGroup,
    ChoiceOption,
    ChoiceWriteIn,
    Citation,
    HistoricalBasis,
    MultiSelectValue,
    OcrCitation,
    Requirement,
)
from bd_packet_builder.draft import verify_historical_context
from bd_packet_builder.historical_context import HistoricalContextCheck, control_option_id
from bd_packet_builder.inventory import Inventory
from bd_packet_builder.layout import MappedResponse, OptionPlacement, PageBox
from bd_packet_builder.scan import (
    HistoricalControl,
    HistoricalPageField,
    HistoricalPagePart,
    ScanTranscript,
)
from bd_packet_builder.visual import NormalizedBox


def field(left, selected, label="Other"):
    return HistoricalPageField(
        question=HistoricalPagePart(
            text="Select instruments",
            box=NormalizedBox(left=40, top=100, right=900, bottom=120),
        ),
        role=None,
        answer=HistoricalPagePart(
            text=label,
            box=NormalizedBox(left=left + 20, top=200, right=left + 90, bottom=220),
        ),
        control=HistoricalControl(
            state="selected" if selected else "unselected",
            box=NormalizedBox(left=left, top=200, right=left + 12, bottom=215),
        ),
    )


def test_duplicate_labels_use_question_and_column_not_a_global_other_match():
    requirement = Requirement(
        requirement_id="instruments",
        application_sha256="a" * 64,
        page=1,
        instruction="Select instruments",
        kind="multi_select",
        choices=ChoiceGroup(
            options=(
                ChoiceOption(option_id="left_other", label="Other_", instruction="Other_"),
                ChoiceOption(option_id="right_other", label="Other_", instruction="Other_"),
            )
        ),
    )
    placements = tuple(
        OptionPlacement(
            option_id=identity,
            control="checkbox",
            box=PageBox(page=1, left=x, right=x + 10, bottom=600, top=610),
            label_box=PageBox(page=1, left=x + 15, right=x + 80, bottom=600, top=610),
            label_quote="Other_",
        )
        for identity, x in (("left_other", 40.0), ("right_other", 340.0))
    )
    mapping = MappedResponse(requirement=requirement, options=placements)
    left, right = field(80, True), field(560, False)
    assert control_option_id(left, (left, right), requirement, mapping) == "left_other"
    assert control_option_id(right, (left, right), requirement, mapping) == "right_other"
    assert control_option_id(left, (left,), requirement, mapping) is None


def test_option_match_does_not_depend_on_whole_page_coordinates():
    requirement = Requirement(
        requirement_id="services",
        application_sha256="a" * 64,
        page=1,
        instruction="Select services",
        kind="single_select",
        choices=ChoiceGroup(
            options=(
                ChoiceOption(option_id="yes", label="Yes", instruction="Yes"),
                ChoiceOption(option_id="no", label="No", instruction="No"),
            )
        ),
    )
    selected = field(500, True, "Yes")
    assert control_option_id(selected, (selected,), requirement, None) == "yes"


@pytest.mark.parametrize("wrong", ["column", "page", "value"])
def test_write_in_must_belong_to_same_selected_control(tmp_path, wrong):
    source = "b" * 64
    requirement = Requirement(
        requirement_id="instruments",
        application_sha256="a" * 64,
        page=1,
        instruction="Select instruments",
        kind="multi_select",
        choices=ChoiceGroup(
            options=(
                ChoiceOption(option_id="other", label="Other", instruction="Other", write_in=True),
                ChoiceOption(option_id="bonds", label="Bonds", instruction="Bonds"),
            )
        ),
    )
    selected = field(80, True)
    transcript = ScanTranscript(
        readable=True,
        subject=None,
        text="",
        reporting_period=None,
        historical_fields=(selected,),
    )
    question = OcrCitation(
        evidence_kind="ocr",
        source_id=source,
        source_sha256="c" * 64,
        page=1,
        artifact_path=f"outputs/ocr-{'0' * 32}/ocr.json",
        artifact_sha256="d" * 64,
        render_sha256="e" * 64,
        word_start=0,
        word_end=1,
        quote="Select instruments",
    )
    answer = Citation(source_id=source, page=1, start=0, end=5, quote="Other")
    control = HistoricalContextCheck(
        prompt_version="scan-cross-check-v4",
        endpoint="https://example.openai.azure.com/openai/v1",
        deployment="test",
        field=selected,
        transcript=transcript,
        question=question,
        role=None,
        answer=answer,
    )
    written = Citation(
        source_id=source, page=2 if wrong == "page" else 1, start=6, end=21, quote="Fictional Notes"
    )
    write_field = HistoricalPageField(
        question=selected.answer,
        role=None,
        answer=HistoricalPagePart(
            text="Wrong Notes" if wrong == "value" else "Fictional Notes",
            box=NormalizedBox(
                left=600 if wrong == "column" else 190,
                top=200,
                right=800 if wrong == "column" else 390,
                bottom=220,
            ),
        ),
    )
    extra = control.model_copy(
        update={
            "field": write_field,
            "answer": written,
            "question": question.model_copy(update={"page": written.page}),
        }
    )
    proposal = AnswerProposal(
        requirement_id="instruments",
        outcome="proposed",
        confidence=1.0,
        value=MultiSelectValue(
            kind="multi_select",
            selected=("other",),
            write_ins=(ChoiceWriteIn(option_id="other", text="Fictional Notes"),),
        ),
        citations=(answer, written),
        historical_basis=HistoricalBasis(
            category="trading_capability",
            context="firm_wide",
            prior_question=control.context_citation,
            current_checks=(),
            reviewer_confirmation="Synthetic candidate.",
        ),
    )
    issues, _ = verify_historical_context(
        tmp_path,
        Inventory(datetime.now(UTC), (), ()),
        proposal,
        (control, extra),
        {},
        requirement,
        True,
    )
    assert issues == ("historical_write_in_relationship_unresolved",)
