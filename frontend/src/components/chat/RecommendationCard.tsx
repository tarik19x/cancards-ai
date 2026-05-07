import Link from "next/link"
import type { CardRecommendation } from "@/types"

interface Props {
  card: CardRecommendation
  rank: number
}

export default function RecommendationCard({ card, rank }: Props) {
  return (
    <div className="rounded-lg border border-teal-100 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-teal-600 text-xs font-bold text-white">
              {rank}
            </span>
            <h4 className="font-semibold text-slate-800">{card.card_name}</h4>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            {card.annual_fee_cad === 0
              ? "No annual fee"
              : `$${card.annual_fee_cad}/yr`}
          </p>
        </div>
        <Link
          href={`/cards/${card.card_id}`}
          className="shrink-0 rounded border border-teal-200 px-2 py-0.5 text-xs font-medium text-teal-700 hover:bg-teal-50"
        >
          Details →
        </Link>
      </div>
      <p className="mt-2 text-sm text-slate-600">{card.why}</p>
      <ul className="mt-2 space-y-0.5">
        {card.key_benefits.map((b) => (
          <li key={b} className="flex items-start gap-1.5 text-xs text-slate-600">
            <span className="mt-0.5 text-teal-500">✓</span>
            {b}
          </li>
        ))}
      </ul>
    </div>
  )
}