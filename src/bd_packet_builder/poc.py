"""Single maintained workbook intake for the local PoC; no model or packet generation."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from bd_packet_builder.fact_sheet import FactSheetError, _run_fact_sheet_check
from bd_packet_builder.fact_sheet_excel import export_workbook
from bd_packet_builder.inventory import Inventory

MAINTAINED_WORKBOOK = Path("outputs/maintained/fact-sheet.xlsx")


def initialize_poc(root: Path) -> Path:
    """One-time blank template setup; refuse to overwrite any existing workbook."""
    root = root.resolve(strict=True)
    target = root / MAINTAINED_WORKBOOK
    if target.resolve() != target:
        raise FactSheetError("Maintained workbook must not resolve through a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = export_workbook(None, Inventory(datetime.now(UTC), (), ()))
    with TemporaryDirectory(prefix=".setup-", dir=target.parent) as temporary:
        staged = Path(temporary) / "template.xlsx"
        staged.write_bytes(data)
        try:
            os.link(staged, target)
        except FileExistsError:
            raise FactSheetError(
                "Maintained workbook already exists; edit it instead of running setup again"
            ) from None
    return target


def run_poc(root: Path, *, as_of: date) -> Path:
    """Always validate the designated workbook; archive exact input, never a new master."""
    root = root.resolve(strict=True)
    if not (root / MAINTAINED_WORKBOOK).exists():
        raise FactSheetError(
            "Maintained workbook is missing; run poc-init once, then complete and save Excel"
        )
    return _run_fact_sheet_check(root, MAINTAINED_WORKBOOK, as_of=as_of, archive_only=True)
