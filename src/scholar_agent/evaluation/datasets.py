"""Public evaluation datasets (SciFact, PubMedQA), downloaded once and cached.

Neither dataset contains the user's notes: the first evaluation of the agent is done on external
data, as intended.
"""

from __future__ import annotations

import io
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

import httpx

SCIFACT_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
PUBMEDQA_URL = "https://raw.githubusercontent.com/pubmedqa/pubmedqa/master/data/ori_pqal.json"


def _download(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _safe_name(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#^]', "", text).strip(" .")
    return re.sub(r"\s+", " ", cleaned)[:limit].strip(" .")


# ------------------------------------------------------------------------------ SciFact
@dataclass
class SciFactClaim:
    id: int
    claim: str
    label: str                 # SUPPORT | CONTRADICT | NEI
    gold_docs: set[str]        # doc ids that contain the evidence ("" set for NEI)


def scifact_dir(cache: Path) -> Path:
    target = cache / "scifact"
    if not (target / "corpus.jsonl").exists():
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(_download(SCIFACT_URL)), mode="r:gz") as tar:
            for member in tar.getmembers():
                name = Path(member.name).name
                if member.isfile() and name in {"corpus.jsonl", "claims_dev.jsonl", "claims_train.jsonl"}:
                    (target / name).write_bytes(tar.extractfile(member).read())  # type: ignore[union-attr]
    return target


def load_scifact_claims(cache: Path, split: str = "dev") -> list[SciFactClaim]:
    claims = []
    for line in (scifact_dir(cache) / f"claims_{split}.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        evidence = row.get("evidence") or {}
        labels = {e["label"] for items in evidence.values() for e in items}
        label = "NEI" if not evidence else ("CONTRADICT" if labels == {"CONTRADICT"} else "SUPPORT")
        claims.append(SciFactClaim(row["id"], row["claim"], label, set(evidence)))
    return claims


def materialize_scifact(cache: Path) -> Path:
    """Write the SciFact corpus as Markdown notes (so the real ingestion pipeline is evaluated)."""
    notes = cache / "scifact_notes"
    marker = notes / ".complete"
    if marker.exists():
        return notes
    notes.mkdir(parents=True, exist_ok=True)
    for line in (scifact_dir(cache) / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        doc = json.loads(line)
        title = doc["title"].strip()
        body = " ".join(doc["abstract"]).strip()
        name = f"{_safe_name(title)} ({doc['doc_id']}).md"
        (notes / name).write_text(
            f"---\ntipo: resumen\nestado: activo\nfuentes: []\n---\n\n# {title}\n\n{body}\n", encoding="utf-8"
        )
    marker.write_text("ok")
    return notes


def scifact_doc_id(path: str) -> str:
    match = re.search(r"\((\d+)\)\.md$", path)
    return match.group(1) if match else path


# ----------------------------------------------------------------------------- PubMedQA
@dataclass
class PubMedQAItem:
    pmid: str
    question: str
    decision: str              # yes | no | maybe
    contexts: list[str]
    labels: list[str]


def load_pubmedqa(cache: Path) -> list[PubMedQAItem]:
    target = cache / "pubmedqa_ori_pqal.json"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_download(PUBMEDQA_URL))
    data = json.loads(target.read_text(encoding="utf-8"))
    return [
        PubMedQAItem(pmid, v["QUESTION"], v["final_decision"], v["CONTEXTS"], v["LABELS"])
        for pmid, v in data.items()
    ]


def materialize_pubmedqa(items: list[PubMedQAItem], cache: Path, name: str) -> Path:
    """One note per abstract. The title carries no answer information (just the PMID)."""
    notes = cache / name
    notes.mkdir(parents=True, exist_ok=True)
    for item in items:
        sections = "\n\n".join(f"**{lab.title()}.** {ctx}" for lab, ctx in zip(item.labels, item.contexts, strict=False))
        (notes / f"PMID {item.pmid}.md").write_text(
            f"---\ntipo: resumen\nestado: activo\n---\n\n# PMID {item.pmid}\n\n{sections}\n", encoding="utf-8"
        )
    return notes
