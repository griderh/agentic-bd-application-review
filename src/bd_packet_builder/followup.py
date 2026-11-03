"""Bounded verification requests; observations and model assessments are not approvals."""

import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from bd_packet_builder.contracts import Contract, Identifier, Nonblank, Sha256


class MinimumAmountCheck(Contract):
    criterion_quote: Nonblank
    field_label: Nonblank
    line_label: Nonblank


class VerificationRequest(Contract):
    requirement_id: Identifier
    source_id: Sha256
    page: Annotated[int, Field(ge=1)]
    quote: Annotated[str, Field(min_length=1, max_length=2000)]
    expected_subject: Nonblank
    method: Literal["native", "scan"]
    minimum_amount: MinimumAmountCheck | None = None


class ConditionAssessment(Contract):
    requirement_id: Identifier
    criterion_quote: Nonblank
    status: Literal["supported", "contradicted", "not_applicable", "unresolved"]
    reason: Literal[
        "verified_evidence",
        "not_searched",
        "verification_failed",
        "source_lacks_fact",
        "conflicting_evidence",
        "not_applicable_with_evidence",
    ]
    explanation: Nonblank


class MinimumAmountError(ValueError):
    """An explicit threshold or its source-row relationship cannot be established."""


def contains_issuer_quote(instruction: str, quote: str) -> bool:
    """Ignore extraction whitespace only; preserve spelling, punctuation and case."""
    return " ".join(quote.split()) in " ".join(instruction.split())


def minimum_amount_result(
    check: MinimumAmountCheck, quote: str, texts: tuple[str, ...]
) -> dict[str, str | bool]:
    """Resolve one explicit USD minimum and a unique same-row label/amount/line association."""
    if not texts:
        raise MinimumAmountError("minimum_amount_requires_source_text")
    threshold_match = re.search(
        r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(million|billion)?",
        check.criterion_quote,
        re.IGNORECASE,
    )
    if threshold_match is None or len(re.findall(r"\$", check.criterion_quote)) != 1:
        raise MinimumAmountError("minimum_amount_requires_one_explicit_USD_threshold")
    if not re.search(r"\b(minimum|at least|not less than)\b", check.criterion_quote, re.I):
        raise MinimumAmountError("minimum_amount_requires_explicit_minimum_wording")
    amount_text = quote.strip().lstrip("$").strip()
    if not re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?", amount_text):
        raise MinimumAmountError("minimum_amount_requires_exact_nonnegative_amount_quote")
    amount = Decimal(amount_text.replace(",", ""))
    threshold = Decimal(threshold_match[1].replace(",", ""))
    scale = (threshold_match[2] or "").lower()
    threshold *= {"": Decimal(1), "million": Decimal(1000000), "billion": Decimal(1000000000)}[
        scale
    ]
    label = " ".join(check.field_label.casefold().split())
    line_pattern = r"(?<!\w)" + re.escape(check.line_label) + r"(?!\w)"
    amount_pattern = r"(?<![\w,.])" + re.escape(amount_text) + r"(?![\w,.])"
    unit_confirmed = False
    for text in texts:
        matches = [
            row
            for row in text.splitlines()
            if label in " ".join(row.casefold().split())
            and re.search(line_pattern, row)
            and re.search(amount_pattern, row)
        ]
        if len(matches) != 1:
            raise MinimumAmountError("minimum_amount_row_missing_or_ambiguous")
        unit_confirmed |= "$" in matches[0] or bool(re.search(r"\bUSD\b", matches[0]))
        if re.search(r"\b(EUR|GBP|CAD|AUD)\b|[\u20ac\u00a3]", matches[0]) or re.search(
            r"\bin\s+(thousands|millions|billions)\b", text, re.I
        ):
            raise MinimumAmountError("minimum_amount_source_unit_unresolved")
        if re.search(r"\(\s*\$?\s*" + re.escape(amount_text) + r"\s*\)", matches[0]) or re.search(
            r"[-\u2212]\s*\$?\s*" + re.escape(amount_text), matches[0]
        ):
            raise MinimumAmountError("minimum_amount_negative_value")
    if not unit_confirmed:
        raise MinimumAmountError("minimum_amount_source_unit_unresolved")
    return {
        "unit": "USD",
        "value": str(amount),
        "minimum": str(threshold),
        "meets_minimum": amount >= threshold,
        "field_label": check.field_label,
        "line_label": check.line_label,
        "criterion_quote": check.criterion_quote,
        "scope": "one_condition_only_not_eligibility_or_packet_approval",
    }
