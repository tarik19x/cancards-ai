"use client"

import { useEffect, useState } from "react"
import { usePanel } from "@/lib/panel-store"
import {
  annualRewards, breakEvenSpend, money, netValue, parseEarnRates,
  type EarnRate,
} from "@/lib/value-calc"
import SpendBars from "@/components/panel/SpendBars"
import SpendForm from "@/components/panel/SpendForm"
import MetricsStrip from "@/components/panel/MetricsStrip"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

export default function InsightPanel() {
  const { answer, spend } = usePanel()
  const [editing, setEditing] = useState(false)
  const [rates, setRates] = useState<EarnRate[]>([])
  const [fee, setFee] = useState(0)

  // When the answer changes, fetch the top card and read its rates.
  useEffect(() => {
    if (!answer?.topCardId) {
      setRates([])
      setFee(0)
      return
    }
    let cancelled = false

    fetch(`${BACKEND}/api/cards/${answer.topCardId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((card) => {
        if (cancelled || !card) return
        setRates(parseEarnRates(card))
        setFee(Number(card.annual_fee ?? 0))
      })
      .catch(() => {
        // card lookup failed — panel just hides the breakdown
      })

    return () => {
      cancelled = true
    }
  }, [answer?.topCardId])

  const hasRates = rates.length > 0
  const calc = spend && hasRates ? annualRewards(spend, rates) : null
  const net = calc ? netValue(calc.total, fee) : null
  const breakEven = hasRates ? breakEvenSpend(fee, rates) : null

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3.5 py-4" data-testid="insight-panel">
      {editing ? (
        <SpendForm onDone={() => setEditing(false)} />
      ) : !answer ? (
        /* state 1: nothing asked yet */
        <>
          <p className="g-label">Your numbers</p>
          <p className="mt-3 text-[11px] leading-relaxed text-stone-400">
            The value breakdown for your best-matched card appears here.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            {[52, 40, 46].map((w, i) => (
              <div key={i}>
                <div className="h-[7px] rounded-sm bg-stone-900" style={{ width: `${w}%` }} />
                <div className="mt-1.5 h-[3px] rounded-sm bg-[#161311]" />
              </div>
            ))}
          </div>
        </>
      ) : !hasRates ? (
        /* state 2: card matched, no rate data */
        <>
          <p className="g-label">Top match</p>
          <p className="mt-2 text-sm text-stone-100">{answer.topCardName}</p>
          <p className="mt-3 text-[11px] leading-relaxed text-stone-500">
            No reward-rate data for this card yet, so the value breakdown is
            unavailable.
          </p>
        </>
      ) : !spend ? (
        /* state 3: rates known, spending unknown */
        <>
          <p className="g-label">Where value comes from</p>
          <p className="mt-2 text-sm text-stone-100">{answer.topCardName}</p>
          <div className="mt-4 flex flex-col gap-2.5">
            {rates.slice(0, 5).map((r) => (
              <div key={r.category}>
                <div className="flex justify-between text-[11px] text-stone-300">
                  <span className="capitalize">{r.category}</span>
                  <span className="text-stone-50">{r.percent}%</span>
                </div>
                <div className="mt-1.5 h-[3px] rounded-sm bg-stone-800">
                  <div
                    className="h-[3px] rounded-sm bg-amber-500"
                    style={{ width: `${(r.percent / Math.max(...rates.map((x) => x.percent))) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {breakEven !== null && (
            <p className="mt-4 text-[11px] leading-relaxed text-stone-500">
              Breaks even on the {money(fee)} fee at {money(breakEven)} of yearly spend.
            </p>
          )}

          <button onClick={() => setEditing(true)} className="mt-4 text-left text-[11px] text-amber-400">
            Add your spending →
          </button>
        </>
      ) : (
        /* state 4: fully personalised */
        <>
          <p className="g-label">Your monthly spend</p>
          <div className="mt-3">
            <SpendBars rows={calc!.rows} amounts={spend} />
          </div>

          <div className="mt-6">
            <p className="text-[11px] text-stone-400">Best net value found</p>
            <p className="mt-0.5 font-display text-[29px] leading-tight tracking-tight text-amber-400">
              {money(net!)}
              <span className="font-sans text-xs text-stone-500">/yr</span>
            </p>
            <p className="mt-1.5 text-[11px] text-stone-400">
              {money(calc!.total)} earned − {money(fee)} fee
            </p>
            <p className="mt-2.5 text-[11px] leading-relaxed text-stone-600">
              Estimates use published earn rates.
            </p>
            <button onClick={() => setEditing(true)} className="mt-2 text-left text-[11px] text-stone-500 hover:underline">
              Edit spending
            </button>
          </div>
        </>
      )}

      <MetricsStrip />
    </div>
  )
}