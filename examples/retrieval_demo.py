"""Fictional requirement-driven routing/retrieval evaluation; no real document access."""

import argparse
import json
from pathlib import Path
from typing import Never
from uuid import uuid4

from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import ApplicationRequirements
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.retrieval import (
    EvidencePlan,
    default_catalog,
    retrieve_evidence,
    run_targeted_retrieval,
)


def _pdf(path: Path, text: str, pages: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), invariant=True)
    for number in range(pages):
        canvas.setFont("Helvetica", 11)
        lines = (
            text.splitlines()
            if number == 0
            else [
                "Fictional supporting notes. No additional applicant facts on this page.",
                "This page is deliberately present to test that retrieval is bounded.",
            ]
        )
        for index, line in enumerate(lines):
            canvas.drawString(45, 740 - index * 18, line)
        canvas.showPage()
    canvas.save()


def prepare(root: Path) -> Path:
    root = root.resolve(strict=True)
    output = root / "outputs"
    if output.resolve() != output:
        raise ValueError("Output must not resolve through a symlink")
    output.mkdir(exist_ok=True)
    data = output / f"retrieval-demo-{uuid4().hex}" / "synthetic-root"
    support = data / "bd_agreements/supporting_data"
    _pdf(
        support / "FINRA_Certification/registration.pdf",
        "Fictional registration record.\nLegal name: Example Demonstration LLC.\nCRD: 001234\n"
        "This synthetic record supports identity only, not a negative disclosure.",
        8,
    )
    _pdf(
        support / "Insperex_Public_Funds/overview.pdf",
        "Fictional firm overview.\nThe firm provides public-sector fixed-income services.\n"
        "This is synthetic evidence for a controlled demonstration, not a real firm claim.",
        6,
    )
    _pdf(
        support / "SIPC_list/membership.pdf",
        "Fictional membership proof for Example Demonstration LLC.\n"
        "This document is a test attachment, not valid real-world membership evidence.\n"
        "Its contents require human review before any actual submission.",
        6,
    )
    _pdf(
        support / "Focus_Reports/FOCUS_2026-08.pdf",
        "As of August 31, 2026\nExcess net capital: USD 12000000.00\n"
        "This fictional August report must not answer a September financial requirement.",
        3,
    )
    _pdf(support / "Unrelated/never-read.pdf", "UNRELATED_SENTINEL", 10)
    definitions = [
        ("crd", "Provide the firm's CRD number.", "identifier"),
        ("services", "Describe the firm's services.", "narrative"),
        ("membership", "Attach the firm's SIPC membership proof.", "attachment"),
        ("tax-id", "Provide the firm's tax identifier.", "identifier"),
        ("capital", "Provide excess net capital for September 2026.", "money"),
        ("signature", "Authorized signature.", "signature"),
    ]
    requirements = []
    for identity, instruction, kind in definitions:
        item: dict[str, object] = dict(
            requirement_id=identity,
            application_sha256="a" * 64,
            page=1,
            instruction=instruction,
            kind=kind,
        )
        if kind == "money":
            item.update(unit="USD", requested_period={"start": "2026-09-01", "end": "2026-09-30"})
        requirements.append(item)
    checked = ApplicationRequirements.model_validate_json(
        json.dumps({"requirements": requirements})
    )
    (data / "outputs").mkdir()
    (data / "outputs/requirements.json").write_text(checked.model_dump_json(indent=2) + "\n")
    return data


def evaluate(report: dict) -> dict[str, bool]:
    needs = {item["requirement_id"]: item for item in report["needs"]}
    proposals = {
        p["requirement_id"]: p for p in (report["proposals"] or {"proposals": []})["proposals"]
    }
    crd = proposals.get("crd", {})
    services = proposals.get("services", {})
    return {
        "leading_zero_identifier": (crd.get("value") or {}).get("value") == "001234"
        and any("CRD: 001234" in c["quote"] for c in crd.get("citations", []))
        and {s["family"] for s in needs["crd"]["sources"]} == {"FINRA_Certification"},
        "supported_narrative": services.get("outcome") == "proposed"
        and "public-sector fixed-income services" in (services.get("value") or {}).get("value", "")
        and any(
            "public-sector fixed-income services" in c["quote"]
            for c in services.get("citations", [])
        )
        and {s["family"] for s in needs["services"]["sources"]} == {"Insperex_Public_Funds"},
        "missing_tax_abstained": proposals.get("tax-id", {}).get("outcome")
        in (None, "missing_evidence"),
        "wrong_period_withheld": not needs["capital"]["answer_evidence_usable"]
        and "capital" not in proposals
        and "requested_period_unavailable" in needs["capital"]["issues"],
        "signature_unresolved": needs["signature"]["action"] == "unresolved",
        "attachment_candidate_separate": bool(needs["membership"]["attachment_candidate"])
        and "membership" not in proposals
        and needs["membership"]["action"] == "attach"
        and {s["family"] for s in needs["membership"]["attachment_candidate"]} == {"SIPC_list"},
        "bounded_reading": len(report["pages"]) <= 8 < 33,
        "unrelated_family_not_exposed": "UNRELATED_SENTINEL" not in json.dumps(report),
        "all_answers_unapproved": all(
            c["fill_value"] is None and c["status"] != "rejected" for c in report["proposal_checks"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--deployment")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    if not args.prepare_only and not (args.allow_paid and args.endpoint and args.deployment):
        parser.error("Supply --prepare-only or endpoint, deployment and --allow-paid")
    data = prepare(args.root)
    print(f"Fictional inputs prepared: {data}")
    if args.prepare_only:
        return 0
    config = FoundryConfig(endpoint=args.endpoint, deployment=args.deployment)
    output = run_targeted_retrieval(
        data, Path("outputs/requirements.json"), config=config, allow_paid=True
    )
    report = json.loads((output / "retrieval.json").read_text())
    checks = evaluate(report)

    def no_model(_: FoundryConfig) -> Never:
        raise AssertionError("Unchanged evidence cache unexpectedly requested another model call")

    reused = retrieve_evidence(
        data,
        ApplicationRequirements.model_validate_json(json.dumps(report["requirements"])),
        default_catalog(),
        EvidencePlan.model_validate_json(json.dumps(report["plan"])),
        config=config,
        allow_paid=True,
        cache_path=(output / "retrieval.json").relative_to(data),
        client_factory=no_model,
    )
    cached = json.loads((reused / "retrieval.json").read_text())
    checks["unchanged_native_proposals_reused_without_model"] = cached["cache_status"].startswith(
        "reused_unapproved"
    )
    evaluation = {
        "scope": "one_fixed_synthetic_case_not_general_grounding",
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
        "report": str(output / "retrieval.json"),
        "cache_report": str(reused / "retrieval.json"),
        "pages_read": len(report["pages"]),
        "pages_available": 33,
        "requests": [report["routing_request"], report["answer_request"]],
    }
    (output / "retrieval-evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    print(json.dumps(evaluation, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
