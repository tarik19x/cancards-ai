"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { fetchCard } from "@/lib/api"
import type { Card } from "@/types"

function FeeRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <span className="text-sm text-stone-500">{label}</span>
      <span className="text-right text-sm font-medium text-stone-200">{value}</span>
    </div>
  )
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-sm text-stone-500">{label}</span>
      <span className={value ? "text-[#6EE7B7]" : "text-stone-700"}>
        {value ? "✓" : "✗"}
      </span>
    </div>
  )
}

export default function CardDetailPage() {
  const params = useParams()
  const cardId = params.id as string

  const [card, setCard] = useState<Card | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!cardId) return
    fetchCard(cardId)
      .then(setCard)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Card not found")
      )
      .finally(() => setLoading(false))
  }, [cardId])

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-8">
        <div className="h-8 w-64 animate-pulse rounded bg-[#0d0d10]" />
        <div className="h-48 animate-pulse rounded-xl bg-[#0d0d10]" />
        <div className="h-48 animate-pulse rounded-xl bg-[#0d0d10]" />
      </div>
    )
  }

  if (error || !card) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="rounded-xl bg-red-500/10 p-6 text-center shadow-[inset_0_0_0_1px_rgba(251,113,133,0.3)]">
          <p className="font-medium text-red-400">{error ?? "Card not found"}</p>
          <Link href="/cards" className="mt-2 block text-sm text-[#A78BFA] underline">
            ← Back to all cards
          </Link>
        </div>
      </div>
    )
  }

  const ins = card.insurance_detail

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
        {/* Back */}
        <Link href="/cards" className="text-sm text-stone-600 hover:text-[#A78BFA]">
          ← All cards
        </Link>

        {/* Header */}
        <div className="rounded-xl bg-[#0d0d10] p-6 shadow-[inset_0_0_0_1px_#1e1e24]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-stone-500">{card.issuer}</p>
              <h1 className="mt-1 font-display text-2xl text-stone-100">
                {card.name}
              </h1>
              <p className="mt-1 text-sm text-stone-500">
                {card.network} · Verified {card.last_verified}
              </p>
            </div>
            
<a href={card.official_url} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded-lg bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90">Apply →</a>

          </div>

          <Separator className="my-4 bg-[#1e1e24]" />

          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-xs text-stone-600">Annual Fee</p>
              <p className="mt-0.5 text-xl font-bold text-stone-100">
                {card.annual_fee_cad === 0 ? "Free" : `$${card.annual_fee_cad}`}
              </p>
            </div>
            <div>
              <p className="text-xs text-stone-600">FX Fee</p>
              <p
                className={[
                  "mt-0.5 text-xl font-bold",
                  card.foreign_transaction_fee_pct === 0
                    ? "text-[#6EE7B7]"
                    : "text-stone-100",
                ].join(" ")}
              >
                {card.foreign_transaction_fee_pct === 0
                  ? "None"
                  : `${card.foreign_transaction_fee_pct}%`}
              </p>
            </div>
            <div>
              <p className="text-xs text-stone-600">Min. Score</p>
              <p className="mt-0.5 text-xl font-bold text-stone-100">
                {card.min_credit_score_recommended ?? "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Best for / not great for */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-[#6EE7B7]/[0.06] p-4 shadow-[inset_0_0_0_1px_rgba(110,231,183,0.2)]">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#6EE7B7]">
              Best For
            </p>
            <div className="flex flex-wrap gap-1.5">
              {card.best_for.map((tag) => (
                <Badge
                  key={tag}
                  className="border-0 bg-[#0d0d10] text-xs capitalize text-[#6EE7B7] hover:bg-[#0d0d10]"
                >
                  {tag.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-[#FB7185]/[0.06] p-4 shadow-[inset_0_0_0_1px_rgba(251,113,133,0.2)]">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#FB7185]">
              Not Great For
            </p>
            <div className="flex flex-wrap gap-1.5">
              {card.not_great_for.map((tag) => (
                <Badge
                  key={tag}
                  className="border-0 bg-[#0d0d10] text-xs capitalize text-[#FB7185] hover:bg-[#0d0d10]"
                >
                  {tag.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          </div>
        </div>

        {/* Rewards */}
        <div className="rounded-xl bg-[#0d0d10] p-5 shadow-[inset_0_0_0_1px_#1e1e24]">
          <h2 className="font-semibold text-stone-100">Rewards</h2>
          <p className="mt-1 text-sm text-stone-400">{card.rewards_summary}</p>

          {card.welcome_bonus_description && (
            <>
              <Separator className="my-3 bg-[#1e1e24]" />
              <div className="rounded-lg bg-[#A78BFA]/10 px-3 py-2">
                <p className="text-xs font-semibold text-[#C4B5FD]">Welcome Bonus</p>
                <p className="mt-0.5 text-sm text-stone-200">
                  {card.welcome_bonus_description}
                </p>
              </div>
            </>
          )}

          <Separator className="my-3 bg-[#1e1e24]" />
          <div className="divide-y divide-[#16161a]">
            {Object.entries(card.rewards_detail).map(([cat, detail]) => (
              <FeeRow
                key={cat}
                label={cat.replace(/_/g, " ")}
                value={`${detail.rate}× ${detail.unit.replace(/_/g, " ")}`}
              />
            ))}
          </div>

          {card.estimated_point_value_cents && (
            <p className="mt-2 text-xs text-stone-600">
              ≈ {card.estimated_point_value_cents}¢ per point when redeemed for travel
            </p>
          )}
        </div>

        {/* Fees */}
        <div className="rounded-xl bg-[#0d0d10] p-5 shadow-[inset_0_0_0_1px_#1e1e24]">
          <h2 className="font-semibold text-stone-100">Fees</h2>
          <div className="mt-2 divide-y divide-[#16161a]">
            <FeeRow
              label="Annual fee"
              value={
                card.annual_fee_cad === 0
                  ? "Free"
                  : `$${card.annual_fee_cad} CAD`
              }
            />
            {card.monthly_fee_cad && (
              <FeeRow
                label="Monthly fee"
                value={`$${card.monthly_fee_cad} CAD`}
              />
            )}
            <FeeRow
              label="Foreign transaction fee"
              value={
                card.foreign_transaction_fee_pct === 0 ? (
                  <span className="font-semibold text-[#6EE7B7]">None</span>
                ) : (
                  `${card.foreign_transaction_fee_pct}%`
                )
              }
            />
          </div>
        </div>

        {/* Insurance */}
        <div className="rounded-xl bg-[#0d0d10] p-5 shadow-[inset_0_0_0_1px_#1e1e24]">
          <h2 className="font-semibold text-stone-100">Insurance & Benefits</h2>
          <p className="mt-1 text-sm text-stone-400">{card.insurance_summary}</p>
          <Separator className="my-3 bg-[#1e1e24]" />
          <div className="divide-y divide-[#16161a]">
            {ins.travel_emergency_medical_days && (
              <FeeRow
                label="Travel emergency medical"
                value={`${ins.travel_emergency_medical_days} days`}
              />
            )}
            {ins.purchase_protection_days && (
              <FeeRow
                label="Purchase protection"
                value={`${ins.purchase_protection_days} days`}
              />
            )}
            <BoolRow label="Rental car collision" value={ins.rental_car_collision} />
            <BoolRow label="Trip cancellation" value={ins.trip_cancellation} />
            <BoolRow label="Trip interruption" value={ins.trip_interruption} />
            <BoolRow label="Flight delay" value={ins.flight_delay} />
            <BoolRow label="Baggage insurance" value={ins.baggage_insurance} />
            <BoolRow label="Extended warranty" value={ins.extended_warranty} />
            <BoolRow label="Airport lounge access" value={ins.lounge_access} />
          </div>
        </div>

        {/* Eligibility */}
        <div className="rounded-xl bg-[#0d0d10] p-5 shadow-[inset_0_0_0_1px_#1e1e24]">
          <h2 className="font-semibold text-stone-100">Eligibility</h2>
          <div className="mt-2 divide-y divide-[#16161a]">
            {card.min_credit_score_recommended && (
              <FeeRow
                label="Recommended credit score"
                value={`${card.min_credit_score_recommended}+`}
              />
            )}
            {card.min_personal_income_cad && (
              <FeeRow
                label="Min. personal income"
                value={`$${card.min_personal_income_cad.toLocaleString()} CAD`}
              />
            )}
            {card.min_household_income_cad && (
              <FeeRow
                label="Min. household income"
                value={`$${card.min_household_income_cad.toLocaleString()} CAD`}
              />
            )}
            {!card.min_credit_score_recommended &&
              !card.min_personal_income_cad &&
              !card.min_household_income_cad && (
                <p className="py-2 text-sm text-stone-600">
                  No minimum income requirement listed.
                </p>
              )}
          </div>
        </div>

        {/* Compare CTA */}
        <div className="rounded-xl bg-[#A78BFA]/[0.06] p-4 text-center shadow-[inset_0_0_0_1px_rgba(167,139,250,0.18)]">
          <p className="text-sm text-stone-300">
            Want to see how this card stacks up against another?
          </p>
          <Link
            href="/compare"
            className="mt-2 inline-block rounded-lg bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Compare cards →
          </Link>
        </div>
      </div>
    </div>
  )
}