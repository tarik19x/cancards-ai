"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { Input } from "@/components/ui/input"
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

// One line of the ledger. Left accent bar carries the network colour so
// the eye can scan issuer without reading the badge text.
function CardRow({ card }: { card: Card }) {
  return (
    <Link
      href={`/cards/${card.card_id}`}
      className="group flex items-center gap-4 border-b border-[#16161a] px-1 py-[18px] transition-colors last:border-0 hover:bg-[#0d0d10]/60"
    >
      <span
        className="h-[38px] w-[5px] shrink-0 rounded-full"
        style={{
          background:
            card.network === "Visa" ? "#7DD3FC"
            : card.network === "Mastercard" ? "#F0A58C"
            : "#A78BFA",
        }}
      />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-stone-500">{card.issuer}</p>
        <h3 className="mt-0.5 truncate text-base text-stone-100 group-hover:text-[#C4B5FD]">
          {card.name}
        </h3>
      </div>

      <div className="w-[150px] shrink-0 text-right">
        <p className="text-[17px] text-stone-100">
          {card.annual_fee_cad === 0 ? (
            <span className="text-[#6EE7B7]">Free</span>
          ) : (
            <>${card.annual_fee_cad}<span className="text-xs text-stone-500">/yr</span></>
          )}
        </p>
        <p className="mt-0.5 truncate text-xs text-stone-500">
          {card.insurance_detail.lounge_access
            ? "Lounge access"
            : card.foreign_transaction_fee_pct === 0
              ? "No FX fee"
              : card.rewards_summary.split(";")[0].slice(0, 24)}
        </p>
      </div>
    </Link>
  )
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
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load cards"))
      .finally(() => setLoading(false))
  }, [])

  const visible = applyFilter(cards, filter, search)

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-[#0d0d10]" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl bg-red-500/10 p-6 text-center shadow-[inset_0_0_0_1px_rgba(251,113,133,0.3)]">
        <p className="font-medium text-red-400">Failed to load cards</p>
        <p className="mt-1 text-sm text-red-400/70">{error}</p>
        <p className="mt-2 text-xs text-red-400/50">Is the backend running at localhost:8000?</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by card name or issuer…"
        className="max-w-sm border-0 bg-[#0d0d10] text-stone-200 shadow-[inset_0_0_0_1px_#1e1e24] placeholder:text-stone-600 focus-visible:ring-1 focus-visible:ring-[#A78BFA]"
      />

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={
              filter === f.value
                ? "rounded-full bg-[#A78BFA] px-3.5 py-1.5 text-xs font-semibold text-black transition-colors"
                : "rounded-full px-3.5 py-1.5 text-xs text-stone-400 shadow-[inset_0_0_0_1px_#1e1e24] transition-colors hover:text-stone-200"
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      <p className="text-xs text-stone-600">
        {visible.length} card{visible.length !== 1 ? "s" : ""} shown
      </p>

      {visible.length === 0 ? (
        <div className="rounded-xl py-12 text-center shadow-[inset_0_0_0_1px_#1e1e24]">
          <p className="text-stone-500">No cards match your filter.</p>
          <button
            onClick={() => { setFilter("all"); setSearch("") }}
            className="mt-2 text-sm text-[#A78BFA] underline underline-offset-2"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div>
          {visible.map((card) => (
            <CardRow key={card.card_id} card={card} />
          ))}
        </div>
      )}
    </div>
  )
}