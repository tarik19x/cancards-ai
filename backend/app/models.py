"""Pydantic models for request/response shapes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.coach.scoring import HistoryLength, MissedPayments, ScoreResult, Utilization

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


# ============== Credit Coach / Conversation Models ==============


class CreditProfile(BaseModel):
    """What the coach has learned so far. Every field optional: a profile is
    built up over several turns, and holding a half-filled one is normal.

    Whether it is complete enough to score is ReadyCreditProfile's job.

    Income and profession are collected as context for card eligibility only.
    They are deliberately NOT scoring inputs: bureau scores do not use them, and
    scoring someone on their job would be unfair as well as wrong.
    """

    card_count: int | None = Field(default=None, ge=0)
    utilization: Utilization | None = None
    history_length: HistoryLength | None = None
    missed_payments: MissedPayments | None = None
    recent_inquiries: int | None = Field(default=None, ge=0)

    # People answer "how much of your limit do you use?" in dollars far more often than
    # in percentages. These two are how the coach works the band out itself when they do
    # (see app/coach/profile.py derive_utilization); neither is scored directly.
    typical_balance_cad: float | None = Field(default=None, ge=0)
    total_credit_limit_cad: float | None = Field(default=None, ge=0)
    annual_income_cad: float | None = Field(default=None, ge=0)


class ReadyCreditProfile(BaseModel):
    """The five facts the estimate cannot be computed without.

    Validating a CreditProfile against this is the readiness check, and the
    fields Pydantic reports missing are exactly what the coach asks for next --
    so the questions can never drift out of step with the rule that gates the
    score.
    """

    card_count: int = Field(ge=0)
    utilization: Utilization
    history_length: HistoryLength
    missed_payments: MissedPayments
    recent_inquiries: int = Field(ge=0)


# The server mints conversation ids with uuid4, so that is the only shape it accepts back.
# An open-ended string would let a client probe for other people's conversations and would
# put arbitrary text into the database's key column.
THREAD_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    # Absent on the first message; the server mints one and the client keeps it.
    thread_id: str | None = Field(default=None, pattern=THREAD_ID_PATTERN)


class ChatResponse(BaseModel):
    thread_id: str
    reply_markdown: str
    profile: CreditProfile
    missing_fields: list[str]
    gave_score: bool
    score: ScoreResult | None = None
    score_message_index: int | None = None
    turn_count: int


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ThreadResponse(BaseModel):
    """A saved conversation, as reloaded from the checkpointer."""

    thread_id: str
    messages: list[ThreadMessage]
    profile: CreditProfile
    missing_fields: list[str]
    score: ScoreResult | None = None
    score_message_index: int | None = None
    turn_count: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    timestamp: datetime
