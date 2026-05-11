"""Endpoints for listing card data (used by frontend directory)."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models import Card

router = APIRouter(prefix="/api/cards", tags=["cards"])

CARDS_PATH = Path(__file__).resolve().parents[2] / "data" / "cards.json"


@lru_cache
def _load_cards() -> list[Card]:
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8-sig"))
    return [Card.model_validate(item) for item in raw]


@router.get("", response_model=list[Card])
async def list_cards() -> list[Card]:
    return _load_cards()


@router.get("/{card_id}", response_model=Card)
async def get_card(card_id: str) -> Card:
    cards = _load_cards()
    for c in cards:
        if c.card_id == card_id:
            return c
    raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found")
