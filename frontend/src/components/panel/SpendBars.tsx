import type { ValueRow } from "@/lib/value-calc"
import { money } from "@/lib/value-calc"

type Props = { rows: ValueRow[]; amounts: Record<string, number> }

export default function SpendBars({ rows }: Props) {
  const max = Math.max(...rows.map((r) => r.dollars), 1)
  return (
    <div className="flex flex-col gap-3.5">
      {rows.map((row) => {
        const width = Math.max((row.dollars / max) * 100, 2)
        const strong = row.percent >= 2
        return (
          <div key={row.key}>
            <div className="mb-1.5 flex items-baseline justify-between font-sans text-sm">
              <span className="text-stone-300">{row.label}</span>
              <span className="text-stone-50">
                {money(row.dollars)}<span className="text-xs text-stone-500">/yr back</span>
              </span>
            </div>
            <div className="h-[9px] overflow-hidden rounded-full bg-[#221e1c]">
              <div
                className={strong
                  ? "bar-fill h-[9px] rounded-full bg-gradient-to-r from-[#F0A58C] to-[#A78BFA] shadow-[0_0_12px_rgba(167,139,250,0.4)]"
                  : "bar-fill h-[9px] rounded-full bg-stone-600"}
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}