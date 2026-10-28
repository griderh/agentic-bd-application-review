"""Code-only answer validation gate; replaces human pre-write approval for application runs.

The gate turns untrusted model proposals into the writer's decision record using only
deterministic checks. A passed gate means the cited quotes resolve in version-bound sources, the
answer fits its declared type, period and placement, and the requirement is not a signing item.
It does not prove narrative support or business correctness; humans review the draft afterwards.
Model confidence is never an input.
"""

import hashlib
import re
from pathlib import Path

from bd_packet_builder.contracts import (
    Citation,
    IdentifierValue,
    OcrCitation,
    TextValue,
    check_proposal,
)
from bd_packet_builder.draft import (
    DraftDecision,
    DraftRequest,
    DraftReview,
    publish_draft,
    selected_inventory,
)
from bd_packet_builder.local_inputs import read_local_input

GATE_VERSION = "answer-gate-v1"
GATE_REVIEWER = "application_validation_gate_v1"
_MAX_REQUEST_BYTES = 2 * 1024 * 1024


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def validate_answers(root: Path, request: DraftRequest, request_sha256: str) -> DraftReview:
    """Return one decision per proposal; per-answer failures become withheld decisions.

    Technical failures such as changed or unreadable sources propagate instead of being
    reported as review exceptions.
    """
    inventory = selected_inventory(root, request)
    requirements = {r.requirement_id: r for r in request.requirements.requirements}
    mappings = {m.requirement.requirement_id for m in request.layout.responses}
    attached = set(request.attachments)
    decisions: list[DraftDecision] = []
    supporting: list[str] = []
    for proposal in request.proposals.proposals:
        requirement = requirements[proposal.requirement_id]
        check = check_proposal(root, inventory, requirement, proposal)
        issues: list[str] = []
        if requirement.kind in ("signature", "signature_date"):
            issues.append("human_signing_required")
        elif proposal.outcome != "proposed":
            issues.append(proposal.outcome)
        else:
            if any(isinstance(c, OcrCitation) for c in proposal.citations):
                issues.append("ocr_evidence_requires_machine_verification")
            if check.status == "rejected":
                issues.extend(check.issues)
            if proposal.requirement_id not in mappings:
                issues.append("placement_not_available")
            period = requirement.requested_period
            if period is not None and proposal.claimed_period != period:
                issues.append("requested_period_not_confirmed")
            if any(c.source_id not in attached for c in proposal.citations):
                issues.append("supporting_evidence_not_attached")
            quotes = [c.quote for c in proposal.citations if isinstance(c, Citation)]
            value = proposal.value
            if isinstance(value, IdentifierValue) and not any(
                re.search(r"(?<!\w)" + re.escape(value.value) + r"(?!\w)", q) for q in quotes
            ):
                issues.append("identifier_not_in_cited_evidence")
            if isinstance(value, TextValue) and not any(
                _normalized(value.value) in _normalized(q) for q in quotes
            ):
                issues.append("text_value_not_in_cited_evidence")
        unique = tuple(dict.fromkeys(issues))
        verified = not unique
        if verified:
            supporting.extend(c.source_id for c in proposal.citations)
        decisions.append(
            DraftDecision(
                requirement_id=proposal.requirement_id,
                decision="draft_verified" if verified else "withhold",
                evidence_support_confirmed=verified,
                source_approved=verified,
                placement_confirmed=verified,
                reason=(
                    f"{GATE_VERSION}: code checks passed; no human approval."
                    if verified
                    else f"{GATE_VERSION}: " + ", ".join(unique)
                ),
            )
        )
    return DraftReview(
        request_sha256=request_sha256,
        reviewer=GATE_REVIEWER,
        decisions=tuple(decisions),
        attachment_source_ids=tuple(
            identity for identity in request.attachments if identity in set(supporting)
        ),
    )


def run_application_draft(root: Path, request_path: Path) -> Path:
    """Validate answers in code, then publish one incomplete draft for later human review."""
    root = root.resolve(strict=True)
    raw = read_local_input(root, request_path, Path("outputs"), _MAX_REQUEST_BYTES)
    request = DraftRequest.model_validate_json(raw)
    review = validate_answers(root, request, hashlib.sha256(raw).hexdigest())
    return publish_draft(
        root, request_path, raw, request, review, review.model_dump_json().encode(), None
    )
