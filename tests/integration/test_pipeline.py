from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scholar_agent.indexing.embedder import HashEmbedder
from scholar_agent.ingestion.pipeline import ingest
from scholar_agent.retrieval.hybrid import NoteRetriever
from scholar_agent.services import build_services

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_vault"


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    target = tmp_path / "vault"
    shutil.copytree(DEMO, target)
    return target


def run(svc, vault, **kw):
    return ingest(vault, "v", svc.embedder, svc.store, svc.catalog, **kw)


def test_incremental_ingestion_handles_add_update_remove(settings, vault):
    svc = build_services(settings, with_reranker=False)
    try:
        first = run(svc, vault)
        assert first.added == 19 and first.errors == []
        assert run(svc, vault).unchanged == 19

        (vault / "inbox" / "ideas sueltas 2025.txt").write_text("LTP y metaplasticidad: nueva idea sobre umbrales.\n", "utf-8")
        (vault / "inbox" / "apuntes clase semana 3.txt").unlink()
        (vault / "inbox" / "nueva nota.txt").write_text("Nota nueva sobre dopamina y D1/D5 en CA1.\n", "utf-8")
        second = run(svc, vault)
        assert (second.added, second.updated, second.removed) == (1, 1, 1)

        assert svc.catalog.find_note("apuntes clase semana 3") is None
        assert svc.catalog.find_note("nueva nota") is not None
        hits = NoteRetriever(svc).search("dopamina D1 D5 CA1", k=3, graph=False)
        assert hits[0].path == "inbox/nueva nota.txt"
        stale = NoteRetriever(svc).search("el profe dijo que la LTD usa otras vias", k=5, graph=False)
        assert all(h.path != "inbox/apuntes clase semana 3.txt" for h in stale)
    finally:
        svc.close()


def test_legacy_encoding_and_broken_files_do_not_stop_ingestion(settings, tmp_path):
    root = tmp_path / "messy"
    root.mkdir()
    (root / "latin.txt").write_bytes("Potenciación sináptica en el hipocampo, según el año 1973.".encode("cp1252"))
    (root / "empty.md").write_text("", "utf-8")
    (root / "bad_yaml.md").write_text("---\ntipo: [sin cerrar\n---\ncontenido útil sobre LTP", "utf-8")
    (root / ".obsidian").mkdir()
    (root / ".obsidian" / "workspace.md").write_text("ignored", "utf-8")
    svc = build_services(settings, with_reranker=False)
    try:
        report = ingest(root, "m", svc.embedder, svc.store, svc.catalog)
        assert report.errors == [] and report.scanned == 3
        hit = NoteRetriever(svc).search("potenciación sináptica hipocampo", k=1, graph=False)[0]
        assert "sináptica" in hit.text and hit.path == "latin.txt"
        assert "empty.md" in svc.catalog.doctor()["empty_notes"]
    finally:
        svc.close()


def test_embedder_mismatch_requires_rebuild(settings, vault):
    svc = build_services(settings, with_reranker=False)
    try:
        run(svc, vault)
        with pytest.raises(RuntimeError, match="--rebuild"):
            ingest(vault, "v", HashEmbedder(dim=128), svc.store, svc.catalog)
        rebuilt = ingest(vault, "v", HashEmbedder(dim=128), svc.store, svc.catalog, rebuild=True)
        assert rebuilt.added == 19
    finally:
        svc.close()


def test_graph_expansion_adds_linked_notes_with_relation(services):
    hits = NoteRetriever(services).search("detector de coincidencia magnesio", k=3, graph=True)
    graph_hits = [h for h in hits if h.via == "graph"]
    assert graph_hits and all(h.relation for h in graph_hits)
    assert {h.path for h in hits}.issuperset({"plasticidad/CON — Receptor NMDA como detector de coincidencia.md"})
