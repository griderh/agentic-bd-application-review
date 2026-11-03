"""Bounded historical tenure arithmetic, never financial or reporting-period roll-forward."""

import calendar
import re
from datetime import date, datetime

from bd_packet_builder.contracts import AnswerProposal, HistoricalBasis, TextValue

_YEARS = re.compile(
    r"(?P<prefix>(?:(?:approximately|approx\.?|about)\s+|~\s*)?)"
    r"(?P<years>\d{1,3})(?P<suffix>\s+years?)?",
    re.IGNORECASE,
)
_DATES = re.compile(
    r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4})(?!\d)",
    re.IGNORECASE,
)


def anniversary_years(start: date, end: date) -> int:
    if start > end:
        raise ValueError("Historical signature date is in the future")
    day = min(start.day, calendar.monthrange(end.year, start.month)[1])
    return end.year - start.year - (end < date(end.year, start.month, day))


def increment_years(prior: str, increment: int) -> str:
    match = _YEARS.fullmatch(prior.strip())
    if match is None or increment < 0:
        raise ValueError("Historical tenure requires one explicit nonnegative integer in years")
    return f"{match['prefix']}{int(match['years']) + increment}{match['suffix'] or ''}"


def signed_date(text: str) -> date:
    matches = _DATES.findall(text)
    if len(matches) != 1:
        raise ValueError("Signature date must contain one unambiguous date with a four-digit year")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(matches[0].replace(",", ""), pattern).date()
        except ValueError:
            continue
    raise ValueError("Signature date is not a valid explicit calendar date")


def prior_tenure_proposal(proposal: AnswerProposal) -> AnswerProposal:
    basis = proposal.historical_basis
    if basis is None or basis.tenure is None:
        return proposal
    return proposal.model_copy(
        update={"value": TextValue(kind="text", value=basis.tenure.prior_value)}
    )


def signature_proposal(proposal: AnswerProposal) -> AnswerProposal:
    basis = proposal.historical_basis
    assert basis is not None and basis.tenure is not None
    temporal = basis.tenure
    return AnswerProposal(
        requirement_id=proposal.requirement_id,
        outcome="proposed",
        value=TextValue(kind="text", value=temporal.date_citation.quote),
        citations=(temporal.date_citation,),
        confidence=1.0,
        historical_basis=HistoricalBasis(
            category="firm_description",
            context="firm_wide",
            prior_question=temporal.date_context,
            current_checks=(),
            reviewer_confirmation="Historical signing metadata only; never a new signing act.",
        ),
    )


def adjusted_tenure(proposal: AnswerProposal, as_of: date) -> AnswerProposal:
    basis = proposal.historical_basis
    if basis is None or basis.tenure is None or proposal.outcome != "proposed":
        return proposal
    if basis.category != "tenure" or not isinstance(proposal.value, TextValue):
        raise ValueError("Historical adjustment is allowed only for textual tenure candidates")
    temporal = basis.tenure
    value = increment_years(temporal.prior_value, anniversary_years(temporal.signed_on, as_of))
    return proposal.model_copy(update={"value": TextValue(kind="text", value=value)})
