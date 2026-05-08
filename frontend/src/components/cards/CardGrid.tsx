"use client"

import { useState, useEffect } from "react"
import { Input } from "@/components/ui/input"
import CreditCardCard from "@/components/cards/CreditCardCard"
import { fetchCards } from "@/lib/api"
import type { Card } from "@/types"

const FILTERS = [
  { label: "All", value: "all" },
  { label: "No Annual Fee", value: "no-fee" },
  { label: "No FX Fee", value: "no-fx" },
  { label: "Lounge Access", value: "lounge" },
  { label: "Visa", value: "visa" },
  { label: "Mastercard", value: "mc" },
  { label: "Amex", value: "amex" },
]

function applyFilter(cards: Card[], filter: string, search: string): Card[] {
  let result = cards

  if (filter === "no-fee") result = result.filter((c) => c.annual_fee_cad === 0)
  else if (filter === "no-fx") result = result.filter((c) => c.foreign_transaction_fee_pct === 0)
  else if (filter === "lounge") result = result.filter((c) => c.insurance_detail.lounge_access)
  else if (filter === "visa") result = result.filter((c) => c.network === "Visa")
  else if (filter === "mc") result = result.filter((c) => c.network === "Mastercard")
  else if (filter === "amex") result = result.filter((c) => c.network === "Amex")

  if (search.trim()) {
    const q = search.toLowerCase()
    result = result.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.issuer.toLowerCase().includes(q) ||
        c.rewards_summary.toLowerCase().includes(q)
    )
  }

  return result
}

export default function CardGrid() {
  const [cards, setCards] = useState<Card[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState("all")
  const [search, setSearch] = useState("")

  useEffect(() => {
    fetchCards()
      .then(setCards)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load cards")
      )
      .finally(() => setLoading(false))
  }, [])

  const visible = applyFilter(cards, filter, search)

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-48 animate-pulse rounded-xl bg-slate-200"
          />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="font-medium text-red-700">Failed to load cards</p>
        <p className="mt-1 text-sm text-red-500">{error}</p>
        <p className="mt-2 text-xs text-red-400">
          Is the backend running at localhost:8000?
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by card name or issuer..."
        className="max-w-sm border-slate-200 focus-visible:ring-teal-500"
      />

      {/* Filter pills */}
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={[
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              filter === f.value
                ? "bg-teal-600 text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:border-teal-200 hover:text-teal-700",
            ].join(" ")}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Results count */}
      <p className="text-xs text-slate-400">
        {visible.length} card{visible.length !== 1 ? "s" : ""} shown
      </p>

      {/* Grid */}
      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 py-12 text-center">
          <p className="text-slate-500">No cards match your filter.</p>
          <button
            onClick={() => { setFilter("all"); setSearch("") }}
            className="mt-2 text-sm text-teal-600 underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((card) => (
            <CreditCardCard key={card.card_id} card={card} />
          ))}
        </div>
      )}
    </div>
  )
}
