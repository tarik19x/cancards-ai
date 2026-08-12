"use client"

import { useEffect, useState } from "react"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

export default function SettingsPage() {
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking")
  const [cleared, setCleared] = useState(false)

  // real check, not decoration — the badge should go red if the API is down
  useEffect(() => {
    fetch(`${BACKEND}/health`)
      .then((r) => setHealth(r.ok ? "ok" : "down"))
      .catch(() => setHealth("down"))
  }, [])

  function clearSpend() {
    localStorage.removeItem("cancards.spend")
    setCleared(true)
    // panel reads spend once on mount; reload is the cheap sync
    setTimeout(() => window.location.reload(), 600)
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8">
      <p className="g-label">Settings</p>
      <h1 className="mt-1 font-display text-3xl text-stone-50">Settings</h1>

      <div className="mt-6 space-y-3">
        <div className="g-panel flex items-center justify-between p-4">
          <div>
            <p className="text-sm text-stone-200">Backend</p>
            <p className="mt-1 text-xs text-stone-500">{BACKEND}</p>
          </div>
          <span
            className={
              health === "ok" ? "text-xs text-emerald-400"
              : health === "down" ? "text-xs text-red-400"
              : "text-xs text-stone-500"
            }
          >
            {health === "ok" ? "connected" : health === "down" ? "unreachable" : "checking"}
          </span>
        </div>

        <div className="g-panel flex items-center justify-between p-4">
          <div>
            <p className="text-sm text-stone-200">Saved spending</p>
            <p className="mt-1 text-xs text-stone-500">
              Stored in this browser only. Never sent anywhere.
            </p>
          </div>
          <button
            onClick={clearSpend}
            className="rounded-lg border border-stone-800 px-3 py-1.5 text-xs text-stone-300
              transition-colors hover:border-stone-700 hover:text-stone-100"
          >
            {cleared ? "Cleared" : "Clear"}
          </button>
        </div>

        <p className="pt-2 text-xs leading-relaxed text-stone-600">
          Planned: default currency, saved comparisons, export.
        </p>
      </div>
    </div>
  )
}