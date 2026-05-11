"""Pydantic models for request/response shapes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ============== Card Database Models ==============


class RewardCategory(BaseModel):
    rate: float
    unit: Literal["points_per_dollar", "percent_cashback", "miles_per_dollar"]
    monthly_cap_cad: float | None = None
    annual_cap_cad: float | None = None


class CardInsurance(BaseModel):
    travel_emergency_medical_days: int | None = None
    rental_car_collision: bool = False
    trip_interruption: bool = False
    trip_cancellation: bool = False
    flight_delay: bool = False
    baggage_insurance: bool = False
    purchase_protection_days: int | None = None
    extended_warranty: bool = False
    lounge_access: bool = False


class Card(BaseModel):
    card_id: str
    name: str
    issuer: str
    network: Literal["Visa", "Mastercard", "Amex"]
    annual_fee_cad: float
    monthly_fee_cad: float | None = None
    welcome_bonus_description: str | None = None
    rewards_summary: str
    rewards_detail: dict[str, RewardCategory]
    estimated_point_value_cents: float | None = None
    foreign_transaction_fee_pct: float
    insurance_summary: str
    insurance_detail: CardInsurance
    min_credit_score_recommended: int | None = None
    min_personal_income_cad: float | None = None
    min_household_income_cad: float | None = None
    best_for: list[str]
    not_great_for: list[str]
    official_url: str
    last_verified: str  # ISO date


# ============== API Request/Response Models ==============


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class Citation(BaseModel):
    card_id: str
    card_name: str
    issuer: str
    section: str


class CardRecommendation(BaseModel):
    card_id: str
    card_name: str
    annual_fee_cad: float
    why: str
    key_benefits: list[str]


class AnswerResponse(BaseModel):
    answer_markdown: str
    recommended_cards: list[CardRecommendation]
    citations: list[Citation]
    confidence_notes: str | None = None
    response_id: str
    timestamp: datetime


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    timestamp: datetime
