"""Offline intake polling spike; no SharePoint or Azure network adapters."""

import hashlib
import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from bd_packet_builder.contracts import Contract, Nonblank


class PollError(ValueError):
    """A poll could not complete safely; messages contain no document details."""


class CursorExpired(PollError):
    """The source cursor needs a complete resynchronization."""


class IntakeItem(Contract):
    library_id: Nonblank
    item_id: Nonblank
    version: Nonblank
    name: Nonblank
    kind: Literal["file", "folder", "deleted"] = "file"


class QueueMessage(Contract):
    schema_version: Literal[1] = 1
    library_id: Nonblank
    item_id: Nonblank
    version: Nonblank
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def for_item(cls, library_id: str, item_id: str, version: str) -> "QueueMessage":
        canonical = json.dumps(
            [library_id, item_id, version], ensure_ascii=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return cls(library_id=library_id, item_id=item_id, version=version, idempotency_key=digest)


@dataclass(frozen=True)
class ChangePage:
    items: tuple[IntakeItem, ...]
    next_cursor: str | None = None
    delta_cursor: str | None = None


@dataclass(frozen=True)
class PollResult:
    queued: int
    review_needed: int


class IntakeSource(Protocol):
    def changes(self, cursor: str | None) -> ChangePage: ...

    def get(self, item_id: str) -> IntakeItem | None: ...


class MessageQueue(Protocol):
    def send(self, message: QueueMessage) -> None: ...


class LocalState:
    """Local SQLite test state; not a distributed production lock or state store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS metadata "
                    "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS items ("
                    "item_id TEXT PRIMARY KEY, version TEXT NOT NULL, "
                    "status TEXT NOT NULL "
                    "CHECK(status IN ('pending','queued','review_needed','deleted')))"
                )
        except sqlite3.Error as error:
            raise PollError("state_initialization_failed") from error

    def status(self, item_id: str) -> str | None:
        try:
            with sqlite3.connect(self.path) as connection:
                row = connection.execute(
                    "SELECT status FROM items WHERE item_id = ?", (item_id,)
                ).fetchone()
                return str(row[0]) if row else None
        except sqlite3.Error as error:
            raise PollError("state_read_failed") from error


class IntakePoller:
    def __init__(
        self,
        library_id: str,
        source: IntakeSource,
        queue: MessageQueue,
        state: LocalState,
        *,
        max_pages: int = 100,
        max_items: int = 10_000,
    ) -> None:
        if not library_id.strip() or max_pages < 1 or max_items < 1:
            raise PollError("invalid_configuration")
        self.library_id = library_id
        self.source = source
        self.queue = queue
        self.state = state
        self.max_pages = max_pages
        self.max_items = max_items

    def _read_changes(self, cursor: str | None) -> tuple[dict[str, IntakeItem], str]:
        seen: set[str | None] = set()
        changes: dict[str, IntakeItem] = {}
        count = 0
        for _ in range(self.max_pages):
            if cursor in seen:
                raise PollError("source_cursor_loop")
            seen.add(cursor)
            page = self.source.changes(cursor)
            if bool(page.next_cursor) == bool(page.delta_cursor):
                raise PollError("invalid_source_page")
            count += len(page.items)
            if count > self.max_items:
                raise PollError("source_item_limit")
            for entry in page.items:
                if entry.library_id != self.library_id:
                    raise PollError("library_mismatch")
                changes[entry.item_id] = entry
            if page.delta_cursor:
                return changes, page.delta_cursor
            cursor = page.next_cursor
        raise PollError("source_page_limit")

    def poll(self) -> PollResult:
        try:
            with sqlite3.connect(self.state.path, timeout=0) as connection:
                connection.execute("BEGIN IMMEDIATE")
                stored = dict(connection.execute("SELECT key, value FROM metadata"))
                if stored.get("library_id", self.library_id) != self.library_id:
                    raise PollError("library_mismatch")
                resync = False
                try:
                    changes, cursor = self._read_changes(stored.get("cursor"))
                except CursorExpired:
                    changes, cursor = self._read_changes(None)
                    resync = True
                previous = {
                    row[0]: (row[1], row[2])
                    for row in connection.execute("SELECT item_id, version, status FROM items")
                }
                if len(previous) > self.max_items:
                    raise PollError("state_item_limit")
                review = 0
                if resync:
                    for item_id, (_, status) in previous.items():
                        if item_id not in changes and status in ("pending", "queued"):
                            replacement = "review_needed" if status == "queued" else "deleted"
                            connection.execute(
                                "UPDATE items SET status = ? WHERE item_id = ?",
                                (replacement, item_id),
                            )
                            review += status == "queued"
                for item_id, (_, status) in previous.items():
                    if not resync and status == "pending" and item_id not in changes:
                        current = self.source.get(item_id)
                        if current is None:
                            connection.execute(
                                "UPDATE items SET status = 'deleted' WHERE item_id = ?", (item_id,)
                            )
                            continue
                        if current.item_id != item_id or current.library_id != self.library_id:
                            raise PollError("source_identity_mismatch")
                        changes[item_id] = current
                if len(set(previous) | set(changes)) > self.max_items:
                    raise PollError("state_item_limit")
                queued = 0
                for item_id, entry in changes.items():
                    prior = previous.get(item_id)
                    eligible = entry.kind == "file" and entry.name.lower().endswith(".pdf")
                    if prior and prior[1] in ("queued", "review_needed"):
                        if prior[1] == "queued" and (not eligible or entry.version != prior[0]):
                            connection.execute(
                                "UPDATE items SET status = 'review_needed' WHERE item_id = ?",
                                (item_id,),
                            )
                            review += 1
                        continue
                    if not eligible:
                        if prior:
                            connection.execute(
                                "UPDATE items SET status = 'deleted' WHERE item_id = ?", (item_id,)
                            )
                        continue
                    if prior and prior == (entry.version, "pending"):
                        self.queue.send(
                            QueueMessage.for_item(self.library_id, item_id, entry.version)
                        )
                        connection.execute(
                            "UPDATE items SET status = 'queued' WHERE item_id = ?", (item_id,)
                        )
                        queued += 1
                    else:
                        connection.execute(
                            "INSERT INTO items (item_id, version, status) VALUES (?, ?, 'pending') "
                            "ON CONFLICT(item_id) DO UPDATE SET version=excluded.version, "
                            "status='pending'",
                            (item_id, entry.version),
                        )
                for key, value in (("library_id", self.library_id), ("cursor", cursor)):
                    connection.execute(
                        "INSERT INTO metadata (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value),
                    )
                return PollResult(queued=queued, review_needed=review)
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower():
                raise PollError("state_busy") from error
            raise PollError("state_operation_failed") from error
        except sqlite3.Error as error:
            raise PollError("state_operation_failed") from error


class _DemoSource:
    def __init__(self) -> None:
        self.item = IntakeItem(
            library_id="synthetic-library", item_id="synthetic-item", version="1", name="blank.pdf"
        )

    def changes(self, cursor: str | None) -> ChangePage:
        return ChangePage((self.item,) if cursor is None else (), delta_cursor="synthetic-cursor")

    def get(self, item_id: str) -> IntakeItem | None:
        return self.item if item_id == self.item.item_id else None


class _DemoQueue:
    def __init__(self) -> None:
        self.messages: list[QueueMessage] = []

    def send(self, message: QueueMessage) -> None:
        self.messages.append(message)


def main() -> None:
    """Run a synthetic two-poll demo without network access or persistent output."""
    with tempfile.TemporaryDirectory(prefix="bd-intake-demo-") as directory:
        queue = _DemoQueue()
        poller = IntakePoller(
            "synthetic-library", _DemoSource(), queue, LocalState(Path(directory) / "state.db")
        )
        first, second = poller.poll(), poller.poll()
        print(
            f"Offline synthetic demo: first poll queued {first.queued}; "
            f"second poll queued {second.queued}."
        )
        print("No SharePoint or Azure queue was contacted. No packet was started.")


if __name__ == "__main__":
    main()
