"""One-shot script to ingest the card database into Pinecone.

Run with:  python -m scripts.ingest
"""
import asyncio
from pathlib import Path

from app.logging_config import configure_logging, get_logger
from app.rag.ingest import ingest_cards


async def main() -> None:
    configure_logging("INFO")
    log = get_logger(__name__)

    cards_path = Path(__file__).resolve().parents[1] / "data" / "cards.json"
    log.info("starting_ingest", path=str(cards_path))

    count = await ingest_cards(cards_path)
    log.info("ingest_complete", vectors_upserted=count)


if __name__ == "__main__":
    asyncio.run(main())
