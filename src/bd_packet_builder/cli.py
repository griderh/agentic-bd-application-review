"""Local-only command line entry points for the foundation increment."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from pypdf.errors import PdfReadError
from pypdfium2 import PdfiumError

from bd_packet_builder.evidence import (
    EvidenceError,
    ExtractionLimits,
    extract_evidence,
    publish_evidence,
)
from bd_packet_builder.inventory import InventoryError, build_inventory, publish_inventory
from bd_packet_builder.ocr import OcrError, OcrLimits, run_ocr
from bd_packet_builder.pdf_demo import PdfDemoError, create_demo, inspect_pdf


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local PDF feasibility tools; no model calls")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
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
        else:
            result = create_demo(args.root, args.source)
            print(f"Synthetic demo only, not a completed application: {result}")
    except (PdfDemoError, InventoryError, EvidenceError, OcrError) as error:
        label = (
            args.command.capitalize() if args.command in ("inventory", "evidence", "ocr") else "PDF"
        )
        print(f"{label} command rejected: {error}", file=sys.stderr)
        return 1
    except OSError:
        label = (
            args.command.capitalize() if args.command in ("inventory", "evidence", "ocr") else "PDF"
        )
        print(
            f"{label} I/O failed. Check the input exists and output folder is writable.",
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
