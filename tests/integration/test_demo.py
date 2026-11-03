import hashlib
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.demo import (
    BROWARD_BLANK,
    BROWARD_REFERENCE,
    demo_config,
    prepare_broward_demo,
)
from bd_packet_builder.history import ArchiveManifest


def create_pdf(path: Path, text: str) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(40, 740, text)
    pdf.save()
    data = stream.getvalue()
    path.write_bytes(data)
    return data


def demo_root(root: Path) -> bytes:
    create_pdf(root / BROWARD_BLANK, "Synthetic blank form.")
    history = create_pdf(root / BROWARD_REFERENCE, "Synthetic Broward history.")
    create_pdf(root / "bd_agreements/supporting_data/Firm/firm.pdf", "Synthetic support only.")
    return history


def test_demo_preflight_hash_binds_only_explicit_broward_reference(tmp_path: Path) -> None:
    raw = demo_root(tmp_path)
    plan = prepare_broward_demo(tmp_path)
    archive = ArchiveManifest.model_validate_json(
        (tmp_path / plan.historical_manifest).read_bytes()
    )
    assert len(archive.entries) == 1
    assert archive.entries[0].path == BROWARD_REFERENCE.as_posix()
    assert archive.entries[0].partition == "reference"
    assert archive.entries[0].sha256 == hashlib.sha256(raw).hexdigest()
    assert len(plan.available_sources) == 1
    assert "Synthetic support only" not in repr(plan.available_sources)


def test_dense_document_demo_uses_explicit_bounded_request_timeout() -> None:
    assert demo_config().timeout_seconds == 180
    assert demo_config(timeout_seconds=240).timeout_seconds == 240
    with pytest.raises(ValueError):
        demo_config(timeout_seconds=601)


def test_demo_refuses_changed_reference_manifest(tmp_path: Path) -> None:
    demo_root(tmp_path)
    plan = prepare_broward_demo(tmp_path)
    manifest_path = tmp_path / plan.historical_manifest
    manifest = json.loads(manifest_path.read_bytes())
    manifest["entries"][0]["issuer"] = "Different issuer"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="does not match"):
        prepare_broward_demo(tmp_path)


def test_demo_evidence_set_changes_when_historical_source_changes(tmp_path: Path) -> None:
    demo_root(tmp_path)
    original = prepare_broward_demo(tmp_path)
    history = tmp_path / BROWARD_REFERENCE
    create_pdf(history, "Updated synthetic Broward history.")
    changed = prepare_broward_demo(tmp_path)
    assert changed.historical_source.sha256 != original.historical_source.sha256
    assert changed.evidence_set_id != original.evidence_set_id


def test_cli_cancellation_finishes_preflight_without_starting_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from bd_packet_builder import cli

    demo_root(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "CANCEL")
    monkeypatch.setattr(
        cli,
        "run_broward_demo",
        lambda *args, **kwargs: pytest.fail("Cancelled demo must not call the agent"),
    )
    status = cli.main(
        ["broward-demo", "--root", str(tmp_path), "--deployment", "test", "--allow-paid"]
    )
    assert status == 1
    output = capsys.readouterr().out
    assert "BROWARD DEMO PREFLIGHT" in output
    assert "Synthetic support only" not in output
    assert "Demo cancelled; no model calls were made." in output


def test_demo_requires_paid_flag_before_preflight(tmp_path: Path, capsys) -> None:
    from bd_packet_builder.cli import main

    status = main(["broward-demo", "--root", str(tmp_path)])
    assert status == 1
    assert "--allow-paid" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("timeout", [180, 240])
def test_confirmed_cli_invokes_fresh_run_with_progress_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, timeout: int
) -> None:
    from bd_packet_builder import cli

    demo_root(tmp_path)
    captured = {}
    monkeypatch.setattr("builtins.input", lambda _: "RUN")

    def fake_run(plan, config, **kwargs):
        captured["plan"] = plan
        captured["config"] = config
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            run_id="synthetic-run",
            status="published",
            outcome="draft_ready",
            exceptions=lambda: (),
        )

    monkeypatch.setattr(cli, "run_broward_demo", fake_run)
    status = cli.main(
        [
            "broward-demo",
            "--root",
            str(tmp_path),
            "--deployment",
            "test",
            "--request-timeout-seconds",
            str(timeout),
            "--allow-paid",
        ]
    )
    assert status == 0
    assert captured["plan"].historical_source.partition == "reference"
    assert captured["config"].deployment == "test"
    assert captured["config"].timeout_seconds == timeout
    assert callable(captured["kwargs"]["progress_sink"])
    output = capsys.readouterr().out
    assert "Fresh run synthetic-run" in output
    assert "document text shown" in output
    assert f"HTTP request timeout: {timeout} seconds" in output
