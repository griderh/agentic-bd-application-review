import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bd_packet_builder.intake_poller import (
    ChangePage,
    CursorExpired,
    IntakeItem,
    IntakePoller,
    LocalState,
    PollError,
)


def item(version: str = "v1", **changes: object) -> IntakeItem:
    return IntakeItem(
        library_id="library", item_id="item", version=version, name="blank.pdf", **changes
    )


class Source:
    def __init__(self) -> None:
        self.pages: dict[str | None, ChangePage | Exception] = {}
        self.current: dict[str, IntakeItem | None] = {}

    def changes(self, cursor: str | None) -> ChangePage:
        result = self.pages[cursor]
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, item_id: str) -> IntakeItem | None:
        return self.current[item_id]


class Queue:
    def __init__(self) -> None:
        self.messages = []
        self.fail_after_send = False

    def send(self, message) -> None:
        self.messages.append(message)
        if self.fail_after_send:
            raise PollError("queue_send_unknown")


@pytest.fixture
def setup(tmp_path: Path):
    source, queue = Source(), Queue()
    state = LocalState(tmp_path / "state.db")
    poller = IntakePoller("library", source, queue, state)
    return source, queue, state, poller


def test_existing_pdf_is_stabilized_then_queued_after_restart(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), next_cursor="page2")
    source.pages["page2"] = ChangePage((), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.current["item"] = item()
    assert poller.poll().queued == 0
    assert not queue.messages
    restarted = IntakePoller("library", source, queue, state)
    assert restarted.poll().queued == 1
    message = queue.messages[0]
    assert (message.library_id, message.item_id, message.version) == ("library", "item", "v1")
    assert set(message.model_dump()) == {
        "schema_version",
        "library_id",
        "item_id",
        "version",
        "idempotency_key",
    }
    assert "blank.pdf" not in message.model_dump_json()
    source.pages["d2"] = ChangePage((), delta_cursor="d3")
    assert restarted.poll().queued == 0
    assert len(queue.messages) == 1


def test_changes_after_queue_require_review(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.pages["d2"] = ChangePage((item("v2"),), delta_cursor="d3")
    source.current["item"] = item()
    poller.poll()
    poller.poll()
    assert poller.poll().review_needed == 1
    assert len(queue.messages) == 1
    assert state.status("item") == "review_needed"


def test_ambiguous_send_replays_same_idempotency_key(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.current["item"] = item()
    poller.poll()
    queue.fail_after_send = True
    with pytest.raises(PollError, match="queue_send_unknown"):
        poller.poll()
    queue.fail_after_send = False
    assert poller.poll().queued == 1
    assert len(queue.messages) == 2
    assert queue.messages[0].idempotency_key == queue.messages[1].idempotency_key
    assert state.status("item") == "queued"


def test_expired_cursor_resync_retains_queued_records(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.current["item"] = item()
    poller.poll()
    poller.poll()
    source.pages["d2"] = CursorExpired()
    source.pages[None] = ChangePage((item(),), delta_cursor="d3")
    assert poller.poll().queued == 0
    assert len(queue.messages) == 1


def test_changed_before_stable_and_deleted_are_not_queued(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.pages["d2"] = ChangePage((), delta_cursor="d3")
    source.current["item"] = item("v2")
    poller.poll()
    assert poller.poll().queued == 0
    source.current["item"] = None
    assert poller.poll().queued == 0
    assert not queue.messages


def test_wrong_library_and_unsupported_file_are_not_queued(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage(
        (IntakeItem(library_id="library", item_id="other", version="v1", name="notes.txt"),),
        delta_cursor="d1",
    )
    assert poller.poll().queued == 0
    assert not queue.messages
    source.pages["d1"] = ChangePage(
        (IntakeItem(library_id="wrong", item_id="item", version="v1", name="a.pdf"),),
        delta_cursor="d2",
    )
    with pytest.raises(PollError, match="library_mismatch"):
        poller.poll()


def test_concurrent_polls_fail_closed(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((), delta_cursor="d1")
    with sqlite3.connect(state.path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(PollError, match="state_busy"):
            poller.poll()


def test_failed_pagination_does_not_advance_cursor(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), next_cursor="page2")
    source.pages["page2"] = PollError("source_unavailable")
    with pytest.raises(PollError, match="source_unavailable"):
        poller.poll()
    source.pages["page2"] = ChangePage((), delta_cursor="d1")
    assert poller.poll().queued == 0
    assert state.status("item") == "pending"


def test_queued_file_deleted_is_held_for_review(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.pages["d2"] = ChangePage((item(kind="deleted"),), delta_cursor="d3")
    source.current["item"] = item()
    poller.poll()
    poller.poll()
    assert poller.poll().review_needed == 1
    assert state.status("item") == "review_needed"


def test_expired_cursor_resync_flags_missing_queued_file(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), delta_cursor="d1")
    source.pages["d1"] = ChangePage((), delta_cursor="d2")
    source.current["item"] = item()
    poller.poll()
    poller.poll()
    source.pages["d2"] = CursorExpired()
    source.pages[None] = ChangePage((), delta_cursor="d3")
    assert poller.poll().review_needed == 1
    assert state.status("item") == "review_needed"


def test_damaged_state_fails_not_resets(tmp_path):
    path = tmp_path / "state.db"
    path.write_bytes(b"not a database")
    with pytest.raises(PollError, match="state_initialization_failed"):
        LocalState(path)
    assert path.read_bytes() == b"not a database"


def test_unbounded_paging_and_state_are_rejected(setup):
    source, queue, state, _ = setup
    poller = IntakePoller("library", source, queue, state, max_items=1, max_pages=1)
    source.pages[None] = ChangePage((item(),), next_cursor="next")
    with pytest.raises(PollError, match="source_page_limit"):
        poller.poll()
    source.pages[None] = ChangePage(
        (item(), IntakeItem(library_id="library", item_id="two", version="1", name="two.pdf")),
        delta_cursor="d1",
    )
    with pytest.raises(PollError, match="source_item_limit"):
        poller.poll()
    assert state.status("item") is None


def test_duplicate_changes_in_one_poll_do_not_count_as_two_observations(setup):
    source, queue, state, poller = setup
    source.pages[None] = ChangePage((item(),), next_cursor="page2")
    source.pages["page2"] = ChangePage((item(),), delta_cursor="d1")
    assert poller.poll().queued == 0
    assert queue.messages == []


def test_source_error_does_not_print_item_details(setup, capsys):
    source, queue, state, poller = setup
    source.pages[None] = PollError("source_unavailable")
    with pytest.raises(PollError, match="source_unavailable"):
        poller.poll()
    assert capsys.readouterr().out == ""


def test_synthetic_demo_runs_without_network():
    completed = subprocess.run(
        [sys.executable, "-m", "bd_packet_builder.intake_poller"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert "first poll queued 0; second poll queued 1" in completed.stdout
    assert "No SharePoint or Azure queue was contacted" in completed.stdout
