"""Local PDF workflows and explicitly opted-in model experiments."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from pypdf.errors import PdfReadError
from pypdfium2 import PdfiumError

from bd_packet_builder.demo import (
    DEFAULT_DEPLOYMENT,
    DEFAULT_ENDPOINT,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    demo_config,
    prepare_broward_demo,
    run_broward_demo,
)
from bd_packet_builder.discovery import discover_requirements
from bd_packet_builder.draft import DraftError, run_draft
from bd_packet_builder.evidence import (
    EvidenceError,
    ExtractionLimits,
    extract_evidence,
    publish_evidence,
)
from bd_packet_builder.fact_sheet import FactSheetError, run_fact_sheet_check
from bd_packet_builder.foundry import FoundryConfig, FoundryError, run_foundry_smoke
from bd_packet_builder.history import HistoryError, run_history_check
from bd_packet_builder.inventory import InventoryError, build_inventory, publish_inventory
from bd_packet_builder.live import LIVE_MAX_MODEL_CALLS, resume_agent_command, run_agent_command
from bd_packet_builder.local_inputs import LocalInputError
from bd_packet_builder.ocr import OcrError, OcrLimits, run_ocr
from bd_packet_builder.pdf_demo import PdfDemoError, create_demo, inspect_pdf
from bd_packet_builder.poc import initialize_poc, run_poc
from bd_packet_builder.retrieval import RetrievalError, run_targeted_retrieval
from bd_packet_builder.review import ReviewError, run_review
from bd_packet_builder.run import RunInputError
from bd_packet_builder.visual import map_visual


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local PDF tools; model smoke test is opt-in")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Report PDF page/text-field counts, not values")
    inspect.add_argument("source", type=Path)
    demo = commands.add_parser(
        "demo", help="Write a fixed synthetic firm name; never submit output"
    )
    demo.add_argument("--root", type=Path, required=True, help="Explicit repository/data root")
    demo.add_argument("--source", type=Path, required=True, help="Root-relative blank PDF path")
    inventory = commands.add_parser(
        "inventory", help="Snapshot local supporting-document metadata; no extracted text"
    )
    inventory.add_argument("--root", type=Path, required=True, help="Explicit repository/data root")
    evidence = commands.add_parser(
        "evidence", help="Extract confidential native PDF text locally; no model calls"
    )
    evidence.add_argument("--root", type=Path, required=True, help="Explicit repository/data root")
    defaults = ExtractionLimits()
    evidence.add_argument(
        "--max-pages-per-document",
        type=int,
        default=defaults.max_pages_per_document,
        help="Positive PDF page limit (default: %(default)s)",
    )
    evidence.add_argument(
        "--max-chars-per-page",
        type=int,
        default=defaults.max_chars_per_page,
        help="Positive native character limit per page (default: %(default)s)",
    )
    evidence.add_argument(
        "--max-chars-per-run",
        type=int,
        default=defaults.max_chars_per_run,
        help="Positive extracted character limit per run (default: %(default)s)",
    )
    ocr = commands.add_parser("ocr", help="Opt-in single supporting PDF page OCR; unverified")
    ocr.add_argument("--root", type=Path, required=True)
    ocr.add_argument("--source", type=Path, required=True, help="Root-relative supporting PDF")
    ocr.add_argument("--page", type=int, required=True, help="One-based PDF page")
    ocr_defaults = OcrLimits()
    ocr.add_argument("--timeout-seconds", type=int, default=ocr_defaults.timeout_seconds)
    ocr.add_argument("--max-pixels", type=int, default=ocr_defaults.max_pixels)
    ocr.add_argument("--max-output-bytes", type=int, default=ocr_defaults.max_output_bytes)
    review = commands.add_parser(
        "review", help="Check manual requirements/proposals; internal report only, no filling"
    )
    review.add_argument("--root", type=Path, required=True)
    review.add_argument(
        "--source", type=Path, required=True, help="Root-relative blank application PDF"
    )
    review.add_argument("--requirements", type=Path, required=True, help="JSON under outputs/")
    review.add_argument("--proposals", type=Path, required=True, help="JSON under outputs/")
    fact_sheet = commands.add_parser(
        "fact-sheet-check", help="Check a local draft; never approve, release or fill facts"
    )
    fact_sheet.add_argument("--root", type=Path, required=True)
    fact_sheet.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Draft .xlsx under outputs/ (internal .json supported)",
    )
    fact_sheet.add_argument("--as-of", required=True, help="Explicit validation date YYYY-MM-DD")
    setup = commands.add_parser(
        "poc-init", help="Create the one maintained workbook once; no facts"
    )
    setup.add_argument("--root", type=Path, required=True)
    poc = commands.add_parser(
        "poc", help="Read maintained workbook; validate intake, no packet yet"
    )
    poc.add_argument("--root", type=Path, required=True)
    poc.add_argument("--as-of", help="Evaluation date YYYY-MM-DD (default: local date today)")
    history = commands.add_parser(
        "history-check", help="Check manually supplied historical pairs; no retrieval or filling"
    )
    history.add_argument("--root", type=Path, required=True)
    history.add_argument(
        "--manifest", type=Path, required=True, help="Partition JSON under outputs/"
    )
    history.add_argument("--comparisons", type=Path, required=True, help="Pair JSON under outputs/")
    smoke = commands.add_parser("foundry-smoke", help="One paid synthetic-only model request")
    smoke.add_argument("--root", type=Path, required=True)
    smoke.add_argument("--endpoint", required=True, help="HTTPS Azure OpenAI /openai/v1 endpoint")
    smoke.add_argument("--deployment", required=True)
    smoke.add_argument(
        "--allow-paid", action="store_true", help="Explicitly permit one paid request"
    )
    discovery = commands.add_parser(
        "discover", help="Paid native-text discovery from one explicitly approved blank PDF"
    )
    discovery.add_argument("--root", type=Path, required=True)
    discovery.add_argument("--source", type=Path, required=True, help="Root-relative blank PDF")
    discovery.add_argument("--endpoint", required=True)
    discovery.add_argument("--deployment", required=True)
    discovery.add_argument(
        "--checklist", type=Path, help="Independent local evaluation JSON under outputs/"
    )
    discovery.add_argument("--allow-paid", action="store_true")
    visual = commands.add_parser(
        "map-visual", help="Paid visual mapping of approved blank pages; no answers"
    )
    visual.add_argument("--root", type=Path, required=True)
    visual.add_argument("--source", type=Path, required=True)
    visual.add_argument("--endpoint", required=True)
    visual.add_argument("--deployment", required=True)
    visual.add_argument(
        "--pages", type=int, nargs="+", help="1-5 explicit page numbers; default all up to 5"
    )
    visual.add_argument(
        "--reference", type=Path, help="Withheld local reference JSON under outputs/"
    )
    visual.add_argument("--allow-paid", action="store_true")
    retrieval = commands.add_parser(
        "retrieve", help="Requirement-driven evidence reading; no packet"
    )
    retrieval.add_argument("--root", type=Path, required=True)
    retrieval.add_argument(
        "--requirements", type=Path, required=True, help="Requirements JSON under outputs/"
    )
    retrieval.add_argument(
        "--catalog", type=Path, help="Optional source-family catalog JSON under outputs/"
    )
    retrieval.add_argument(
        "--plan",
        type=Path,
        help="Offline routing JSON under outputs/; otherwise paid model routing",
    )
    retrieval.add_argument(
        "--cache",
        type=Path,
        help="Prior retrieval report under outputs/; unapproved native proposals only",
    )
    retrieval.add_argument("--endpoint")
    retrieval.add_argument("--deployment")
    retrieval.add_argument("--allow-paid", action="store_true")
    retrieval.add_argument(
        "--allow-ocr", action="store_true", help="Explicitly allow local Tesseract on sparse pages"
    )
    draft = commands.add_parser("draft", help="Write an explicitly reviewed incomplete local draft")
    draft.add_argument("--root", type=Path, required=True)
    draft.add_argument(
        "--request", type=Path, required=True, help="Draft request JSON under outputs/"
    )
    draft.add_argument(
        "--review", type=Path, required=True, help="Snapshot-bound review JSON under outputs/"
    )
    agent = commands.add_parser(
        "agent-run",
        help="Paid live agent run on one blank using explicitly approved evidence",
    )
    agent.add_argument("--root", type=Path, required=True)
    agent.add_argument("--blank", type=Path, required=True, help="Root-relative blank PDF")
    agent.add_argument("--endpoint", required=True)
    agent.add_argument("--deployment", required=True)
    agent.add_argument("--request-timeout-seconds", type=int, default=60)
    agent.add_argument("--requester-id", default="developer-workstation")
    agent.add_argument("--evidence-set-id", default="local-evidence-set")
    agent.add_argument("--as-of", help="Reporting date YYYY-MM-DD")
    agent.add_argument("--issuer", help="Target issuer for historical-context checks")
    agent.add_argument(
        "--historical-policy",
        choices=("conservative", "answer_first_review"),
        default="answer_first_review",
        help="Prefill checked historical candidates with reviewer concerns; never signing",
    )
    agent.add_argument(
        "--historical-manifest", type=Path, help="Approved partition JSON under outputs/"
    )
    agent.add_argument(
        "--requirement-assessments",
        type=Path,
        help="Trusted form/hash-bound reviewer assessments JSON under outputs/; not model output",
    )
    agent.add_argument(
        "--runs-dir", type=Path, help="Folder for run output; default <root>/outputs/agent-runs"
    )
    agent.add_argument("--allow-paid", action="store_true")
    resume = commands.add_parser(
        "agent-resume", help="Explicit paid recovery of unfinished saved answer groups"
    )
    resume.add_argument("--root", type=Path, required=True)
    resume.add_argument("--runs-dir", type=Path, required=True)
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--endpoint", required=True)
    resume.add_argument("--deployment", required=True)
    resume.add_argument("--allow-paid", action="store_true")
    broward_demo = commands.add_parser(
        "broward-demo",
        help="Run the fresh paid Broward demo with explicit inputs and live safe progress",
    )
    broward_demo.add_argument("--root", type=Path, required=True)
    broward_demo.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    broward_demo.add_argument("--deployment", default=DEFAULT_DEPLOYMENT)
    broward_demo.add_argument(
        "--request-timeout-seconds", type=int, default=DEFAULT_REQUEST_TIMEOUT_SECONDS
    )
    broward_demo.add_argument("--runs-dir", type=Path)
    broward_demo.add_argument("--requirement-assessments", type=Path)
    broward_demo.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "agent-resume":
            manifest = resume_agent_command(
                args.root,
                args.runs_dir,
                args.run_id,
                FoundryConfig(endpoint=args.endpoint, deployment=args.deployment),
                allow_paid=args.allow_paid,
            )
            print(f"Run {manifest.run_id}: status={manifest.status} outcome={manifest.outcome}")
            return 1 if manifest.status == "failed" else 0
        if args.command == "agent-run":
            as_of = date.fromisoformat(args.as_of) if args.as_of else None
            try:
                agent_config = FoundryConfig(
                    endpoint=args.endpoint,
                    deployment=args.deployment,
                    timeout_seconds=args.request_timeout_seconds,
                )
            except ValidationError:
                raise FoundryError(
                    "Invalid Foundry endpoint, deployment or request timeout"
                ) from None
            print(
                "Starting fresh paid model execution. Page images and selected evidence may be "
                "sent to Foundry; progress output excludes document text.",
                flush=True,
            )
            manifest = run_agent_command(
                args.root,
                args.blank,
                agent_config,
                requester_id=args.requester_id,
                evidence_set_id=args.evidence_set_id,
                as_of=as_of,
                allow_paid=args.allow_paid,
                runs_dir=args.runs_dir,
                historical_manifest=args.historical_manifest,
                issuer=args.issuer,
                historical_policy=args.historical_policy,
                requirement_assessments=args.requirement_assessments,
                progress_sink=lambda event: print(f"[progress] {event}", flush=True),
            )
            runs_dir = args.runs_dir or args.root / "outputs" / "agent-runs"
            print(
                f"Run {manifest.run_id}: status={manifest.status} outcome={manifest.outcome}; "
                f"{len(manifest.exceptions())} review exceptions. Not for submission. "
                f"Readable outputs: {runs_dir / manifest.run_id / 'readable'}"
            )
            return 0 if manifest.status != "failed" else 1
        if args.command == "broward-demo":
            if not args.allow_paid:
                raise FoundryError("The Broward demo requires explicit --allow-paid authorization")
            broward_config = demo_config(
                args.endpoint, args.deployment, args.request_timeout_seconds
            )
            plan = prepare_broward_demo(args.root)
            print("BROWARD DEMO PREFLIGHT (metadata only; no document text shown)")
            print(f"Blank: {plan.blank} sha256={plan.blank_sha256}")
            print(
                f"Approved historical reference: {plan.historical_source.path} "
                f"sha256={plan.historical_source.sha256}"
            )
            print(
                "Historical policy: answer_first_review; no other completed applications included"
            )
            print(f"Available supporting documents: {len(plan.available_sources)}")
            for source in plan.available_sources:
                print(f"  {source.family}: {source.path} sha256={source.sha256}")
            print(
                f"Model: {args.deployment} at {args.endpoint}\n"
                f"HTTP request timeout: {broward_config.timeout_seconds} seconds; "
                "automatic retries: 0.\n"
                f"This fresh run may make up to {LIVE_MAX_MODEL_CALLS} paid model calls, "
                "run for up to 60 minutes, "
                "and send selected document text and page images to Foundry. No total dollar "
                "spending cap is configured. It creates an incomplete, unsigned draft only."
            )
            try:
                confirmation = input("Type RUN to start the paid model-driven demo: ")
            except EOFError:
                confirmation = ""
            if confirmation != "RUN":
                print("Demo cancelled; no model calls were made.")
                return 1
            manifest = run_broward_demo(
                plan,
                broward_config,
                progress_sink=lambda event: print(f"[progress] {event}", flush=True),
                runs_dir=args.runs_dir,
                requirement_assessments=args.requirement_assessments,
            )
            print(
                f"Fresh run {manifest.run_id}: status={manifest.status}; "
                f"outcome={manifest.outcome}; not for submission."
            )
            return 0 if manifest.status != "failed" else 1
        if args.command == "draft":
            result = run_draft(args.root, args.request, args.review)
            print(f"Incomplete draft; NOT FOR SUBMISSION: {result / 'draft-packet.pdf'}")
            return 0
        if args.command == "retrieve":
            config = None
            if args.endpoint or args.deployment:
                if not args.endpoint or not args.deployment:
                    raise RetrievalError("Specify both endpoint and deployment")
                config = FoundryConfig(endpoint=args.endpoint, deployment=args.deployment)
            result = run_targeted_retrieval(
                args.root,
                args.requirements,
                catalog_path=args.catalog,
                plan_path=args.plan,
                config=config,
                allow_paid=args.allow_paid,
                allow_ocr=args.allow_ocr,
                cache_path=args.cache,
            )
            print(
                f"Targeted evidence is unapproved and needs review; no packet. "
                f"Report: {result / 'retrieval.json'}"
            )
            return 0
        if args.command in ("foundry-smoke", "discover", "map-visual"):
            try:
                config = FoundryConfig(endpoint=args.endpoint, deployment=args.deployment)
            except ValidationError:
                raise FoundryError(
                    "Invalid Azure v1 endpoint or deployment configuration"
                ) from None
            if args.command == "map-visual":
                result = map_visual(
                    args.root,
                    args.source,
                    config,
                    allow_paid=args.allow_paid,
                    pages=tuple(args.pages) if args.pages else None,
                    reference_path=args.reference,
                )
                data = json.loads((result / "visual-map.json").read_text(encoding="utf-8"))
                print(
                    "Unapproved visual map; no answers or packet. "
                    f"Report: {result / 'visual-map.json'}"
                )
                if data["evaluation"] is None:
                    print("No independent reference evaluation: accuracy not established.")
                    return 1
                print(f"Reference evaluation passed: {data['evaluation']['passed']}")
                return 0 if data["evaluation"]["passed"] else 1
            if args.command == "discover":
                result = discover_requirements(
                    args.root,
                    args.source,
                    config,
                    allow_paid=args.allow_paid,
                    checklist_path=args.checklist,
                )
                data = json.loads((result / "discovery.json").read_text(encoding="utf-8"))
                print(
                    f"Requirement discovery needs review; {len(data['findings'])} findings. "
                    f"No answers or packet. Report: {result / 'discovery.json'}"
                )
                complete_evaluation = data["evaluation"] is None or (
                    data["evaluation"]["covered"] == data["evaluation"]["total"]
                )
                return (
                    0
                    if (
                        not data["page_issues"]
                        and set(data["counts"]) == {"anchored"}
                        and complete_evaluation
                    )
                    else 1
                )
            result = run_foundry_smoke(args.root, config, allow_paid=args.allow_paid)
            data = json.loads((result / "foundry-smoke.json").read_text(encoding="utf-8"))
            print(
                f"Synthetic checks: {data['checks_passed']}/{data['checks_total']}. "
                f"Not a packet or general grounding evaluation: {result / 'foundry-smoke.json'}"
            )
            return 0 if data["status"] == "synthetic_smoke_passed_not_packet" else 1
        elif args.command == "history-check":
            result = run_history_check(args.root, args.manifest, args.comparisons)
            print(
                "Historical review only, no packet or replacements: "
                f"{result / 'history-check.json'}"
            )
        elif args.command == "poc-init":
            path = initialize_poc(args.root)
            print(f"Setup complete. The only workbook to maintain: {path}")
        elif args.command == "poc":
            as_of_text = args.as_of or date.today().isoformat()
            try:
                as_of = date.fromisoformat(as_of_text)
            except ValueError:
                raise FactSheetError("Validation as-of date must be YYYY-MM-DD") from None
            if as_of.isoformat() != as_of_text:
                raise FactSheetError("Validation as-of date must be YYYY-MM-DD")
            result = run_poc(args.root, as_of=as_of)
            print(
                f"PoC intake checked. No packet or answers generated. "
                f"Validation results: {result / 'validation.html'}. "
                "Continue editing the same workbook under outputs/maintained/."
            )
        elif args.command == "inspect":
            print(json.dumps(asdict(inspect_pdf(args.source))))
        elif args.command == "inventory":
            snapshot = build_inventory(args.root)
            result = publish_inventory(args.root, snapshot)
            flagged = sum(bool(source.flags) for source in snapshot.sources)
            print(
                f"Metadata inventory only: {len(snapshot.sources)} sources, "
                f"{flagged} flagged sources, {len(snapshot.issues)} excluded-input issues. "
                f"Review local manifest: {result / 'inventory.json'}"
            )
        elif args.command == "evidence":
            limits = ExtractionLimits(
                args.max_pages_per_document, args.max_chars_per_page, args.max_chars_per_run
            )
            snapshot = build_inventory(args.root)
            bundle = extract_evidence(args.root, snapshot, limits=limits)
            result = publish_evidence(args.root, snapshot, bundle)
            flagged = sum(
                bool(d.flags) or d.period_check.status != "filename_period_corroborated"
                for d in bundle.documents
            )
            print(
                f"Native-text evidence only, not approved answers: "
                f"{len(bundle.documents)} documents, "
                f"{flagged} needing review. Review confidential local bundle: "
                f"{result / 'evidence.json'}"
            )
        elif args.command == "ocr":
            result = run_ocr(
                args.root,
                args.source,
                args.page,
                limits=OcrLimits(args.timeout_seconds, args.max_pixels, args.max_output_bytes),
            )
            print(f"Unverified local OCR only, not approved answers: {result / 'ocr.json'}")
        elif args.command == "review":
            result = run_review(args.root, args.source, args.requirements, args.proposals)
            data = json.loads((result / "review.json").read_text(encoding="utf-8"))
            print(
                f"Internal review only, no packet: {len(data['items'])} requirements. "
                f"Review report: {result / 'review.json'}"
            )
        elif args.command == "fact-sheet-check":
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError:
                raise FactSheetError("Validation as-of date must be YYYY-MM-DD") from None
            if as_of.isoformat() != args.as_of:
                raise FactSheetError("Validation as-of date must be YYYY-MM-DD")
            result = run_fact_sheet_check(args.root, args.source, as_of=as_of)
            data = json.loads((result / "fact-sheet-check.json").read_text(encoding="utf-8"))
            print(
                f"Draft validation only, not approved: {len(data['items'])} facts, "
                f"{data['facts_with_exceptions']} with exceptions. "
                f"Excel fact sheet: {result / 'fact-sheet.xlsx'}. "
                f"Internal report: {result / 'fact-sheet-check.json'}"
            )
        else:
            result = create_demo(args.root, args.source)
            print(f"Synthetic demo only, not a completed application: {result}")
    except (
        PdfDemoError,
        InventoryError,
        EvidenceError,
        OcrError,
        ReviewError,
        FactSheetError,
        HistoryError,
        FoundryError,
        LocalInputError,
        RetrievalError,
        DraftError,
    ) as error:
        label = (
            args.command.capitalize()
            if args.command
            in (
                "inventory",
                "evidence",
                "ocr",
                "review",
                "fact-sheet-check",
                "poc",
                "poc-init",
                "history-check",
                "foundry-smoke",
                "discover",
                "map-visual",
                "retrieve",
                "draft",
                "agent-run",
                "broward-demo",
            )
            else "PDF"
        )
        print(f"{label} command rejected: {error}", file=sys.stderr)
        return 1
    except ValidationError:
        print(
            "Invalid input: check strict requirements, catalog, routing or draft/review JSON.",
            file=sys.stderr,
        )
        return 1
    except OSError:
        label = (
            args.command.capitalize()
            if args.command
            in (
                "inventory",
                "evidence",
                "ocr",
                "review",
                "fact-sheet-check",
                "poc",
                "poc-init",
                "history-check",
                "foundry-smoke",
                "discover",
                "map-visual",
                "retrieve",
                "draft",
                "agent-run",
                "broward-demo",
            )
            else "PDF"
        )
        print(
            f"{label} I/O failed. Check the input exists and output folder is writable.",
            file=sys.stderr,
        )
        return 1
    except RunInputError as error:
        print(f"Run input rejected: {error}", file=sys.stderr)
        if args.command == "agent-resume":
            print(
                "Recovery did not complete. For changed evidence, restore the original source "
                "version or start a new run; do not replace the saved snapshot.",
                file=sys.stderr,
            )
        return 1
    except (ValueError, PdfReadError, PdfiumError) as error:
        print(
            f"PDF processing failed ({type(error).__name__}). "
            "Check that the input is a valid supported PDF; no successful run reported.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
