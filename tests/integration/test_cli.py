from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from scholar_agent.cli import app

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_vault"
runner = CliRunner()


@pytest.fixture()
def cfg(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "test.yaml"
    path.write_text(yaml.safe_dump({
        "embeddings": {"provider": "hash"},
        "paths": {"index_dir": str(tmp_path / "idx"), "cache_dir": str(tmp_path / "cache"),
                  "sqlite": str(tmp_path / "idx" / "catalog.sqlite")},
    }), encoding="utf-8")
    return path


def test_ingest_search_doctor_usage_roundtrip(cfg):
    out = runner.invoke(app, ["ingest", str(DEMO), "--source", "demo", "-c", str(cfg)])
    assert out.exit_code == 0, out.output
    assert "19" in out.output

    out = runner.invoke(app, ["search", "receptor NMDA magnesio coincidencia", "-k", "3", "-c", str(cfg)])
    assert out.exit_code == 0 and "Receptor NMDA" in out.output

    out = runner.invoke(app, ["doctor", "-c", str(cfg)])
    assert out.exit_code == 0 and "orphans" in out.output and "19 notes" in out.output

    out = runner.invoke(app, ["usage", "-c", str(cfg)])
    assert out.exit_code == 0 and "0 queries" in out.output


def test_ask_without_index_or_keys_fails_with_a_clear_message(cfg, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_PAID_TIER", "false")
    out = runner.invoke(app, ["ask", "¿Qué es la LTP?", "--mode", "notes", "-c", str(cfg)])
    assert out.exit_code == 1
    assert "paid" in out.output.lower() or "GROQ_API_KEY" in out.output


def test_ask_notes_mode_requires_ingestion(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_PAID_TIER", "true")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    out = runner.invoke(app, ["ask", "¿Qué es la LTP?", "--mode", "notes", "-c", str(cfg)])
    assert out.exit_code == 1 and "research ingest" in out.output
