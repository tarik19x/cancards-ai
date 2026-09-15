"""One-shot script to ingest downloaded PDFs into Pinecone, next to the
existing per-card synthetic chunks from scripts/ingest.py.

Run with:  python -m scripts.ingest_documents
"""

import asyncio
from pathlib import Path

from app.logging_config import configure_logging, get_logger
from app.rag.pdf_ingest import ingest_documents


async def main() -> None:
    configure_logging("INFO")
    log = get_logger(__name__)

    data_dir = Path(__file__).resolve().parents[1] / "data"
    pdf_dir = data_dir / "documents" / "pdf"
    cards_path = data_dir / "cards.json"
    manifest_path = data_dir / "documents" / "manifest.json"
    log.info("starting_document_ingest", pdf_dir=str(pdf_dir))

    count = await ingest_documents(pdf_dir, cards_path, manifest_path)
    log.info("document_ingest_complete", vectors_upserted=count)


if __name__ == "__main__":
    asyncio.run(main())
