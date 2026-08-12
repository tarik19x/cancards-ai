import type { ValueRow } from "@/lib/value-calc"
import { money } from "@/lib/value-calc"

type Props = {
  rows: ValueRow[]
  amounts: Record<string, number>
}

export default function SpendBars({ rows, amounts }: Props) {
  // Longest bar is 100%. The rest scale against it.
  const values = rows.map((r) => amounts[r.key] ?? 0)
  const max = Math.max(...values, 1)

  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((row) => {
        const value = amounts[row.key] ?? 0
        const width = Math.max((value / max) * 100, 2)
        const strong = row.percent >= 2 // amber when the card rewards it
        return (
          <div key={row.key}>
            <div className="flex justify-between text-[11px] text-stone-300">
              <span>{row.label}</span>
              <span className="text-stone-50">{money(value)}</span>
            </div>
            <div className="mt-1.5 h-[3px] rounded-sm bg-stone-800">
              <div
                className={`h-[3px] rounded-sm ${strong ? "bg-amber-500" : "bg-stone-500"}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}