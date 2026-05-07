// Types matching backend/app/models.py exactly

export interface RewardCategory {
  rate: number
  unit: "points_per_dollar" | "percent_cashback" | "miles_per_dollar"
  monthly_cap_cad: number | null
  annual_cap_cad: number | null
}

export interface CardInsurance {
  travel_emergency_medical_days: number | null
  rental_car_collision: boolean
  trip_interruption: boolean
  trip_cancellation: boolean
  flight_delay: boolean
  baggage_insurance: boolean
  purchase_protection_days: number | null
  extended_warranty: boolean
  lounge_access: boolean
}

export interface Card {
  card_id: string
  name: string
  issuer: string
  network: "Visa" | "Mastercard" | "Amex"
  annual_fee_cad: number
  monthly_fee_cad: number | null
  welcome_bonus_description: string | null
  rewards_summary: string
  rewards_detail: Record<string, RewardCategory>
  estimated_point_value_cents: number | null
  foreign_transaction_fee_pct: number
  insurance_summary: string
  insurance_detail: CardInsurance
  min_credit_score_recommended: number | null
  min_personal_income_cad: number | null
  min_household_income_cad: number | null
  best_for: string[]
  not_great_for: string[]
  official_url: string
  last_verified: string
}

export interface Citation {
  card_id: string
  card_name: string
  issuer: string
  section: string
}

export interface CardRecommendation {
  card_id: string
  card_name: string
  annual_fee_cad: number
  why: string
  key_benefits: string[]
}

export interface AnswerResponse {
  answer_markdown: string
  recommended_cards: CardRecommendation[]
  citations: Citation[]
  confidence_notes: string | null
  response_id: string
  timestamp: string
}

// Internal chat message shape (not from backend)
export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  response?: AnswerResponse
  timestamp: Date
  error?: boolean
}
