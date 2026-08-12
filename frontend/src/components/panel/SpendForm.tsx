"use client"

import { useState } from "react"
import { usePanel, type SpendProfile } from "@/lib/panel-store"

const FIELDS: { key: keyof SpendProfile; label: string }[] = [
  { key: "groceries", label: "Groceries" },
  { key: "dining", label: "Dining" },
  { key: "gas", label: "Gas" },
  { key: "travel", label: "Travel" },
  { key: "other", label: "Everything else" },
]

const EMPTY: SpendProfile = { groceries: 0, dining: 0, gas: 0, travel: 0, other: 0 }

export default function SpendForm({ onDone }: { onDone: () => void }) {
  const { spend, saveSpend } = usePanel()
  const [draft, setDraft] = useState<SpendProfile>(spend ?? EMPTY)

  function update(key: keyof SpendProfile, raw: string) {
    const n = Number(raw.replace(/[^0-9]/g, "")) // digits only
    setDraft({ ...draft, [key]: isNaN(n) ? 0 : n })
  }

  function save() {
    saveSpend(draft)
    onDone()
  }

  return (
    <div>
      <p className="g-label">Monthly spending</p>
      <div className="mt-3 flex flex-col gap-2">
        {FIELDS.map(({ key, label }) => (
          <label key={key} className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-stone-400">{label}</span>
            <span className="flex items-center gap-1">
              <span className="text-[11px] text-stone-600">$</span>
              <input
                inputMode="numeric"
                value={draft[key] || ""}
                onChange={(e) => update(key, e.target.value)}
                placeholder="0"
                className="w-16 rounded border border-stone-800 bg-stone-900/60 px-2 py-1 text-right text-[11px] text-stone-100 outline-none focus:border-amber-500"
              />
            </span>
          </label>
        ))}
      </div>

      <div className="mt-4 flex gap-2">
        <button onClick={save} className="rounded-md bg-amber-500 px-3 py-1.5 text-[11px] text-amber-950">
          Save
        </button>
        <button onClick={onDone} className="rounded-md border border-stone-800 px-3 py-1.5 text-[11px] text-stone-400">
          Cancel
        </button>
      </div>
    </div>
  )
}