from __future__ import annotations

from pathlib import Path

from scholar_agent.ingestion.chunker import chunk_document
from scholar_agent.ingestion.loaders.base import get_loader
from scholar_agent.ingestion.loaders.obsidian import (
    blank_comments,
    clean_stem,
    extract_links,
    kind_from,
    split_frontmatter,
)
from scholar_agent.ingestion.pipeline import iter_note_files
from scholar_agent.text import detect_language, normalize

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_vault"


def test_wikilinks_with_labels_brackets_and_aliases():
    body = "- **Descrita en** → [[RES — [1] Bliss y Lømo 1973]]\ntexto [[A|alias]] y [[B#sec]] ![[img.png]]"
    links = extract_links(body, 10)
    assert [(lk.target, lk.label, lk.line) for lk in links] == [
        ("RES — [1] Bliss y Lømo 1973", "Descrita en", 10), ("A", None, 11), ("B", None, 11)]


def test_frontmatter_and_body_offset():
    meta, body, start = split_frontmatter("---\ntipo: concepto\ntags: [a, b]\n---\n\n# T\ntext")
    assert meta["tags"] == ["a", "b"] and start == 5 and body.startswith("\n# T")


def test_broken_frontmatter_does_not_crash():
    meta, body, start = split_frontmatter("---\ntipo: [unclosed\n---\nbody")
    assert meta == {} and body == "body"


def test_obsidian_comments_keep_line_numbers():
    assert blank_comments("a\n%%x\ny%%\nb").split("\n") == ["a", "", "", "b"]


def test_notion_hash_and_kind_detection():
    assert clean_stem("Untitled 3 3477ab3af5d5818a91bacafac6bc979b") == "Untitled 3"
    assert kind_from("HIP — algo", {}) == "hypothesis"
    assert kind_from("x", {"tipo": "síntesis"}) == "synthesis"
    assert kind_from("Apuntes", {}) == "note"


def test_language_detection():
    assert detect_language("La potenciación a largo plazo es un aumento de la eficacia") == "es"
    assert detect_language("The weak stimulus sets a tag that is captured by the proteins") == "en"
    assert normalize("Sináptica—LTP!") == "sinaptica ltp"


def test_chunk_line_ranges_point_at_real_file_lines():
    for file in iter_note_files(DEMO):
        doc = get_loader(file).load("demo", DEMO, file)
        raw_lines = file.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
        for chunk in chunk_document(doc):
            assert 1 <= chunk.line_start <= chunk.line_end <= len(raw_lines)
            first_line = chunk.text.split("\n")[0].strip()
            assert first_line in raw_lines[chunk.line_start - 1].strip() or \
                raw_lines[chunk.line_start - 1].strip() in first_line, (file.name, chunk.line_start)


def test_chunks_respect_token_limit_and_carry_context():
    long = "# T\n\n" + " ".join(f"Frase número {i} sobre sinapsis." for i in range(400))
    tmp = DEMO / "inbox" / "ideas sueltas 2025.txt"
    doc = get_loader(tmp).load("demo", DEMO, tmp)
    doc.body, doc.body_start_line = long, 1
    chunks = chunk_document(doc, max_tokens=120, min_tokens=20)
    assert len(chunks) > 5
    assert all(len(c.text) / 3.6 <= 160 for c in chunks)
    assert all(c.embed_text.startswith(doc.title) for c in chunks)


def test_txt_notion_and_image_embeds_are_loaded():
    notion = next(DEMO.rglob("Untitled 3*.md"))
    doc = get_loader(notion).load("demo", DEMO, notion)
    assert doc.title == "Untitled 3"
    assert "diagrama_ltp_dos_fases.png" in doc.embeds and "assets/dopamina_d1.png" in doc.embeds
    assert any("scholarpedia" in u for u in doc.urls)
    txt = next(DEMO.rglob("*.txt"))
    assert get_loader(txt).load("demo", DEMO, txt).kind == "note"
