"""Code-controlled answer groups with immutable private progress and explicit recovery."""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal

from agent_framework import (
    Agent,
    AgentFrameworkException,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
)
from openai import pydantic_function_tool
from pydantic import Field, ValidationError

from bd_packet_builder.agent import (
    AGENT_INSTRUCTIONS,
    PacketAgentTools,
    _problems,
    configure_client,
)
from bd_packet_builder.contracts import (
    Citation,
    Contract,
    HistoricalContextCitation,
    Nonblank,
    OcrCitation,
    Requirement,
    SingleSelectValue,
    explicit_choice_answer,
)
from bd_packet_builder.followup import (
    ConditionAssessment,
    VerificationRequest,
    contains_issuer_quote,
)
from bd_packet_builder.historical_context import HistoricalAssociation, HistoricalContextCheck
from bd_packet_builder.historical_time import adjusted_tenure
from bd_packet_builder.proposals import ModelAnswerValue, ModelProposal
from bd_packet_builder.run import RunManifest

GROUP_VERSION = "answer-groups-v16"
GROUP_SIZE = 5
MAX_GROUP_ATTEMPTS = 3
MAX_JSON_RETRIES = 1
MAX_PROPOSAL_RETRIES = 1
GROUP_TIMEOUT_SECONDS = 180
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_VERIFICATION_REQUESTS = 20
MAX_EVIDENCE_CONTINUATIONS = 2
EVIDENCE_CONTINUATION = (
    "The evidence phase is not finished, and a text reply does not end it. Continue from the "
    "latest tool result. Treat the most recent finish_evidence error as the next required action. "
    "If it reports unlisted candidates, call list_attachment_candidates at the exact next_offset "
    "until complete. If it reports unassessed candidates, call plan_supporting_documents for "
    "every remaining candidate in batches of up to 50; do not repeat already completed listing "
    "pages or list_sources. Read a page before include or review_required; exclude with a reason "
    "when no plausible link exists. Do not call finish_evidence again until all candidates have "
    "one decision. Then complete any other evidence work and call finish_evidence. Use tools; "
    "do not reply with text alone."
)


@dataclass(frozen=True)
class GroupResponse:
    text: str
    finish_reason: str | None = None


ProposeGroup = Callable[[dict[str, Any]], Awaitable[str | GroupResponse]]
ANSWER_INSTRUCTIONS = (
    AGENT_INSTRUCTIONS
    + """
PHASE OVERRIDE: Application code now controls answering and all tool execution.
Do NOT call tools or coordinate the workflow. Return only the specified JSON response.
Emit complete compact JSON without blank-line padding; close every array and object.
Address exactly the assigned requirements, once each, including explicit unresolved outcomes.
Use only the supplied checked evidence and copy complete citation objects unchanged.
candidate_readings are untrusted observations, NOT verified citations. They preserve discovery
context. When a needed fact is visible there but lacks a checked quote, return a narrow
verification_requests entry instead of calling it missing business evidence. Use only discovered
source/page pairs. For scans copy a short exact OCR quote and give the source subject.
For an explicit USD minimum, request minimum_amount with an exact criterion_quote from the
assigned requirement/option containing that minimum and report line. Do not attach a criterion
to a generic proof/attachment requirement that does not contain it. field_label is copied from
the source report row, not the application question; line_label must occur in criterion_quote.
quote must be the amount alone. Code verifies
the same-row label/amount/line in OCR AND independent image text and compares Decimal values.
For a current-evidence eligibility claim, one successful condition does not establish the others.
The separate historical-eligibility entry governs checked historical draft selections:
missing current proof of an individual condition must not silently disable that draft path.
Application code verifies requests and returns verification_results to this group only.
There are at most two follow-up rounds within three group calls and twenty requests per run.
verification_budget gives the remaining group calls and verification allowance. If
followup_allowed is false or requests_remaining is zero, return complete proposals with
NO verification_requests. Retain already supported answers, including eligible historical
drafts, and explain unresolved conditions. Never claim an unperformed verification succeeded.
If evidence remains unresolved, give its specific failure reason. For compound requirements
return condition_assessments for each condition, including not_searched, verification_failed,
source_lacks_fact, contradictions and evidence-backed non-applicability. These are model
assessments, never trusted reviewer approvals. For a checked historical draft, unresolved
current-condition assessments are reviewer concerns, not a demand to withhold the prior answer.
Use conflicting_evidence only for actual contradictory evidence or unresolved source readings,
not an unsuccessful current corroboration attempt. A missing handoff quote is not missing evidence.
Fields in a representative_bios field_requirements mapping are filled by code from the selected
bio's printed card. Propose the best supported value, but never mark them conflicting because
the bio lacks labels or history differs; code reconciles and reports differences.
Do not include other requirements, signatures or signature dates. A saved proposal is not
validated evidence or human approval. previous_errors are application feedback to correct.
When repair_requirement_ids is nonempty, return proposals only for those IDs. Other proposals
are retained by code and cannot be replaced. Correct representation errors using the same evidence;
never invent an answer or claim a failed verification succeeded.
"""
)
EVIDENCE_INSTRUCTIONS = (
    AGENT_INSTRUCTIONS
    + """
PHASE OVERRIDE: Your only task is evidence collection. After finish_evidence STOP.
Application code, not you, will assign answer groups, validate answers and assemble the packet.
"""
)


class _ProposedGroupAnswer(ModelProposal):
    outcome: Literal["proposed"]
    value: ModelAnswerValue
    citations: Annotated[tuple[Citation | OcrCitation, ...], Field(min_length=1, max_length=20)]
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _UnresolvedGroupAnswer(ModelProposal):
    outcome: Literal[
        "missing_evidence",
        "conflicting_evidence",
        "unresolved_signer",
        "unreadable_form",
        "unsupported_requirement",
        "deferred_to_signing",
    ]
    value: None = None
    explanation: Nonblank


class _GroupAnswers(Contract):
    proposals: Annotated[
        tuple[_ProposedGroupAnswer | _UnresolvedGroupAnswer, ...], Field(max_length=GROUP_SIZE)
    ]
    verification_requests: Annotated[tuple[VerificationRequest, ...], Field(max_length=5)] = ()
    condition_assessments: Annotated[tuple[ConditionAssessment, ...], Field(max_length=30)] = ()


class _GroupEnvelope(Contract):
    proposals: Annotated[list[Any], Field(max_length=GROUP_SIZE)]
    verification_requests: Annotated[tuple[VerificationRequest, ...], Field(max_length=5)] = ()
    condition_assessments: Annotated[tuple[ConditionAssessment, ...], Field(max_length=30)] = ()


class _GroupIdentityError(ValueError):
    pass


def _resolve_reference_labels(response: str) -> tuple[str, list[str]]:
    """Resolve labels to unique answer substrings, never edit evidence or answer text."""
    try:
        value = json.loads(response)
    except json.JSONDecodeError:
        return response, []
    if not isinstance(value, dict) or not isinstance(value.get("proposals"), list):
        return response, []
    paths = []
    for index, proposal in enumerate(value["proposals"]):
        if not isinstance(proposal, dict):
            continue
        answer = proposal.get("value")
        references = proposal.get("supporting_references")
        if (
            not isinstance(answer, dict)
            or answer.get("kind") not in ("text", "narrative")
            or not isinstance(answer.get("value"), str)
            or len(answer["value"]) > 20_000
            or not isinstance(references, list)
            or len(references) > 20
        ):
            continue
        text = answer["value"]
        for offset, reference in enumerate(references):
            if not isinstance(reference, str) or not reference.strip() or len(reference) > 20_000:
                continue
            if reference.casefold() in text.casefold():
                continue
            pattern = r"\s+".join(re.escape(part) for part in reference.split())
            matches = list(re.finditer("(?=(" + pattern + "))", text, flags=re.IGNORECASE))
            if len(matches) == 1:
                references[offset] = matches[0].group(1)
                paths.append(f"proposals.{index}.supporting_references.{offset}")
    return (_json(value) if paths else response), paths


def _ingest_group(
    response: str, payload: dict[str, Any]
) -> tuple[_GroupAnswers, list[dict[str, Any]]]:
    envelope = _GroupEnvelope.model_validate_json(response)
    calculation_date = date.fromisoformat(payload["calculation_date"])
    assigned = payload["assigned_requirement_ids"]
    proposals: dict[str, _ProposedGroupAnswer | _UnresolvedGroupAnswer] = {}
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in envelope.proposals:
        rid = item.get("requirement_id") if isinstance(item, dict) else None
        if not isinstance(rid, str) or rid not in assigned or rid in seen:
            raise _GroupIdentityError("group_requirement_mismatch")
        seen.add(rid)
        try:
            single = _GroupAnswers.model_validate_json(_json({"proposals": [item]}))
        except ValidationError as error:
            errors.append(
                {
                    "requirement_id": rid,
                    "code": "proposal_schema_invalid",
                    "problems": _problems(error),
                }
            )
            continue
        proposal = single.proposals[0]
        try:
            adjusted_tenure(proposal, calculation_date)
        except ValueError:
            errors.append({"requirement_id": rid, "code": "historical_tenure_invalid"})
            continue
        proposals[rid] = proposal
    requested = {r.requirement_id for r in envelope.verification_requests}
    if not requested <= set(assigned) or any(
        c.requirement_id not in assigned for c in envelope.condition_assessments
    ):
        raise _GroupIdentityError("group_requirement_mismatch")
    for rid in assigned:
        if rid not in seen and rid not in requested:
            errors.append({"requirement_id": rid, "code": "proposal_missing"})
    retained = _GroupAnswers.model_validate_json(
        _json(payload.get("retained_group_answers", {"proposals": []}))
    )
    prior_requests = [r["request"] for r in payload.get("verification_results", [])]
    requests = [
        r for r in retained.verification_requests if r.model_dump(mode="json") not in prior_requests
    ]
    requests.extend(envelope.verification_requests)
    combined = dict(proposals)
    combined.update((p.requirement_id, p) for p in retained.proposals)
    return (
        _GroupAnswers(
            proposals=tuple(combined.values()),
            verification_requests=tuple(requests),
            condition_assessments=(
                *(c for c in retained.condition_assessments if c.requirement_id not in assigned),
                *envelope.condition_assessments,
            ),
        ),
        errors,
    )


def _retained_group_answers(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not any(r["status"] == "proposal_recovery_requested" for r in records):
        return {"proposals": []}
    latest = next(
        r
        for r in reversed(records)
        if r["status"] in ("proposal_recovery_requested", "evidence_requested")
    )
    retained: dict[str, Any] = json.loads(latest["canonical_response"])
    if latest["status"] == "evidence_requested":
        pending = {r["requirement_id"] for r in retained["verification_requests"]}
        retained["proposals"] = [
            p for p in retained["proposals"] if p["requirement_id"] not in pending
        ]
        retained["verification_requests"] = []
        kept = {p["requirement_id"] for p in retained["proposals"]}
        retained["condition_assessments"] = [
            c for c in retained["condition_assessments"] if c["requirement_id"] in kept
        ]
    return retained


def _complete_proposal_exceptions(
    tools: PacketAgentTools,
    group: list[dict[str, Any]],
    record: dict[str, Any],
    handoff: dict[str, Any],
    name: str,
) -> None:
    batch = _GroupAnswers.model_validate_json(record["canonical_response"])
    proposals = {p.requirement_id: p.model_dump(mode="json") for p in batch.proposals}
    exceptions = []
    reasons = {e["requirement_id"]: e["code"] for e in record["proposal_errors"]}
    for requirement in group:
        rid = requirement["requirement_id"]
        if rid in proposals:
            continue
        reason = reasons.get(rid, "verification_not_completed")
        proposals[rid] = {
            "requirement_id": rid,
            "outcome": "technical_review_required",
            "explanation": (
                f"TECHNICAL REVIEW REQUIRED: {reason}. LEFT BLANK after bounded proposal recovery; "
                "this is not a finding of missing business evidence. Review the saved source "
                "and private proposal diagnostics, then provide a supported answer or leave blank."
            ),
        }
        exceptions.append({"requirement_id": rid, "code": reason})
        tools.answer_progress(f"Technical review required: requirement={rid}; code={reason}")
    deferred = [
        {
            "ok": False,
            "request": r.model_dump(mode="json"),
            "error": "verification_not_performed_proposal_recovery_exhausted",
        }
        for r in batch.verification_requests
    ]
    annotated = json.loads(
        _staging_response(batch, [*handoff.get("verification_results", []), *deferred])
    )
    for proposal in annotated["proposals"]:
        proposals[proposal["requirement_id"]] = proposal
    staging = _json({"proposals": [proposals[r["requirement_id"]] for r in group]})
    tools.answer_checkpoint(
        name,
        {"version": GROUP_VERSION, "staging_response": staging, "exceptions": exceptions},
    )
    staged = json.loads(tools.call("stage_answers", staging))
    if not staged["ok"]:
        raise ValueError("Canonical review exceptions no longer satisfy staging contracts")


def _staging_response(
    batch: _GroupAnswers, verification_results: list[dict[str, Any]] | None = None
) -> str:
    proposals = [p.model_dump(mode="json") for p in batch.proposals]
    for proposal in proposals:
        notes = [
            f"Condition (model assessment, not approval): {c.criterion_quote}; "
            f"{c.status}; reason={c.reason}; {c.explanation}"
            for c in batch.condition_assessments
            if c.requirement_id == proposal["requirement_id"]
        ]
        for result in verification_results or []:
            request = result["request"]
            if request["requirement_id"] != proposal["requirement_id"]:
                continue
            comparison = result.get("minimum_amount_result")
            if result["ok"] and comparison is not None:
                transcript = (result.get("scan_check") or {}).get("transcript", {})
                notes.append(
                    f"Checked monetary condition: {comparison['criterion_quote']}; "
                    f"USD {comparison['value']} compared with minimum USD {comparison['minimum']}; "
                    f"{'MET' if comparison['meets_minimum'] else 'NOT MET'}; "
                    f"source {request['source_id']}, page {request['page']}, "
                    f"subject {request['expected_subject']}, "
                    f"reporting period {transcript.get('reporting_period') or 'not established'}. "
                    "This establishes only this condition, not overall eligibility."
                )
            elif not result["ok"]:
                notes.append(
                    f"Evidence verification needs attention: source {request['source_id']}, "
                    f"page {request['page']}; reason={result['error']}. "
                    "The candidate has not been established as supporting evidence."
                )
        if notes:
            proposal["explanation"] = "\n".join([proposal.get("explanation") or "", *notes]).strip()
    return _json({"proposals": proposals})


def group_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "answer_group",
            "strict": True,
            "schema": pydantic_function_tool(_GroupAnswers)["function"]["parameters"],
        },
    }


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _resolve_citations(response: str, handoff: dict[str, Any]) -> tuple[str, list[str]]:
    """Resolve metadata from unique checked receipts or exact, unique native-page text."""
    try:
        value = json.loads(response)
    except json.JSONDecodeError:
        return response, []
    receipts = [*handoff.get("native_quote_citations", [])]
    receipts.extend(item["citation"] for item in handoff.get("scan_quotes", []))
    receipts.extend(item["answer_citation"] for item in handoff.get("historical_candidates", []))
    by_reference: dict[tuple[str, int, str], dict[str, dict[str, Any]]] = {}
    for receipt in receipts:
        kind = OcrCitation if receipt.get("evidence_kind") == "ocr" else Citation
        checked = kind.model_validate_json(_json(receipt)).model_dump(mode="json")
        key = (checked["source_id"], checked["page"], checked["quote"])
        by_reference.setdefault(key, {})[_json(checked)] = checked
    sources = {
        source["source_id"]: source["page_count"]
        for source in handoff.get("sources", [])
        if source.get("format") == "pdf" and type(source.get("page_count")) is int
    }
    native_pages: dict[tuple[str, int], set[tuple[str, str]]] = {}
    for reading in handoff.get("candidate_readings", []):
        source_id = reading.get("source_id")
        page = reading.get("page")
        text = reading.get("text")
        digest = reading.get("source_sha256")
        if (
            reading.get("mode") == "native"
            and reading.get("citable") is True
            and reading.get("artifact_path") is None
            and isinstance(source_id, str)
            and source_id in sources
            and type(page) is int
            and 1 <= page <= sources[source_id]
            and isinstance(text, str)
            and isinstance(digest, str)
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest)
        ):
            native_pages.setdefault((source_id, page), set()).add((digest, text))
    resolved: list[str] = []

    def visit(item: Any, path: str) -> Any:
        if isinstance(item, dict):
            if (
                item.get("evidence_kind") == "ocr"
                and isinstance(item.get("source_id"), str)
                and type(item.get("page")) is int
                and isinstance(item.get("quote"), str)
                and isinstance(item.get("render_sha256"), str)
            ):
                matches = by_reference.get((item["source_id"], item["page"], item["quote"]), {})
                # The artifact hash and exact word span bind the reference. Resolve a copied
                # render hash only by replacing the entire uniquely identified checked receipt.
                exact = [
                    receipt
                    for receipt in matches.values()
                    if set(item) == set(receipt)
                    and all(item[k] == receipt[k] for k in item if k != "render_sha256")
                ]
                if len(exact) == 1 and exact[0] != item:
                    resolved.append(path)
                    return exact[0]
            if (
                set(item) == {"source_id", "page", "quote", "start", "end"}
                and isinstance(item["source_id"], str)
                and type(item["page"]) is int
                and isinstance(item["quote"], str)
                and type(item["start"]) is int
                and type(item["end"]) is int
                and 0 <= item["start"] < item["end"]
            ):
                matches = by_reference.get((item["source_id"], item["page"], item["quote"]), {})
                if len(matches) == 1:
                    checked = next(iter(matches.values()))
                    if checked != item:
                        resolved.append(path)
                        return checked
                if not matches and item["quote"].strip():
                    pages = native_pages.get((item["source_id"], item["page"]), set())
                    if len(pages) == 1:
                        _, text = next(iter(pages))
                        start = text.find(item["quote"])
                        if start >= 0 and text.find(item["quote"], start + 1) < 0:
                            # Offsets are derived here; source and answer support are still
                            # independently checked by the gate and writer.
                            located = item | {"start": start, "end": start + len(item["quote"])}
                            if located != item:
                                resolved.append(path)
                                return located
            return {k: visit(v, f"{path}.{k}" if path else k) for k, v in item.items()}
        if isinstance(item, list):
            return [visit(v, f"{path}.{i}") for i, v in enumerate(item)]
        return item

    result = visit(value, "")
    return (_json(result) if resolved else response), resolved


def _bind_historical_choice_citations(
    response: str,
    handoff: dict[str, Any],
    checks: tuple[HistoricalContextCheck, ...],
    application_sha256: str,
) -> tuple[str, list[str]]:
    """Bind an unchanged choice through its exact checked relationship, not its label."""
    try:
        value = json.loads(response)
    except json.JSONDecodeError:
        return response, []
    if not isinstance(value, dict) or not isinstance(value.get("proposals"), list):
        return response, []
    requirements = {
        item["requirement_id"]: Requirement.model_validate_json(
            _json(item | {"application_sha256": application_sha256})
        )
        for item in handoff.get("requirements", [])
    }
    associations = tuple(
        HistoricalAssociation.model_validate_json(_json(item))
        for item in handoff.get("historical_candidates", [])
    )
    paths: list[str] = []
    for index, item in enumerate(value["proposals"]):
        try:
            proposal = ModelProposal.model_validate_json(_json(item))
        except ValidationError:
            # Normal ingestion owns malformed-item diagnostics and bounded correction.
            continue
        basis = proposal.historical_basis
        requirement = requirements.get(proposal.requirement_id)
        if (
            proposal.outcome != "proposed"
            or not isinstance(proposal.value, SingleSelectValue)
            or proposal.value.write_ins
            or basis is None
            or not isinstance(basis.prior_question, HistoricalContextCitation)
            or basis.additional_contexts
            or basis.tenure is not None
            or basis.reading_resolution is not None
            or requirement is None
            or requirement.kind != "single_select"
            or len(proposal.citations) != 1
            or not isinstance(proposal.citations[0], Citation)
        ):
            continue
        matches = {
            a.model_dump_json(): a
            for a in associations
            if a.context_citation == basis.prior_question
        }
        if len(matches) != 1:
            continue
        association = next(iter(matches.values()))
        checked = {
            c.model_dump_json(): c
            for c in checks
            if c.context_citation == association.context_citation
        }
        if len(checked) != 1:
            continue
        check = next(iter(checked.values()))
        original = proposal.citations[0]
        if (
            association.write_in is not None
            or check.field.write_in is not None
            or check.answer != association.answer_citation
            or check.field.control is None
            or check.field.control.state != "selected"
            or check.answer_disputed
            or any(d.part == "control" for d in check.discrepancies)
            or original.source_id != check.answer.source_id
            or original.page != check.answer.page
            or not explicit_choice_answer(requirement, proposal.value, check.answer.quote)
            or not check.supports(
                proposal.model_copy(update={"citations": (check.answer,)}), requirement
            )
        ):
            continue
        replacement = check.answer.model_dump(mode="json")
        if item["citations"][0] != replacement:
            item["citations"] = [replacement]
            paths.append(f"proposals.{index}.citations.0")
    return (_json(value) if paths else response), paths


def _technical_error(error: BaseException) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": "group_model_failed",
        "type": type(error).__name__,
        "causes": [],
    }
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(seen) < 4:
        seen.add(id(current))
        label = type(current).__name__
        status = getattr(current, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            label += f" HTTP {status}"
        result["causes"].append(label)
        if isinstance(current, ValidationError):
            result["problems"] = _problems(current)
        current = (
            current.__cause__
            or current.__context__
            or next((arg for arg in current.args if isinstance(arg, BaseException)), None)
        )
    return result


def _verification_handoff(
    tools: PacketAgentTools, handoff: dict[str, Any], prefix: str
) -> dict[str, Any]:
    artifacts = {a.name for a in tools.manifest().artifacts}
    results = [
        result
        for artifact in tools.manifest().artifacts
        if artifact.name.startswith(prefix) and artifact.name.endswith("-verification.json")
        for result in json.loads(tools.answer_artifact(artifact.name))["results"]
    ]
    for name in sorted(artifacts):
        if (
            name.startswith(prefix)
            and name.endswith("-verification-request.json")
            and name.replace("-request.json", ".json") not in artifacts
        ):
            pending = json.loads(tools.answer_artifact(name))
            results.extend(
                {
                    "ok": False,
                    "request": request,
                    "error": "verification_interrupted_do_not_repeat_unknown_paid_work",
                }
                for request in pending["requests"]
            )
    native = list(handoff.get("native_quote_citations", []))
    scans = list(handoff.get("scan_quotes", []))
    candidates = list(handoff.get("candidate_readings", []))
    for artifact in tools.manifest().artifacts:
        if artifact.name.startswith(prefix) and artifact.name.endswith("-verification.json"):
            for observation in json.loads(tools.answer_artifact(artifact.name)).get(
                "candidate_readings", []
            ):
                if observation not in candidates:
                    candidates.append(observation)
    for result in results:
        if result["ok"]:
            citation = result["citation"]
            if citation.get("evidence_kind") == "ocr":
                check = result["scan_check"]
                scans.append(
                    {
                        "citation": citation,
                        "subject": check["expected_subject"],
                        "reporting_period": check["transcript"]["reporting_period"],
                    }
                )
            else:
                native.append(citation)
    return {
        **handoff,
        "verification_results": results,
        "native_quote_citations": native,
        "scan_quotes": scans,
        "candidate_readings": candidates,
    }


async def _attempt_group(
    tools: PacketAgentTools,
    propose: ProposeGroup,
    payload: dict[str, Any],
    name: str,
    requests_remaining: int,
    can_followup: bool,
    *,
    json_retry_of_attempt: int | None = None,
    proposal_retry_of_attempt: int | None = None,
    timeout_seconds: float = GROUP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "version": GROUP_VERSION,
        "requirement_ids": payload["assigned_requirement_ids"],
        "input_sha256": _digest(payload),
        "response": None,
        "status": "technical_failure",
        "error": None,
        "citation_resolution": "checked-citations-and-historical-choices-v4",
        "resolved_citation_paths": [],
        "historical_binding_paths": [],
        "reference_resolution_paths": [],
        "instructions_sha256": _digest(ANSWER_INSTRUCTIONS),
        "response_schema_sha256": _digest(group_response_format()),
        "response_bytes": None,
        "finish_reason": None,
    }
    request_marker = {k: record[k] for k in ("version", "requirement_ids", "input_sha256")}
    if json_retry_of_attempt is not None:
        record["json_retry_of_attempt"] = request_marker["json_retry_of_attempt"] = (
            json_retry_of_attempt
        )
    if proposal_retry_of_attempt is not None:
        record["proposal_retry_of_attempt"] = request_marker["proposal_retry_of_attempt"] = (
            proposal_retry_of_attempt
        )
    tools.answer_checkpoint(
        name.replace(".json", "-request.json"),
        request_marker,
    )
    try:
        model_response = await asyncio.wait_for(propose(payload), timeout=timeout_seconds)
    except (AgentFrameworkException, TimeoutError) as error:
        record["error"] = _technical_error(error)
        return record
    response = model_response.text if isinstance(model_response, GroupResponse) else model_response
    if isinstance(model_response, GroupResponse):
        record["finish_reason"] = (
            model_response.finish_reason
            if model_response.finish_reason
            in (None, "stop", "length", "tool_calls", "content_filter")
            else "unknown"
        )
    record["response_bytes"] = len(response.encode())
    if record["response_bytes"] > MAX_RESPONSE_BYTES:
        record["error"] = {"code": "group_response_too_large"}
        return record
    record["response"] = response
    checks = tuple(
        HistoricalContextCheck.model_validate_json(_json(item))
        for item in json.loads(tools.answer_artifact("historical_context_checks.json"))["checks"]
    )
    resolved, binding_paths = _bind_historical_choice_citations(
        response, payload, checks, tools.manifest().blank_sha256
    )
    record["historical_binding_paths"] = binding_paths
    resolved, paths = _resolve_citations(resolved, payload)
    record["resolved_citation_paths"] = paths
    resolved, reference_paths = _resolve_reference_labels(resolved)
    record["reference_resolution_paths"] = reference_paths
    try:
        batch, proposal_errors = _ingest_group(resolved, payload)
    except _GroupIdentityError:
        record.update(status="invalid_response", error={"code": "group_requirement_mismatch"})
        return record
    except ValidationError as error:
        record.update(
            status="invalid_response",
            error={
                "code": "invalid_arguments",
                "problems": _problems(error),
                "details": error.errors(
                    include_input=False, include_context=False, include_url=False
                )[:20],
            },
        )
        return record
    record["canonical_response"] = batch.model_dump_json()
    record["proposal_errors"] = proposal_errors
    assigned = {
        *payload["assigned_requirement_ids"],
        *(
            p["requirement_id"]
            for p in payload.get("retained_group_answers", {}).get("proposals", [])
        ),
        *(
            r["requirement_id"]
            for r in payload.get("retained_group_answers", {}).get("verification_requests", [])
        ),
    }
    ids = [p.requirement_id for p in batch.proposals]
    requested = [r.requirement_id for r in batch.verification_requests]
    instructions = {
        r["requirement_id"]: r["instruction"]
        + "\n"
        + "\n".join(c["instruction"] for c in (r.get("choices") or {}).get("options", []))
        for r in payload.get("group_requirements", payload["requirements"])
    }
    if any(
        not contains_issuer_quote(instructions.get(c.requirement_id, ""), c.criterion_quote)
        for c in batch.condition_assessments
    ):
        record.update(status="invalid_response", error={"code": "condition_not_in_requirement"})
        return record
    if proposal_errors:
        record.update(
            status="proposal_recovery_requested",
            error={"code": "proposal_validation_failed", "problems": proposal_errors},
        )
        return record
    if (
        len(ids) != len(set(ids))
        or not set(ids + requested) <= assigned
        or any(c.requirement_id not in assigned for c in batch.condition_assessments)
        or (not requested and set(ids) != assigned)
    ):
        record.update(status="invalid_response", error={"code": "group_requirement_mismatch"})
        return record
    if batch.verification_requests:
        if not can_followup or len(batch.verification_requests) > requests_remaining:
            if set(ids) != assigned:
                record.update(
                    status="proposal_recovery_requested",
                    proposal_errors=[
                        {"requirement_id": rid, "code": "evidence_followup_limit_exceeded"}
                        for rid in sorted(assigned - set(ids))
                    ],
                    error={"code": "evidence_followup_limit_exceeded"},
                )
                return record
            results = [
                {
                    "ok": False,
                    "request": request.model_dump(mode="json"),
                    "error": "evidence_followup_limit_exceeded",
                }
                for request in batch.verification_requests
            ]
            tools.answer_checkpoint(
                name.replace(".json", "-verification.json"),
                {"results": results, **tools.answer_verification_state()},
            )
            tools.answer_progress(
                "Evidence follow-up limit reached; no verification performed. "
                "Complete proposals will undergo final validation with explicit review concerns."
            )
            staged = json.loads(
                tools.call(
                    "stage_answers",
                    _staging_response(batch, [*payload.get("verification_results", []), *results]),
                )
            )
            record.update(
                status="staged_unvalidated" if staged["ok"] else "invalid_response",
                error=staged.get("error"),
            )
            return record
        prior_requests = [r["request"] for r in payload.get("verification_results", [])]
        tools.answer_checkpoint(
            name.replace(".json", "-verification-request.json"),
            {
                "requests": [r.model_dump(mode="json") for r in batch.verification_requests],
                "response": response,
            },
        )
        results = []
        for request in batch.verification_requests:
            result: dict[str, Any]
            if request.model_dump(mode="json") in prior_requests:
                result = {
                    "ok": False,
                    "request": request.model_dump(mode="json"),
                    "error": "verification_request_already_attempted",
                }
            else:
                logging.getLogger(__name__).info(
                    "Answer evidence verification started: run=%s requirement=%s method=%s",
                    tools.manifest().run_id,
                    request.requirement_id,
                    request.method,
                )
                verification_scope = {
                    **payload,
                    "requirements": payload.get("group_requirements", payload["requirements"]),
                }
                result = await asyncio.to_thread(
                    tools.verify_answer_evidence, request, verification_scope
                )
                logging.getLogger(__name__).info(
                    "Answer evidence verification finished: run=%s requirement=%s ok=%s error=%s",
                    tools.manifest().run_id,
                    request.requirement_id,
                    result["ok"],
                    result.get("error", "none"),
                )
            tools.answer_progress(
                f"Evidence follow-up: requirement={request.requirement_id}; "
                f"{'completed' if result['ok'] else 'needs attention'}; "
                f"code={result.get('error', 'none')}"
            )
            results.append(result)
            if result.get("ok") and result.get("scan_check") is not None:
                citation = result["citation"]
                artifact_name = f"ocr-{citation['artifact_sha256']}.json"
                if artifact_name not in {a.name for a in tools.manifest().artifacts}:
                    # Candidate OCR is normally archived by discovery; do not add new source paths.
                    raise ValueError("Verified OCR receipt lacks its immutable candidate archive")
        tools.answer_checkpoint(
            name.replace(".json", "-verification.json"),
            {"results": results, **tools.answer_verification_state()},
        )
        record.update(status="evidence_requested")
        return record
    staged = json.loads(
        tools.call("stage_answers", _staging_response(batch, payload.get("verification_results")))
    )
    record.update(
        status="staged_unvalidated" if staged["ok"] else "invalid_response",
        error=staged.get("error"),
    )
    return record


class _EvidenceBoundary(FunctionMiddleware):
    def __init__(self, tools: PacketAgentTools) -> None:
        self.tools = tools

    async def process(
        self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
    ) -> None:
        await call_next()
        if self.tools.manifest().status not in ("created", "form_interpreted"):
            raise MiddlewareTermination(result="Evidence phase ended; application owns next step.")


def _finalize_packet(tools: PacketAgentTools, *, submit: bool = True) -> RunManifest:
    submission = (("submit_answers", '{"proposals":[]}'),) if submit else ()
    for tool, args in (
        *submission,
        ("assemble_packet", "{}"),
        ("publish_results", "{}"),
    ):
        result = json.loads(tools.call(tool, args))
        if not result["ok"]:
            if tools.manifest().status == "failed":
                return tools.manifest()
            return tools.fail("group_finalization_failed", "Answer validation or assembly failed.")
    return tools.manifest()


async def run_answer_groups(
    tools: PacketAgentTools, propose: ProposeGroup, *, resume: bool = False
) -> RunManifest:
    """Bound retries; isolate attributable proposal errors as explicit review exceptions."""
    handoff = tools.answer_handoff()
    retained = handoff.get("retained_proposals", [])
    retained_ids = {p["requirement_id"] for p in retained}
    requirements = [
        r
        for r in handoff["requirements"]
        if r["kind"] not in ("signature", "signature_date")
        and r["requirement_id"] not in retained_ids
    ]
    groups = [requirements[i : i + GROUP_SIZE] for i in range(0, len(requirements), GROUP_SIZE)]
    plan: dict[str, Any] = {
        "version": GROUP_VERSION,
        "handoff_sha256": _digest(handoff),
        "versions": [v.model_dump(mode="json") for v in tools.manifest().versions],
        "groups": [[r["requirement_id"] for r in group] for group in groups],
        "group_size": GROUP_SIZE,
        "max_group_attempts": MAX_GROUP_ATTEMPTS,
        "max_json_retries": MAX_JSON_RETRIES,
        "max_proposal_retries": MAX_PROPOSAL_RETRIES,
        "timeout_seconds": GROUP_TIMEOUT_SECONDS,
        "group_model_limit": tools.limits.max_turns - tools.limits.max_turns // 2,
        "max_verification_requests": MAX_VERIFICATION_REQUESTS,
    }
    names = {a.name for a in tools.manifest().artifacts}
    if (
        "answer-plan.json" in names
        and json.loads(tools.answer_artifact("answer-plan.json")) != plan
    ):
        raise ValueError("Answer plan or component versions changed; start a new run")
    tools.prepare_answer_recovery(resume=resume)
    if tools.manifest().status == "answers_validated":
        tools.answer_progress("Assembly recovery: reusing saved validated answers; no model calls.")
        return _finalize_packet(tools, submit=False)
    for start in range(0, len(retained), 10):
        result = json.loads(
            tools.call("stage_answers", _json({"proposals": retained[start : start + 10]}))
        )
        if not result["ok"]:
            raise ValueError("Retained answers no longer satisfy staging contracts")
    if "answer-plan.json" not in names:
        tools.answer_checkpoint("answer-plan.json", plan)
    started = time.monotonic()
    attempts_used = sum(
        name.startswith("answer-group-")
        and name.endswith("-request.json")
        and not name.endswith("-verification-request.json")
        for name in names
    )
    incomplete = False
    consecutive_transport_failures = 0
    for index, group in enumerate(groups):
        prefix = f"answer-group-{index:03d}-attempt-"
        completion_name = f"answer-group-{index:03d}-completion.json"
        if completion_name in names:
            completion = json.loads(tools.answer_artifact(completion_name))
            staged = json.loads(tools.call("stage_answers", completion["staging_response"]))
            if not staged["ok"]:
                raise ValueError("Saved canonical group completion no longer satisfies staging")
            continue
        requests = sorted(
            name
            for name in names
            if name.startswith(prefix)
            and name.endswith("-request.json")
            and not name.endswith("-verification-request.json")
        )
        records: list[dict[str, Any]] = []
        json_retries_used = sum(
            "json_retry_of_attempt" in json.loads(tools.answer_artifact(request))
            for request in requests
        )
        proposal_retries_used = sum(
            "proposal_retry_of_attempt" in json.loads(tools.answer_artifact(request))
            for request in requests
        )
        for request in requests:
            response_name = request.replace("-request.json", ".json")
            records.append(
                json.loads(tools.answer_artifact(response_name))
                if response_name in names
                else {"status": "interrupted", "error": {"code": "group_interrupted"}}
            )
        accepted = next((r for r in records if r["status"] == "staged_unvalidated"), None)
        if accepted is not None:
            effective = _verification_handoff(tools, handoff, prefix)
            response = accepted["canonical_response"]
            batch = _GroupAnswers.model_validate_json(response)
            staged = json.loads(
                tools.call(
                    "stage_answers", _staging_response(batch, effective["verification_results"])
                )
            )
            if not staged["ok"]:
                raise ValueError("Saved answer group no longer satisfies staging contracts")
            continue
        partial = next(
            (r for r in reversed(records) if r["status"] == "proposal_recovery_requested"), None
        )
        if records and records[-1]["status"] not in ("proposal_recovery_requested", "interrupted"):
            partial = None
        exhausted = (
            len(records) >= MAX_GROUP_ATTEMPTS
            or attempts_used >= plan["group_model_limit"]
            or time.monotonic() - started >= tools.limits.max_seconds
        )
        if partial is not None and (proposal_retries_used >= MAX_PROPOSAL_RETRIES or exhausted):
            _complete_proposal_exceptions(
                tools,
                group,
                partial,
                _verification_handoff(tools, handoff, prefix),
                completion_name,
            )
            continue
        if (
            len(records) >= MAX_GROUP_ATTEMPTS
            or attempts_used >= plan["group_model_limit"]
            or time.monotonic() - started >= tools.limits.max_seconds
        ):
            incomplete = True
            continue
        json_retry_of_attempt = None
        for attempt in range(len(records) + 1, MAX_GROUP_ATTEMPTS + 1):
            partial = (
                records[-1]
                if records and records[-1]["status"] == "proposal_recovery_requested"
                else None
            )
            repair_ids = (
                [e["requirement_id"] for e in partial["proposal_errors"]]
                if partial is not None
                else []
            )
            proposal_retry_of_attempt = len(records) if partial is not None else None
            if partial is not None:
                proposal_retries_used += 1
            verification_used = sum(
                len(json.loads(tools.answer_artifact(a.name))["requests"])
                for a in tools.manifest().artifacts
                if a.name.endswith("-verification-request.json")
            )
            calls_remaining = min(
                MAX_GROUP_ATTEMPTS - attempt + 1, plan["group_model_limit"] - attempts_used
            )
            requests_remaining = max(0, MAX_VERIFICATION_REQUESTS - verification_used)
            retained_answers = _retained_group_answers(records)
            retained_ids = {p["requirement_id"] for p in retained_answers["proposals"]}
            assigned_ids = repair_ids or [
                rid for rid in plan["groups"][index] if rid not in retained_ids
            ]
            payload = {
                **_verification_handoff(tools, handoff, prefix),
                "requirements": [r for r in group if r["requirement_id"] in assigned_ids],
                "group_requirements": group,
                "assigned_requirement_ids": assigned_ids,
                "repair_requirement_ids": repair_ids,
                "retained_group_answers": retained_answers,
                "previous_errors": [r["error"] for r in records if r.get("error")],
                "verification_budget": {
                    "group_calls_remaining": calls_remaining,
                    "requests_remaining": requests_remaining,
                    "followup_allowed": calls_remaining > 1 and requests_remaining > 0,
                },
            }
            name = f"{prefix}{attempt}.json"
            if json_retry_of_attempt is not None:
                message = (
                    f"Answer JSON retry started: group={index} attempt={attempt} "
                    f"retry_of_attempt={json_retry_of_attempt} reason=json_invalid"
                )
                logging.getLogger(__name__).info("%s run=%s", message, tools.manifest().run_id)
                tools.answer_progress(message)
            attempts_used += 1
            if proposal_retry_of_attempt is not None:
                tools.answer_progress(
                    f"Proposal correction started: group={index}; "
                    f"requirements={len(repair_ids)}; attempt={attempt}"
                )
            record = await _attempt_group(
                tools,
                propose,
                payload,
                name,
                requests_remaining,
                calls_remaining > 1,
                json_retry_of_attempt=json_retry_of_attempt,
                proposal_retry_of_attempt=proposal_retry_of_attempt,
                timeout_seconds=min(
                    GROUP_TIMEOUT_SECONDS,
                    max(0, tools.limits.max_seconds - (time.monotonic() - started)),
                ),
            )
            tools.answer_checkpoint(name, record)
            records.append(record)
            if json_retry_of_attempt is not None:
                message = (
                    f"Answer JSON retry finished: group={index} attempt={attempt} "
                    f"status={record['status']} response_bytes={record['response_bytes']} "
                    f"finish_reason={record['finish_reason'] or 'unavailable'}"
                )
                logging.getLogger(__name__).info("%s run=%s", message, tools.manifest().run_id)
                tools.answer_progress(message)
                json_retry_of_attempt = None
            if record["status"] == "proposal_recovery_requested":
                if (
                    proposal_retries_used < MAX_PROPOSAL_RETRIES
                    and attempt < MAX_GROUP_ATTEMPTS
                    and attempts_used < plan["group_model_limit"]
                    and time.monotonic() - started < tools.limits.max_seconds
                ):
                    continue
                _complete_proposal_exceptions(
                    tools,
                    group,
                    record,
                    _verification_handoff(tools, handoff, prefix),
                    completion_name,
                )
                record = {**record, "status": "staged_unvalidated"}
                break
            invalid_json = record["status"] == "invalid_response" and any(
                problem["type"] == "json_invalid"
                for problem in (record["error"] or {}).get("problems", [])
            )
            if invalid_json:
                reason = None
                if json_retries_used >= MAX_JSON_RETRIES:
                    reason = "retry_limit"
                elif attempt >= MAX_GROUP_ATTEMPTS:
                    reason = "group_attempt_limit"
                elif attempts_used >= plan["group_model_limit"]:
                    reason = "model_call_limit"
                elif time.monotonic() - started >= tools.limits.max_seconds:
                    reason = "elapsed_time_limit"
                if reason is not None:
                    message = f"Answer JSON retry unavailable: group={index} reason={reason}"
                    logging.getLogger(__name__).info("%s run=%s", message, tools.manifest().run_id)
                    tools.answer_progress(message)
                    break
                json_retries_used += 1
                json_retry_of_attempt = attempt
                continue
            if record["status"] != "evidence_requested":
                break
            if (
                attempts_used >= plan["group_model_limit"]
                or time.monotonic() - started >= tools.limits.max_seconds
            ):
                record["status"] = "followup_interrupted"
                break
        logging.getLogger(__name__).info(
            "Answer group checkpoint: run=%s group=%s status=%s error=%s",
            tools.manifest().run_id,
            index,
            record["status"],
            record["error"]["code"] if record["error"] else "none",
        )
        incomplete |= record["status"] != "staged_unvalidated"
        consecutive_transport_failures = (
            consecutive_transport_failures + 1 if record["status"] == "technical_failure" else 0
        )
        if consecutive_transport_failures >= 3:
            break
    if incomplete:
        return tools.fail(
            "answer_groups_incomplete",
            "Answer groups require recovery. Private proposals and validation diagnostics "
            "are saved; no packet was published. Explicit resume retries unfinished groups only.",
        )
    return _finalize_packet(tools)


async def run_grouped_packet_agent(
    client: Any, tools: PacketAgentTools, *, resume: bool = False
) -> RunManifest:
    """Keep agentic evidence discovery; code owns the answering and publication phases."""
    configure_client(client, tools.limits)
    # Reserve half the calls for discovery, including the SDK's final no-tools turn.
    # Continuations after a premature text reply share this one budget.
    evidence_budget = max(1, tools.limits.max_turns // 2 - 1)
    client.function_invocation_configuration["max_iterations"] = evidence_budget
    client.function_invocation_configuration["allow_concurrent_invocation"] = False
    client.compaction_strategy = None
    evidence_tools = [
        t
        for t in tools.function_tools()
        if t.name not in {"stage_answers", "submit_answers", "assemble_packet", "publish_results"}
    ]
    agent = Agent(
        client,
        EVIDENCE_INSTRUCTIONS,
        name="packet-evidence",
        tools=evidence_tools,
        middleware=[_EvidenceBoundary(tools)],
        default_options={"store": False, "reasoning": {"effort": "low"}, "max_tokens": 16_384},
    )
    started = time.monotonic()
    if not resume and tools.manifest().status in ("created", "form_interpreted"):
        session = agent.create_session()
        prompt = "Collect approved evidence, then finish_evidence. Begin with get_run_status."
        continuations = 0
        model_calls = 0
        while True:
            remaining = evidence_budget - model_calls
            if remaining <= 0:
                return tools.fail(
                    "evidence_stopped_early",
                    "Evidence phase ended without handoff; evidence model-call budget "
                    f"({evidence_budget}) exhausted after {continuations} continuation(s).",
                )
            client.function_invocation_configuration["max_iterations"] = remaining
            try:
                response = await agent.run(prompt, session=session)
            except AgentFrameworkException as error:
                diagnostic = _technical_error(error)
                return tools.fail(
                    "evidence_model_failed",
                    "Evidence model call failed: " + " -> ".join(diagnostic["causes"]),
                )
            # Each model call yields exactly one assistant message in the run's response.
            model_calls += max(1, sum(m.role == "assistant" for m in response.messages))
            status = tools.manifest().status
            if status == "failed":
                return tools.manifest()
            if status == "evidence_collected":
                break
            if status not in ("created", "form_interpreted"):
                return tools.fail("evidence_stopped_early", "Evidence phase ended without handoff.")
            if continuations >= MAX_EVIDENCE_CONTINUATIONS:
                return tools.fail(
                    "evidence_stopped_early",
                    f"Evidence phase ended without handoff after {continuations} continuation(s).",
                )
            if time.monotonic() - started >= tools.limits.max_seconds:
                return tools.fail(
                    "evidence_stopped_early",
                    "Evidence phase ended without handoff; elapsed-time budget exhausted.",
                )
            continuations += 1
            # The model's text is not logged; it may quote confidential source content.
            tools.answer_progress(
                "Evidence model ended its turn without finish_evidence; continuation "
                f"{continuations}/{MAX_EVIDENCE_CONTINUATIONS}"
            )
            prompt = EVIDENCE_CONTINUATION

    answer_agent = Agent(
        client,
        ANSWER_INSTRUCTIONS,
        name="packet-answer-group",
        default_options={
            "store": False,
            "reasoning": {"effort": "low"},
            "max_tokens": 8192,
            "response_format": group_response_format(),
            "tool_choice": "none",
        },
    )

    async def propose(payload: dict[str, Any]) -> GroupResponse:
        if time.monotonic() - started >= tools.limits.max_seconds:
            raise TimeoutError("Grouped model budget exhausted")
        response = await answer_agent.run(_json(payload))
        return GroupResponse(response.text, response.finish_reason)

    return await run_answer_groups(tools, propose, resume=resume)
