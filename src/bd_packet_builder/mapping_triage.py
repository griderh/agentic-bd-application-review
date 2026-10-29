"""Opt-in real-form mapping diagnostics; no answers or historical packet inputs."""

import argparse
import sys
from pathlib import Path

from bd_packet_builder.agent import PageMapError
from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.live import FoundryPageMapper
from bd_packet_builder.local_inputs import LocalInputError, read_local_input


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--blank", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--page", type=int, action="append")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if (
            args.output.is_absolute()
            or ".." in args.output.parts
            or not args.output.is_relative_to("outputs")
        ):
            raise FoundryError("Mapping diagnostics must be beneath the configured root's outputs")
        blank = read_local_input(root, args.blank, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
        mapper = FoundryPageMapper(
            FoundryConfig(
                endpoint=args.endpoint,
                deployment=args.deployment,
                timeout_seconds=args.timeout_seconds,
            ),
            allow_paid=args.allow_paid,
            diagnostics_dir=root / args.output,
            selected_pages=tuple(args.page) if args.page else None,
        )
        pages = mapper.map_pages(blank)
    except (FoundryError, PageMapError, LocalInputError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    print(
        f"Schema-valid maps: {len(pages)} pages, {sum(len(p.items) for p in pages.values())} items."
    )
    print("Schema validity is not rendered-placement verification or answer approval.")


if __name__ == "__main__":
    main()
