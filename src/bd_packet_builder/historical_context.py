"""Image-proposed historical relationships cross-checked against local text and geometry."""

import hashlib
import json
import math
import re
from contextlib import closing
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Literal

import pypdfium2 as pdfium
from pydantic import Field

from bd_packet_builder.contracts import (
    AnswerProposal,
    BooleanValue,
    Citation,
    Contract,
    HistoricalContextCitation,
    IdentifierValue,
    NarrativeValue,
    Nonblank,
    OcrCitation,
    Requirement,
    TextValue,
    explicit_choice_answer,
)
from bd_packet_builder.evidence import EvidenceError, resolve_quote
from bd_packet_builder.historical_controls import inspect_control
from bd_packet_builder.inventory import Inventory, read_source_bytes
from bd_packet_builder.layout import MappedResponse
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.ocr import ocr_text
from bd_packet_builder.scan import (
    SCAN_VERSION,
    SUPPORTED_SCAN_VERSIONS,
    HistoricalPageField,
    HistoricalPagePart,
    ScanEvidence,
    ScanTranscript,
    ScanVerificationError,
    _render_image,
    normalized,
    parse_ocr_artifact,
)
from bd_packet_builder.visual import NormalizedBox

CONTEXT_VERSION = "historical-page-context-v7"
QUESTION_READING_VERSION = "question-reading-v1"

_QUESTION_PROTECTED = re.compile(
    r"no|not|never|ever|neither|nor|without|except|unless|only|all|any|each|every|and|or|"
    r"before|after|since|until|within|during|last|past|current|prior|most|recent|"
    r"day|days|month|months|year|years|january|february|march|april|may|june|july|august|"
    r"september|october|november|december|zero|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|hundred|thousand|million|billion|percent|minimum|maximum|at|least|more|less|than"
)


def _question_tokens(text: str) -> list[str]:
    text = re.sub(r"^\s*\d{1,3}[.)]\s*", "", text)
    return re.findall(r"[a-z0-9]+", normalized(text))


def question_text_agrees(image: str, ocr: str, target: str) -> bool:
    """Align a localized question, never an answer or a changed substantive condition."""
    expected, observed = _question_tokens(image), _question_tokens(ocr)
    if expected != _question_tokens(target) or not expected:
        return False
    value_pattern = r"[<>\u2264\u2265=\u00b1%$\u20ac\u00a3]|(?<!\w)[+-]?\d+(?:[.,]\d+)*"
    values = [
        re.findall(value_pattern, re.sub(r"^\s*\d{1,3}[.)]\s*", "", text))
        for text in (image, ocr, target)
    ]
    if values[0] != values[1] or values[0] != values[2]:
        return False

    def protected(tokens: list[str]) -> list[str]:
        return [
            token
            for token in tokens
            if _QUESTION_PROTECTED.fullmatch(token) or any(c.isdigit() for c in token)
        ]

    if protected(expected) != protected(observed):
        return False
    if "".join(expected) == "".join(observed):
        return True
    if len(expected) < 12 or len(expected) != len(observed):
        return False
    changed = [
        i for i, pair in enumerate(zip(expected, observed, strict=True)) if pair[0] != pair[1]
    ]
    if len(changed) != 1:
        return False
    index = changed[0]
    whole, fragment = expected[index], observed[index]
    # A truncated lowercase word can be corroborated, not freely spell-corrected. In
    # particular, do not turn an entity, negation prefix or a different word into agreement.
    original_words = re.findall(r"[A-Za-z0-9]+", re.sub(r"^\s*\d{1,3}[.)]\s*", "", image))
    return (
        len(original_words) == len(expected)
        and original_words[index].islower()
        and not whole.startswith(("un", "non", "dis"))
        and len(whole) >= 8
        and 3 <= len(fragment) <= len(whole) * 0.6
        and fragment in whole
        and SequenceMatcher(None, " ".join(expected), " ".join(observed), autojunk=False).ratio()
        >= 0.94
    )


def verified_question_requirements(
    blank: bytes, requirements: tuple[Requirement, ...]
) -> tuple[Requirement, ...]:
    """Return only unique native questions from this exact blank, not model assertions."""
    digest = hashlib.sha256(blank).hexdigest()
    result: list[Requirement] = []
    with pdfium.PdfDocument(blank) as document:
        pages: dict[int, str] = {}
        for requirement in requirements:
            if requirement.application_sha256 != digest or requirement.page > len(document):
                continue
            if requirement.page not in pages:
                with (
                    closing(document[requirement.page - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    pages[requirement.page] = normalized(text.get_text_bounded(errors="strict"))
            wanted = normalized(requirement.instruction)
            if (
                wanted
                and len(
                    re.findall(r"(?<!\w)" + re.escape(wanted) + r"(?!\w)", pages[requirement.page])
                )
                == 1
            ):
                result.append(requirement)
    return tuple(result)


class QuestionReconciliation(Contract):
    version: str = QUESTION_READING_VERSION
    target_requirement_ids: tuple[str, ...]
    status: Literal["reconciled_against_native_blank"] = "reconciled_against_native_blank"
    explanation: str = (
        "The historical image question matches a unique native question in the exact blank. "
        "Localized OCR differs only in spacing/punctuation or one bounded lowercase word "
        "fragment; protected wording and values are unchanged. The selected answer is checked "
        "separately. This resolves question transcription, not current business truth."
    )


def question_reconciliation(
    check: "HistoricalContextCheck", targets: tuple[Requirement, ...]
) -> QuestionReconciliation | None:
    differences = [d for d in check.discrepancies if d.part == "question"]
    if (
        not differences
        or check.field.control is None
        or check.field.control.state != "selected"
        or any(d.part == "control" for d in check.discrepancies)
        or any(
            d.code not in ("historical_text_or_region_disagrees", "historical_low_word_confidence")
            or d.image_reading != check.field.question.text
            or d.ocr_reading != check.question.quote
            for d in differences
        )
    ):
        return None
    identities = tuple(
        target.requirement_id
        for target in targets
        if question_text_agrees(check.field.question.text, check.question.quote, target.instruction)
    )
    return QuestionReconciliation(target_requirement_ids=identities) if identities else None


def option_label(text: str) -> str:
    return normalized(text).strip(" _:.")


def option_label_matches(left: str, right: str) -> bool:
    a, b = option_label(left), option_label(right)
    return a == b or (min(len(a), len(b)) >= 25 and (a.startswith(b) or b.startswith(a)))


def control_option_id(
    field: HistoricalPageField,
    fields: tuple[HistoricalPageField, ...],
    requirement: Requirement,
    mapping: MappedResponse | None,
) -> str | None:
    if field.control is None or requirement.choices is None:
        return None
    label = option_label(field.answer.text)
    options = [
        option
        for option in requirement.choices.options
        if option_label_matches(option.label, label)
    ]
    if len(options) == 1:
        return options[0].option_id
    if not options or mapping is None:
        return None
    peers = sorted(
        (
            f
            for f in fields
            if f.control is not None
            and f.question == field.question
            and option_label(f.answer.text) == label
        ),
        key=lambda f: f.answer.box.left,
    )
    ids = {option.option_id for option in options}
    targets = sorted(
        (p for p in mapping.options if p.option_id in ids), key=lambda p: p.label_box.left
    )
    if (
        len(peers) != len(targets)
        or field not in peers
        or any(
            b.answer.box.left - a.answer.box.left < 60
            for a, b in zip(peers, peers[1:], strict=False)
        )
        or any(
            b.label_box.left - a.label_box.left < 30
            for a, b in zip(targets, targets[1:], strict=False)
        )
    ):
        return None
    return targets[peers.index(field)].option_id


class ExtractionDiscrepancy(Contract):
    part: Literal["question", "role", "answer", "control"]
    code: str
    image_reading: str
    ocr_reading: str
    selection_reason: str


def _read_part(
    raw: bytes,
    path: str,
    part: HistoricalPagePart,
    name: Literal["question", "role", "answer"],
    allow_disagreements: bool,
) -> tuple[OcrCitation, tuple[ExtractionDiscrepancy, ...]]:
    try:
        return _ocr_citation(raw, path, part, question=name == "question"), ()
    except ScanVerificationError as error:
        if not allow_disagreements or str(error) not in (
            "historical_text_or_region_disagrees",
            "historical_low_word_confidence",
        ):
            raise
        code = str(error)
    if code == "historical_low_word_confidence":
        citation = _ocr_citation(raw, path, part, question=name == "question", min_confidence=0)
        return citation, (
            ExtractionDiscrepancy(
                part=name,
                code=code,
                image_reading=part.text,
                ocr_reading=citation.quote,
                selection_reason="Localized readings match but OCR confidence is below the "
                "verification threshold. Prefill as a historical candidate for review.",
            ),
        )
    data = parse_ocr_artifact(raw)
    indices = [
        i
        for i, word in enumerate(data.words)
        if _contains(
            part.box,
            (word.left + word.width / 2) * 1000 / data.image_width,
            (word.top + word.height / 2) * 1000 / data.image_height,
        )
    ]
    if not indices:
        raise ScanVerificationError("historical_region_has_no_local_text")
    start, end = min(indices), max(indices) + 1
    # A regional citation must not include text from another column between its words.
    if indices != list(range(start, end)):
        if end - start > len(indices) + 12 or any(
            not part.box.top - 8
            <= (w.top + w.height / 2) * 1000 / data.image_height
            <= part.box.bottom + 8
            for w in data.words[start:end]
        ):
            raise ScanVerificationError("historical_region_text_not_contiguous")
        code = "historical_region_words_interleaved"
    citation = OcrCitation(
        evidence_kind="ocr",
        source_id=data.source.source_id,
        source_sha256=data.source.sha256,
        page=data.page,
        artifact_path=path,
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        render_sha256=data.render_sha256,
        word_start=start,
        word_end=end,
        quote=ocr_text(data.words[start:end]),
    )
    return citation, (
        ExtractionDiscrepancy(
            part=name,
            code=code,
            image_reading=part.text,
            ocr_reading=citation.quote,
            selection_reason=(
                "Neither reading is preferred. Compare the localized alternatives with "
                "independent identity-linked evidence before choosing a value. "
                "If the difference cannot be resolved, leave the field blank."
            ),
        ),
    )


def _make_check(
    root: Path,
    inventory: Inventory,
    raw: bytes,
    artifact_path: str,
    source_id: str,
    page: int,
    field: HistoricalPageField,
    transcript: ScanTranscript,
    endpoint: str,
    deployment: str,
    allow_disagreements: bool,
    prompt_version: str = SCAN_VERSION,
    context_version: str = CONTEXT_VERSION,
) -> "HistoricalContextCheck":
    _geometry(field, transcript.historical_fields)
    question, warnings = _read_part(
        raw, artifact_path, field.question, "question", allow_disagreements
    )
    role = None
    if field.role is not None:
        role, extra = _read_part(raw, artifact_path, field.role, "role", allow_disagreements)
        warnings += extra
    native = _native_citation(root, inventory, source_id, page, field.answer)
    answer: Citation | OcrCitation
    if native is None:
        answer, extra = _read_part(raw, artifact_path, field.answer, "answer", allow_disagreements)
        warnings += extra
    else:
        answer = native[0]
    if (
        field.control is None
        and isinstance(answer, OcrCitation)
        and re.fullmatch(r"[0-9]{1,64}", field.answer.text)
        and re.fullmatch(r"[0-9]{1,64}", answer.quote)
        and all(
            word.confidence >= 90
            for word in parse_ocr_artifact(raw).words[answer.word_start : answer.word_end]
        )
        and all(
            d.part != "answer" or d.code == "historical_text_or_region_disagrees" for d in warnings
        )
    ):
        native = _native_citation(
            root, inventory, source_id, page, field.answer.model_copy(update={"text": answer.quote})
        )
        if native is not None:
            answer = native[0]
            warnings = tuple(
                d.model_copy(
                    update={
                        "code": "historical_native_numeric_layout_reconciled",
                        "selection_reason": "Exact native digits in the answer region agree with "
                        "high-confidence local OCR. Original image reading retained; no digit "
                        "was inferred and no current identity or continuity was assumed.",
                    }
                )
                if d.part == "answer"
                else d
                for d in warnings
            )
    if field.control is not None and field.write_in is not None:
        write_in_native = _native_citation(root, inventory, source_id, page, field.write_in)
        if write_in_native is None:
            _ocr_citation(raw, artifact_path, field.write_in)
        if (
            field.write_in.box.left < field.answer.box.right - 8
            or field.write_in.box.left - field.answer.box.right > 200
            or abs(field.write_in.box.top - field.answer.box.top) > 25
        ):
            raise ScanVerificationError("historical_write_in_relationship_unresolved")
        if isinstance(answer, OcrCitation) and write_in_native is not None:
            words = parse_ocr_artifact(raw)
            first = words.words[answer.word_start]
            last = words.words[answer.word_end - 1]
            label = normalized(field.answer.text)
            merged = normalized(answer.quote)
            write_box = write_in_native[1]
            if (
                merged.startswith(label)
                and len(merged) > len(label)
                and not merged[len(label)].isalnum()
                and first.left * 1000 / words.image_width < field.answer.box.right
                and (last.left + last.width) * 1000 / words.image_width > write_box.left
                and all(
                    d.part != "answer" or d.code == "historical_text_or_region_disagrees"
                    for d in warnings
                )
            ):
                warnings = tuple(
                    d.model_copy(
                        update={
                            "code": "historical_label_write_in_separated",
                            "selection_reason": "Printed label and adjacent native write-in are "
                            "separate fields. The merged OCR token crosses their boundary; "
                            "the label prefix and native write-in geometry were rechecked. "
                            "Merged-token confidence does not measure the label separately.",
                        }
                    )
                    if d.part == "answer"
                    else d
                    for d in warnings
                )
    _grounded_geometry(
        raw,
        field,
        transcript.historical_fields,
        question,
        role,
        answer,
        native[1] if native else None,
        allow_interleaved=any(d.code == "historical_region_words_interleaved" for d in warnings),
    )
    if field.control is not None:
        try:
            _verify_control(root, inventory, source_id, page, field)
            if isinstance(answer, OcrCitation) and _control_label_agrees(raw, field, answer):
                warnings = tuple(
                    d.model_copy(
                        update={
                            "code": "historical_control_label_layout_reconciled",
                            "selection_reason": "All option words match in order. Only localized "
                            "control/bullet margin artifacts differ; the mark was pixel-checked. "
                            "Original readings retained; no business condition inferred.",
                        }
                    )
                    if d.part == "answer" and d.code == "historical_text_or_region_disagrees"
                    else d
                    for d in warnings
                )
        except ScanVerificationError as error:
            if not allow_disagreements or str(error) not in (
                "control_outline_not_resolved",
                "historical_control_mark_disagrees",
            ):
                raise
            warnings += (
                ExtractionDiscrepancy(
                    part="control",
                    code=str(error),
                    image_reading=field.control.state,
                    ocr_reading="pixel inspection: " + str(error),
                    selection_reason=(
                        "Image-selected historical candidate; local control inspection "
                        "did not agree. Reviewer must inspect the mark. Not a verified selection."
                    ),
                ),
            )
    return HistoricalContextCheck(
        version=context_version,
        prompt_version=prompt_version,
        endpoint=endpoint,
        deployment=deployment,
        field=field,
        transcript=transcript,
        question=question,
        role=role,
        answer=answer,
        discrepancies=warnings,
    )


def _control_label_agrees(raw: bytes, field: HistoricalPageField, answer: OcrCitation) -> bool:
    data = parse_ocr_artifact(raw)
    wanted = [w for w in normalized(field.answer.text).split() if w not in ("•", "·", "●")]
    offset = 0
    for word in data.words[answer.word_start : answer.word_end]:
        token = normalized(word.text)
        if offset < len(wanted) and token == wanted[offset]:
            offset += 1
            continue
        x = word.left * 1000 / data.image_width
        bottom = (word.top + word.height) * 1000 / data.image_height
        if (
            len(token) != 1
            or token.isnumeric()
            or not (bottom < field.answer.box.top or x <= field.answer.box.left + 8)
        ):
            return False
    return offset == len(wanted)


def _verify_control(
    root: Path, inventory: Inventory, source_id: str, page: int, field: HistoricalPageField
) -> None:
    control = field.control
    if control is None:
        return
    box, label = control.box, field.answer.box
    if abs((box.top + box.bottom - label.top - label.bottom) / 2) > max(
        box.bottom - box.top, label.bottom - label.top
    ) + 8 or not (
        -max(8, (box.right - box.left) / 2) <= label.left - box.right <= 100
        or -max(8, (box.right - box.left) / 2) <= box.left - label.right <= 100
    ):
        raise ScanVerificationError("historical_control_label_geometry_disagrees")
    try:
        pixels = inspect_control(_render_image(root, inventory, source_id, page), box)
    except ValueError as error:
        raise ScanVerificationError(str(error)) from None
    if pixels.state == "ambiguous" or pixels.state != control.state:
        raise ScanVerificationError("historical_control_mark_disagrees")


def _contains(box: NormalizedBox, x: float, y: float) -> bool:
    return box.left - 8 <= x <= box.right + 8 and box.top - 8 <= y <= box.bottom + 8


def _geometry(field: HistoricalPageField, fields: tuple[HistoricalPageField, ...]) -> None:
    question, answer = field.question.box, field.answer.box
    same_row = (
        abs((question.top + question.bottom - answer.top - answer.bottom) / 2)
        <= max(question.bottom - question.top, answer.bottom - answer.top) + 12
        and answer.left >= question.left
    )
    below = question.bottom <= answer.top <= question.bottom + (
        350 if field.control is not None else 120
    ) and (
        min(question.right, answer.right) > max(question.left, answer.left)
        or (field.control is not None and question.left <= answer.left <= question.right + 400)
    )
    if not (same_row or below):
        raise ScanVerificationError("historical_answer_not_adjacent_to_question")
    if same_row and any(
        other != field
        and question.right < other.question.box.left < answer.left
        and min(other.question.box.bottom, question.bottom)
        > max(other.question.box.top, question.top)
        for other in fields
    ):
        raise ScanVerificationError("historical_intervening_question")
    if below and any(
        other != field
        and question.bottom < other.question.box.top < answer.top
        and min(other.question.box.right, answer.right) > max(other.question.box.left, answer.left)
        for other in fields
    ):
        raise ScanVerificationError("historical_intervening_question")
    role = field.role
    if role is not None:
        control_subheader = (
            field.control is not None
            and question.bottom <= role.box.top < role.box.bottom <= answer.top
            and role.box.left <= answer.left <= role.box.right + 200
        )
        if not control_subheader and (
            role.box.top >= question.top or question.top - role.box.bottom > 300
        ):
            raise ScanVerificationError("historical_role_region_mismatch")
        for other in fields:
            header = other.role
            if header is None or header == role:
                continue
            same_row = (
                abs((header.box.top + header.box.bottom - role.box.top - role.box.bottom) / 2) <= 12
            )
            if same_row and normalized(header.text) == normalized(role.text):
                continue
            # A section header may govern a whole row, not just its printed text column.
            newer_section = role.box.bottom < header.box.top < question.top and (
                min(header.box.right, role.box.right) > max(header.box.left, role.box.left)
                or min(header.box.right, question.right) > max(header.box.left, question.left)
            )
            competing_column = (
                same_row
                and header.box.left <= question.left + 8
                and (role.box.left > question.left + 8 or header.box.left > role.box.left + 8)
            )
            if newer_section or competing_column:
                raise ScanVerificationError("historical_role_region_mismatch")


def _ocr_citation(
    artifact: bytes,
    path: str,
    part: HistoricalPagePart,
    *,
    question: bool = False,
    min_confidence: int = 90,
) -> OcrCitation:
    data = parse_ocr_artifact(artifact)
    words = data.words
    wanted = normalized(part.text).split()
    numbered = question and re.match(r"^\d{1,3}[.)]\s*[a-z]", normalized(part.text)) is not None

    def comparable(value: str) -> str:
        value = normalized(value)
        return re.sub(r"^(\d{1,3}[.)])\s*(?=[a-z])", r"\1", value) if numbered else value

    lengths = {len(wanted)}
    if numbered:
        lengths.update((len(wanted) - 1, len(wanted) + 1))
    matches: list[tuple[int, int]] = []
    for start in range(len(words)):
        for length in lengths:
            if length <= 0 or start + length > len(words):
                continue
            selected = words[start : start + length]
            if comparable(" ".join(w.text for w in selected)) == comparable(part.text) and all(
                _contains(
                    part.box,
                    (w.left + w.width / 2) * 1000 / data.image_width,
                    (w.top + w.height / 2) * 1000 / data.image_height,
                )
                for w in selected
            ):
                matches.append((start, start + length))
    if len(matches) != 1:
        raise ScanVerificationError("historical_text_or_region_disagrees")
    start, end = matches[0]
    if any(w.confidence < min_confidence for w in words[start:end]):
        raise ScanVerificationError("historical_low_word_confidence")
    return OcrCitation(
        evidence_kind="ocr",
        source_id=data.source.source_id,
        source_sha256=data.source.sha256,
        page=data.page,
        artifact_path=path,
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        render_sha256=data.render_sha256,
        word_start=start,
        word_end=end,
        quote=ocr_text(words[start:end]),
    )


def _write_in_fields(
    root: Path,
    inventory: Inventory,
    source_id: str,
    page_number: int,
    transcript: ScanTranscript,
) -> ScanTranscript:
    fields: list[HistoricalPageField] = []
    for field in transcript.historical_fields:
        write_in = field.write_in
        if (
            field.control is not None
            and write_in is None
            and re.search(r"\b(other|specify|describe)\b", field.answer.text, re.IGNORECASE)
        ):
            label = field.answer.box
            neighbours = [
                other.control.box.left - 8
                for other in transcript.historical_fields
                if other != field
                and other.control is not None
                and other.control.box.left > label.right
                and abs(other.answer.box.top - label.top) <= 25
            ]
            right = min(neighbours, default=min(1000, label.right + 400))
            if right > label.right:
                with (
                    pdfium.PdfDocument(read_source_bytes(root, inventory, source_id)) as doc,
                    closing(doc[page_number - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    width, height = page.get_size()
                    if page.get_rotation() == 0 and text.count_chars() <= 100_000:
                        value = text.get_text_bounded(
                            left=label.right * width / 1000,
                            right=right * width / 1000,
                            top=height * (1 - (label.top - 8) / 1000),
                            bottom=height * (1 - (label.bottom + 8) / 1000),
                            errors="strict",
                        ).strip()
                        if value and len(value) <= 2000 and "\n" not in value and "\r" not in value:
                            part = HistoricalPagePart(
                                text=value,
                                box=NormalizedBox(
                                    left=label.right,
                                    right=right,
                                    top=max(0, label.top - 8),
                                    bottom=min(1000, label.bottom + 8),
                                ),
                            )
                            native = _native_citation(root, inventory, source_id, page_number, part)
                            if native is not None:
                                write_in = part.model_copy(update={"box": native[1]})
                                field = field.model_copy(update={"write_in": write_in})
        fields.append(field)
        if field.control is not None and write_in is not None:
            companion = HistoricalPageField(
                question=field.answer,
                answer=write_in,
                role=field.role,
            )
            if companion not in transcript.historical_fields and companion not in fields:
                fields.append(companion)
    if len(fields) > 60:
        raise ScanVerificationError("historical_field_limit")
    return transcript.model_copy(update={"historical_fields": tuple(fields)})


def _native_citation(
    root: Path,
    inventory: Inventory,
    source_id: str,
    page_number: int,
    part: HistoricalPagePart,
) -> tuple[Citation, NormalizedBox] | None:
    data = read_source_bytes(root, inventory, source_id)
    with (
        pdfium.PdfDocument(data) as document,
        closing(document[page_number - 1]) as page,
        closing(page.get_textpage()) as text,
    ):
        if text.count_chars() > 100_000:
            raise ScanVerificationError("historical_native_character_limit")
        if page.get_rotation() != 0:
            return None
        width, height = page.get_size()
        left, top, right, bottom = part.box.display_points(width, height)
        bounded = text.get_text_bounded(
            left=left - width * 0.008,
            bottom=height - bottom - height * 0.008,
            right=right + width * 0.008,
            top=height - top + height * 0.008,
            errors="strict",
        )
        pattern = (
            r"(?<!\w)" + r"\s+".join(re.escape(token) for token in part.text.split()) + r"(?!\w)"
        )
        if re.search(pattern, bounded, flags=re.IGNORECASE) is None:
            return None
        native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
        matches = tuple(re.finditer(pattern, native, flags=re.IGNORECASE))
        candidates: list[tuple[re.Match[str], NormalizedBox]] = []
        for quote in dict.fromkeys(m.group() for m in matches):
            spans: list[tuple[int, int]] = []
            with closing(
                text.search(
                    quote.replace("\n", "\r\n"),
                    match_case=True,
                    match_whole_word=True,
                )
            ) as search:
                while (span := search.get_next()) is not None:
                    spans.append(span)
            occurrences = [m for m in matches if m.group() == quote]
            if len(occurrences) != len(spans):
                return None
            for match, span in zip(occurrences, spans, strict=True):
                boxes = [text.get_charbox(index) for index in range(span[0], span[0] + span[1])]
                if not all(
                    _contains(
                        part.box, (a + c) * 500 / width, (height - (b + d) / 2) * 1000 / height
                    )
                    for a, b, c, d in boxes
                ):
                    continue
                left, bottom = min(b[0] for b in boxes), min(b[1] for b in boxes)
                right, top = max(b[2] for b in boxes), max(b[3] for b in boxes)
                native_box = NormalizedBox(
                    left=max(0, math.floor(left * 1000 / width)),
                    top=max(0, math.floor((height - top) * 1000 / height)),
                    right=min(1000, math.ceil(right * 1000 / width)),
                    bottom=min(1000, math.ceil((height - bottom) * 1000 / height)),
                )
                candidates.append((match, native_box))
        if len(candidates) != 1:
            return None
        match, native_box = candidates[0]
    citation = Citation(
        source_id=source_id,
        page=page_number,
        start=match.start(),
        end=match.end(),
        quote=match.group(),
    )
    try:
        resolve_quote(root, inventory, citation.text_citation())
    except EvidenceError:
        return None
    return citation, native_box


def _grounded_geometry(
    raw: bytes,
    field: HistoricalPageField,
    fields: tuple[HistoricalPageField, ...],
    question: OcrCitation,
    role: OcrCitation | None,
    answer: Citation | OcrCitation,
    native_box: NormalizedBox | None,
    *,
    allow_interleaved: bool = False,
) -> None:
    data = parse_ocr_artifact(raw)

    def region(citation: OcrCitation, proposed: NormalizedBox) -> NormalizedBox:
        words = data.words[citation.word_start : citation.word_end]
        if allow_interleaved:
            words = tuple(
                w
                for w in words
                if _contains(
                    proposed,
                    (w.left + w.width / 2) * 1000 / data.image_width,
                    (w.top + w.height / 2) * 1000 / data.image_height,
                )
            )
            if not words:
                raise ScanVerificationError("historical_region_has_no_ocr_words")
        return NormalizedBox(
            left=math.floor(min(w.left for w in words) * 1000 / data.image_width),
            top=math.floor(min(w.top for w in words) * 1000 / data.image_height),
            right=math.ceil(max(w.left + w.width for w in words) * 1000 / data.image_width),
            bottom=math.ceil(max(w.top + w.height for w in words) * 1000 / data.image_height),
        )

    answer_box = region(answer, field.answer.box) if isinstance(answer, OcrCitation) else native_box
    if answer_box is None:
        raise ScanVerificationError("historical_answer_geometry_unavailable")
    grounded = HistoricalPageField(
        question=HistoricalPagePart(
            text=field.question.text, box=region(question, field.question.box)
        ),
        role=HistoricalPagePart(text=field.role.text, box=region(role, field.role.box))
        if field.role is not None and role is not None
        else None,
        answer=HistoricalPagePart(text=field.answer.text, box=answer_box),
        control=field.control,
    )
    _geometry(
        grounded,
        tuple(
            grounded if other == field else other
            for other in fields
            if not (
                field.control is not None
                and field.write_in is not None
                and other.control is None
                and other.question == field.answer
                and other.answer == field.write_in
            )
        ),
    )


class HistoricalContextCheck(Contract):
    """Trusted runtime receipt, not accepted from the answering model."""

    version: str = CONTEXT_VERSION
    prompt_version: str
    endpoint: str
    deployment: str
    field: HistoricalPageField
    transcript: ScanTranscript
    question: OcrCitation
    role: OcrCitation | None
    answer: Citation | OcrCitation
    min_word_confidence: Annotated[int, Field(ge=90, le=100)] = 90
    discrepancies: tuple[ExtractionDiscrepancy, ...] = ()

    @property
    def answer_disputed(self) -> bool:
        return any(
            d.part == "answer"
            and d.code
            not in (
                "historical_label_write_in_separated",
                "historical_control_label_layout_reconciled",
                "historical_native_numeric_layout_reconciled",
            )
            and normalized(d.image_reading) != normalized(d.ocr_reading)
            for d in self.discrepancies
        )

    @property
    def context_role(self) -> OcrCitation | None:
        return self.role if self.field.section_role is not None else None

    @property
    def context_citation(self) -> HistoricalContextCitation:
        role = self.context_role
        quote = (" ".join(role.quote.split()) + "\n" if role else "") + " ".join(
            (self.field.question.text if self.discrepancies else self.question.quote).split()
        )
        payload = self.model_dump_json().encode()
        if not self.discrepancies:
            legacy_current = self.model_dump(mode="json", exclude={"discrepancies"})
            payload = json.dumps(legacy_current, separators=(",", ":"), ensure_ascii=False).encode()
        if self.version in (
            "historical-page-context-v1",
            "historical-page-context-v2",
            "historical-page-context-v3",
            "historical-page-context-v4",
        ):
            legacy = self.model_dump(mode="json")
            legacy.pop("discrepancies")
            legacy["field"].pop("control")
            for field in legacy["transcript"]["historical_fields"]:
                field.pop("control")
            payload = json.dumps(legacy, separators=(",", ":"), ensure_ascii=False).encode()
        if self.version not in ("historical-page-context-v6", CONTEXT_VERSION):
            legacy = json.loads(payload)
            legacy["field"].pop("write_in", None)
            for field in legacy["transcript"]["historical_fields"]:
                field.pop("write_in", None)
            payload = json.dumps(legacy, separators=(",", ":"), ensure_ascii=False).encode()
        return HistoricalContextCitation(
            evidence_kind="historical_context",
            source_id=self.question.source_id,
            page=self.question.page,
            check_sha256=hashlib.sha256(payload).hexdigest(),
            quote=quote,
        )

    @property
    def ocr_citations(self) -> tuple[OcrCitation, ...]:
        return (
            (self.question,)
            + ((self.role,) if self.role else ())
            + ((self.answer,) if isinstance(self.answer, OcrCitation) else ())
        )

    def supports(self, proposal: AnswerProposal, requirement: Requirement | None = None) -> bool:
        from bd_packet_builder.historical_time import prior_tenure_proposal

        proposal = prior_tenure_proposal(proposal)
        basis = proposal.historical_basis
        value = proposal.value
        answer_text = (
            self.answer.quote
            if any(
                d.code == "historical_native_numeric_layout_reconciled" for d in self.discrepancies
            )
            or not self.discrepancies
            else self.field.answer.text
        )
        if self.answer_disputed:
            if (
                basis is None
                or basis.reading_resolution is None
                or not isinstance(value, (IdentifierValue, TextValue))
                or value.value not in (self.field.answer.text, self.answer.quote)
            ):
                return False
            answer_text = value.value
        literal_match = (
            answer_text.strip().casefold() == ("yes" if value.value else "no")
            if isinstance(value, BooleanValue)
            else isinstance(value, (IdentifierValue, TextValue, NarrativeValue))
            and re.search(
                r"(?<!\w)" + re.escape(" ".join(value.value.split())) + r"(?!\w)",
                " ".join(answer_text.split()),
                flags=re.IGNORECASE if isinstance(value, (TextValue, NarrativeValue)) else 0,
            )
            is not None
        )
        return (
            self.version
            in (
                "historical-page-context-v1",
                "historical-page-context-v2",
                "historical-page-context-v3",
                "historical-page-context-v4",
                "historical-page-context-v5",
                "historical-page-context-v6",
                CONTEXT_VERSION,
            )
            and self.prompt_version in SUPPORTED_SCAN_VERSIONS
            and (
                self.field.control is None
                or (
                    self.field.control.state == "selected"
                    and self.version
                    in ("historical-page-context-v5", "historical-page-context-v6", CONTEXT_VERSION)
                    and self.prompt_version
                    in (
                        "scan-cross-check-v3",
                        "scan-cross-check-v4",
                        "scan-cross-check-v5",
                        SCAN_VERSION,
                    )
                )
            )
            and basis is not None
            and (
                basis.prior_question == self.context_citation
                or (
                    self.field.control is not None
                    and isinstance(basis.prior_question, HistoricalContextCitation)
                    and basis.prior_question.source_id == self.question.source_id
                    and basis.prior_question.page == self.question.page
                    and basis.prior_question.quote == self.context_citation.quote
                )
            )
            and self.answer in proposal.citations
            and (
                basis.category != "headcount"
                or isinstance(value, TextValue)
                and normalized(value.value) == normalized(answer_text)
            )
            and (
                literal_match
                or explicit_choice_answer(requirement, value, answer_text)
                or (
                    self.field.control is not None
                    and self.field.control.state == "selected"
                    and requirement is not None
                    and requirement.choices is not None
                    and value is not None
                    and value.kind in ("single_select", "multi_select")
                    and any(
                        option.option_id in value.selected
                        and option_label_matches(option.label, answer_text)
                        for option in requirement.choices.options
                    )
                )
            )
            and (
                basis.role is None
                or (self.role is not None and normalized(basis.role) == normalized(self.role.quote))
            )
        )

    def recheck(
        self,
        root: Path,
        inventory: Inventory,
        artifact: bytes,
        *,
        allow_disagreements: bool = False,
    ) -> bool:
        if self.field not in self.transcript.historical_fields:
            return False
        try:
            if self.discrepancies or self.field.write_in is not None:
                if self.discrepancies and not allow_disagreements:
                    return False
                return self == _make_check(
                    root,
                    inventory,
                    artifact,
                    self.question.artifact_path,
                    self.question.source_id,
                    self.question.page,
                    self.field,
                    self.transcript,
                    self.endpoint,
                    self.deployment,
                    allow_disagreements,
                    self.prompt_version,
                    self.version,
                )
            if self.field.control is not None:
                _verify_control(
                    root, inventory, self.question.source_id, self.question.page, self.field
                )
            _geometry(self.field, self.transcript.historical_fields)
            if (
                _ocr_citation(
                    artifact,
                    self.question.artifact_path,
                    self.field.question,
                    question=True,
                )
                != self.question
            ):
                return False
            if self.field.role is not None:
                if (
                    _ocr_citation(artifact, self.question.artifact_path, self.field.role)
                    != self.role
                ):
                    return False
            elif self.role is not None:
                return False
            if isinstance(self.answer, OcrCitation):
                if (
                    _ocr_citation(artifact, self.question.artifact_path, self.field.answer)
                    != self.answer
                ):
                    return False
                native_box = None
            else:
                native = _native_citation(
                    root,
                    inventory,
                    self.question.source_id,
                    self.question.page,
                    self.field.answer,
                )
                if native is None or native[0] != self.answer:
                    return False
                native_box = native[1]
            _grounded_geometry(
                artifact,
                self.field,
                self.transcript.historical_fields,
                self.question,
                self.role,
                self.answer,
                native_box,
            )
            return True
        except ScanVerificationError:
            return False


class HistoricalWriteInEvidence(Contract):
    text: Nonblank
    answer_citation: Citation | OcrCitation
    context_citation: HistoricalContextCitation


class HistoricalAssociation(Contract):
    context_citation: HistoricalContextCitation
    answer_citation: Citation | OcrCitation
    question: str
    role: str | None
    discrepancies: tuple[ExtractionDiscrepancy, ...] = ()
    candidate_answer: str | None = None
    write_in: HistoricalWriteInEvidence | None = None
    question_reconciliation: QuestionReconciliation | None = None


class HistoricalPageIssue(Contract):
    field_index: int
    code: str
    part: Literal["relationship", "question", "role", "answer", "control"]


class HistoricalPageResult(Contract):
    associations: tuple[HistoricalAssociation, ...]
    issues: tuple[HistoricalPageIssue, ...]
    controls: tuple[HistoricalPageField, ...] = ()
    content_trust: str = "untrusted_document_text"
    scope: str = "machine_cross_checked_historical_relationship_not_current_confirmation"


class HistoricalPageReading(Contract):
    source_id: str
    page: int
    artifact_path: str
    artifact_sha256: str
    transcript: ScanTranscript
    result: HistoricalPageResult


class HistoricalContextEvidence:
    def __init__(
        self,
        scans: ScanEvidence,
        *,
        allow_disagreements: bool = False,
        question_requirements: tuple[Requirement, ...] = (),
    ) -> None:
        self.scans = scans
        self.allow_disagreements = allow_disagreements
        self.question_requirements = question_requirements
        self.checks: list[HistoricalContextCheck] = []
        self.readings: list[HistoricalPageReading] = []
        self._cache: dict[tuple[str, int, str], HistoricalPageResult] = {}

    def read(self, source_id: str, page: int, artifact_path: str) -> HistoricalPageResult:
        root, inventory = self.scans.root, self.scans.inventory
        source = next((s for s in inventory.sources if s.source_id == source_id), None)
        if source is None or source.family != "historical_reference":
            raise ScanVerificationError("historical_reference_required")
        raw = read_local_input(root, Path(artifact_path), Path("outputs"), 2 * 1024 * 1024)
        data = parse_ocr_artifact(raw)
        if (
            data.source.source_id != source_id
            or data.source.sha256 != source.sha256
            or data.source.path != source.path
            or data.page != page
        ):
            raise ScanVerificationError("historical_source_version_mismatch")
        read_source_bytes(root, inventory, source_id)
        key = source_id, page, hashlib.sha256(raw).hexdigest()
        if key in self._cache:
            return self._cache[key]
        transcript = self.scans.transcribe_page(source_id, page, data.render_sha256)
        transcript = _write_in_fields(root, inventory, source_id, page, transcript)
        associations: list[HistoricalAssociation] = []
        issues: list[HistoricalPageIssue] = []
        for index, field in enumerate(transcript.historical_fields):
            part: Literal["relationship", "question", "role", "answer", "control"] = "relationship"
            try:
                if self.allow_disagreements:
                    check = _make_check(
                        root,
                        inventory,
                        raw,
                        artifact_path,
                        source_id,
                        page,
                        field,
                        transcript,
                        self.scans.endpoint,
                        self.scans.deployment,
                        True,
                    )
                    if field.control is not None and field.control.state != "selected":
                        continue
                    self.checks.append(check)
                    associations.append(
                        HistoricalAssociation(
                            context_citation=check.context_citation,
                            answer_citation=check.answer,
                            question=field.question.text,
                            role=check.context_role.quote if check.context_role else None,
                            discrepancies=check.discrepancies,
                            question_reconciliation=question_reconciliation(
                                check, self.question_requirements
                            ),
                            candidate_answer=(
                                None
                                if check.answer_disputed
                                else check.answer.quote
                                if any(
                                    d.code == "historical_native_numeric_layout_reconciled"
                                    for d in check.discrepancies
                                )
                                else field.answer.text
                            ),
                        )
                    )
                    continue
                _geometry(field, transcript.historical_fields)
                part = "question"
                question = _ocr_citation(raw, artifact_path, field.question, question=True)
                part = "role"
                role = _ocr_citation(raw, artifact_path, field.role) if field.role else None
                part = "answer"
                native = _native_citation(root, inventory, source_id, page, field.answer)
                answer: Citation | OcrCitation = (
                    native[0] if native else _ocr_citation(raw, artifact_path, field.answer)
                )
                part = "relationship"
                _grounded_geometry(
                    raw,
                    field,
                    transcript.historical_fields,
                    question,
                    role,
                    answer,
                    native[1] if native else None,
                )
                if field.control is not None:
                    part = "control"
                    _verify_control(root, inventory, source_id, page, field)
                    if field.control.state != "selected":
                        continue
                check = HistoricalContextCheck(
                    prompt_version=SCAN_VERSION,
                    endpoint=self.scans.endpoint,
                    deployment=self.scans.deployment,
                    field=field,
                    transcript=transcript,
                    question=question,
                    role=role,
                    answer=answer,
                )
                self.checks.append(check)
                associations.append(
                    HistoricalAssociation(
                        context_citation=check.context_citation,
                        answer_citation=answer,
                        question=question.quote,
                        role=check.context_role.quote if check.context_role else None,
                    )
                )
            except ScanVerificationError as error:
                issues.append(HistoricalPageIssue(field_index=index, code=str(error), part=part))
        if not transcript.historical_fields:
            issues.append(
                HistoricalPageIssue(
                    field_index=-1, code="historical_no_readable_associations", part="relationship"
                )
            )
        for index, association in enumerate(associations):
            control = next(
                c for c in self.checks if c.context_citation == association.context_citation
            )
            if control.field.control is None or control.field.write_in is None:
                continue
            companion = next(
                (
                    c
                    for c in self.checks
                    if c.question.source_id == control.question.source_id
                    and c.question.page == control.question.page
                    and c.field.control is None
                    and c.field.question == control.field.answer
                    and c.field.answer == control.field.write_in
                    and not any(d.part == "answer" for d in c.discrepancies)
                ),
                None,
            )
            if companion is not None:
                associations[index] = association.model_copy(
                    update={
                        "write_in": HistoricalWriteInEvidence(
                            text=companion.field.answer.text,
                            answer_citation=companion.answer,
                            context_citation=companion.context_citation,
                        ),
                    }
                )
        result = HistoricalPageResult(
            associations=tuple(associations),
            issues=tuple(issues),
            controls=tuple(f for f in transcript.historical_fields if f.control is not None),
            scope=(
                "localized_historical_candidates_with_extraction_discrepancies_not_current_confirmation"
                if any(a.discrepancies for a in associations)
                else "machine_cross_checked_historical_relationship_not_current_confirmation"
            ),
        )
        self._cache[key] = result
        self.readings.append(
            HistoricalPageReading(
                source_id=source_id,
                page=page,
                artifact_path=artifact_path,
                artifact_sha256=key[2],
                transcript=transcript,
                result=result,
            )
        )
        return result
