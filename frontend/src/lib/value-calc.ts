import type { SpendProfile } from "@/lib/panel-store"

// One reward rate on a card.
// percent 4 means "4% back".
// cap fields are optional — some cards only pay the high rate up to a limit.
export type EarnRate = {
  category: string
  percent: number
  monthlyCap?: number // dollars per month at this rate
  annualCap?: number  // dollars per year at this rate
}

export type ValueRow = {
  key: keyof SpendProfile
  label: string
  dollars: number
  percent: number
}

// Words that might show up in a card's category names. All lowercase.
// Matched with "contains", so "grocer" catches "grocery_stores" too.
const ALIASES: Record<keyof SpendProfile, string[]> = {
  groceries: ["grocer", "supermarket", "loblaws", "food"],
  dining: ["dining", "restaurant", "eats", "eat", "drink", "bar", "coffee", "entertainment"],
  gas: ["gas", "fuel", "esso", "ev charging"],
  travel: ["travel", "flight", "hotel", "airline", "westjet", "transit"],
  other: ["everything", "other", "all other", "base", "general"],
}

const LABELS: Record<keyof SpendProfile, string> = {
  groceries: "Groceries",
  dining: "Dining",
  gas: "Gas",
  travel: "Travel",
  other: "Everything else",
}

/**
 * Read reward rates out of a card object.
 *
 * Cards store rewards like this:
 *   rewards_detail: {
 *     grocery_stores: { rate: 5, unit: "percent_cashback", monthly_cap_cad: 500 }
 *   }
 *
 * Two kinds of unit:
 *   "percent_cashback"  → rate is already a percent, use it as-is
 *   "points_per_dollar" → 5x points worth 1 cent each = 5% back
 *
 * Returns [] when a card has no structured rates. The panel then hides
 * the breakdown instead of showing made-up numbers.
 */
export function parseEarnRates(card: unknown): EarnRate[] {
  if (!card || typeof card !== "object") return []
  const c = card as Record<string, unknown>

  const detail = c.rewards_detail
  if (!detail || typeof detail !== "object") return []

  // how many cents one point is worth. defaults to 1.
  const pointValue = Number(c.estimated_point_value_cents ?? 1) || 1

  const rates: EarnRate[] = []
  for (const [category, raw] of Object.entries(detail as Record<string, unknown>)) {
    if (!raw || typeof raw !== "object") continue
    const row = raw as Record<string, unknown>

    const rate = Number(row.rate)
    if (isNaN(rate)) continue

    const unit = String(row.unit ?? "")
    // points need converting to a real percent. cash back is already one.
    const percent = unit.includes("point") ? rate * pointValue : rate

    const monthlyCap = Number(row.monthly_cap_cad)
    const annualCap = Number(row.annual_cap_cad)

    rates.push({
      // "eat_and_drink" → "eat and drink"
      category: category.replace(/_/g, " "),
      percent,
      monthlyCap: isNaN(monthlyCap) ? undefined : monthlyCap,
      annualCap: isNaN(annualCap) ? undefined : annualCap,
    })
  }

  return rates
}

/** The "everything else" rate a card falls back to. */
function baseRate(rates: EarnRate[]): number {
  const base = rates.find((r) =>
    ALIASES.other.some((w) => r.category.includes(w))
  )
  return base ? base.percent : 0
}

/**
 * Dollars per year each spend category returns.
 *
 * Respects spending caps. Example: a card pays 5% on groceries but only
 * on the first $500 a month. If you spend $850, you get 5% on $500 and
 * the base rate on the other $350.
 */
export function annualRewards(spend: SpendProfile, rates: EarnRate[]) {
  const keys = Object.keys(spend) as (keyof SpendProfile)[]
  const fallback = baseRate(rates)

  const rows: ValueRow[] = keys.map((key) => {
    const words = ALIASES[key]
    const match = rates.find((r) => words.some((w) => r.category.includes(w)))

    const yearlySpend = spend[key] * 12

    // no matching category on this card — everything earns the base rate
    if (!match) {
      return {
        key,
        label: LABELS[key],
        dollars: (yearlySpend * fallback) / 100,
        percent: fallback,
      }
    }

    // how much of the spend gets the good rate
    let cappedSpend = yearlySpend
    if (match.monthlyCap) cappedSpend = Math.min(yearlySpend, match.monthlyCap * 12)
    if (match.annualCap) cappedSpend = Math.min(cappedSpend, match.annualCap)

    // good rate up to the cap, base rate on whatever is left over
    const aboveCap = yearlySpend - cappedSpend
    const dollars =
      (cappedSpend * match.percent) / 100 + (aboveCap * fallback) / 100

    return { key, label: LABELS[key], dollars, percent: match.percent }
  })

  const total = rows.reduce((sum, r) => sum + r.dollars, 0)
  return { rows, total }
}

/** Rewards earned minus the yearly fee. Can be negative. */
export function netValue(totalEarned: number, annualFee: number) {
  return totalEarned - annualFee
}

/**
 * How much you must spend in a year, at the card's best rate, before
 * the rewards cover the fee. Returns null for free cards.
 */
export function breakEvenSpend(annualFee: number, rates: EarnRate[]) {
  if (annualFee <= 0) return null
  const best = Math.max(...rates.map((r) => r.percent), 0)
  if (best <= 0) return null
  return Math.round((annualFee / (best / 100)) / 100) * 100 // round to $100
}

/** $1,234 with no cents. */
export function money(n: number) {
  return `$${Math.round(n).toLocaleString("en-CA")}`
}