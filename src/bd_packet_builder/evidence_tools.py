"""Narrow, bounded evidence tools for the agent; they read only the run's evidence snapshot.

Every result is data for the model, not instructions: document text is labeled untrusted, tools
accept only source IDs from the verified inventory, and no tool accepts a path, URL, recipient or
command. OCR text is not citable until independently image-cross-checked for scalar draft
answers. Budgets are enforced in code and are per-tool-instance, so a hosted runtime that
restarts mid-run must reconstruct the used amounts.
"""

from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

import pypdfium2 as pdfium
from pydantic import Field

from bd_packet_builder.contracts import Contract, Identifier, Nonblank, OcrCitation, Sha256
from bd_packet_builder.evidence import EvidenceError, TextCitation, resolve_quote
from bd_packet_builder.historical_context import HistoricalContextEvidence, HistoricalPageResult
from bd_packet_builder.history import ArchiveManifest, historical_inventory
from bd_packet_builder.inventory import (
    Inventory,
    InventoryError,
    SourceRecord,
    read_source_bytes,
    select_evidence,
)
from bd_packet_builder.ocr import OcrError, run_ocr
from bd_packet_builder.retrieval import default_catalog, read_page
from bd_packet_builder.run import EvidenceSnapshot
from bd_packet_builder.scan import ScanEvidence, ScanVerificationError

Trust = Literal["untrusted_document_text"]
_UNRELIABLE_NATIVE = frozenset(
    {"sparse_native_text_ocr_not_enabled", "image_dominant_page_ocr_not_enabled"}
)
_MAX_TERMS = 10
_MAX_TERM_CHARS = 100
_MAX_SEARCH_PAGE_CHARS = 100_000
_SNIPPET_BEFORE = 60
_SNIPPET_AFTER = 100


class EvidenceToolError(ValueError):
    """Safe tool failure without document text or absolute paths."""


class ToolInputError(EvidenceToolError):
    """The model asked for something outside the verified evidence set; recoverable."""


class ToolLimitError(EvidenceToolError):
    """A configured per-run budget was reached; the agent must stop using that tool."""


class EvidenceLimits(Contract):
    max_calls: Annotated[int, Field(ge=1, le=10_000)] = 60
    max_pages_read: Annotated[int, Field(ge=1, le=1_000)] = 25
    max_search_pages: Annotated[int, Field(ge=1, le=10_000)] = 300
    max_search_hits: Annotated[int, Field(ge=1, le=100)] = 20
    max_chars_returned: Annotated[int, Field(ge=1, le=5_000_000)] = 200_000
    max_ocr_pages: Annotated[int, Field(ge=0, le=100)] = 5
    max_attachments: Annotated[int, Field(ge=1, le=20)] = 20


class SourceSummary(Contract):
    source_id: Sha256
    path: Nonblank
    family: Identifier
    format: Identifier
    page_count: int | None
    period: str | None
    period_basis: str | None
    flags: tuple[str, ...]
    historical_issuer: str | None = None
    completed_on: str | None = None


class SelectionSummary(Contract):
    family: Identifier
    source_id: Sha256 | None
    period: str | None
    requested_period: str | None
    flags: tuple[str, ...]


class SourceListing(Contract):
    sources: tuple[SourceSummary, ...]
    selection: SelectionSummary | None


class SearchHit(Contract):
    source_id: Sha256
    page: int
    terms: tuple[str, ...]
    snippet: str


class TextlessPage(Contract):
    source_id: Sha256
    page: int


class SearchResult(Contract):
    hits: tuple[SearchHit, ...]
    textless_pages: tuple[TextlessPage, ...]
    pages_scanned: int
    truncated: bool
    content_trust: Trust = "untrusted_document_text"


class PageRead(Contract):
    source_id: Sha256
    page: int
    mode: Literal["native", "ocr", "unreadable"]
    text: str
    issues: tuple[str, ...]
    citable: bool
    content_trust: Trust = "untrusted_document_text"


class PageIndexEntry(Contract):
    page: int
    native_character_count: int
    excerpt: str
    issues: tuple[str, ...]


class SourceIndex(Contract):
    version: Literal["source-page-index-v1"] = "source-page-index-v1"
    source_id: Sha256
    source_sha256: Sha256
    historical_issuer: str | None
    pages: tuple[PageIndexEntry, ...]
    next_page: int | None
    content_trust: Trust = "untrusted_document_text"
    scope: Literal["navigation_only_not_answer_evidence"] = "navigation_only_not_answer_evidence"


class QuoteLocation(Contract):
    source_id: Sha256
    page: int
    start: int
    end: int
    quote: str
    occurrences: int


def _normalized_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(" ".join(t.split()).casefold() for t in terms))
    if (
        not cleaned
        or len(terms) > _MAX_TERMS
        or any(not t or len(t) > _MAX_TERM_CHARS for t in cleaned)
    ):
        raise ToolInputError("Search needs 1-10 nonblank terms of at most 100 characters")
    return cleaned


def _snippet(text: str, term: str, index: int) -> str:
    window = text[max(0, index - _SNIPPET_BEFORE) : index + len(term) + _SNIPPET_AFTER]
    return " ".join(window.split())


class EvidenceTools:
    def __init__(
        self,
        root: Path,
        inventory: Inventory,
        snapshot: EvidenceSnapshot,
        *,
        limits: EvidenceLimits | None = None,
        allow_ocr: bool = True,
        scan_evidence: ScanEvidence | None = None,
        historical_archive: ArchiveManifest | None = None,
        allow_historical_disagreements: bool = False,
    ) -> None:
        history = historical_inventory(root, historical_archive) if historical_archive else None
        allowed_history = {s.source_id for s in history.sources} if history else set()
        if any(
            s.family == "historical_reference" and s.source_id not in allowed_history
            for s in inventory.sources
        ):
            raise EvidenceToolError("Historical source is not approved by the partition manifest")
        items = {i.path: i for i in snapshot.items}
        for source in inventory.sources:
            item = items.get(source.path)
            if item is None or item.sha256 != source.sha256 or item.size_bytes != source.size_bytes:
                raise EvidenceToolError("Inventory source is not in this run's evidence snapshot")
        self._root = root.resolve(strict=True)
        folders = {f.folder for f in default_catalog().families} | {"historical_reference"}
        # Only designated families are visible; the writer rejects anything else later.
        self._inventory = Inventory(
            inventory.created_at,
            tuple(s for s in inventory.sources if s.family in folders),
            inventory.issues,
        )
        self._limits = limits or EvidenceLimits()
        self._allow_ocr = allow_ocr
        self._folders = folders
        self._historical = (
            {
                entry.path: entry
                for entry in historical_archive.entries
                if entry.partition == "reference"
            }
            if historical_archive
            else {}
        )
        self._calls = 0
        self._pages: set[tuple[str, int]] = set()
        self._chars = 0
        self._ocr = 0
        self._attachments: list[str] = []
        self._scan_evidence = scan_evidence
        self.historical_context = (
            HistoricalContextEvidence(
                scan_evidence, allow_disagreements=allow_historical_disagreements
            )
            if scan_evidence
            else None
        )
        self._page_cache: dict[tuple[str, int, bool], tuple[PageRead, bool]] = {}
        self._ocr_artifacts: dict[tuple[str, int], str] = {}

    @property
    def attachments(self) -> tuple[str, ...]:
        return tuple(self._attachments)

    @property
    def reading_usage(self) -> dict[str, int]:
        return {
            "distinct_pages": len(self._pages),
            "ocr_pages": self._ocr,
            "independent_image_pages": self._scan_evidence.pages_attempted
            if self._scan_evidence is not None
            else 0,
            "evidence_calls": self._calls,
            "returned_characters": self._chars,
        }

    def _tick(self) -> None:
        if self._calls >= self._limits.max_calls:
            raise ToolLimitError("Evidence tool call limit reached")
        self._calls += 1

    def _spend_chars(self, count: int) -> None:
        if self._chars + count > self._limits.max_chars_returned:
            raise ToolLimitError("Evidence returned-character limit reached")
        self._chars += count

    def _source(self, source_id: str) -> SourceRecord:
        source = next((s for s in self._inventory.sources if s.source_id == source_id), None)
        if source is None:
            raise ToolInputError("Unknown source identity")
        return source

    def _pdf(self, source_id: str, page: int | None = None) -> SourceRecord:
        source = self._source(source_id)
        if source.format != "pdf" or source.page_count is None:
            raise ToolInputError("Only readable PDF sources are available")
        if page is not None and (type(page) is not int or not 1 <= page <= source.page_count):
            raise ToolInputError("Page is outside the source")
        return source

    def _family(self, family: str) -> str:
        if family not in self._folders:
            raise ToolInputError("Unknown source family")
        return family

    def list_sources(
        self, family: str | None = None, requested_period: str | None = None
    ) -> SourceListing:
        """Catalog metadata only; never document text."""
        self._tick()
        selected = [
            s for s in self._inventory.sources if family is None or s.family == self._family(family)
        ]
        if family is not None:
            self._family(family)
        selection: SelectionSummary | None = None
        if family is not None and family in ("Focus_Reports", "Audited_Financials"):
            try:
                chosen = select_evidence(self._inventory, family, requested_period=requested_period)
            except InventoryError:
                raise ToolInputError("Requested period does not match the family cadence") from None
            selection = SelectionSummary(
                family=family,
                source_id=chosen.source.source_id if chosen.source else None,
                period=chosen.period,
                requested_period=chosen.requested_period,
                flags=chosen.flags,
            )
        elif requested_period is not None:
            raise ToolInputError("Period selection applies only to dated report families")
        summaries = tuple(
            SourceSummary(
                source_id=s.source_id,
                path=s.path,
                family=s.family,
                format=s.format,
                page_count=s.page_count,
                period=s.period,
                period_basis=s.period_basis,
                flags=s.flags,
                historical_issuer=self._historical[s.path].issuer
                if s.path in self._historical
                else None,
                completed_on=(
                    str(self._historical[s.path].completed_on)
                    if s.path in self._historical
                    and self._historical[s.path].completed_on is not None
                    else None
                ),
            )
            for s in selected
        )
        return SourceListing(sources=summaries, selection=selection)

    def index_source(
        self, source_id: str, *, start_page: int = 1, page_limit: int = 20
    ) -> SourceIndex:
        """Bounded page previews; missing native text never establishes missing evidence."""
        self._tick()
        source = self._pdf(source_id, start_page)
        if type(page_limit) is not int or not 1 <= page_limit <= 50:
            raise ToolInputError("Index page limit must be an integer from one to fifty")
        count = min(page_limit, self._limits.max_search_pages)
        data = read_source_bytes(self._root, self._inventory, source_id)
        entries: list[PageIndexEntry] = []
        try:
            with pdfium.PdfDocument(data) as document:
                stop = min(start_page - 1 + count, len(document))
                for index in range(start_page - 1, stop):
                    with (
                        closing(document[index]) as page,
                        closing(page.get_textpage()) as text,
                    ):
                        chars = text.count_chars()
                        if chars > _MAX_SEARCH_PAGE_CHARS:
                            raise EvidenceToolError("Page text exceeds the index limit")
                        native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
                        has_images = any(obj.type == 3 for obj in page.get_objects())
                    excerpt = native.strip()[:600]
                    self._spend_chars(len(excerpt))
                    issues = (
                        ("no_native_text_requires_image_reading",)
                        if not native.strip()
                        else ("page_images_may_contain_unindexed_text",)
                        if has_images
                        else ()
                    )
                    entries.append(
                        PageIndexEntry(
                            page=index + 1,
                            native_character_count=chars,
                            excerpt=excerpt,
                            issues=issues,
                        )
                    )
                next_page = stop + 1 if stop < len(document) else None
        except (pdfium.PdfiumError, UnicodeError):
            raise EvidenceToolError("A source could not be indexed") from None
        read_source_bytes(self._root, self._inventory, source_id)
        entry = self._historical.get(source.path)
        return SourceIndex(
            source_id=source_id,
            source_sha256=source.sha256,
            historical_issuer=entry.issuer if entry else None,
            pages=tuple(entries),
            next_page=next_page,
        )

    def search_pages(self, terms: tuple[str, ...], *, family: str) -> SearchResult:
        """Case-insensitive native-text search within one catalog family."""
        self._tick()
        wanted = _normalized_terms(terms)
        folder = self._family(family)
        hits: list[SearchHit] = []
        textless: list[TextlessPage] = []
        scanned = 0
        truncated = False
        for source in self._inventory.sources:
            if source.family != folder or source.format != "pdf" or source.page_count is None:
                continue
            data = read_source_bytes(self._root, self._inventory, source.source_id)
            try:
                with pdfium.PdfDocument(data) as document:
                    for index in range(len(document)):
                        if scanned >= self._limits.max_search_pages:
                            truncated = True
                            break
                        scanned += 1
                        with (
                            closing(document[index]) as page,
                            closing(page.get_textpage()) as text,
                        ):
                            if text.count_chars() > _MAX_SEARCH_PAGE_CHARS:
                                raise EvidenceToolError("Page text exceeds the search limit")
                            native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
                        if not native.strip():
                            if len(textless) < self._limits.max_search_hits:
                                textless.append(
                                    TextlessPage(source_id=source.source_id, page=index + 1)
                                )
                            else:
                                truncated = True
                            continue
                        lowered = native.casefold()
                        found = tuple(t for t in wanted if t in lowered)
                        if not found:
                            continue
                        if len(hits) >= self._limits.max_search_hits:
                            truncated = True
                            continue
                        snippet = _snippet(native, found[0], lowered.index(found[0]))
                        self._spend_chars(len(snippet))
                        hits.append(
                            SearchHit(
                                source_id=source.source_id,
                                page=index + 1,
                                terms=found,
                                snippet=snippet,
                            )
                        )
            except (pdfium.PdfiumError, UnicodeError):
                raise EvidenceToolError("A source could not be searched") from None
            read_source_bytes(self._root, self._inventory, source.source_id)
            if truncated and scanned >= self._limits.max_search_pages:
                break
        return SearchResult(
            hits=tuple(hits),
            textless_pages=tuple(textless),
            pages_scanned=scanned,
            truncated=truncated,
        )

    def _page(self, source: SourceRecord, page: int, *, ocr: bool) -> tuple[PageRead, bool]:
        identity = (source.source_id, page)
        if identity not in self._pages:
            if len(self._pages) >= self._limits.max_pages_read:
                raise ToolLimitError("Evidence distinct-page read limit reached")
            self._pages.add(identity)
        cached = self._page_cache.get((source.source_id, page, ocr))
        if cached is not None:
            read_source_bytes(self._root, self._inventory, source.source_id)
            return cached[0], False
        retrieved = read_page(self._root, self._inventory, source, page, ocr)
        used_ocr = retrieved.mode == "ocr"
        issues = retrieved.issues
        reliable = retrieved.mode == "native" and not (set(issues) & _UNRELIABLE_NATIVE)
        if retrieved.ocr_report is not None:
            self._ocr_artifacts[source.source_id, page] = retrieved.ocr_report
        result = (
            PageRead(
                source_id=source.source_id,
                page=page,
                mode=retrieved.mode,
                text=retrieved.text,
                issues=issues,
                citable=reliable,
            ),
            used_ocr,
        )
        self._page_cache[source.source_id, page, ocr] = result
        return result

    @property
    def candidate_readings(self) -> tuple[dict[str, object], ...]:
        sources = {s.source_id: s for s in self._inventory.sources}
        return tuple(
            {
                **read.model_dump(mode="json"),
                "source_sha256": sources[read.source_id].sha256,
                "artifact_path": self._ocr_artifacts.get((read.source_id, read.page)),
                "scope": "candidate_observation_not_verified_answer_evidence",
            }
            for read, _ in self._page_cache.values()
        )

    def read_page(self, source_id: str, page: int) -> PageRead:
        """One page of native text, with automatic OCR for textless or sparse pages."""
        self._tick()
        source = self._pdf(source_id, page)
        budget_left = self._ocr < self._limits.max_ocr_pages
        extra: tuple[str, ...] = ()
        try:
            result, used_ocr = self._page(source, page, ocr=self._allow_ocr and budget_left)
        except OcrError:
            result, used_ocr = self._page(source, page, ocr=False)
            extra = ("ocr_unavailable",)
        if (
            self._allow_ocr
            and not budget_left
            and set(result.issues) & _UNRELIABLE_NATIVE
            and not extra
        ):
            extra = ("ocr_budget_exhausted",)
        if extra:
            result = result.model_copy(update={"issues": (*result.issues, *extra)})
        self._spend_chars(len(result.text))
        if used_ocr:
            self._ocr += 1
        return result

    def locate_quote(self, source_id: str, page: int, quote: str) -> QuoteLocation:
        """Exact offsets of a native-text quote, so the model never counts characters."""
        self._tick()
        source = self._pdf(source_id, page)
        if not quote or not quote.strip():
            raise ToolInputError("Quote must be nonblank")
        read, _ = self._page(source, page, ocr=False)
        if not read.citable:
            raise ToolInputError(
                "Quote location needs reliable native text; this page needs OCR review"
            )
        start = read.text.find(quote)
        if start < 0:
            raise ToolInputError("Quote not found in the page's native text")
        try:
            resolve_quote(
                self._root,
                self._inventory,
                TextCitation(source_id, page, start, start + len(quote), quote),
            )
        except EvidenceError:
            raise ToolInputError("Quote could not be verified against the page") from None
        self._spend_chars(len(quote))
        return QuoteLocation(
            source_id=source_id,
            page=page,
            start=start,
            end=start + len(quote),
            quote=quote,
            occurrences=read.text.count(quote),
        )

    def select_attachment(self, source_id: str) -> tuple[str, ...]:
        """Candidate packet attachment; the answer gate still decides which are kept."""
        self._tick()
        source = self._pdf(source_id)
        if source.family == "historical_reference":
            raise ToolInputError("Prior packets are internal evidence, never packet attachments")
        if source_id not in self._attachments:
            if len(self._attachments) >= self._limits.max_attachments:
                raise ToolLimitError("Attachment limit reached")
            self._attachments.append(source_id)
        return self.attachments

    def verify_scan_quote(
        self,
        source_id: str,
        page: int,
        quote: str,
        expected_subject: str,
    ) -> OcrCitation:
        """Cross-check a quote from a previously OCR-read page against a blind image reading."""
        self._tick()
        self._pdf(source_id, page)
        if self._scan_evidence is None:
            raise ToolInputError("Scanned-evidence cross-checking is not enabled")
        artifact = self._ocr_artifacts.get((source_id, page))
        if artifact is None:
            raise ToolInputError("Read this scanned page with OCR before verifying its quote")
        if not quote.strip() or len(quote) > 2000 or not expected_subject.strip():
            raise ToolInputError(
                "Scan quotes need 1-2000 characters and an explicit source subject"
            )
        try:
            citation = self._scan_evidence.locate(
                source_id,
                page,
                quote,
                expected_subject,
                artifact,
            )
            self._spend_chars(len(citation.quote) + len(expected_subject))
            return citation
        except ScanVerificationError as error:
            raise ToolInputError(str(error)) from None

    def verify_exhibit_title(self, source_id: str, page: int, title: str) -> OcrCitation:
        """Verify an image exhibit label without granting scalar-answer evidence status."""
        self._tick()
        self._pdf(source_id, page)
        artifact = self._ocr_artifacts.get((source_id, page))
        if self._scan_evidence is None or artifact is None:
            raise ToolInputError("Image exhibit needs OCR and independent image reading")
        if not title.strip() or len(title) > 200:
            raise ToolInputError("Exhibit title must contain 1-200 characters")
        try:
            citation = self._scan_evidence.locate_exhibit(source_id, page, title, artifact)
        except ScanVerificationError as error:
            raise ToolInputError(str(error)) from None
        self._spend_chars(len(citation.quote))
        return citation

    def read_historical_page(self, source_id: str, page: int) -> HistoricalPageResult:
        """Force OCR of question labels, even when filled answers have native PDF text."""
        self._tick()
        source = self._pdf(source_id, page)
        if source.family != "historical_reference":
            raise ToolInputError("Historical page reading requires an approved reference source")
        if self.historical_context is None or not self._allow_ocr:
            raise ToolInputError("Historical image/OCR relationship reading is not enabled")
        # Share page and OCR allowances with ordinary evidence reading.
        self._page(source, page, ocr=False)
        artifact = self._ocr_artifacts.get((source_id, page))
        if artifact is None:
            if self._ocr >= self._limits.max_ocr_pages:
                raise ToolLimitError("Historical page reading reached the OCR page limit")
            self._ocr += 1
            path = run_ocr(
                self._root,
                Path(source.path),
                page,
                inventory=Inventory(self._inventory.created_at, (source,), ()),
            )
            artifact = path.relative_to(self._root).as_posix() + "/ocr.json"
            self._ocr_artifacts[source_id, page] = artifact
        try:
            result = self.historical_context.read(source_id, page, artifact)
        except ScanVerificationError as error:
            raise ToolInputError(str(error)) from None
        self._spend_chars(len(result.model_dump_json()))
        return result
