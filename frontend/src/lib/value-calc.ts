import type { SpendProfile } from "@/lib/panel-store"

export type EarnRate = {
  category: string
  percent: number
  monthlyCap?: number
  annualCap?: number
}

export type ValueRow = {
  key: keyof SpendProfile
  label: string
  dollars: number
  percent: number
}

// Issuers name the same category a dozen different ways
// (grocery_stores, eligible_grocery_stores, loblaws_banner_stores).
// Substring match against these rather than maintaining an exact map.
//
// Every token here has to be checked against the real category list before it
// goes in. "food" used to live under groceries and quietly handed Amex
// Platinum's dining rate to grocery spend, on a card with no grocery bonus.
const ALIASES: Record<keyof SpendProfile, string[]> = {
  groceries: ["grocer", "supermarket", "loblaws", "sobeys"],
  dining: ["dining", "restaurant", "eats", "eat", "drink", "bar", "coffee", "entertainment"],
  gas: ["gas", "fuel", "esso", "ev charging"],
  travel: [
    "travel",
    "flight",
    "hotel",
    "airline",
    "air canada",
    "air miles",
    "westjet",
    "marriott",
    "expedia",
    "transit",
  ],
  other: ["everything", "no rewards"],
}

const LABELS: Record<keyof SpendProfile, string> = {
  groceries: "Groceries",
  dining: "Dining",
  gas: "Gas",
  travel: "Travel",
  other: "Everything else",
}

/**
 * Normalizes rewards_detail into comparable percentages.
 *
 * Points cards and cashback cards can't be compared directly — 5x points
 * is only 5% if a point is worth a cent. estimated_point_value_cents is
 * our own valuation, so treat the output as an estimate, not a quote.
 *
 * Returns [] for cards without structured rates; callers should hide the
 * breakdown rather than fall back to a default.
 */
export function parseEarnRates(card: unknown): EarnRate[] {
  if (!card || typeof card !== "object") return []
  const c = card as Record<string, unknown>

  const detail = c.rewards_detail
  if (!detail || typeof detail !== "object") return []

  const pointValue = Number(c.estimated_point_value_cents ?? 1) || 1

  const rates: EarnRate[] = []
  for (const [category, raw] of Object.entries(detail as Record<string, unknown>)) {
    if (!raw || typeof raw !== "object") continue
    const row = raw as Record<string, unknown>

    const rate = Number(row.rate)
    if (isNaN(rate)) continue

    const unit = String(row.unit ?? "")
    const percent = unit.includes("point") ? rate * pointValue : rate

    rates.push({
      category: category.replace(/_/g, " "),
      // 3 points x 0.67c renders as 2.0100000000000002 if this isn't rounded,
      // and the panel prints the raw number.
      percent: Math.round(percent * 100) / 100,
      monthlyCap: capOrUndefined(row.monthly_cap_cad),
      annualCap: capOrUndefined(row.annual_cap_cad),
    })
  }

  return rates
}

// Caps come through as null when uncapped, and Number(null) is 0 — which reads
// as "capped at $0" rather than "no cap". Check the value, not the coercion.
function capOrUndefined(raw: unknown): number | undefined {
  if (raw === null || raw === undefined) return undefined
  const n = Number(raw)
  return isNaN(n) || n <= 0 ? undefined : n
}

// Spend that doesn't hit a bonus category earns this instead.
// Zero for the low-interest cards that carry no rewards at all.
//
// Anchored to "everything*" specifically. Matching the bare word "other" pulled
// in Scotia Gold's `other_grocery_dining_delivery` — a 5% bonus category — and
// applied it to every unmatched dollar, overstating the card by $336/yr.
function baseRate(rates: EarnRate[]): number {
  const base = bestMatch(rates, ALIASES.other)
  return base ? base.percent : 0
}

// Best rate wins, not first-in-object-order. Scotia Gold lists both
// `sobeys_group_grocery` (6%) and `other_grocery_dining_delivery` (5%); which
// one a grocery dollar earned used to depend on JSON key order.
function bestMatch(rates: EarnRate[], words: string[]): EarnRate | undefined {
  return rates
    .filter((r) => words.some((w) => r.category.includes(w)))
    .reduce<EarnRate | undefined>(
      (best, r) => (best === undefined || r.percent > best.percent ? r : best),
      undefined
    )
}

/**
 * Annual return per category.
 *
 * Caps are the reason this isn't a one-liner: BMO's 5% grocery rate stops
 * at $500/month and drops to base after. Ignoring that overstates the card
 * by roughly $200/yr at typical grocery spend.
 */
export function annualRewards(spend: SpendProfile, rates: EarnRate[]) {
  const keys = Object.keys(spend) as (keyof SpendProfile)[]
  const fallback = baseRate(rates)

  const rows: ValueRow[] = keys.map((key) => {
    const match = bestMatch(rates, ALIASES[key])
    const yearlySpend = spend[key] * 12

    if (!match) {
      return {
        key,
        label: LABELS[key],
        dollars: (yearlySpend * fallback) / 100,
        percent: fallback,
      }
    }

    // Monthly caps annualize cleanly enough — assumes even spend across
    // the year, which is wrong for seasonal spenders but close enough.
    let cappedSpend = yearlySpend
    if (match.monthlyCap) cappedSpend = Math.min(yearlySpend, match.monthlyCap * 12)
    if (match.annualCap) cappedSpend = Math.min(cappedSpend, match.annualCap)

    const aboveCap = yearlySpend - cappedSpend
    const dollars =
      (cappedSpend * match.percent) / 100 + (aboveCap * fallback) / 100

    return { key, label: LABELS[key], dollars, percent: match.percent }
  })

  const total = rows.reduce((sum, r) => sum + r.dollars, 0)
  return { rows, total }
}

export function netValue(totalEarned: number, annualFee: number) {
  return totalEarned - annualFee
}

/**
 * Spend needed to cover the annual fee at the card's top rate.
 * Optimistic by design — real spend is spread across categories, so
 * treat this as a floor.
 */
export function breakEvenSpend(annualFee: number, rates: EarnRate[]) {
  if (annualFee <= 0) return null
  const best = Math.max(...rates.map((r) => r.percent), 0)
  if (best <= 0) return null
  return Math.round((annualFee / (best / 100)) / 100) * 100
}

export function money(n: number) {
  return `$${Math.round(n).toLocaleString("en-CA")}`
}
