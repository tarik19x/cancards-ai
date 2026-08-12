"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { fetchCards } from "@/lib/api"
import type { Card } from "@/types"

function CompareRow({
  label,
  a,
  b,
}: {
  label: string
  a: React.ReactNode
  b: React.ReactNode
}) {
  return (
    <div className="grid grid-cols-[1fr,2fr,2fr] items-start gap-4 py-3">
      <span className="text-xs font-medium text-stone-500">{label}</span>
      <span className="text-sm text-stone-300">{a}</span>
      <span className="text-sm text-stone-300">{b}</span>
    </div>
  )
}

function BoolCompare({ value }: { value: boolean }) {
  // "no" stays dim on purpose — absence shouldn't compete with presence
  return (
    <span className={value ? "font-medium text-emerald-400" : "text-stone-600"}>
      {value ? "✓ Yes" : "✗ No"}
    </span>
  )
}

export default function ComparePage() {
  const [cards, setCards] = useState<Card[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [idA, setIdA] = useState("")
  const [idB, setIdB] = useState("")

  useEffect(() => {
    fetchCards()
      .then((data) => {
        setCards(data)
        if (data.length >= 2) {
          setIdA(data[0].card_id)
          setIdB(data[1].card_id)
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [])

  const cardA = cards.find((c) => c.card_id === idA)
  const cardB = cards.find((c) => c.card_id === idB)

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-8">
        <div className="h-8 w-48 animate-pulse rounded bg-stone-800" />
        <div className="h-96 animate-pulse rounded-xl bg-stone-800/60" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8">
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-center">
          <p className="text-red-400">{error}</p>
          <p className="mt-1 text-xs text-red-400/60">Is the backend running?</p>
        </div>
      </div>
    )
  }

  return (
    // AppShell's <main> clips overflow; this wrapper owns the scroll
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
        <div>
          <h1 className="font-display text-3xl text-stone-100">Compare cards</h1>
          <p className="mt-1 text-sm text-stone-400">
            Pick two cards below to see them side by side.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              Card A
            </label>
            <select
              value={idA}
              onChange={(e) => setIdA(e.target.value)}
              className="w-full rounded-lg border border-stone-800 bg-stone-900 px-3 py-2 text-sm text-stone-300 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              {cards.map((c) => (
                <option key={c.card_id} value={c.card_id} disabled={c.card_id === idB}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-stone-500">
              Card B
            </label>
            <select
              value={idB}
              onChange={(e) => setIdB(e.target.value)}
              className="w-full rounded-lg border border-stone-800 bg-stone-900 px-3 py-2 text-sm text-stone-300 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              {cards.map((c) => (
                <option key={c.card_id} value={c.card_id} disabled={c.card_id === idA}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {cardA && cardB ? (
          <div className="rounded-xl border border-stone-800 bg-stone-900/40">
            <div className="grid grid-cols-[1fr,2fr,2fr] gap-4 rounded-t-xl bg-stone-900/60 p-4">
              <span />
              <div>
                <p className="text-xs text-stone-500">{cardA.issuer}</p>
                <p className="font-semibold text-stone-100">{cardA.name}</p>
              </div>
              <div>
                <p className="text-xs text-stone-500">{cardB.issuer}</p>
                <p className="font-semibold text-stone-100">{cardB.name}</p>
              </div>
            </div>

            <div className="divide-y divide-stone-800/60 px-4">
              <div className="py-2">
                <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Fees
                </p>
              </div>
              <CompareRow
                label="Annual fee"
                a={cardA.annual_fee_cad === 0 ? "Free" : `$${cardA.annual_fee_cad}/yr`}
                b={cardB.annual_fee_cad === 0 ? "Free" : `$${cardB.annual_fee_cad}/yr`}
              />
              <CompareRow
                label="FX fee"
                a={
                  cardA.foreign_transaction_fee_pct === 0 ? (
                    <span className="font-medium text-emerald-400">None</span>
                  ) : (
                    `${cardA.foreign_transaction_fee_pct}%`
                  )
                }
                b={
                  cardB.foreign_transaction_fee_pct === 0 ? (
                    <span className="font-medium text-emerald-400">None</span>
                  ) : (
                    `${cardB.foreign_transaction_fee_pct}%`
                  )
                }
              />

              <div className="py-2">
                <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Rewards
                </p>
              </div>
              <CompareRow
                label="Summary"
                a={<span className="line-clamp-3">{cardA.rewards_summary}</span>}
                b={<span className="line-clamp-3">{cardB.rewards_summary}</span>}
              />
              <CompareRow
                label="Point value"
                a={
                  cardA.estimated_point_value_cents
                    ? `≈ ${cardA.estimated_point_value_cents}¢/pt`
                    : "Cashback"
                }
                b={
                  cardB.estimated_point_value_cents
                    ? `≈ ${cardB.estimated_point_value_cents}¢/pt`
                    : "Cashback"
                }
              />

              <div className="py-2">
                <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Insurance
                </p>
              </div>
              <CompareRow
                label="Travel medical"
                a={
                  cardA.insurance_detail.travel_emergency_medical_days
                    ? `${cardA.insurance_detail.travel_emergency_medical_days} days`
                    : "None"
                }
                b={
                  cardB.insurance_detail.travel_emergency_medical_days
                    ? `${cardB.insurance_detail.travel_emergency_medical_days} days`
                    : "None"
                }
              />
              <CompareRow
                label="Trip cancellation"
                a={<BoolCompare value={cardA.insurance_detail.trip_cancellation} />}
                b={<BoolCompare value={cardB.insurance_detail.trip_cancellation} />}
              />
              <CompareRow
                label="Rental car"
                a={<BoolCompare value={cardA.insurance_detail.rental_car_collision} />}
                b={<BoolCompare value={cardB.insurance_detail.rental_car_collision} />}
              />
              <CompareRow
                label="Lounge access"
                a={<BoolCompare value={cardA.insurance_detail.lounge_access} />}
                b={<BoolCompare value={cardB.insurance_detail.lounge_access} />}
              />

              <div className="py-2">
                <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Eligibility
                </p>
              </div>
              <CompareRow
                label="Min. credit score"
                a={cardA.min_credit_score_recommended ?? "Not specified"}
                b={cardB.min_credit_score_recommended ?? "Not specified"}
              />
              <CompareRow
                label="Min. income"
                a={
                  cardA.min_personal_income_cad
                    ? `$${cardA.min_personal_income_cad.toLocaleString()}`
                    : "None"
                }
                b={
                  cardB.min_personal_income_cad
                    ? `$${cardB.min_personal_income_cad.toLocaleString()}`
                    : "None"
                }
              />
            </div>

            <div className="grid grid-cols-[1fr,2fr,2fr] gap-4 rounded-b-xl border-t border-stone-800 bg-stone-900/60 p-4">
              <span />
              <Link
                href={`/cards/${cardA.card_id}`}
                className="text-xs text-amber-400 underline underline-offset-2 hover:text-amber-300"
              >
                Full {cardA.name} details →
              </Link>
              <Link
                href={`/cards/${cardB.card_id}`}
                className="text-xs text-amber-400 underline underline-offset-2 hover:text-amber-300"
              >
                Full {cardB.name} details →
              </Link>
            </div>
          </div>
        ) : (
          <p className="text-sm text-stone-500">Select two cards above to compare.</p>
        )}

        <div className="rounded-xl bg-amber-500/[0.06] p-4 text-center shadow-[inset_0_0_0_1px_rgb(251_191_36_/_0.18)]">
          <p className="text-sm text-[#d8c69a]">
            Still not sure which card to choose? Ask the AI.
          </p>
          <Link
            href="/"
            className="mt-2 inline-block rounded-lg bg-[#fbbf24] px-4 py-2 text-sm font-medium text-[#1c1207] transition-opacity hover:opacity-90"
          >
            Ask CanCards AI →
          </Link>
        </div>
      </div>
    </div>
  )
}