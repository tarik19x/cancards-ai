"""Ingest the downloaded cardholder agreements and benefit guides into Pinecone.

Adds document chunks next to the existing per-card synthetic chunks from
ingest.py — same index, same embedding model, disjoint id namespace
(``<card_id>::<doc_type>::<n>`` vs. ``<card_id>::<section>``), so this can
run independently without touching the 250 chunks already there.
"""

import json
import re
from pathlib import Path
from typing import Any, Literal

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.clients.openai_client import embed_batch
from app.clients.pinecone_client import upsert_vectors
from app.logging_config import get_logger
from app.models import Card

log = get_logger(__name__)

DocType = Literal["cardholder_agreement", "benefit_guide", "insurance_certificate"]

# ~1000 chars (~200-250 tokens) keeps a chunk to roughly one clause/paragraph
# of a cardholder agreement; 150 char overlap avoids splitting a sentence that
# carries the only mention of a term (e.g. an annual fee) across two chunks.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# A page pypdf can't extract text from (scanned image, broken font) returns
# a near-empty string; skipping it beats silently embedding whitespace.
MIN_CHARS_PER_DOCUMENT = 200


class PdfDocument:
    """One downloaded PDF, located on disk by (card_id, doc_type)."""

    def __init__(self, card_id: str, doc_type: DocType, path: Path):
        self.card_id = card_id
        self.doc_type = doc_type
        self.path = path


def find_pdf_documents(pdf_dir: Path) -> list[PdfDocument]:
    """Discover every downloaded PDF under data/documents/pdf/<card_id>/<doc_type>.pdf.

    Reads the filesystem, not manifest.json, so a hand-dropped file (e.g. a
    failed download filled in manually) is picked up the same as a scripted one.
    """
    docs: list[PdfDocument] = []
    for card_dir in sorted(p for p in pdf_dir.iterdir() if p.is_dir()):
        for pdf_path in sorted(card_dir.glob("*.pdf")):
            docs.append(PdfDocument(card_dir.name, pdf_path.stem, pdf_path))  # type: ignore[arg-type]
    return docs


def load_document_urls(manifest_path: Path) -> dict[tuple[str, str], str]:
    """Map (card_id, doc_type) -> source URL, for citation metadata."""
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {(e["card_id"], e["doc_type"]): e["url"] for e in entries}


def extract_pdf_text(path: Path) -> str:
    """Extract and lightly normalize text from every page of a PDF."""
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages)
    # Collapse the runs of blank lines and mid-word hyphenation gaps that
    # PDF text extraction leaves behind; downstream chunking assumes prose.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str) -> list[str]:
    """Split extracted document text into overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


def document_to_chunks(
    doc: PdfDocument,
    text: str,
    card: Card,
    source_url: str | None,
) -> list[dict[str, Any]]:
    """Convert one document's extracted text into chunk dicts, matching
    ingest.py's shape (id, text, section, metadata) so both feed the same
    upsert path.
    """
    pieces = chunk_text(text)
    chunks: list[dict[str, Any]] = []
    for i, piece in enumerate(pieces):
        chunks.append(
            {
                "id": f"{doc.card_id}::{doc.doc_type}::{i}",
                "text": piece,
                "section": doc.doc_type,
                "metadata": {
                    "card_id": card.card_id,
                    "card_name": card.name,
                    "issuer": card.issuer,
                    "network": card.network,
                    "annual_fee_cad": card.annual_fee_cad,
                    "doc_type": doc.doc_type,
                    "document_url": source_url,
                    "chunk_index": i,
                    "section": doc.doc_type,
                    "text": piece,
                },
            }
        )
    return chunks


async def ingest_documents(pdf_dir: Path, cards_path: Path, manifest_path: Path) -> int:
    """Extract, chunk, embed, and upsert every downloaded PDF. Returns chunk count."""
    raw = json.loads(cards_path.read_text(encoding="utf-8-sig"))
    cards_by_id = {c["card_id"]: Card.model_validate(c) for c in raw}
    urls = load_document_urls(manifest_path)

    docs = find_pdf_documents(pdf_dir)
    log.info("found_documents", count=len(docs))

    all_chunks: list[dict[str, Any]] = []
    for doc in docs:
        card = cards_by_id.get(doc.card_id)
        if card is None:
            log.warning("skipped_unknown_card", card_id=doc.card_id, doc_type=doc.doc_type)
            continue

        text = extract_pdf_text(doc.path)
        if len(text) < MIN_CHARS_PER_DOCUMENT:
            log.warning(
                "skipped_low_text_document",
                card_id=doc.card_id,
                doc_type=doc.doc_type,
                chars=len(text),
            )
            continue

        doc_chunks = document_to_chunks(doc, text, card, urls.get((doc.card_id, doc.doc_type)))
        all_chunks.extend(doc_chunks)
        log.info(
            "chunked_document",
            card_id=doc.card_id,
            doc_type=doc.doc_type,
            chunks=len(doc_chunks),
        )

    log.info("built_chunks", count=len(all_chunks))

    texts = [str(c["text"]) for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        batch_emb = await embed_batch(batch)
        embeddings.extend(batch_emb)
        log.info("embedded_batch", from_idx=i, to_idx=i + len(batch))

    vectors = [
        {"id": chunk["id"], "values": emb, "metadata": chunk["metadata"]}
        for chunk, emb in zip(all_chunks, embeddings)
    ]

    upsert_vectors(vectors)
    log.info("upserted_vectors", count=len(vectors))
    return len(vectors)
