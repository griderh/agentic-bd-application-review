"""Reviewed, version-bound local drafts; not automatic answer approval or submission."""

import hashlib
import json
import math
import re
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw
from pydantic import Field, ValidationError, model_validator
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import (
    AnswerProposal,
    ApplicationRequirements,
    BooleanValue,
    Contract,
    EvidenceStatus,
    HistoricalBasis,
    HistoricalContextCitation,
    Identifier,
    IdentifierValue,
    MultiSelectValue,
    NarrativeValue,
    Nonblank,
    OcrCitation,
    Requirement,
    Sha256,
    SingleSelectValue,
    TextValue,
    check_native_citations,
    check_proposal,
)
from bd_packet_builder.exhibits import (
    ExhibitError,
    HistoricalExhibit,
    audit_support,
    extract_exhibit,
)
from bd_packet_builder.historical_context import (
    HistoricalContextCheck,
    _native_citation,
    control_option_id,
    question_reconciliation,
    verified_question_requirements,
)
from bd_packet_builder.history import (
    ArchiveManifest,
    HistoricalReusePolicy,
    historical_issues,
    historical_review_concerns,
    requires_personal_action,
    with_historical_sources,
)
from bd_packet_builder.inventory import (
    Inventory,
    SourceRecord,
    build_inventory,
    publish_json_run,
    read_source_bytes,
)
from bd_packet_builder.knowledge import knowledge_context
from bd_packet_builder.layout import MappedResponse, PageBox, ResponseLayout, validate_layout
from bd_packet_builder.local_inputs import LocalInputError, read_local_input
from bd_packet_builder.ocr import OcrWordEvidence, ocr_text
from bd_packet_builder.question_presentation import (
    question_presentation as _question_presentation,
)
from bd_packet_builder.question_presentation import questions_agree, truncated_question_continues
from bd_packet_builder.reconciliation import (
    ReconciliationError,
    RequirementAssessment,
    reconcile_requirement,
    validate_assessments,
)
from bd_packet_builder.responses import (
    NarrativeRegion,
    PacketPagination,
    PacketReference,
    PacketSection,
    wrap_text,
)
from bd_packet_builder.retrieval import default_catalog
from bd_packet_builder.review import AnswerProposals
from bd_packet_builder.scan import (
    SUPPORTED_SCAN_VERSIONS,
    ExhibitImageCheck,
    ScanCheck,
    ScanVerificationError,
    check_agreement,
    normalized,
    parse_ocr_artifact,
)


@dataclass(frozen=True)
class ConditionalApplicability:
    parent_id: str
    applicable: bool | None
    historical_candidate: bool


def conditional_applicability(
    requirements: tuple[Requirement, ...],
    requirement: Requirement,
    written: dict[str, AnswerProposal],
) -> ConditionalApplicability | None:
    if not re.fullmatch(
        r"if yes[,:\s]+(?:please\s+)?explain[:.\s]*", requirement.instruction.strip(), re.IGNORECASE
    ):
        return None
    index = requirements.index(requirement)
    if index == 0:
        return None
    parent = requirements[index - 1]
    if parent.page != requirement.page or parent.kind not in ("boolean", "single_select"):
        return None
    proposal = written.get(parent.requirement_id)
    value = proposal.value if proposal is not None else None
    answer: bool | None = None
    if isinstance(value, BooleanValue):
        answer = value.value
    elif isinstance(value, SingleSelectValue) and parent.choices is not None:
        label = next(
            (
                o.label.strip().casefold()
                for o in parent.choices.options
                if o.option_id in value.selected
            ),
            "",
        )
        if label in ("yes", "no"):
            answer = label == "yes"
    return ConditionalApplicability(
        parent.requirement_id,
        answer,
        proposal is not None and proposal.historical_basis is not None,
    )


MAX_PACKET_PAGES = 200
MAX_INPUT_PAGES = 100
BANNER_HEIGHT = 24
RENDER_SCALE = 2
MAX_RENDER_PIXELS = 12_000_000
SUPPLEMENT_LINES = 42


class DraftError(ValueError):
    """Safe failures of draft input, placement, rendering or publication."""


class DraftSource(Contract):
    path: Nonblank
    sha256: Sha256


class DraftFormField(Contract):
    requirement_id: Identifier
    region: NarrativeRegion


class DraftAdditionalForm(Contract):
    source: DraftSource
    fields: Annotated[tuple[DraftFormField, ...], Field(max_length=20)]
    protected_regions: Annotated[tuple[PageBox, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def unique_placements(self) -> Self:
        placements = {
            (
                field.region.page,
                field.region.left,
                field.region.bottom,
                field.region.right,
                field.region.top,
            )
            for field in self.fields
        }
        if len(placements) != len(self.fields):
            raise ValueError("Additional form placements must be unique")
        return self


class DraftRequest(Contract):
    schema_version: Literal[1, 2] = 1
    mode: Literal["fictional", "reviewed_evidence"]
    source: Nonblank
    requirements: ApplicationRequirements
    layout: ResponseLayout
    proposals: AnswerProposals
    sources: Annotated[tuple[DraftSource, ...], Field(max_length=26)]
    attachments: Annotated[tuple[Sha256, ...], Field(max_length=20)]
    protected_regions: Annotated[tuple[PageBox, ...], Field(max_length=100)]
    additional_forms: Annotated[tuple[DraftAdditionalForm, ...], Field(max_length=10)] = ()
    issuer: Nonblank | None = None
    historical_archive: ArchiveManifest | None = None
    historical_policy: HistoricalReusePolicy = "conservative"
    calculation_date: date | None = None
    navigation_context: dict[Identifier, Nonblank] = Field(default_factory=dict)
    historical_exhibits: Annotated[tuple[HistoricalExhibit, ...], Field(max_length=5)] = ()

    @model_validator(mode="after")
    def identities(self) -> Self:
        requirements = {r.requirement_id: r for r in self.requirements.requirements}
        if not self.navigation_context.keys() <= requirements.keys():
            raise ValueError("Navigation context must refer to declared requirements")
        if any(e.requirement_id not in requirements for e in self.historical_exhibits):
            raise ValueError("Exhibits must refer to declared requirements")
        keys = [e.exhibit_id for e in self.historical_exhibits]
        if len(set(keys)) != len(keys):
            raise ValueError("Historical exhibit selections must be unique")
        if len(requirements) > 100:
            raise ValueError("Draft trial supports at most 100 requirements")
        if {p.requirement_id for p in self.proposals.proposals} != requirements.keys():
            raise ValueError("Draft proposals must cover exactly the declared requirements")
        if any(
            requirements.get(m.requirement.requirement_id) != m.requirement
            for m in self.layout.responses
        ):
            raise ValueError("Mapped requirements must match the declared requirement contracts")
        if any(
            r.application_sha256 != self.layout.application_sha256
            for r in self.requirements.requirements
        ):
            raise ValueError("All draft inputs must refer to one blank application version")
        if len({s.path for s in self.sources}) != len(self.sources):
            raise ValueError("Draft source paths must be unique")
        if len(set(self.attachments)) != len(self.attachments):
            raise ValueError("Draft attachment identities must be unique")
        blank_sources = [form.source.path for form in self.additional_forms]
        if (
            len(set(blank_sources)) != len(blank_sources)
            or self.source in blank_sources
            or any(
                field.requirement_id not in requirements
                for additional_form in self.additional_forms
                for field in additional_form.fields
            )
        ):
            raise ValueError("Additional forms must be distinct and reference known requirements")
        if (
            any(r.kind in ("signature", "signature_date") for r in requirements.values())
            and not self.protected_regions
        ):
            raise ValueError("Signing requirements require explicit protected regions")
        return self


class DraftDecision(Contract):
    requirement_id: Identifier
    decision: Literal["draft_verified", "withhold"]
    evidence_support_confirmed: bool
    source_approved: bool
    placement_confirmed: bool
    source_subject_confirmed: bool = False
    ocr_visual_confirmed: bool = False
    confirmed_source_subject: Nonblank | None = None
    evidence_status: EvidenceStatus = "current_evidence"
    reason: Nonblank

    @model_validator(mode="after")
    def confirmations(self) -> Self:
        if self.decision == "draft_verified" and not (
            self.evidence_support_confirmed and self.source_approved and self.placement_confirmed
        ):
            raise ValueError("Draft writing requires source, support and placement confirmation")
        return self


class DraftReview(Contract):
    request_sha256: Sha256
    reviewer: Nonblank
    decisions: Annotated[tuple[DraftDecision, ...], Field(max_length=100)]
    attachment_source_ids: Annotated[tuple[Sha256, ...], Field(max_length=20)] = ()
    reviewer_notes: Annotated[tuple[Nonblank, ...], Field(max_length=200)] = ()
    scan_checks: Annotated[tuple[ScanCheck, ...], Field(max_length=100)] = ()
    historical_context_checks: Annotated[
        tuple[HistoricalContextCheck, ...], Field(max_length=100)
    ] = ()
    historical_exhibit_ids: Annotated[tuple[Identifier, ...], Field(max_length=5)] = ()
    exhibit_image_checks: Annotated[tuple[ExhibitImageCheck, ...], Field(max_length=5)] = ()
    requirement_assessments: Annotated[
        tuple[RequirementAssessment, ...], Field(max_length=100)
    ] = ()

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({d.requirement_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Draft review decisions cannot repeat a requirement")
        if len(set(self.attachment_source_ids)) != len(self.attachment_source_ids):
            raise ValueError("Attachment reviews cannot repeat a source")
        if len(set(self.historical_exhibit_ids)) != len(self.historical_exhibit_ids):
            raise ValueError("Exhibit reviews cannot repeat a selection")
        if len({a.requirement_id for a in self.requirement_assessments}) != len(
            self.requirement_assessments
        ):
            raise ValueError("Requirement assessments cannot repeat")
        return self


# Short single-box answers may shrink/wrap down to this size before using the supplement.
MIN_SHORT_FONT = 6.0
_SHORT_FONT_STEP = 0.5
_COMPACT_LEADING = 1.15
_DESCENT = 0.22


@dataclass(frozen=True)
class TextPlacement:
    region: NarrativeRegion
    lines: tuple[str, ...]
    font_size: float | None = None
    leading: float | None = None

    @property
    def fit(self) -> Literal["standard", "reduced_font", "wrapped"]:
        if self.font_size is None:
            return "standard"
        return "wrapped" if len(self.lines) > 1 else "reduced_font"


@dataclass(frozen=True)
class MarkPlacement:
    box: PageBox
    control: Literal["radio", "checkbox"]


def _measure(text: str, size: float) -> float:
    return float(stringWidth(text, "Helvetica", size))


def _lines(text: str, region: NarrativeRegion) -> tuple[str, ...]:
    if any(not (32 <= ord(c) <= 126 or c == "\n") for c in text):
        raise DraftError("Unsupported font characters; answer needs a reviewed font/layout")
    lines = wrap_text(text, region.right - region.left, region.font_size, _measure)
    if lines is None or len(lines) > math.floor((region.top - region.bottom) / region.leading):
        raise DraftError("Answer cannot fit at the configured readable font size")
    return lines


def fit_short_text(text: str, region: NarrativeRegion) -> TextPlacement | None:
    """Largest font from the region size down to MIN_SHORT_FONT whose wrapped lines fit."""
    if any(not (32 <= ord(c) <= 126 or c == "\n") for c in text):
        raise DraftError("Unsupported font characters; answer needs a reviewed font/layout")
    width, height = region.right - region.left, region.top - region.bottom
    lines = wrap_text(text, width, region.font_size, _measure)
    if lines is not None and len(lines) <= math.floor(height / region.leading):
        return TextPlacement(region, lines)
    size = region.font_size - _SHORT_FONT_STEP
    while size >= MIN_SHORT_FONT:
        leading = round(size * _COMPACT_LEADING, 2)
        # The last line's descenders must stay inside the reviewed box.
        capacity = math.floor((height - size * (1 + _DESCENT)) / leading) + 1
        lines = wrap_text(text, width, size, _measure)
        if lines is not None and len(lines) <= capacity:
            return TextPlacement(region, lines, size, leading)
        size -= _SHORT_FONT_STEP
    return None


def _overlap(a: PageBox | NarrativeRegion, b: PageBox | NarrativeRegion) -> bool:
    return (
        a.page == b.page
        and min(a.right, b.right) > max(a.left, b.left)
        and (min(a.top, b.top) > max(a.bottom, b.bottom))
    )


def verify_ocr_citation(
    root: Path,
    inventory: Inventory,
    citation: OcrCitation,
    render_hashes: dict[tuple[str, int], str],
) -> tuple[str | None, bytes | None, dict[str, object] | None]:
    try:
        artifact_path = Path(citation.artifact_path)
        artifact = read_local_input(root, artifact_path, Path("outputs"), 2 * 1024 * 1024)
    except (LocalInputError, FileNotFoundError, IsADirectoryError):
        return "ocr_artifact_unavailable", None, None
    if hashlib.sha256(artifact).hexdigest() != citation.artifact_sha256:
        return "ocr_artifact_hash_mismatch", None, None
    try:
        data: object = json.loads(artifact)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "ocr_artifact_malformed", None, None
    if not isinstance(data, dict) or data.get("status") != "ocr_feasibility_unverified_not_answers":
        return "ocr_artifact_status_invalid", None, None
    source = next((s for s in inventory.sources if s.source_id == citation.source_id), None)
    artifact_source = data.get("source")
    if (
        source is None
        or not isinstance(artifact_source, dict)
        or source.sha256 != citation.source_sha256
        or artifact_source.get("source_id") != citation.source_id
        or artifact_source.get("sha256") != citation.source_sha256
        or artifact_source.get("path") != source.path
        or data.get("page") != citation.page
        or source.page_count is None
        or citation.page > source.page_count
    ):
        return "ocr_source_version_mismatch", None, None
    if (
        type(data.get("dpi")) is not int
        or data["dpi"] != 300
        or data.get("engine") != "tesseract"
        or not isinstance(data.get("engine_version"), str)
        or re.fullmatch(r"5\.\d+\.\d+", data["engine_version"]) is None
        or data.get("language") != "eng"
        or type(data.get("page_segmentation_mode")) is not int
        or data["page_segmentation_mode"] != 6
        or data.get("coordinate_system") != "rendered_pixels_top_left_not_pdf_points"
        or type(data.get("image_width")) is not int
        or type(data.get("image_height")) is not int
        or min(data["image_width"], data["image_height"]) < 1
        or data["image_width"] * data["image_height"] > 20_000_000
    ):
        return "ocr_render_or_configuration_mismatch", None, None
    if data.get("render_sha256") != citation.render_sha256:
        return "ocr_render_mismatch", None, None
    flags = data.get("flags")
    if (
        not isinstance(flags, list)
        or not all(isinstance(flag, str) for flag in flags)
        or not {"ocr_unverified", "not_semantic_grounding"} <= set(flags)
    ):
        return "ocr_artifact_status_invalid", None, None
    raw_words = data.get("words")
    if not isinstance(raw_words, list) or not 1 <= len(raw_words) <= 50_000:
        return "ocr_words_invalid", None, None
    try:
        words = [OcrWordEvidence.model_validate(word) for word in raw_words]
    except ValidationError:
        return "ocr_words_invalid", None, None
    if any(
        word.left + word.width > data["image_width"]
        or word.top + word.height > data["image_height"]
        for word in words
    ):
        return "ocr_words_invalid", None, None
    if data.get("text") != ocr_text(words):
        return "ocr_text_mismatch", None, None
    selected = words[citation.word_start : citation.word_end]
    if citation.word_end > len(words) or not selected or ocr_text(selected) != citation.quote:
        return "ocr_quote_mismatch", None, None
    key = citation.source_id, citation.page
    rendered = render_hashes.get(key)
    if rendered is None:
        try:
            source_data = read_source_bytes(root, inventory, citation.source_id)
            with (
                pdfium.PdfDocument(source_data) as document,
                closing(document[citation.page - 1]) as page,
            ):
                bitmap = page.render(scale=300 / 72)  # pyright: ignore[reportArgumentType]
                with closing(bitmap), closing(bitmap.to_pil()) as image:
                    if image.size != (data["image_width"], data["image_height"]):
                        return "ocr_render_mismatch", None, None
                    stream = BytesIO()
                    image.save(stream, format="PNG")
                    rendered = hashlib.sha256(stream.getvalue()).hexdigest()
        except pdfium.PdfiumError:
            return "ocr_render_unavailable", None, None
        render_hashes[key] = rendered
    if rendered != citation.render_sha256:
        return "ocr_render_mismatch", None, None
    selected_words = words[citation.word_start : citation.word_end]
    left = min(word.left for word in selected_words)
    top = min(word.top for word in selected_words)
    right = max(word.left + word.width for word in selected_words)
    bottom = max(word.top + word.height for word in selected_words)
    return (
        None,
        artifact,
        {
            "artifact_path": citation.artifact_path,
            "artifact_sha256": citation.artifact_sha256,
            "render_sha256": citation.render_sha256,
            "word_start": citation.word_start,
            "word_end": citation.word_end,
            "quote": citation.quote,
            "pixel_bounds_top_left": [left, top, right, bottom],
            "engine": data.get("engine"),
            "engine_version": data.get("engine_version"),
            "dpi": data["dpi"],
        },
    )


def historical_answer_citations(
    proposal: AnswerProposal, snapshots: tuple[tuple[OcrCitation, bytes], ...]
) -> tuple[OcrCitation, ...]:
    basis = proposal.historical_basis
    if basis is None:
        return ()
    return tuple(
        citation
        for citation, _ in snapshots
        if citation.source_id == basis.prior_question.source_id
        or (basis.reading_resolution is not None and citation == basis.reading_resolution.citation)
    )


def verify_historical_context(
    root: Path,
    inventory: Inventory,
    proposal: AnswerProposal,
    checks: tuple[HistoricalContextCheck, ...],
    render_hashes: dict[tuple[str, int], str],
    requirement: Requirement | None = None,
    allow_disagreements: bool = False,
    mapping: MappedResponse | None = None,
    scan_checks: tuple[ScanCheck, ...] = (),
    *,
    question_requirements: tuple[Requirement, ...] = (),
) -> tuple[tuple[str, ...], tuple[tuple[OcrCitation, bytes], ...]]:
    basis = proposal.historical_basis
    if basis is None:
        return (), ()
    current_snapshots: list[tuple[OcrCitation, bytes]] = []
    for current_check in basis.current_checks:
        citation = current_check.citation
        if not isinstance(citation, OcrCitation):
            continue
        issue, raw, _ = verify_ocr_citation(root, inventory, citation, render_hashes)
        if issue or raw is None:
            return (issue or "historical_current_scan_unavailable",), ()
        verified = False
        for scan in scan_checks:
            if (
                scan.citation != citation
                or scan.prompt_version not in SUPPORTED_SCAN_VERSIONS
                or not scan.agrees_with_artifact(raw)
            ):
                continue
            try:
                check_agreement(scan.transcript, scan.expected_subject, citation.quote)
            except ScanVerificationError:
                continue
            verified = True
            break
        if not verified:
            return ("historical_current_scan_requires_machine_verification",), ()
        current_snapshots.append((citation, raw))
    if not isinstance(basis.prior_question, HistoricalContextCitation):
        if basis.question_links:
            return ("historical_question_link_requires_checked_answer",), ()
        issues, date_snapshots = _verify_signature_metadata(
            root, inventory, proposal, checks, render_hashes
        )
        return (issues, ()) if issues else ((), tuple(current_snapshots) + date_snapshots)
    receipt = next(
        (check for check in checks if check.context_citation == basis.prior_question), None
    )
    if receipt is None:
        return ("historical_relationship_receipt_missing_or_mismatched",), ()
    snapshots = current_snapshots
    receipts = [receipt]
    if receipt.answer_disputed or basis.reading_resolution is not None:
        resolution_issue, subject_receipt, resolution_snapshots = _verify_reading_resolution(
            root, inventory, proposal, receipt, checks, render_hashes, requirement, scan_checks
        )
        if resolution_issue:
            return (resolution_issue,), ()
        if subject_receipt is not None:
            receipts.append(subject_receipt)
        snapshots.extend(resolution_snapshots)
    choice_contexts = (
        proposal.value is not None
        and proposal.value.kind in ("single_select", "multi_select")
        and receipt.field.control is not None
    )
    if basis.additional_contexts and not choice_contexts:
        if basis.tenure is not None or not isinstance(proposal.value, (TextValue, NarrativeValue)):
            return ("historical_composition_kind_not_allowed",), ()
        for context in basis.additional_contexts:
            part = next((c for c in checks if c.context_citation == context), None)
            if part is None or part in receipts:
                return ("historical_composition_receipt_missing_or_repeated",), ()
            receipts.append(part)
        if basis.correspondence is None or any(
            c.field.control is not None
            or c.answer.source_id != receipt.answer.source_id
            or (normalized(c.role.quote) if c.role else None)
            != (normalized(receipt.role.quote) if receipt.role else None)
            for c in receipts
        ):
            return ("historical_composition_context_mismatch",), ()

        def part_text(c: HistoricalContextCheck) -> str:
            return c.field.answer.text if c.discrepancies else c.answer.quote

        def joined(text: str) -> str:
            return re.sub(r"[\s,;/&]+", " ", text).strip().casefold()

        if joined(proposal.value.value) != joined(" ".join(part_text(c) for c in receipts)):
            return ("historical_composition_has_unsupported_text",), ()
        for checked in receipts:
            part_proposal = proposal.model_copy(
                update={
                    "value": TextValue(kind="text", value=part_text(checked)),
                    "historical_basis": basis.model_copy(
                        update={
                            "prior_question": checked.context_citation,
                            "additional_contexts": (),
                        }
                    ),
                }
            )
            if not checked.supports(part_proposal, requirement):
                return ("historical_relationship_receipt_missing_or_mismatched",), ()
    elif not receipt.supports(proposal, requirement):
        return ("historical_relationship_receipt_missing_or_mismatched",), ()
    if receipt.field.control is not None:
        receipts.extend(
            check
            for check in checks
            if check != receipt
            and check.field.control is not None
            and check.answer in proposal.citations
            and check.supports(proposal, requirement)
        )
        if requirement is not None and requirement.choices is not None:
            selected = (
                set(proposal.value.selected)
                if proposal.value is not None
                and proposal.value.kind in ("single_select", "multi_select")
                else set()
            )
            covered: set[str] = set()
            for checked in receipts:
                option_id = control_option_id(
                    checked.effective_field,
                    checked.transcript.historical_fields,
                    requirement,
                    mapping,
                )
                if option_id is not None:
                    covered.add(option_id)
            observed: set[str] = set()
            main_role = receipt.field.section_role
            for field in receipt.transcript.historical_fields:
                field_role = field.section_role
                if (
                    field.control is None
                    or field.control.state == "unselected"
                    or normalized(field.question.text) != normalized(receipt.field.question.text)
                    or (normalized(field_role.text) if field_role else None)
                    != (normalized(main_role.text) if main_role else None)
                ):
                    continue
                effective = next((c.effective_field for c in receipts if c.field == field), field)
                option_id = control_option_id(
                    effective, receipt.transcript.historical_fields, requirement, mapping
                )
                if field.control.state == "ambiguous" or option_id is None:
                    return ("historical_selected_controls_incomplete_or_ambiguous",), ()
                observed.add(option_id)
            if selected != covered or selected != observed:
                return ("historical_selected_controls_incomplete_or_ambiguous",), ()
            value = proposal.value
            if value is not None and value.kind in ("single_select", "multi_select"):
                required_write_ins = {
                    option.option_id
                    for option in requirement.choices.options
                    if option.option_id in selected and option.write_in
                }
                if not required_write_ins <= {w.option_id for w in value.write_ins}:
                    return ("historical_write_in_relationship_unresolved",), ()
                for write_in in value.write_ins:
                    control = next(
                        (
                            c
                            for c in receipts
                            if control_option_id(
                                c.effective_field,
                                c.transcript.historical_fields,
                                requirement,
                                mapping,
                            )
                            == write_in.option_id
                        ),
                        None,
                    )
                    linked = [
                        c
                        for c in checks
                        if control is not None
                        and c.field.control is None
                        and c.answer in proposal.citations
                        and c.question.source_id == control.question.source_id
                        and c.question.page == control.question.page
                        and normalized(c.field.answer.text) == normalized(write_in.text)
                        and abs(c.field.answer.box.top - control.field.answer.box.top) <= 25
                        and 0 <= c.field.answer.box.left - control.field.answer.box.left <= 200
                        and normalized(c.field.question.text).strip(" _:.")
                        == normalized(control.field.answer.text).strip(" _:.")
                    ]
                    if linked and all(
                        c.answer == linked[0].answer
                        and max(
                            abs(a - b)
                            for a, b in zip(
                                c.field.answer.box.model_dump().values(),
                                linked[0].field.answer.box.model_dump().values(),
                                strict=True,
                            )
                        )
                        <= 8
                        for c in linked
                    ):
                        linked = [min(linked, key=lambda c: len(c.discrepancies))]
                    if len(linked) != 1:
                        return ("historical_write_in_relationship_unresolved",), ()
                    receipts.extend(c for c in linked if c not in receipts)
                linked_contexts = {c.context_citation for c in receipts if c.field.control is None}
                if any(c not in linked_contexts for c in basis.additional_contexts):
                    return ("historical_write_in_relationship_unresolved",), ()
    for checked in receipts:
        if checked.field.control is not None and any(
            d.part == "question" and not questions_agree(d.image_reading, d.ocr_reading)
            for d in checked.discrepancies
        ):
            reconciled = question_reconciliation(checked, question_requirements)
            if (
                requirement is None
                or reconciled is None
                or requirement not in question_requirements
                or requirement.requirement_id not in reconciled.target_requirement_ids
            ):
                return ("historical_question_reading_unresolved",), ()
        current: list[tuple[OcrCitation, bytes]] = []
        for citation in checked.ocr_citations:
            issue, raw, _ = verify_ocr_citation(root, inventory, citation, render_hashes)
            if issue or raw is None:
                return (issue or "historical_relationship_artifact_unavailable",), ()
            current.append((citation, raw))
        if not current or not checked.recheck(
            root, inventory, current[0][1], allow_disagreements=allow_disagreements
        ):
            return ("historical_relationship_text_or_geometry_disagrees",), ()
        snapshots.extend(current)
    link_issue = _verify_question_links(
        root, inventory, basis, receipt, receipts, checks, render_hashes, allow_disagreements
    )
    if link_issue:
        return (link_issue,), ()
    date_issues, date_snapshots = _verify_signature_metadata(
        root, inventory, proposal, checks, render_hashes
    )
    if date_issues:
        return date_issues, ()
    return (), tuple(snapshots) + date_snapshots


_POINTER = re.compile(
    r"\b(see|refer\w*)\b.*\b(supplement\w*|attach\w*|addend\w*|exhibit\w*|continu\w*)",
    re.IGNORECASE | re.DOTALL,
)


_PLAIN_HISTORICAL_REASONS = {
    "historical_question_correspondence_required": (
        "The historical answer lacks an assessment tied to this exact target question."
    ),
    "historical_question_applicability_uncertain": (
        "It is uncertain whether the historical answer addresses this question. This is "
        "different from unconfirmed current continuity."
    ),
    "historical_question_partially_applicable": (
        "Only part of the question has applicable historical support. Partial-response "
        "writing is not enabled; supported and missing parts are identified below."
    ),
    "historical_composition_has_unsupported_text": (
        "The proposed answer does not exactly equal the cited historical answer pieces joined "
        "in order. A 'see supplement' pointer cited as an answer piece causes this."
    ),
    "historical_question_link_not_a_pointer": (
        "A record cited as a 'see supplement' link does not read as a short pointer."
    ),
    "historical_question_link_question_mismatch": (
        "The 'see supplement' link belongs to a different question than the cited answer."
    ),
    "historical_question_link_context_mismatch": (
        "The 'see supplement' link is from a different packet, section or answer type."
    ),
    "historical_question_link_receipt_missing": (
        "The 'see supplement' link has no checked page-reading record."
    ),
    "historical_question_link_repeats_answer": (
        "The same record was cited as both an answer piece and a 'see supplement' link."
    ),
    "historical_question_link_text_or_geometry_disagrees": (
        "The 'see supplement' link no longer matches the page text or position on recheck."
    ),
}


def _question_links_agree(
    pointer: str, answer: str, *, allow_truncated_answer: bool = False
) -> bool:
    pointer_number, pointer_words = _question_presentation(pointer)
    answer_number, answer_words = _question_presentation(answer)
    if pointer_number is not None and answer_number is not None and pointer_number != answer_number:
        return False
    if pointer_words and pointer_words == answer_words:
        return True
    return allow_truncated_answer and truncated_question_continues(answer, pointer)


def _verify_question_links(
    root: Path,
    inventory: Inventory,
    basis: HistoricalBasis,
    receipt: HistoricalContextCheck,
    receipts: list[HistoricalContextCheck],
    checks: tuple[HistoricalContextCheck, ...],
    render_hashes: dict[tuple[str, int], str],
    allow_disagreements: bool,
) -> str | None:
    """Check navigation pointers separately; they never contribute answer text or evidence."""
    answer_contexts = {c.context_citation for c in receipts} | set(basis.additional_contexts)
    role = normalized(receipt.role.quote) if receipt.role else None
    for index, link in enumerate(basis.question_links):
        if link in answer_contexts or link in basis.question_links[:index]:
            return "historical_question_link_repeats_answer"
        checked = next((c for c in checks if c.context_citation == link), None)
        if checked is None:
            return "historical_question_link_receipt_missing"
        if (
            checked.field.control is not None
            or checked.answer.source_id != receipt.answer.source_id
            or (normalized(checked.role.quote) if checked.role else None) != role
        ):
            return "historical_question_link_context_mismatch"
        if (
            any(d.part == "answer" for d in checked.discrepancies)
            or len(checked.answer.quote.split()) > 20
            or not _POINTER.search(checked.answer.quote)
        ):
            return "historical_question_link_not_a_pointer"
        if not _question_links_agree(checked.question.quote, receipt.question.quote) and (
            not _question_links_agree(
                checked.question.quote, receipt.question.quote, allow_truncated_answer=True
            )
            or _native_citation(
                root,
                inventory,
                receipt.question.source_id,
                receipt.question.page,
                receipt.field.question,
            )
            is None
            and (
                not questions_agree(receipt.field.question.text, receipt.question.quote)
                or _native_citation(
                    root,
                    inventory,
                    receipt.question.source_id,
                    receipt.question.page,
                    receipt.field.question.model_copy(update={"text": receipt.question.quote}),
                )
                is None
            )
        ):
            return "historical_question_link_question_mismatch"
        current: list[bytes] = []
        for citation in checked.ocr_citations:
            issue, raw, _ = verify_ocr_citation(root, inventory, citation, render_hashes)
            if issue or raw is None:
                return issue or "historical_relationship_artifact_unavailable"
            current.append(raw)
        if not current or not checked.recheck(
            root, inventory, current[0], allow_disagreements=allow_disagreements
        ):
            return "historical_question_link_text_or_geometry_disagrees"
    return None


def _verify_reading_resolution(
    root: Path,
    inventory: Inventory,
    proposal: AnswerProposal,
    receipt: HistoricalContextCheck,
    checks: tuple[HistoricalContextCheck, ...],
    render_hashes: dict[tuple[str, int], str],
    requirement: Requirement | None,
    scan_checks: tuple[ScanCheck, ...],
) -> tuple[str | None, HistoricalContextCheck | None, tuple[tuple[OcrCitation, bytes], ...]]:
    basis = proposal.historical_basis
    resolution = basis.reading_resolution if basis is not None else None
    value = proposal.value
    if resolution is None:
        return "reading_conflict_requires_reconciliation", None, ()
    if (
        not isinstance(value, (IdentifierValue, TextValue))
        or receipt.field.control is not None
        or basis is None
        or basis.tenure is not None
        or basis.additional_contexts
        or value.value not in (receipt.field.answer.text, receipt.answer.quote)
        or requirement is None
    ):
        return "reading_resolution_value_or_context_invalid", None, ()
    subject = next((c for c in checks if c.context_citation == resolution.subject_context), None)
    if (
        subject is None
        or subject == receipt
        or subject.discrepancies
        or subject.field.control is not None
        or subject.answer.source_id != receipt.answer.source_id
        or normalized(subject.answer.quote) != normalized(resolution.subject)
        or not re.search(r"\bname\b", subject.question.quote, re.IGNORECASE)
        or (normalized(subject.role.quote) if subject.role else None)
        != (normalized(receipt.role.quote) if receipt.role else None)
    ):
        return "reading_resolution_subject_not_verified", None, ()
    citation = resolution.citation
    source = next((s for s in inventory.sources if s.source_id == citation.source_id), None)
    original = next((s for s in inventory.sources if s.source_id == receipt.answer.source_id), None)
    if (
        source is None
        or original is None
        or source.family == "historical_reference"
        or source.sha256 == original.sha256
        or citation not in proposal.citations
    ):
        return "reading_resolution_requires_independent_current_source", None, ()
    label = normalized(resolution.field_label).strip(" :.#")
    if (
        len(label) < 3
        or not re.search(
            r"(?<!\w)" + re.escape(label) + r"(?!\w)", normalized(receipt.field.question.text)
        )
        or not re.search(
            r"(?<!\w)" + re.escape(label) + r"(?!\w)", normalized(receipt.question.quote)
        )
        or not re.search(
            r"(?<!\w)" + re.escape(label) + r"(?!\w)", normalized(requirement.instruction)
        )
        or not re.search(
            r"(?<!\w)"
            + re.escape(normalized(resolution.subject))
            + r"[\s;,:.-]+"
            + re.escape(label)
            + r"\s*[:#=-]?\s*"
            + re.escape(normalized(value.value))
            + r"(?!\w)",
            normalized(citation.quote),
        )
    ):
        return "reading_resolution_identity_field_value_not_linked", None, ()
    for other in (receipt.field.answer.text, receipt.answer.quote):
        if other != value.value and re.search(
            r"(?<!\w)"
            + re.escape(normalized(resolution.subject))
            + r"[\s;,:.-]+"
            + re.escape(label)
            + r"\s*[:#=-]?\s*"
            + re.escape(normalized(other))
            + r"(?!\w)",
            normalized(citation.quote),
        ):
            return "reading_resolution_corroborating_quote_conflicts", None, ()
    if isinstance(citation, OcrCitation):
        issue, raw, _ = verify_ocr_citation(root, inventory, citation, render_hashes)
        if (
            issue
            or raw is None
            or not any(
                c.citation == citation
                and normalized(c.expected_subject) == normalized(resolution.subject)
                and c.supports(requirement, proposal)
                and c.agrees_with_artifact(raw)
                for c in scan_checks
            )
        ):
            return "reading_resolution_current_scan_not_verified", None, ()
        return None, subject, ((citation, raw),)
    _, issues = check_native_citations(root, inventory, (citation,))
    if issues:
        return "reading_resolution_current_quote_not_verified", None, ()
    return None, subject, ()


def _verify_signature_metadata(
    root: Path,
    inventory: Inventory,
    proposal: AnswerProposal,
    checks: tuple[HistoricalContextCheck, ...],
    render_hashes: dict[tuple[str, int], str],
) -> tuple[tuple[str, ...], tuple[tuple[OcrCitation, bytes], ...]]:
    basis = proposal.historical_basis
    if (
        basis is not None
        and basis.tenure is not None
        and isinstance(basis.tenure.date_context, HistoricalContextCitation)
    ):
        from bd_packet_builder.historical_time import signature_proposal, signed_date

        date_receipt = next(
            (c for c in checks if c.context_citation == basis.tenure.date_context), None
        )
        if date_receipt is None or (
            not re.search(r"\bdate\b", date_receipt.field.question.text, re.IGNORECASE)
            or not re.search(
                r"\b(sign(?:ed|ature)|executed)\b", date_receipt.transcript.text, re.IGNORECASE
            )
        ):
            return ("historical_signature_context_unresolved",), ()
        dates: set[date] = set()
        for checked in checks:
            if checked.answer.source_id != date_receipt.answer.source_id or not re.search(
                r"\bdate\b", checked.field.question.text, re.IGNORECASE
            ):
                continue
            try:
                dates.add(signed_date(checked.field.answer.text))
            except ValueError:
                continue
        if dates != {basis.tenure.signed_on}:
            return ("historical_signature_dates_conflict_or_unresolved",), ()
        date_issues, date_snapshots = verify_historical_context(
            root,
            inventory,
            signature_proposal(proposal),
            checks,
            render_hashes,
            allow_disagreements=False,
        )
        if not date_issues and not any(
            re.search(
                r"\b(sign(?:ed|ature)|executed)\b",
                ocr_text(parse_ocr_artifact(raw).words),
                re.IGNORECASE,
            )
            for _, raw in date_snapshots
        ):
            return ("historical_signature_anchor_not_locally_verified",), ()
        return date_issues, date_snapshots
    return (), ()


def _writable(mapped: MappedResponse) -> list[PageBox | NarrativeRegion]:
    regions: list[PageBox | NarrativeRegion] = [o.box for o in mapped.options]
    if mapped.checklist_box is not None:
        regions.append(mapped.checklist_box)
    regions.extend(o.write_in_region for o in mapped.options if o.write_in_region is not None)
    if mapped.narrative_region is not None:
        regions.append(mapped.narrative_region)
    if mapped.text_region is not None:
        regions.append(mapped.text_region)
    return regions


def _validate_pdf(data: bytes, *, blank: bool) -> PdfReader:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or not reader.pages or len(reader.pages) > MAX_INPUT_PAGES:
        raise DraftError("Draft input is encrypted, empty or exceeds the page limit")
    if blank and any(
        field.get("/V") not in (None, "", "/Off") for field in (reader.get_fields() or {}).values()
    ):
        raise DraftError("Draft input must not contain prefilled or signed fields")
    for page in reader.pages:
        if blank and (
            page.rotation != 0
            or float(page.mediabox.left) != 0
            or float(page.mediabox.bottom) != 0
            or list(page.cropbox) != list(page.mediabox)
            or page.get("/UserUnit", 1) != 1
        ):
            raise DraftError(
                "This draft writer requires unrotated, uncropped standard-point blanks"
            )
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if (
            width <= 0
            or height <= 0
            or width * (height + BANNER_HEIGHT) * RENDER_SCALE**2 > MAX_RENDER_PIXELS
        ):
            raise DraftError("Draft page exceeds the render size limit")
    return reader


def selected_inventory(root: Path, request: DraftRequest) -> Inventory:
    allowed = {f.folder for f in default_catalog().families}
    families = set()
    for selection in request.sources:
        path = Path(selection.path)
        if path.is_relative_to("bd_agreements/Completed"):
            if request.historical_archive is None or not any(
                e.path == selection.path
                and e.sha256 == selection.sha256
                and e.partition == "reference"
                for e in request.historical_archive.entries
            ):
                raise DraftError("Historical source is not approved by the partition manifest")
            continue
        base = Path("bd_agreements/supporting_data")
        if path.is_absolute() or ".." in path.parts or not path.is_relative_to(base):
            raise DraftError("Draft sources must be within designated supporting folders")
        parts = path.relative_to(base).parts
        if len(parts) < 2 or parts[0] not in allowed:
            raise DraftError("Draft source family is outside the designated catalog")
        families.add(parts[0])
    inventory = (
        build_inventory(root, families=tuple(sorted(families)), max_sources=30)
        if families
        else Inventory(datetime.now(UTC), (), ())
    )
    inventory = with_historical_sources(root, inventory, request.historical_archive)
    selected: list[SourceRecord] = []
    for expected in request.sources:
        source = next((s for s in inventory.sources if s.path == expected.path), None)
        if source is None or source.sha256 != expected.sha256 or source.page_count is None:
            raise DraftError("Draft supporting source is missing, changed or has no readable page")
        selected.append(source)
    return Inventory(inventory.created_at, tuple(selected), ())


def order_attachment_sources(
    sources: tuple[SourceRecord, ...], checklist_source_ids: tuple[str, ...] = ()
) -> tuple[SourceRecord, ...]:
    """Keep families together, positioning checklist-linked families before other support."""
    by_id = {source.source_id: source for source in sources}
    families = dict.fromkeys(
        [
            *(by_id[identity].family for identity in checklist_source_ids if identity in by_id),
            *(source.family for source in sources),
        ]
    )
    ranks = {family: index for index, family in enumerate(families)}
    return tuple(sorted(sources, key=lambda source: ranks[source.family]))


def _draw_text(canvas: Canvas, placement: TextPlacement) -> None:
    region = placement.region
    size = placement.font_size or region.font_size
    leading = placement.leading or region.leading
    canvas.setFont("Helvetica", size)
    for index, line in enumerate(placement.lines):
        canvas.drawString(region.left, region.top - size - index * leading, line)


def _form_pdf(
    original: bytes, texts: list[TextPlacement], marks: list[MarkPlacement], fictional: bool
) -> bytes:
    reader = _validate_pdf(original, blank=True)
    with closing(PdfWriter(clone_from=reader)) as writer:
        for number, page in enumerate(writer.pages, start=1):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            overlay = BytesIO()
            canvas = Canvas(overlay, pagesize=(width, height + BANNER_HEIGHT), invariant=True)
            canvas.setFont("Helvetica-Bold", 9)
            label = "FICTIONAL DATA - " if fictional else ""
            canvas.drawString(12, height + 8, label + "INCOMPLETE DRAFT - NOT FOR SUBMISSION")
            for text in texts:
                if text.region.page == number:
                    _draw_text(canvas, text)
            canvas.setLineWidth(1)
            for mark in marks:
                b = mark.box
                if b.page != number:
                    continue
                if mark.control == "radio":
                    canvas.circle(
                        (b.left + b.right) / 2,
                        (b.bottom + b.top) / 2,
                        min(b.right - b.left, b.top - b.bottom) / 3,
                        stroke=0,
                        fill=1,
                    )
                else:
                    inset = min(b.right - b.left, b.top - b.bottom) / 5
                    canvas.line(b.left + inset, b.bottom + inset, b.right - inset, b.top - inset)
                    canvas.line(b.left + inset, b.top - inset, b.right - inset, b.bottom + inset)
            canvas.save()
            page.mediabox = RectangleObject((0, 0, width, height + BANNER_HEIGHT))
            page.cropbox = page.mediabox
            page.merge_page(PdfReader(overlay).pages[0])
        output = BytesIO()
        writer.write(output)
    return output.getvalue()


def _render_image(data: bytes, index: int) -> Image.Image:
    with pdfium.PdfDocument(data) as document:
        document.init_forms()
        with closing(document[index]) as page, closing(page.render(scale=RENDER_SCALE)) as bitmap:
            image: Image.Image = bitmap.to_pil()
            try:
                return image.convert("RGB")
            finally:
                image.close()


def _render_checks(
    original: bytes,
    packet: bytes,
    output: Path,
    allowed: list[PageBox | NarrativeRegion],
    marks: list[MarkPlacement],
    texts: list[TextPlacement],
    packet_page_offset: int = 0,
    filename_prefix: str = "",
) -> dict[str, object]:
    total_outside = 0
    with pdfium.PdfDocument(packet) as document:
        for placement in texts:
            b = placement.region
            with (
                closing(document[packet_page_offset + b.page - 1]) as page,
                closing(page.get_textpage()) as text,
            ):
                # PDFium replaces a visible line-ending hyphen and break with STX.
                actual = " ".join(
                    text.get_text_bounded(
                        left=b.left, bottom=b.bottom, right=b.right, top=b.top, errors="strict"
                    )
                    .replace("\x02", "- ")
                    .split()
                )
                if any(" ".join(line.split()) not in actual for line in placement.lines):
                    raise DraftError("Written text is missing or clipped in its reviewed region")
    for number in range(1, len(PdfReader(BytesIO(original)).pages) + 1):
        with (
            _render_image(original, number - 1) as before,
            _render_image(packet, packet_page_offset + number - 1) as after,
        ):
            before.save(output / f"{filename_prefix}page-{number}-before.png")
            after.save(output / f"{filename_prefix}page-{number}-after.png")
            with after.crop((0, BANNER_HEIGHT * RENDER_SCALE, before.width, after.height)) as body:
                with ImageChops.difference(before, body) as diff, diff.convert("L") as gray:
                    changed = gray.point([255 if value > 16 else 0 for value in range(256)])
                try:
                    mask = Image.new("L", before.size, 255)
                    with mask:
                        draw = ImageDraw.Draw(mask)
                        for box in allowed:
                            if box.page == number:
                                draw.rectangle(
                                    (
                                        box.left * RENDER_SCALE - 2,
                                        before.height - box.top * RENDER_SCALE - 2,
                                        box.right * RENDER_SCALE + 2,
                                        before.height - box.bottom * RENDER_SCALE + 2,
                                    ),
                                    fill=0,
                                )
                        with ImageChops.multiply(changed, mask) as outside:
                            total_outside += outside.histogram()[255]
                    for mark in marks:
                        control_box = mark.box
                        if control_box.page == number:
                            with changed.crop(
                                (
                                    int(control_box.left * RENDER_SCALE),
                                    int(before.height - control_box.top * RENDER_SCALE),
                                    int(control_box.right * RENDER_SCALE),
                                    int(before.height - control_box.bottom * RENDER_SCALE),
                                )
                            ) as region:
                                if region.histogram()[255] < 4:
                                    raise DraftError(
                                        "Rendered selected control is not visibly marked"
                                    )
                finally:
                    changed.close()
    if total_outside:
        raise DraftError("Rendered draft changed content outside reviewed writable regions")
    return {
        "scale": RENDER_SCALE,
        "luminance_difference_threshold": 16,
        "region_padding_pixels": 2,
        "outside_allowed_regions_changed_pixels": total_outside,
        "scope": "form_pages_only_not_semantic_or_human_visual_approval",
    }


def run_draft(root: Path, request_path: Path, review_path: Path) -> Path:
    """Publish one incomplete draft from an explicitly reviewed local snapshot.

    Review JSON is a trusted local development input, not an authentication mechanism.
    No model calls, signing, external actions or automatic source approval occur.
    """
    root = root.resolve(strict=True)
    raw = read_local_input(root, request_path, Path("outputs"), 2 * 1024 * 1024)
    reviewed = read_local_input(root, review_path, Path("outputs"), 2 * 1024 * 1024)
    request = DraftRequest.model_validate_json(raw)
    review = DraftReview.model_validate_json(reviewed)
    return publish_draft(root, request_path, raw, request, review, reviewed, review_path)


def publish_draft(
    root: Path,
    request_path: Path,
    raw: bytes,
    request: DraftRequest,
    review: DraftReview,
    reviewed: bytes,
    review_path: Path | None,
) -> Path:
    """Write the draft for already-parsed inputs; ``review_path`` is None for gate-made reviews."""
    request_hash = hashlib.sha256(raw).hexdigest()
    if review.request_sha256 != request_hash:
        raise DraftError("Draft review does not match this exact request snapshot")
    requirements = {r.requirement_id: r for r in request.requirements.requirements}
    if any(d.requirement_id not in requirements for d in review.decisions):
        raise DraftError("Draft review contains an unknown requirement")
    if not set(review.attachment_source_ids) <= set(request.attachments):
        raise DraftError("Attachment review contains an unknown attachment")
    if not set(review.historical_exhibit_ids) <= {
        e.exhibit_id for e in request.historical_exhibits
    }:
        raise DraftError("Exhibit review contains an unknown selection")
    if any(
        requirements[d.requirement_id].kind in ("signature", "signature_date")
        and d.decision == "draft_verified"
        for d in review.decisions
    ):
        raise DraftError("Signatures and signature dates cannot be approved for draft writing")
    original = read_local_input(
        root, Path(request.source), Path("bd_agreements/Blank"), 64 * 1024 * 1024
    )
    validate_layout(root, Path(request.source), request.layout)
    reader = _validate_pdf(original, blank=True)
    question_requirements = verified_question_requirements(
        original, request.requirements.requirements
    )
    additional_forms_data: list[tuple[DraftAdditionalForm, bytes, PdfReader]] = []
    additional_form_snapshots: dict[Path, bytes] = {}
    for form in request.additional_forms:
        form_path = Path(form.source.path)
        form_bytes = read_local_input(
            root, form_path, Path("bd_agreements/Blank"), 64 * 1024 * 1024
        )
        if hashlib.sha256(form_bytes).hexdigest() != form.source.sha256:
            raise DraftError("Additional issuer form changed after request preparation")
        form_reader = _validate_pdf(form_bytes, blank=True)
        field_regions: list[PageBox | NarrativeRegion] = []
        with pdfium.PdfDocument(form_bytes) as document:
            for field in form.fields:
                region = field.region
                if region.page > len(form_reader.pages):
                    raise DraftError("Additional-form field is outside the form")
                page_width = float(form_reader.pages[region.page - 1].mediabox.width)
                page_height = float(form_reader.pages[region.page - 1].mediabox.height)
                if region.right > page_width or region.top > page_height:
                    raise DraftError("Additional-form field is outside the form")
                with (
                    closing(document[region.page - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    native = text.get_text_bounded(
                        left=region.left,
                        bottom=region.bottom,
                        right=region.right,
                        top=region.top,
                        errors="strict",
                    )
                    if native.replace("_", "").strip():
                        raise DraftError("Additional-form field overlaps existing issuer text")
                field_regions.append(region)
            for protected in form.protected_regions:
                if (
                    protected.page > len(form_reader.pages)
                    or protected.right > float(form_reader.pages[protected.page - 1].mediabox.width)
                    or protected.top > float(form_reader.pages[protected.page - 1].mediabox.height)
                ):
                    raise DraftError("Additional-form protected region is outside the form")
        if any(
            _overlap(region, protected)
            for region in field_regions
            for protected in form.protected_regions
        ):
            raise DraftError("Additional-form field overlaps protected content")
        if any(
            _overlap(first, second)
            for index, first in enumerate(field_regions)
            for second in field_regions[index + 1 :]
        ):
            raise DraftError("Additional-form fields overlap")
        additional_forms_data.append((form, form_bytes, form_reader))
        additional_form_snapshots[form_path] = form_bytes
    all_regions = [b for m in request.layout.responses for b in _writable(m)]
    with pdfium.PdfDocument(original) as document:
        for response in request.layout.responses:
            for writable_region in _writable(response):
                if not isinstance(writable_region, NarrativeRegion):
                    continue
                with (
                    closing(document[writable_region.page - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    native = text.get_text_bounded(
                        left=writable_region.left,
                        bottom=writable_region.bottom,
                        right=writable_region.right,
                        top=writable_region.top,
                        errors="strict",
                    )
                    if native.replace("_", "").strip():
                        raise DraftError("Writable text region overlaps existing issuer text")
    for protected in request.protected_regions:
        if (
            protected.page > len(reader.pages)
            or protected.right > float(reader.pages[protected.page - 1].mediabox.width)
            or protected.top > float(reader.pages[protected.page - 1].mediabox.height)
        ):
            raise DraftError("Protected region is outside the form")
    if any(_overlap(a, b) for i, a in enumerate(all_regions) for b in all_regions[i + 1 :]):
        raise DraftError("Writable regions overlap; placement needs review")
    if any(_overlap(a, b) for a in all_regions for b in request.protected_regions):
        raise DraftError("Writable region overlaps protected signing or other content")
    inventory = selected_inventory(root, request)
    sources = {s.source_id: s for s in inventory.sources}
    with pdfium.PdfDocument(original) as document:
        form_text: dict[int, str] = {}
        for index in range(len(document)):
            with closing(document[index]) as page, closing(page.get_textpage()) as text:
                form_text[index + 1] = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
    assessments = {a.requirement_id: a for a in review.requirement_assessments}
    for proposal in request.proposals.proposals:
        assessment = assessments.get(proposal.requirement_id)
        if (
            assessment is not None
            and assessment.applicability != "required"
            and proposal.outcome == "proposed"
        ):
            raise DraftError("Applicability review cannot discard a proposed answer")
    if not set(request.attachments) <= sources.keys():
        raise DraftError("Attachment is not a version-bound selected source")
    if any(sources[i].family == "historical_reference" for i in request.attachments):
        raise DraftError("Historical packets must never be submission attachments")
    attachment_ids = [
        source.source_id
        for source in order_attachment_sources(
            tuple(
                sources[identity]
                for identity in request.attachments
                if identity in review.attachment_source_ids
            )
        )
    ]
    attachments = [
        (sources[identity], read_source_bytes(root, inventory, identity))
        for identity in attachment_ids
    ]
    attachment_readers = [
        (source, _validate_pdf(data, blank=False)) for source, data in attachments
    ]
    approved_exhibits = tuple(
        e for e in request.historical_exhibits if e.exhibit_id in review.historical_exhibit_ids
    )
    exhibit_data = []
    for exhibit in approved_exhibits:
        try:
            data = extract_exhibit(
                root,
                inventory,
                exhibit,
                proposals=request.proposals.proposals,
                image_checks=review.exhibit_image_checks,
            )
        except ExhibitError as error:
            raise DraftError(str(error)) from None
        exhibit_data.append((exhibit, data, _validate_pdf(data, blank=False)))
    exhibit_page_count = sum(len(r.pages) for _, _, r in exhibit_data)
    form_count = len(reader.pages) + sum(len(form.pages) for _, _, form in additional_forms_data)
    base_page_count = (
        form_count + exhibit_page_count + sum(len(r.pages) for _, r in attachment_readers)
    )
    if base_page_count > MAX_PACKET_PAGES:
        raise DraftError(
            "Draft packet exceeds its total page budget "
            f"({base_page_count} > {MAX_PACKET_PAGES} pages before supplemental answers)"
        )
    decisions = {d.requirement_id: d for d in review.decisions}
    mappings = {m.requirement.requirement_id: m for m in request.layout.responses}
    texts: list[TextPlacement] = []
    marks: list[MarkPlacement] = []
    results: list[dict[str, object]] = []
    placements: dict[str, dict[str, object]] = {}
    accepted: list[AnswerProposal] = []
    supplements: list[tuple[str, tuple[str, ...]]] = []
    supplement_starts: dict[str, int] = {}
    supplement_page_count = 0
    ocr_render_hashes: dict[tuple[str, int], str] = {}
    ocr_artifact_snapshots: dict[Path, bytes] = {}

    def verify_assessment_ocr(citation: OcrCitation) -> None:
        issue, snapshot, _ = verify_ocr_citation(root, inventory, citation, ocr_render_hashes)
        if issue or snapshot is None:
            raise DraftError(issue or "Assessment OCR artifact unavailable")
        ocr_artifact_snapshots[Path(citation.artifact_path)] = snapshot

    try:
        validate_assessments(
            root,
            inventory,
            request.requirements.requirements,
            review.requirement_assessments,
            form_text,
            verify_ocr=verify_assessment_ocr,
        )
    except ReconciliationError as error:
        raise DraftError(str(error)) from None
    for exhibit in approved_exhibits:
        if isinstance(exhibit.title, OcrCitation):
            path = Path(exhibit.title.artifact_path)
            ocr_artifact_snapshots[path] = read_local_input(
                root, path, Path("outputs"), 2 * 1024 * 1024
            )
            if (
                hashlib.sha256(ocr_artifact_snapshots[path]).hexdigest()
                != exhibit.title.artifact_sha256
            ):
                raise DraftError("Exhibit OCR artifact changed during assembly")

    def reserve_supplement(identity: str, text: str) -> None:
        nonlocal supplement_page_count
        full = wrap_text(text, 520.0, 10.0, _measure)
        if full is None:
            raise DraftError("Answer has an unbreakable word that cannot fit")
        count = max(1, math.ceil(len(full) / SUPPLEMENT_LINES))
        total_pages = base_page_count + supplement_page_count + count
        if total_pages > MAX_PACKET_PAGES:
            raise DraftError(
                "Answer exceeds the bounded supplemental page budget "
                f"({total_pages} > {MAX_PACKET_PAGES} total packet pages)"
            )
        supplement_starts[identity] = supplement_page_count + 1
        supplement_page_count += count
        supplements.append((identity, full))

    written_by_id: dict[str, AnswerProposal] = {}
    requirement_order = {
        r.requirement_id: i for i, r in enumerate(request.requirements.requirements)
    }
    for proposal in sorted(
        request.proposals.proposals, key=lambda p: requirement_order[p.requirement_id]
    ):
        identity = proposal.requirement_id
        req = requirements[identity]
        assessment = assessments.get(identity)
        if assessment is not None and assessment.applicability != "required":
            results.append(
                {
                    "requirement_id": identity,
                    "status": "optional_not_supplied"
                    if assessment.applicability == "optional"
                    else "not_applicable",
                    "issues": [],
                    "proposal": proposal.model_dump(mode="json"),
                    "review_reason": assessment.reason,
                    "effective_explanation": assessment.reason,
                    "evidence_status": "reviewed_applicability_not_an_answer",
                    "requirement_assessment": assessment.model_dump(mode="json"),
                }
            )
            continue
        conditional = conditional_applicability(
            request.requirements.requirements, req, written_by_id
        )
        if conditional is not None and conditional.applicable is not True:
            basis = (
                "historical candidate, NOT confirmation of current facts"
                if conditional.historical_candidate
                else "written answer"
            )
            reason = (
                f"Conditional follow-up is not applicable because {conditional.parent_id} "
                f"is No ({basis}). No explanation is required on that basis."
                if conditional.applicable is False
                else f"Conditional applicability unresolved: {conditional.parent_id} was not "
                "written with an explicit Yes or No. Resolve the parent first."
            )
            results.append(
                {
                    "requirement_id": identity,
                    "status": "not_applicable" if conditional.applicable is False else "blank",
                    "issues": []
                    if conditional.applicable is False
                    else ["conditional_parent_unresolved"],
                    "proposal": proposal.model_dump(mode="json"),
                    "review_reason": reason,
                    "effective_explanation": reason,
                    "conditional": asdict(conditional),
                    "evidence_status": "historical_continuity_unconfirmed"
                    if conditional.historical_candidate
                    else None,
                }
            )
            continue
        decision = decisions.get(identity)
        mapped = mappings.get(identity)
        check = check_proposal(root, inventory, req, proposal)
        context_issues, context_snapshots = verify_historical_context(
            root,
            inventory,
            proposal,
            review.historical_context_checks,
            ocr_render_hashes,
            req,
            request.historical_policy == "answer_first_review",
            mapped,
            review.scan_checks,
            question_requirements=question_requirements,
        )
        answer_citations = historical_answer_citations(proposal, context_snapshots)
        context_verified = bool(answer_citations) and not context_issues
        for context_citation, context_snapshot in context_snapshots:
            ocr_artifact_snapshots[Path(context_citation.artifact_path)] = context_snapshot
        history_issues, evidence_status = historical_issues(
            root,
            inventory,
            request.historical_archive,
            request.issuer,
            req,
            proposal,
            navigation_context=request.navigation_context.get(identity, ""),
            context_verified=context_verified,
            historical_policy=request.historical_policy,
            calculation_date=request.calculation_date,
            verified_current_scans=tuple(c for c, _ in context_snapshots),
            require_applicability=request.schema_version == 2,
        )
        history_issues = (*context_issues, *history_issues)
        issues: list[str] = []
        result: dict[str, object] = {
            "requirement_id": identity,
            "status": "blank",
            "issues": issues,
            "proposal": proposal.model_dump(mode="json"),
            "citation_check": asdict(check),
            "review_reason": decision.reason if decision else None,
            "effective_explanation": proposal.explanation,
            "evidence_status": evidence_status,
        }
        discrepancies = {
            d.model_dump_json(): d.model_dump(mode="json")
            for c in review.historical_context_checks
            if c.supports(proposal, req) or c.answer in proposal.citations
            for d in c.presentation_discrepancies
        }
        if discrepancies:
            result["historical_extraction_discrepancies"] = list(discrepancies.values())
            result["historical_candidate_status"] = (
                "reconciled_with_independent_evidence"
                if context_verified
                and proposal.historical_basis is not None
                and proposal.historical_basis.reading_resolution is not None
                else "reconciled_with_native_text_and_ocr"
                if context_verified
                and any(
                    d["code"] == "historical_native_numeric_layout_reconciled"
                    for d in discrepancies.values()
                )
                else "question_presentation_resolved"
                if context_verified
                and all(
                    d["code"] == "historical_question_presentation_resolved"
                    for d in discrepancies.values()
                )
                else "extraction_discrepancy_unresolved"
            )
            reconciled_questions = [
                reconciliation.model_dump(mode="json")
                for c in review.historical_context_checks
                if (c.supports(proposal, req) or c.answer in proposal.citations)
                and (reconciliation := question_reconciliation(c, question_requirements))
                is not None
                and identity in reconciliation.target_requirement_ids
            ]
            if reconciled_questions:
                result["historical_question_reconciliation"] = reconciled_questions
                if context_verified:
                    result["historical_candidate_status"] = (
                        "question_reconciled_against_native_blank"
                    )
        printed_readings = [
            reading.model_dump(mode="json")
            for c in review.historical_context_checks
            if c.supports(proposal, req) or c.answer in proposal.citations
            for reading in c.printed_readings
        ]
        if printed_readings:
            result["historical_printed_readings"] = printed_readings
            if context_verified and any(r["status"] == "resolved" for r in printed_readings):
                result["historical_candidate_status"] = "printed_wording_resolved"
        ocr_citations = tuple(c for c in proposal.citations if isinstance(c, OcrCitation))
        ocr_evidence: list[dict[str, object]] = []
        ocr_valid = True
        for citation in ocr_citations:
            ocr_issue, snapshot, details = verify_ocr_citation(
                root, inventory, citation, ocr_render_hashes
            )
            if ocr_issue:
                issues.append(ocr_issue)
                ocr_valid = False
            if snapshot is not None:
                ocr_artifact_snapshots[Path(citation.artifact_path)] = snapshot
            if details is not None:
                ocr_evidence.append(details)
        if ocr_citations:
            result["ocr_evidence"] = ocr_evidence
        results.append(result)
        if conditional is not None:
            result["conditional"] = asdict(conditional)
            result["review_reason"] = (
                f"{conditional.parent_id} is Yes; its conditional explanation is required. "
                + (
                    "The explanation has not been supplied."
                    if proposal.outcome != "proposed"
                    else (decision.reason if decision else "Not reviewed.")
                )
            )
            result["effective_explanation"] = result["review_reason"]
        if req.kind in ("signature", "signature_date"):
            issues.append("human_signing_required")
            continue
        if proposal.outcome != "proposed":
            issues.append(proposal.outcome)
            continue
        if decision is None or decision.decision != "draft_verified":
            issues.append("withheld" if decision else "not_reviewed")
            continue
        if history_issues:
            issues.extend(history_issues)
            continue
        if ocr_citations:
            machine_checked = all(
                (context_verified and citation in answer_citations)
                or any(
                    check.citation == citation
                    and check.supports(req, proposal)
                    and Path(citation.artifact_path) in ocr_artifact_snapshots
                    and check.agrees_with_artifact(
                        ocr_artifact_snapshots[Path(citation.artifact_path)]
                    )
                    for check in review.scan_checks
                )
                for citation in ocr_citations
            )
            result["ocr_review_method"] = (
                "machine_cross_checked_draft_not_human_approval"
                if machine_checked
                else "human_visual_review"
            )
            if not machine_checked and (
                not decision.source_subject_confirmed or not decision.confirmed_source_subject
            ):
                issues.append("ocr_source_subject_not_confirmed")
            if not machine_checked and not decision.ocr_visual_confirmed:
                issues.append("ocr_visual_review_not_confirmed")
            if not ocr_valid:
                issues.append("ocr_evidence_not_verified")
            if any(
                issue in issues
                for issue in (
                    "ocr_source_subject_not_confirmed",
                    "ocr_visual_review_not_confirmed",
                    "ocr_evidence_not_verified",
                )
            ):
                continue
        if mapped is None:
            issues.append("placement_not_available")
            continue
        if check.status == "rejected":
            issues.extend(check.issues)
            continue
        if req.requested_period is not None and proposal.claimed_period != req.requested_period:
            issues.append("requested_period_not_confirmed")
            continue
        if any(
            c.source_id not in attachment_ids
            and (
                c.source_id not in sources or sources[c.source_id].family != "historical_reference"
            )
            for c in proposal.citations
        ):
            issues.append("supporting_evidence_not_attached")
            continue
        candidate_texts: list[TextPlacement] = []
        candidate_marks: list[MarkPlacement] = []
        try:
            value = proposal.value
            if isinstance(value, (IdentifierValue, TextValue, BooleanValue)):
                if mapped.text_region is None:
                    raise DraftError("Scalar answer has no reviewed writable region")
                if isinstance(value, IdentifierValue) and not any(
                    re.search(r"(?<!\w)" + re.escape(value.value) + r"(?!\w)", c.quote)
                    for c in proposal.citations
                ):
                    raise DraftError("Exact identifier is not present in the cited evidence")
                text = (
                    ("Yes" if value.value else "No")
                    if isinstance(value, BooleanValue)
                    else value.value
                )
                region = mapped.text_region
                fitted = fit_short_text(text, region)
                if fitted is None and isinstance(value, TextValue):
                    _lines(f"See packet page {MAX_PACKET_PAGES}.", region)
                    reserve_supplement(identity, text)
                    placements[identity] = {"mode": "supplement", "fit": "below_minimum_font"}
                elif fitted is None:
                    raise DraftError("Answer cannot fit at the minimum readable font size")
                else:
                    candidate_texts.append(fitted)
                    placements[identity] = {
                        "mode": "inline",
                        "font_size": fitted.font_size or region.font_size,
                        "line_count": len(fitted.lines),
                        "fit": fitted.fit,
                    }
            elif isinstance(value, (SingleSelectValue, MultiSelectValue)):
                for option in mapped.options:
                    if option.option_id in value.selected:
                        candidate_marks.append(MarkPlacement(option.box, option.control))
                for write_in in value.write_ins:
                    option = next(o for o in mapped.options if o.option_id == write_in.option_id)
                    if option.write_in_region is None:
                        raise DraftError("Selected write-in lacks a reviewed writable region")
                    write_in_fit = fit_short_text(write_in.text, option.write_in_region)
                    if write_in_fit is None:
                        raise DraftError("Answer cannot fit at the minimum readable font size")
                    candidate_texts.append(write_in_fit)
                placements[identity] = {"mode": "choice", "selected": list(value.selected)}
            elif isinstance(value, NarrativeValue):
                if mapped.narrative_region is None:
                    raise DraftError("Narrative answer has no reviewed writable region")
                # Use the largest allowed page number during allocation to avoid under-reserving.
                provisional_refs = "; ".join(
                    f"packet page {MAX_PACKET_PAGES}"
                    for _ in {(c.source_id, c.page) for c in proposal.citations}
                )
                complete = value.value + "\nSupporting evidence: " + provisional_refs + "."
                narrative_region = mapped.narrative_region
                if any(not (32 <= ord(c) <= 126 or c == "\n") for c in complete):
                    raise DraftError("Unsupported font characters; narrative needs font review")
                lines = wrap_text(
                    complete,
                    narrative_region.right - narrative_region.left,
                    narrative_region.font_size,
                    _measure,
                )
                overflow = lines is None or len(lines) > math.floor(
                    (narrative_region.top - narrative_region.bottom) / narrative_region.leading
                )
                if overflow:
                    _lines(
                        f"See Supplemental Answers, {identity}, packet page {MAX_PACKET_PAGES}.",
                        narrative_region,
                    )
                    reserve_supplement(identity, value.value)
                placements[identity] = {"mode": "supplement" if overflow else "inline"}
            else:
                raise DraftError("This draft slice does not write this answer type")
        except DraftError as error:
            issues.append(str(error))
            continue
        texts.extend(candidate_texts)
        marks.extend(candidate_marks)
        result["status"] = "written_to_draft"
        issues.append("draft_only_requires_final_human_review")
        accepted.append(proposal)
        written_by_id[identity] = proposal

    results_by_id = {str(r["requirement_id"]): r for r in results}
    reconciled: set[str] = set()

    def reconcile(identity: str) -> None:
        if identity in reconciled:
            return
        assessment = assessments.get(identity)
        if assessment is None:
            return
        for dependency in assessment.depends_on:
            reconcile(dependency)
        result = results_by_id[identity]
        coverage = reconcile_requirement(
            assessment,
            {key: str(r["status"]) for key, r in results_by_id.items()},
            tuple(attachment_ids),
        )
        result["requirement_assessment"] = assessment.model_dump(mode="json")
        result["coverage"] = asdict(coverage)
        if assessment.applicability == "required" and requirements[identity].kind == "attachment":
            if coverage.satisfied and requires_personal_action(requirements[identity]):
                raise DraftError("Checklist cannot clear a new personal act")
            result["review_reason"] = assessment.reason
            result["effective_explanation"] = assessment.reason
            result["issues"] = (
                [] if coverage.satisfied else ["requirement_coverage_" + coverage.evidence_state]
            )
            result["status"] = "requirement_satisfied" if coverage.satisfied else "blank"
            mapping = mappings.get(identity)
            if coverage.satisfied and mapping is not None and mapping.checklist_box is not None:
                marks.append(MarkPlacement(mapping.checklist_box, "checkbox"))
                result["checklist_state"] = "marked"
            else:
                result["checklist_state"] = (
                    "satisfied_placement_unavailable" if coverage.satisfied else "not_satisfied"
                )
        reconciled.add(identity)

    for identity in assessments:
        reconcile(identity)
    results.sort(key=lambda result: requirement_order[str(result["requirement_id"])])
    completion = {
        "populated": sum(r["status"] == "written_to_draft" for r in results),
        "conditional_not_applicable": sum(
            r["status"] == "not_applicable" and "conditional" in r for r in results
        ),
        "not_applicable": sum(
            r["status"] == "not_applicable" and "conditional" not in r for r in results
        ),
        "optional_not_supplied": sum(r["status"] == "optional_not_supplied" for r in results),
        "evidence_satisfied": sum(r["status"] == "requirement_satisfied" for r in results),
        "human_action_required": 0,
        "unresolved": 0,
    }
    for result in results:
        if result["status"] != "blank":
            continue
        req = requirements[str(result["requirement_id"])]
        result_issues = result["issues"]
        human = requires_personal_action(req) or (
            isinstance(result_issues, list)
            and (
                "historical_personal_act_not_permitted" in result_issues
                or "unresolved_signer" in result_issues
                or "deferred_to_signing" in result_issues
            )
        )
        disposition = "human_action_required" if human else "unresolved"
        result["completion_disposition"] = disposition
        completion[disposition] += 1

    section_data = [
        PacketSection(
            section_id="form",
            source_sha256=request.layout.application_sha256,
            page_count=len(reader.pages),
            role="form",
        )
    ]
    section_data.extend(
        PacketSection(
            section_id=f"additional-form-{form.source.sha256[:16]}",
            source_sha256=form.source.sha256,
            page_count=len(form_reader.pages),
            role="form",
        )
        for form, _, form_reader in additional_forms_data
    )
    if supplement_page_count:
        section_data.append(
            PacketSection(
                section_id="answers",
                source_sha256="0" * 64,
                page_count=supplement_page_count,
                role="supplemental_answers",
            )
        )
    section_data.extend(
        PacketSection(
            section_id=source.source_id,
            source_sha256=source.sha256,
            page_count=len(attachment_reader.pages),
            role="evidence",
        )
        for source, attachment_reader in attachment_readers
    )
    section_data.extend(
        PacketSection(
            section_id=exhibit.exhibit_id,
            source_sha256=hashlib.sha256(data).hexdigest(),
            page_count=len(exhibit_reader.pages),
            role="evidence",
        )
        for exhibit, data, exhibit_reader in exhibit_data
    )
    pagination = PacketPagination(sections=tuple(section_data))
    accepted_by_id = {proposal.requirement_id: proposal for proposal in accepted}
    additional_form_texts: list[list[TextPlacement]] = []
    additional_form_manifest: list[dict[str, object]] = []
    for form, _, _ in additional_forms_data:
        form_texts: list[TextPlacement] = []
        written_requirements: list[str] = []
        for field in form.fields:
            approved_proposal = accepted_by_id.get(field.requirement_id)
            if approved_proposal is None or approved_proposal.value is None:
                continue
            if not isinstance(approved_proposal.value, (TextValue, IdentifierValue)):
                raise DraftError(
                    "Additional issuer form fields require an approved text or identifier answer"
                )
            additional_text = approved_proposal.value.value
            additional_fit = fit_short_text(additional_text, field.region)
            if additional_fit is None:
                raise DraftError("Answer cannot fit at the minimum readable font size")
            form_texts.append(additional_fit)
            if field.requirement_id not in written_requirements:
                written_requirements.append(field.requirement_id)
        additional_form_texts.append(form_texts)
        additional_form_manifest.append(
            {
                "path": form.source.path,
                "sha256": form.source.sha256,
                "written_requirements": written_requirements,
                "fields": [
                    {
                        "requirement_id": field.requirement_id,
                        "page": field.region.page,
                        "written": field.requirement_id in written_requirements,
                    }
                    for field in form.fields
                ],
            }
        )
    supplement_evidence: dict[str, str] = {}
    for proposal in accepted:
        identity = proposal.requirement_id
        evidence_refs = tuple(
            PacketReference(section_id=c.source_id, page=c.page)
            for c in proposal.citations
            if sources[c.source_id].family != "historical_reference"
        )
        refs = tuple(dict.fromkeys(pagination.resolve(r, role="evidence") for r in evidence_refs))
        placements[identity]["evidence_packet_pages"] = list(refs)
        evidence_text = (
            "Supporting evidence: " + "; ".join(f"packet page {p}" for p in refs) + "."
            if refs
            else "Historical draft basis; internal reviewer confirmation required."
        )
        supplement_evidence[identity] = evidence_text
        if isinstance(proposal.value, TextValue) and identity in supplement_starts:
            scalar_region = mappings[identity].text_region
            if scalar_region is None:
                raise DraftError("Text mapping disappeared")
            start = pagination.resolve(
                PacketReference(section_id="answers", page=supplement_starts[identity]),
                role="supplemental_answers",
            )
            texts.append(
                TextPlacement(scalar_region, _lines(f"See packet page {start}.", scalar_region))
            )
        if isinstance(proposal.value, NarrativeValue):
            answer_narrative_region = mappings[identity].narrative_region
            if answer_narrative_region is None:
                raise DraftError("Narrative mapping disappeared")
            if identity in supplement_starts:
                start = pagination.resolve(
                    PacketReference(section_id="answers", page=supplement_starts[identity]),
                    role="supplemental_answers",
                )
                marker = f"See Supplemental Answers, {identity}, packet page {start}."
                texts.append(
                    TextPlacement(
                        answer_narrative_region,
                        _lines(marker, answer_narrative_region),
                    )
                )
            else:
                texts.append(
                    TextPlacement(
                        answer_narrative_region,
                        _lines(
                            proposal.value.value + "\n" + evidence_text,
                            answer_narrative_region,
                        ),
                    )
                )

    supplemental_bytes: bytes | None = None
    if supplements:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        for identity, lines in supplements:
            for start in range(0, len(lines), SUPPLEMENT_LINES):
                canvas.setFont("Helvetica-Bold", 10)
                canvas.drawString(30, 770, "INCOMPLETE DRAFT - NOT FOR SUBMISSION")
                canvas.drawString(40, 735, "Supplemental Answers - " + identity)
                canvas.setFont("Helvetica", 10)
                canvas.drawString(40, 715, f"Response to form page {requirements[identity].page}.")
                for index, line in enumerate(lines[start : start + SUPPLEMENT_LINES]):
                    canvas.drawString(40, 690 - index * 14, line)
                reference_lines = wrap_text(supplement_evidence[identity], 520.0, 10.0, _measure)
                if reference_lines is None or len(reference_lines) > 4:
                    raise DraftError("Supplemental evidence references exceed reserved space")
                for index, line in enumerate(reference_lines):
                    canvas.drawString(40, 70 - index * 12, line)
                canvas.showPage()
        canvas.save()
        supplemental_bytes = stream.getvalue()
        section_data[1] = section_data[1].model_copy(
            update={"source_sha256": hashlib.sha256(supplemental_bytes).hexdigest()}
        )
        pagination = PacketPagination(sections=tuple(section_data))
    main_form_pdf = _form_pdf(original, texts, marks, request.mode == "fictional")
    additional_form_pdfs = [
        _form_pdf(form_bytes, form_texts, [], request.mode == "fictional")
        for (_, form_bytes, _), form_texts in zip(
            additional_forms_data, additional_form_texts, strict=True
        )
    ]
    with closing(PdfWriter(clone_from=PdfReader(BytesIO(main_form_pdf)))) as writer:
        for (additional_form, _, _), additional_pdf in zip(
            additional_forms_data, additional_form_pdfs, strict=True
        ):
            start = len(writer.pages)
            writer.append(PdfReader(BytesIO(additional_pdf)), import_outline=False)
            writer.add_outline_item(f"Issuer form {additional_form.source.sha256[:12]}", start)
        if supplemental_bytes:
            writer.append(PdfReader(BytesIO(supplemental_bytes)), import_outline=False)
        for source, attachment_reader in attachment_readers:
            start = len(writer.pages)
            writer.append(attachment_reader, import_outline=False)
            writer.add_outline_item(f"Evidence {source.source_id[:12]}", start)
        for exhibit, _, exhibit_reader in exhibit_data:
            start = len(writer.pages)
            writer.append(exhibit_reader, import_outline=False)
            writer.add_outline_item(f"Historical exhibit {exhibit.exhibit_id}", start)
        writer.add_metadata({"/Title": "INCOMPLETE DRAFT - NOT FOR SUBMISSION"})
        buffer = BytesIO()
        writer.write(buffer)
    packet = buffer.getvalue()
    if len(PdfReader(BytesIO(packet)).pages) != sum(s.page_count for s in pagination.sections):
        raise DraftError("Final packet pagination does not match assembled output")

    def verify() -> None:
        inputs = [(request_path, raw)]
        if review_path is not None:
            inputs.append((review_path, reviewed))
        for path, snapshot in inputs:
            if read_local_input(root, path, Path("outputs"), 2 * 1024 * 1024) != snapshot:
                raise DraftError("Draft input or review changed; no output published")
        if (
            read_local_input(
                root, Path(request.source), Path("bd_agreements/Blank"), 64 * 1024 * 1024
            )
            != original
        ):
            raise DraftError("Blank application changed; no output published")
        for path, snapshot in additional_form_snapshots.items():
            if (
                read_local_input(root, path, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
                != snapshot
            ):
                raise DraftError("Additional issuer form changed; no output published")
        for path, snapshot in ocr_artifact_snapshots.items():
            if read_local_input(root, path, Path("outputs"), 2 * 1024 * 1024) != snapshot:
                raise DraftError("OCR evidence changed; no output published")

    payload: dict[str, object] = {
        "domain_knowledge": knowledge_context(),
        "schema_version": 1,
        "writer_version": "reviewed-draft-overlay-v20",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "incomplete_draft_not_for_submission",
        "mode": request.mode,
        "request_sha256": request_hash,
        "review_sha256": hashlib.sha256(reviewed).hexdigest(),
        "reviewer": review.reviewer,
        "source": request.source,
        "application_sha256": request.layout.application_sha256,
        "requirements": request.requirements.model_dump(mode="json"),
        "layout": request.layout.model_dump(mode="json"),
        "review": review.model_dump(mode="json"),
        "additional_forms": additional_form_manifest,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "written_requirements": [p.requirement_id for p in accepted],
        "completion": completion,
        "answers": results,
        "placements": placements,
        "pagination": pagination.model_dump(mode="json"),
        "sources": [asdict(s) for s in inventory.sources],
        "historical_exhibits": [
            {
                **exhibit.model_dump(mode="json"),
                "exhibit_id": exhibit.exhibit_id,
                "extracted_sha256": hashlib.sha256(data).hexdigest(),
                "source_sha256": sources[exhibit.title.source_id].sha256,
                "source_path": sources[exhibit.title.source_id].path,
            }
            for exhibit, data, _ in exhibit_data
        ],
        "supporting_document_audit": [
            a.model_dump(mode="json")
            for a in audit_support(
                tuple(accepted), inventory, tuple(attachment_ids), approved_exhibits
            )
        ],
        "historical_archive": (
            request.historical_archive.model_dump(mode="json")
            if request.historical_archive
            else None
        ),
        "signature_policy": "signatures_and_signature_dates_left_blank",
        "unapproved_attachments_omitted": [
            s for s in request.attachments if s not in attachment_ids
        ],
        "limitations": [
            "review_JSON_is_trusted_input_not_authentication",
            "declared_subset_only_not_full_application_coverage",
            "native_unrotated_blank_mapping_only",
            "OCR_requires_human_review_or_scalar_machine_cross_check_not_semantic_approval",
            "no_historical_comparison_or_business_approval",
        ],
    }

    def write(output: Path) -> None:
        (output / "draft-packet.pdf").write_bytes(packet)
        render = _render_checks(
            original,
            packet,
            output,
            [t.region for t in texts] + [m.box for m in marks],
            marks,
            texts,
        )
        additional_render_checks: list[dict[str, object]] = []
        page_offset = len(reader.pages)
        for index, ((_form_request, form_bytes, form_reader), form_texts) in enumerate(
            zip(additional_forms_data, additional_form_texts, strict=True), start=1
        ):
            additional_render_checks.append(
                _render_checks(
                    form_bytes,
                    packet,
                    output,
                    [placement.region for placement in form_texts],
                    [],
                    form_texts,
                    packet_page_offset=page_offset,
                    filename_prefix=f"additional-form-{index}-",
                )
            )
            page_offset += len(form_reader.pages)
        render["additional_forms"] = additional_render_checks
        with pdfium.PdfDocument(packet) as document:
            for identity, lines in supplements:
                for offset in range(0, len(lines), SUPPLEMENT_LINES):
                    number = form_count + supplement_starts[identity] + offset // SUPPLEMENT_LINES
                    with (
                        closing(document[number - 1]) as page,
                        closing(page.get_textpage()) as text,
                    ):
                        extracted = text.get_text_bounded(
                            left=40.0, bottom=105.0, right=560.0, top=705.0, errors="strict"
                        )
                        # PDFium replaces a visible line-ending hyphen and break with STX.
                        actual = " ".join(extracted.replace("\x02", "- ").split())
                        expected = " ".join(
                            " ".join(lines[offset : offset + SUPPLEMENT_LINES]).split()
                        )
                        if expected not in actual:
                            raise DraftError(
                                f"Supplemental answer is missing or clipped: {identity}, "
                                f"page {number}"
                            )
                    with _render_image(packet, number - 1) as image:
                        image.save(output / f"supplement-page-{number}.png")
        render["supplement_pages_rendered_and_text_checked"] = supplement_page_count
        payload["render_checks"] = render
        # The shared publisher writes its initial report before companion validation.
        (output / "draft.json").write_text(json.dumps(payload, indent=2) + "\n")
        summary = [
            "INTERNAL REVIEW - NOT PART OF THE SUBMISSION PACKET",
            "INCOMPLETE DRAFT - NOT FOR SUBMISSION",
            f"Mode: {request.mode}",
            "Coverage: declared subset only; all other form fields remain unresolved.",
            "Signatures and signature dates must be completed only by humans at signing.",
            f"Completion: {completion}. Conditional not-applicable is NOT a populated answer.",
        ]
        for form in additional_form_manifest:
            summary.append(
                "Additional issuer form appended: "
                f"{form['path']}; approved mirrored fields: {form['written_requirements']}."
            )
        if review.reviewer_notes:
            summary.extend(["", "Reviewer notes:"])
            summary.extend(f"- {note}" for note in review.reviewer_notes)
        summary.extend(["", "REVIEWER ACTION LIST (internal only):"])
        for item in results:
            identity = str(item["requirement_id"])
            printed_details = item.get("historical_printed_readings")
            printed_records = (
                [r for r in printed_details if isinstance(r, dict)]
                if isinstance(printed_details, list)
                else []
            )
            resolved_printed = any(r.get("status") == "resolved" for r in printed_records)
            if printed_records:
                for reading in printed_records:
                    summary.append(
                        f"- Form page {requirements[identity].page}, {identity}: "
                        f"PRINTED-WORDING CHECK: {reading['part']}; "
                        f"status={reading['status']}; method="
                        + (
                            "localized source-native text"
                            if reading["native"]
                            else "blind focused image reread"
                            if reading["focused"]
                            else "reread budget exhausted"
                        )
                        + ". Original readings remain below; this does not establish "
                        "current business truth or approve a selection."
                    )
            extraction_details = item.get("historical_extraction_discrepancies")
            extraction_parts = (
                tuple(
                    dict.fromkeys(
                        str(d["part"])
                        for d in extraction_details
                        if isinstance(d, dict)
                        and d.get("code") != "historical_question_presentation_resolved"
                    )
                )
                if isinstance(extraction_details, list)
                else ()
            )
            if isinstance(extraction_details, list) and any(
                isinstance(d, dict) and d.get("code") == "historical_question_presentation_resolved"
                for d in extraction_details
            ):
                summary.append(
                    f"- {identity}: QUESTION PRESENTATION RESOLVED; substantive wording agrees. "
                    "Original readings retained; applicability, answer support and historical "
                    "continuity are separate checks."
                )
            if item["status"] in ("blank", "requirement_satisfied") or identity in assessments:
                assessment = assessments.get(identity)
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    f"{'LEFT BLANK' if item['status'] == 'blank' else item['status']}; "
                    + (
                        "Historical question transcription was reconciled against source "
                        "evidence, but the answer was not written; see validation details."
                        if item.get("historical_question_reconciliation")
                        else "Historical extraction differs in: "
                        + ", ".join(extraction_parts)
                        + ". Question wording, answer text and selected marks are checked "
                        "separately; a question-reading problem does not mean the checkbox "
                        "could not be read."
                        if "question" in extraction_parts
                        else "Conflicting readings were not resolved with verified evidence "
                        "linking the same subject, field and value."
                        if extraction_parts
                        else str(item.get("effective_explanation") or item["review_reason"])
                    )
                )
                if item["status"] == "blank":
                    basis = next(
                        p.historical_basis
                        for p in request.proposals.proposals
                        if p.requirement_id == identity
                    )
                    if basis is not None and basis.correspondence is not None:
                        correspondence = basis.correspondence
                        summary.append(
                            f"  QUESTION CORRESPONDENCE ({correspondence.assessment}; "
                            "model interpretation, not semantic approval): "
                            f"{correspondence.reason} "
                            f"Differences/coverage gap: {correspondence.differences}. "
                            f"Historical source: {basis.prior_question.source_id}, "
                            f"page {basis.prior_question.page}."
                        )
                    summary.append(
                        f"  Validation details: {item['review_reason']}; "
                        f"writer checks: {item['issues']}"
                    )
                    codes = f"{item['review_reason']} {item['issues']}"
                    summary.extend(
                        f"  Plain-language reason: {text}"
                        for code, text in _PLAIN_HISTORICAL_REASONS.items()
                        if code in codes
                    )
                if item.get("historical_extraction_discrepancies"):
                    summary.append(
                        (
                            "  Original extraction readings (question transcription reconciled): "
                            if item.get("historical_question_reconciliation")
                            else "  Conflicting extraction readings (originals): "
                        )
                        + json.dumps(item["historical_extraction_discrepancies"])
                    )
                if assessment is not None:
                    summary.append(
                        f"  Reviewed applicability: {assessment.applicability}; "
                        f"reviewer/provenance: {assessment.reviewer}. "
                        "Local review input is not authenticated approval."
                    )
                    for criterion in assessment.criteria:
                        summary.append(
                            f"  Issuer criterion: {criterion.issuer_quote}; "
                            f"coverage={criterion.status}. {criterion.explanation}"
                        )
                        if criterion.status not in ("supported", "not_applicable"):
                            summary.append(f"  ACTION: {criterion.action}")
                        for assessed_citation in criterion.evidence:
                            assessed_source = sources[assessed_citation.source_id]
                            in_packet = assessed_citation.source_id in attachment_ids
                            packet_page = (
                                pagination.resolve(
                                    PacketReference(
                                        section_id=assessed_citation.source_id,
                                        page=assessed_citation.page,
                                    ),
                                    role="evidence",
                                )
                                if in_packet
                                else "not included"
                            )
                            summary.append(
                                f"  Evidence: {assessed_source.path}; "
                                f"sha256={assessed_source.sha256}; "
                                f"source page {assessed_citation.page}; packet page {packet_page}; "
                                "inclusion alone is not requirement satisfaction."
                            )
                    if assessment.depends_on:
                        summary.append(
                            "  Completion evaluated from actual required-item outcomes: "
                            + str(item.get("coverage"))
                        )
                    for note in assessment.historical_notes:
                        assessed_source = sources[note.citation.source_id]
                        summary.append(
                            f"  HISTORICAL LIMITATION, NOT INITIALS OR CURRENT CONFIRMATION: "
                            f"{note.citation.quote}; {note.explanation} "
                            f"Source: {assessed_source.path}; sha256={assessed_source.sha256}; "
                            f"page {note.citation.page}. ACTION: {note.action}"
                        )
                elif item["status"] == "blank":
                    summary.append(
                        "  ACTION: Question transcription is already resolved. Review the "
                        "remaining validation issues or regenerate the answer proposal; do not "
                        "request new business evidence solely for this OCR defect."
                        if item.get("historical_question_reconciliation")
                        else "  ACTION: Inspect the original historical question and its selected "
                        "answer together. Resolve the specific question wording difference; "
                        "current business evidence is not required merely to repair transcription."
                        if "question" in extraction_parts
                        and not item.get("historical_question_reconciliation")
                        else "  ACTION: Verify the conflicting readings against an independent "
                        "source for the same subject and field; enter the supported value "
                        "only after verification."
                        if extraction_parts
                        else "  ACTION: "
                        + str(item.get("effective_explanation") or item["review_reason"])
                    )
            elif item["status"] == "written_to_draft":
                proposal = next(
                    p for p in request.proposals.proposals if p.requirement_id == identity
                )
                basis = proposal.historical_basis
                if basis is not None and basis.reading_resolution is not None:
                    summary.append(
                        f"- Form page {requirements[identity].page}, {identity}: "
                        "FILLED AFTER RECONCILIATION; selected value "
                        + str(proposal.value.model_dump(mode="json") if proposal.value else None)
                        + "; independent identity/field evidence "
                        + basis.reading_resolution.citation.model_dump_json()
                        + "; original readings "
                        + json.dumps(item.get("historical_extraction_discrepancies", []))
                    )
                elif (
                    item.get("historical_candidate_status") == "reconciled_with_native_text_and_ocr"
                ):
                    summary.append(
                        f"- Form page {requirements[identity].page}, {identity}: "
                        "FILLED AFTER RECONCILIATION; exact native digits and high-confidence "
                        "OCR agree within the historical answer region. Original readings: "
                        + json.dumps(item.get("historical_extraction_discrepancies", []))
                    )
                elif resolved_printed:
                    summary.append(
                        f"- Form page {requirements[identity].page}, {identity}: "
                        "FILLED AFTER PRINTED-WORDING RESOLUTION. Local source evidence resolved "
                        "the transcription difference; the selected answer was checked separately. "
                        "Historical continuity remains unconfirmed."
                    )
                elif item.get("historical_question_reconciliation"):
                    summary.append(
                        f"- Form page {requirements[identity].page}, {identity}: "
                        "FILLED AFTER QUESTION-TEXT RECONCILIATION; the historical image question "
                        "matches the native blank, and bounded OCR alignment passed. "
                        "The selected answer was checked separately. Historical continuity "
                        "remains unconfirmed."
                    )
                    summary.append(
                        "  Historical selected answer: "
                        + "; ".join(
                            c.field.answer.text
                            for c in review.historical_context_checks
                            if c.supports(proposal, requirements[identity])
                        )
                    )
                    if isinstance(extraction_details, list):
                        for difference in extraction_details:
                            if (
                                isinstance(difference, dict)
                                and difference.get("part") == "question"
                            ):
                                summary.extend(
                                    [
                                        "  Image question: " + str(difference["image_reading"]),
                                        "  OCR question: " + str(difference["ocr_reading"]),
                                    ]
                                )
        adjusted = [
            (identity, placement)
            for identity, placement in placements.items()
            if placement.get("fit") not in (None, "standard")
        ]
        if adjusted:
            summary.extend(
                [
                    "",
                    "SHORT-FIELD FIT (internal; reduced font, wrapped or moved to the supplement; "
                    f"minimum {MIN_SHORT_FONT:g} pt; check legibility):",
                ]
            )
            for identity, placement in adjusted:
                summary.append(
                    f"- {identity}: below_minimum_font; written in Supplemental Answers."
                    if placement["mode"] == "supplement"
                    else f"- {identity}: {placement['fit']}; {placement['font_size']:g} pt, "
                    f"{placement['line_count']} line(s)."
                )
        summary.extend(["", "Supporting-document completeness (not semantic approval):"])
        for audit in audit_support(
            tuple(accepted), inventory, tuple(attachment_ids), approved_exhibits
        ):
            summary.append(
                f"- {audit.requirement_id}: current documents="
                f"{','.join(audit.current_source_ids) or 'none'}; "
                f"historical exhibits={','.join(audit.historical_exhibits) or 'none'}; "
                "referenced support="
                f"{'; '.join(audit.referenced_support) or 'none declared/detected'}; "
                f"issues={','.join(audit.issues) or 'no physical dependency gaps detected'}."
            )
        for exhibit in approved_exhibits:
            summary.append(
                f"- HISTORICAL EXHIBIT {exhibit.exhibit_id}, requirement {exhibit.requirement_id}: "
                f"{sources[exhibit.title.source_id].path}, source hash "
                f"{sources[exhibit.title.source_id].sha256}, pages {exhibit.pages}. "
                f"{exhibit.reason} LIMITATION: {exhibit.limitation} "
                "Historical inclusion does not verify current truth or satisfy a dated claim."
            )
        proposals_by_id = {p.requirement_id: p for p in request.proposals.proposals}
        for item in results:
            proposal = proposals_by_id[str(item["requirement_id"])]
            summary_decision = decisions.get(proposal.requirement_id)
            packet_pages = placements.get(proposal.requirement_id, {}).get(
                "evidence_packet_pages", []
            )
            summary.extend(
                [
                    "",
                    f"{item['requirement_id']}: {item['status']} - {item['issues']}",
                    f"Question: {requirements[proposal.requirement_id].instruction}",
                    f"Form page: {requirements[proposal.requirement_id].page}",
                    "Proposed value: "
                    + (
                        "(not applicable; no answer written)"
                        if item["status"] == "not_applicable"
                        else proposal.value.model_dump_json()
                        if proposal.value
                        else "(blank)"
                    ),
                    f"Review: {item['review_reason']}",
                    f"Explanation: {item.get('effective_explanation') or '(none supplied)'}",
                    f"Evidence packet pages: {packet_pages}",
                    "MODEL-REPORTED KNOWLEDGE APPLICATION (not verified reasoning): "
                    + (
                        "; ".join(
                            f"{use.entry_id}: {use.reason}" for use in proposal.knowledge_applied
                        )
                        if proposal.knowledge_applied
                        else "none reported"
                    ),
                ]
            )
            if item["status"] == "not_applicable" or (
                item["status"] != "written_to_draft" and item.get("conditional") is not None
            ):
                continue
            if proposal.historical_basis is not None and isinstance(
                proposal.historical_basis.prior_question, HistoricalContextCitation
            ):
                receipt = next(
                    (
                        c
                        for c in review.historical_context_checks
                        if c.context_citation == proposal.historical_basis.prior_question
                    ),
                    None,
                )
                summary.append(
                    "Question/answer association: localized OCR and independent image reading, "
                    "with source/render hashes and normalized question/answer/role boxes; "
                    "not human approval or current role confirmation."
                )
                if receipt is not None:
                    extraction_details = item.get("historical_extraction_discrepancies", [])
                    if isinstance(extraction_details, list):
                        for discrepancy in extraction_details:
                            summary.append(
                                "EXTRACTION DISCREPANCY - ORIGINAL READINGS "
                                "(see final disposition): " + json.dumps(discrepancy)
                            )
                    summary.append(
                        "Image-proposed association regions (0-1000, full image, top-left; "
                        "also checked against local text geometry): "
                        + receipt.field.model_dump_json()
                    )
            if proposal.historical_basis is not None:
                summary.extend(
                    historical_review_concerns(requirements[proposal.requirement_id], proposal)
                )
                basis = proposal.historical_basis
                status = (
                    "HISTORICAL - CONTINUITY UNCONFIRMED"
                    if item["evidence_status"] == "historical_continuity_unconfirmed"
                    else str(item["evidence_status"]).upper()
                )
                summary.extend(
                    [
                        f"HISTORICAL BASIS: {status}; not human approval.",
                        f"Context: {basis.context}; category={basis.category}; "
                        f"role={basis.role or 'none'}",
                        f"Prior question/context: {basis.prior_question.quote}",
                        f"REVIEWER MUST CONFIRM: {basis.reviewer_confirmation}",
                        "Historical originals are internal only and are NOT appended "
                        "to the packet.",
                    ]
                )
                if basis.tenure is not None:
                    summary.append(
                        f"DERIVED TENURE: prior={basis.tenure.prior_value}; "
                        f"signed={basis.tenure.signed_on}; calculated as of="
                        f"{request.calculation_date}; completed calendar anniversaries "
                        "(February 29 anniversaries use February 28 in non-leap years). "
                        f"Signing metadata provenance: {basis.tenure.model_dump_json()}. "
                        "Not a verified founding/hire date or confirmation of continuity."
                    )
                for entry in (
                    request.historical_archive.entries if request.historical_archive else ()
                ):
                    if any(
                        sources.get(c.source_id) and sources[c.source_id].path == entry.path
                        for c in proposal.citations
                    ):
                        summary.append(
                            f"Prior issuer: {entry.issuer}; packet date: "
                            f"{str(entry.completed_on) if entry.completed_on else 'unknown'}; "
                            f"source: {entry.path}; sha256={entry.sha256}"
                        )
                if not basis.current_checks:
                    summary.append("Current corroboration: no cited current-source checks.")
                for current_check in basis.current_checks:
                    checked = sources.get(current_check.citation.source_id)
                    summary.append(
                        f"Current check (model assessment, not proof): {current_check.finding}; "
                        f"{checked.path if checked else 'UNRESOLVED SOURCE'}; "
                        f"sha256={checked.sha256 if checked else 'unknown'}; "
                        f"page {current_check.citation.page}; {current_check.explanation}"
                    )
            for citation in proposal.citations:
                source = sources.get(citation.source_id)
                summary.append(
                    f"Evidence: {source.path if source else 'UNRESOLVED SOURCE'}; "
                    f"sha256={source.sha256 if source else citation.source_id}; "
                    f"source page {citation.page}"
                )
                if isinstance(citation, OcrCitation):
                    summary.append(
                        f"OCR quote: {citation.quote}; artifact {citation.artifact_path}; "
                        f"word range [{citation.word_start}, {citation.word_end}); "
                        "see draft.json for exact pixel bounds and render hash."
                    )
            if any(isinstance(c, OcrCitation) for c in proposal.citations):
                confirmed_subject = (
                    summary_decision.confirmed_source_subject
                    if summary_decision
                    else "(not confirmed)"
                )
                visual_confirmation = (
                    summary_decision.ocr_visual_confirmed if summary_decision else False
                )
                summary.append(
                    "OCR review: "
                    f"source subject confirmed as {confirmed_subject}; "
                    f"visual confirmation={visual_confirmation}."
                )
                if (
                    item.get("ocr_review_method")
                    == "machine_cross_checked_draft_not_human_approval"
                ):
                    summary.append(
                        "Machine evidence processing: see localized receipt and any extraction "
                        "discrepancies above; agreement must not be presumed. "
                        "not human visual approval or proof of semantic support. "
                        "See answer_review.json for subject, period, prompt/model and transcript."
                    )
        summary.extend(
            [
                "",
                "Detailed checks, quotations and output hashes: see draft.json.",
                "Prior-packet comparison and signer-specific copies: not performed.",
            ]
        )
        (output / "reviewer-summary.txt").write_text("\n".join(summary) + "\n")

    return publish_json_run(
        root, "draft", payload, inventory, verify_inputs=verify, write_artifacts=write
    )
