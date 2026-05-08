import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import type { Card } from "@/types"

interface Props {
  card: Card
}

const NETWORK_COLOR: Record<string, string> = {
  Visa: "bg-blue-50 text-blue-700 border-blue-200",
  Mastercard: "bg-orange-50 text-orange-700 border-orange-200",
  Amex: "bg-violet-50 text-violet-700 border-violet-200",
}

export default function CreditCardCard({ card }: Props) {
  return (
    <Link
      href={`/cards/${card.card_id}`}
      className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium text-slate-400">{card.issuer}</p>
          <h3 className="mt-0.5 text-sm font-semibold leading-tight text-slate-900 group-hover:text-teal-700">
            {card.name}
          </h3>
        </div>
        <span
          className={[
            "shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium",
            NETWORK_COLOR[card.network] ?? "bg-slate-50 text-slate-600",
          ].join(" ")}
        >
          {card.network}
        </span>
      </div>

      {/* Fee */}
      <div className="mt-3">
        <span className="text-lg font-bold text-slate-900">
          {card.annual_fee_cad === 0 ? "Free" : `$${card.annual_fee_cad}`}
        </span>
        {card.annual_fee_cad > 0 && (
          <span className="text-xs text-slate-400"> /yr</span>
        )}
      </div>

      {/* Rewards summary */}
      <p className="mt-2 line-clamp-2 text-xs text-slate-500">
        {card.rewards_summary}
      </p>

      {/* Badges */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {card.foreign_transaction_fee_pct === 0 && (
          <Badge className="border-0 bg-green-50 text-xs text-green-700 hover:bg-green-50">
            No FX fee
          </Badge>
        )}
        {card.insurance_detail.lounge_access && (
          <Badge className="border-0 bg-amber-50 text-xs text-amber-700 hover:bg-amber-50">
            Lounge access
          </Badge>
        )}
        {card.annual_fee_cad === 0 && (
          <Badge className="border-0 bg-slate-100 text-xs text-slate-600 hover:bg-slate-100">
            No annual fee
          </Badge>
        )}
      </div>

      {/* Arrow hint */}
      <div className="mt-3 text-right text-xs text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">
        View details →
      </div>
    </Link>
  )
}
