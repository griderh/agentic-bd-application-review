import asyncio
import json
import os
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from agent_framework import FunctionInvocationLayer
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.agent import PageMapError
from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.live import (
    FoundryPageMapper,
    LiveRunRequest,
    build_live_client,
    prepare_live_run,
    run_live,
)
from bd_packet_builder.run import FileRunStore
from bd_packet_builder.visual import VisualPage

CONFIG = FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test")
UNREADABLE = VisualPage.model_validate_json(
    json.dumps({"readable": False, "explanation": "Synthetic unreadable page.", "items": []})
)


def pdf(pages: int) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792))
    for number in range(pages):
        canvas.drawString(50, 700, f"Synthetic page {number + 1}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def api(page: VisualPage = UNREADABLE) -> Mock:
    instance = Mock()
    instance.responses.parse.return_value = Mock(
        status="completed",
        output_parsed=page,
        model="controlled-test",
        usage=Mock(input_tokens=10, output_tokens=10, total_tokens=20),
    )
    return instance


def test_mapper_makes_one_call_per_page_and_returns_each_page() -> None:
    fake = api()
    mapper = FoundryPageMapper(CONFIG, allow_paid=True, client_factory=lambda _: fake)
    result = mapper.map_pages(pdf(2))
    assert set(result) == {1, 2}
    assert fake.responses.parse.call_count == 2


def test_mapper_requires_explicit_paid_authorization() -> None:
    with pytest.raises(FoundryError):
        FoundryPageMapper(CONFIG, allow_paid=False)


def test_mapper_rejects_oversized_forms_before_any_model_call() -> None:
    fake = api()
    mapper = FoundryPageMapper(CONFIG, allow_paid=True, client_factory=lambda _: fake)
    with pytest.raises(PageMapError):
        mapper.map_pages(pdf(6))
    fake.responses.parse.assert_not_called()


def test_mapper_reports_a_model_failure_as_a_technical_error() -> None:
    def failing(_: FoundryConfig) -> Mock:
        raise FoundryError("Foundry connection failed")

    mapper = FoundryPageMapper(CONFIG, allow_paid=True, client_factory=failing)
    with pytest.raises(PageMapError):
        mapper.map_pages(pdf(1))


def test_live_client_runs_the_framework_tool_loop_and_makes_no_call_to_build() -> None:
    client = build_live_client(CONFIG)
    assert isinstance(client, FunctionInvocationLayer)


@pytest.fixture
def evidence_root(tmp_path: Path) -> Path:
    folder = tmp_path / "evidence" / "bd_agreements" / "supporting_data" / "Firm"
    folder.mkdir(parents=True)
    (folder / "Firm profile.pdf").write_bytes(pdf(1))
    return tmp_path / "evidence"


def request(**overrides: object) -> LiveRunRequest:
    values: dict[str, object] = {
        "blank_name": "Synthetic issuer form.pdf",
        "requester_id": "00000000-0000-0000-0000-000000000001",
        "evidence_set_id": "synthetic-evidence-1",
        "as_of": date(2026, 9, 30),
    }
    return LiveRunRequest(**{**values, **overrides})  # type: ignore[arg-type]


def test_prepare_snapshots_evidence_and_records_agent_and_model_versions(
    tmp_path: Path, evidence_root: Path
) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    store = FileRunStore(runs)
    manifest = prepare_live_run(store, request(), pdf(1), evidence_root, CONFIG)
    assert manifest.status == "created"
    assert [i.path for i in manifest.evidence.items] == [
        "bd_agreements/supporting_data/Firm/Firm profile.pdf"
    ]
    versions = {v.name: v.version for v in manifest.versions}
    assert versions["agent"] == "packet-agent-v1"
    assert versions["model"] == "test"


def test_run_live_requires_explicit_paid_authorization(tmp_path: Path, evidence_root: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    store = FileRunStore(runs)
    manifest = prepare_live_run(store, request(), pdf(1), evidence_root, CONFIG)
    with pytest.raises(FoundryError):
        asyncio.run(run_live(store, manifest.run_id, evidence_root, CONFIG, allow_paid=False))
    assert store.load(manifest.run_id).status == "created"


@pytest.mark.skipif(
    os.environ.get("BD_RUN_LIVE") != "1", reason="Opt in with BD_RUN_LIVE=1; paid synthetic calls"
)
def test_live_synthetic_run_reaches_an_explicit_terminal_state(
    tmp_path: Path, evidence_root: Path
) -> None:
    config = FoundryConfig(
        endpoint=os.environ["BD_FOUNDRY_ENDPOINT"], deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"]
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    store = FileRunStore(runs)
    manifest = prepare_live_run(store, request(), pdf(1), evidence_root, config)
    final = asyncio.run(run_live(store, manifest.run_id, evidence_root, config, allow_paid=True))
    assert final.status in {"published", "failed", "packet_assembled"}
    print(json.dumps({"status": final.status, "outcome": final.outcome}))


def test_cli_agent_run_refuses_without_paid_authorization(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    code = main(
        [
            "agent-run",
            "--root",
            str(tmp_path),
            "--blank",
            "bd_agreements/Blank/form.pdf",
            "--endpoint",
            CONFIG.endpoint,
            "--deployment",
            "test",
        ]
    )
    assert code == 1
    assert "--allow-paid" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()
